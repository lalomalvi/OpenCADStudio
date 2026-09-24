"""Read-only binding of an M7 attempt to its frozen journal and CAD evidence.

This preflight deliberately awards no G0-G10 verdict. Provider, external CAD,
oracle and human evidence must be evaluated separately after this binding.
"""

from __future__ import annotations

from pathlib import Path
import re

from reserved_runner import verify_envelope
from reserved_trial import TrialJournal, _file_sha


class EvaluationError(ValueError):
    pass


_HASH = re.compile(r"[0-9A-F]{64}")
_GATES = tuple(f"G{i}" for i in range(11))


def inspect_slot(journal: TrialJournal, arm: str, case_id: str,
                 repetition: int) -> dict:
    """Verify identities and nested hashes, then expose only pending gates.

    A journal result of `completed` is an invocation disposition, never a
    quality verdict. This function does not open private images or oracles.
    """
    slot = journal.verified_slot(arm, case_id, repetition)
    start, intent, result = slot["start"], slot["intent"], slot["result"]
    blockers = []
    evidence_sha = None
    if result["disposition"] != "completed":
        blockers.append("invocation_not_completed")
    if slot["pending_uncertain"]:
        blockers.append("journal_has_pending_uncertain_intent")
    if result["evidence_file"] is None:
        blockers.append("invocation_envelope_missing")
    else:
        root = journal.path.parent.resolve(strict=True)
        envelope_path = (root / result["evidence_file"]).resolve(strict=True)
        if not envelope_path.is_relative_to(root) or \
                _file_sha(envelope_path) != result["evidence_sha256"]:
            raise EvaluationError("Journal envelope reference changed")
        envelope = verify_envelope(envelope_path)
        expected = {"arm": arm, "case_id": case_id, "repetition": repetition,
                    "request_sha256": intent["request_sha256"],
                    "disposition": result["disposition"],
                    "effective_model": result["effective_model"]}
        if any(envelope.get(key) != value for key, value in expected.items()) or \
                not _HASH.fullmatch(str(envelope.get("response_sha256", ""))):
            raise EvaluationError("Envelope does not match the journal slot")
        evidence_sha = result["evidence_sha256"]
        if envelope.get("cad_evidence") is None:
            blockers.append("cad_evidence_missing")
        if envelope.get("supervisor_usage") is None:
            blockers.append("supervisor_usage_missing")
        if envelope.get("effective_model") != start["requested_model"]:
            blockers.append("effective_model_differs")
        if envelope.get("usage_provenance") != "provider_response_verified":
            blockers.append("provider_identity_and_usage_unverified")
    return {"schema_version": "m7-slot-binding-1", "run_id": journal.run_id,
            "arm": arm, "case_id": case_id, "repetition": repetition,
            "cohort_sha256": start["cohort_sha256"],
            "oracle_manifest_sha256": start["oracle_manifest_sha256"],
            "protocol_sha256": start["arm_contracts"][arm]["protocol_sha256"],
            "cad_binary_sha256": start["arm_contracts"][arm]["cad_binary_sha256"],
            "journal_sha256": slot["journal_sha256"],
            "invocation_envelope_sha256": evidence_sha,
            "disposition": result["disposition"],
            "status": "needs_independent_evidence", "blockers": blockers,
            "gates": {gate: "pending" for gate in _GATES}}
