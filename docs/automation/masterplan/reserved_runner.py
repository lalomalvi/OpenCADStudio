"""One-shot M7 invocation gate. Provider/CAD adapters remain external.

This module never calls a model itself. It makes TrialJournal.reserve mandatory
before an injected adapter runs and never retries an uncertain invocation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Callable

from reserved_trial import TrialJournal, _ID, _file_sha
from provider_response_receipt import from_response, verify_receipt
from usage_evidence import _usage


class InvocationUncertain(RuntimeError):
    """The slot was consumed; never invoke it again with another request ID."""


@dataclass(frozen=True)
class Invocation:
    arm: str
    case_id: str
    repetition: int
    request_id: str
    image_path: Path
    protocol_path: Path
    cad_binary_path: Path
    requested_model: str
    effort: str
    source_sha256: str
    protocol_sha256: str
    cad_binary_sha256: str
    supervisor_protocol_path: Path | None = None
    supervisor_protocol_sha256: str | None = None
    supervisor_model: str | None = None
    supervisor_effort: str | None = None


@dataclass(frozen=True)
class Observation:
    """Metadata returned by an adapter, not independently provider-verified."""

    effective_model: str
    response_id: str
    generator_usage: dict
    supervisor_usage: dict | None
    cad_evidence_path: Path | None
    generator_response: dict | None = None
    supervisor_response: dict | None = None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _evidence_ref(path: Path | None, run_root: Path) -> dict | None:
    if path is None:
        return None
    if not isinstance(path, Path) or not path.is_file() or path.suffix.lower() != ".json":
        raise ValueError("CAD evidence must be an existing JSON file")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(run_root) or resolved.name == "attempts.jsonl":
        raise ValueError("CAD evidence must remain inside the run directory")
    _verify_nested_cad(resolved)
    return {"file": resolved.relative_to(run_root).as_posix(),
            "sha256": _file_sha(resolved)}


def _verify_nested_cad(path: Path) -> None:
    report = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(report, dict) and report.get("schema_version") == "m7-owned-cad-evidence-1":
        from owned_cad_executor import verify_owned_cad_evidence
        verify_owned_cad_evidence(path)


def verify_envelope(path: Path) -> dict:
    """Recheck the nested CAD evidence before consuming an invocation result."""
    if not path.is_absolute() or not path.is_file() or path.suffix.lower() != ".json":
        raise ValueError("Absolute invocation envelope is required")
    envelope = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(envelope, dict) or envelope.get("schema_version") != "m7-invocation-envelope-1" \
            or envelope.get("gates") != "unevaluated":
        raise ValueError("Invocation envelope schema is invalid")
    receipts = envelope.get("direct_response_receipts")
    if receipts is not None:
        if envelope.get("usage_provenance") != "adapter_supplied_direct_response_objects" \
                or not isinstance(receipts, dict) or set(receipts) != {
                    "generator", "supervisor"}:
            raise ValueError("Direct response receipt mapping is invalid")
        generator = verify_receipt(receipts["generator"])
        supervisor = (verify_receipt(receipts["supervisor"])
                      if receipts["supervisor"] is not None else None)
        if generator["response_id_sha256"] != envelope.get("response_sha256") or \
                generator["model"] != envelope.get("effective_model") or \
                generator["usage"] != envelope.get("generator_usage") or \
                ((supervisor is None) != (envelope.get("supervisor_usage") is None)) or \
                (supervisor is not None and supervisor["usage"] !=
                 envelope["supervisor_usage"]):
            raise ValueError("Direct response receipt differs from envelope")
    elif envelope.get("usage_provenance") == "adapter_supplied_direct_response_objects":
        raise ValueError("Direct response receipts are missing")
    ref = envelope.get("cad_evidence")
    if ref is not None:
        if not isinstance(ref, dict) or set(ref) != {"file", "sha256"} \
                or not isinstance(ref["file"], str) or not isinstance(ref["sha256"], str):
            raise ValueError("CAD evidence reference is invalid")
        root = path.parent.resolve(strict=True)
        evidence = (root / ref["file"]).resolve(strict=True)
        if not evidence.is_relative_to(root) or evidence == path.resolve(strict=True) \
                or _file_sha(evidence) != ref["sha256"]:
            raise ValueError("CAD evidence changed after invocation")
        _verify_nested_cad(evidence)
    return envelope


def run_once(journal: TrialJournal, arm: str, case_id: str, repetition: int,
             request_id: str, invoke: Callable[[Invocation], Observation]) -> dict:
    """Reserve durably, call the adapter once, then record a sanitized envelope.

    Any exception after reserve is uncertain. The adapter must not internally
    retry an unknown model/CAD mutation. "completed" records only that complete
    adapter metadata exists; independent G0-G10 and L4/L5 stay unevaluated.
    """
    reserved = journal.reserve(arm, case_id, repetition, request_id)
    if reserved["status"] != "reserved":
        raise InvocationUncertain("Trial slot was not freshly reserved")
    invocation = Invocation(arm, case_id, repetition, request_id,
                            journal.image_paths[case_id], journal.arm_protocols[arm],
                            journal.arm_binaries[arm], journal.requested_model, journal.effort,
                            reserved["source_sha256"], reserved["protocol_sha256"],
                            reserved["cad_binary_sha256"],
                            journal.supervisor_protocol_path,
                            reserved["supervisor_contract"]["protocol_sha256"]
                            if reserved["supervisor_contract"] else None,
                            reserved["supervisor_contract"]["model"]
                            if reserved["supervisor_contract"] else None,
                            reserved["supervisor_contract"]["effort"]
                            if reserved["supervisor_contract"] else None)
    root = journal.path.parent.resolve(strict=True)
    try:
        observed = invoke(invocation)
        if not isinstance(observed, Observation) or not isinstance(observed.response_id, str) \
                or not observed.response_id or not isinstance(observed.effective_model, str) \
                or not _ID.fullmatch(observed.effective_model):
            raise ValueError("Adapter returned invalid response identity")
        generator = _usage(observed.generator_usage)
        supervisor = (_usage(observed.supervisor_usage)
                      if observed.supervisor_usage is not None else None)
        direct_receipts = None
        if observed.generator_response is not None or observed.supervisor_response is not None:
            if observed.generator_response is None:
                raise ValueError("Direct supervisor response needs generator response")
            generator_receipt = from_response(observed.generator_response)
            if generator_receipt["response_id_sha256"] != _sha(
                    observed.response_id.encode("utf-8")) or \
                    generator_receipt["model"] != observed.effective_model or \
                    generator_receipt["usage"] != generator:
                raise ValueError("Generator metadata differs from direct response")
            supervisor_receipt = (from_response(observed.supervisor_response)
                                  if observed.supervisor_response is not None else None)
            if supervisor_receipt is not None and \
                    (supervisor is None or supervisor_receipt["usage"] != supervisor or
                     supervisor_receipt["response_id_sha256"] ==
                     generator_receipt["response_id_sha256"]):
                raise ValueError("Supervisor metadata differs from direct response")
            direct_receipts = {"generator": generator_receipt,
                               "supervisor": supervisor_receipt}
        cad_evidence = _evidence_ref(observed.cad_evidence_path, root)
    except Exception as error:
        # A callback may have reached the provider or mutated CAD before error.
        # Preserve that ambiguity and consume the slot without another call.
        journal.record_result(arm, case_id, repetition, request_id,
                              disposition="uncertain", effective_model="unknown")
        raise InvocationUncertain("Invocation outcome is uncertain; slot consumed") from error

    complete = (observed.effective_model == journal.requested_model
                and supervisor is not None and cad_evidence is not None)
    disposition = "completed" if complete else "partial"
    envelope = {
        "schema_version": "m7-invocation-envelope-1",
        "arm": arm, "case_id": case_id, "repetition": repetition,
        "request_sha256": _sha(request_id.encode("utf-8")),
        "response_sha256": _sha(observed.response_id.encode("utf-8")),
        "effective_model": observed.effective_model,
        "usage_provenance": ("adapter_supplied_direct_response_objects" if direct_receipts
                             else "adapter_reported_unverified"),
        "direct_response_receipts": direct_receipts,
        "generator_usage": generator, "supervisor_usage": supervisor,
        "cad_evidence": cad_evidence, "disposition": disposition,
        "gates": "unevaluated",
    }
    path = root / f"invocation-{arm}-{case_id}-r{repetition}.json"
    try:
        with path.open("x", encoding="utf-8") as target:
            json.dump(envelope, target, sort_keys=True, separators=(",", ":"))
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
    except OSError as error:
        # Do not turn a potentially completed CAD operation into a retryable one.
        journal.record_result(arm, case_id, repetition, request_id,
                              disposition="uncertain", effective_model="unknown")
        raise InvocationUncertain("Invocation evidence could not be sealed") from error
    journal.record_result(arm, case_id, repetition, request_id,
                          disposition=disposition,
                          effective_model=observed.effective_model,
                          evidence_path=path)
    verify_envelope(path)
    return {"disposition": disposition, "evidence_path": path,
            "journal_sha256": journal.snapshot()["journal_sha256"]}
