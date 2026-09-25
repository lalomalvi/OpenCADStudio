"""Single-writer M7 trial journal: freeze-bound intent before each model attempt.

This records attempts, not verdicts. No model or CAD operation is invoked here.
An uncertain intent cannot be replayed with a new request identity.
"""

from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from reserved_oracle import OracleError, _read_cohort, verify_ready


class TrialError(ValueError):
    pass


_HASH = re.compile(r"[0-9A-F]{64}")
_ID = re.compile(r"[A-Za-z0-9_.-]{1,128}")
_ARMS = ("baseline", "candidate")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _file_sha(path: Path) -> str:
    if not path.is_absolute() or not path.is_file():
        raise TrialError("Absolute protocol, binary or evidence file is required")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _locked(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._exclusive():
            return method(self, *args, **kwargs)
    return wrapper


class TrialJournal:
    def __init__(self, checkpoint: Path, run_id: str, *, cohort_path: Path,
                 image_paths: dict[str, Path], input_root: Path,
                 oracle_manifest_path: Path, oracle_paths: dict[str, Path],
                 oracle_root: Path, arm_protocols: dict[str, Path],
                 arm_binaries: dict[str, Path],
                 requested_model: str, effort: str, hardware_label: str,
                 supervisor_protocol_path: Path | None = None,
                 supervisor_model: str | None = None,
                 supervisor_effort: str | None = None) -> None:
        if not checkpoint.is_absolute() or checkpoint.suffix.lower() != ".jsonl" \
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id) \
                or not isinstance(requested_model, str) or not _ID.fullmatch(requested_model) \
                or effort not in {"low", "medium", "high", "xhigh", "max"} \
                or set(arm_protocols) != set(_ARMS) \
                or set(arm_binaries) != set(_ARMS) \
                or not isinstance(hardware_label, str) or not hardware_label.strip():
            raise TrialError("Trial identity, model, effort or checkpoint is invalid")
        if (supervisor_protocol_path is None) != (supervisor_model is None) or \
                (supervisor_protocol_path is None) != (supervisor_effort is None) or \
                (supervisor_protocol_path is not None and (
                    not isinstance(supervisor_protocol_path, Path) or
                    not supervisor_protocol_path.is_absolute() or
                    not isinstance(supervisor_model, str) or
                    not _ID.fullmatch(supervisor_model) or
                    supervisor_effort not in {"low", "medium", "high", "xhigh", "max"})):
            raise TrialError("Supervisor contract must be complete before trial")
        self.path = checkpoint
        self.run_id = run_id
        self.cohort_path = cohort_path
        self.image_paths = image_paths
        self.input_root = input_root
        self.oracle_manifest_path = oracle_manifest_path
        self.oracle_paths = oracle_paths
        self.oracle_root = oracle_root
        self.arm_protocols = arm_protocols
        self.arm_binaries = arm_binaries
        self.requested_model = requested_model
        self.effort = effort
        self.supervisor_protocol_path = supervisor_protocol_path
        self.supervisor_model = supervisor_model
        self.supervisor_effort = supervisor_effort
        self.hardware_sha256 = _digest(hardware_label.encode("utf-8"))
        if checkpoint.resolve(strict=False).is_relative_to(input_root.resolve(strict=True)) \
                or checkpoint.resolve(strict=False).is_relative_to(oracle_root.resolve(strict=True)):
            raise TrialError("Trial journal must stay outside private source roots")

    @contextmanager
    def _exclusive(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with lock_path.open("a+b") as lock:
            if lock.tell() == 0 and lock.seek(0, os.SEEK_END) == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _identity(self) -> tuple[dict, dict]:
        try:
            ready = verify_ready(self.cohort_path, self.image_paths,
                                 input_root=self.input_root,
                                 oracle_manifest_path=self.oracle_manifest_path,
                                 oracle_paths=self.oracle_paths, oracle_root=self.oracle_root)
            cohort, _ = _read_cohort(self.cohort_path)
        except (OracleError, OSError) as error:
            raise TrialError("M7 frozen cohort and oracles are not ready") from error
        start = {"event": "start", "schema_version": "m7-trial-journal-1",
                 "run_id": self.run_id,
                 "cohort_sha256": ready["cohort_sha256"],
                 "oracle_manifest_sha256": ready["oracle_manifest_sha256"],
                 "arm_contracts": {arm: {"protocol_sha256": _file_sha(self.arm_protocols[arm]),
                                         "cad_binary_sha256": _file_sha(self.arm_binaries[arm])}
                                   for arm in _ARMS},
                 "requested_model": self.requested_model, "effort": self.effort,
                 "hardware_sha256": self.hardware_sha256, "arms": list(_ARMS),
                 "slots": 36}
        if self.supervisor_protocol_path is not None:
            start["supervisor_contract"] = {
                "protocol_sha256": _file_sha(self.supervisor_protocol_path),
                "model": self.supervisor_model, "effort": self.supervisor_effort}
        return start, cohort

    def _append(self, records: list[dict], event: dict) -> None:
        record = {"sequence": len(records),
                  "previous_sha256": records[-1]["record_sha256"] if records else "0" * 64,
                  **event}
        record["record_sha256"] = _digest(_canonical(record))
        with self.path.open("a", encoding="utf-8") as target:
            target.write(_canonical(record).decode("utf-8") + "\n")
            target.flush()
            os.fsync(target.fileno())
        records.append(record)

    def _read(self, expected_start: dict, cohort: dict) -> tuple[list[dict], dict, dict | None]:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("x", encoding="utf-8"):
                pass
            records: list[dict] = []
            self._append(records, expected_start)
        else:
            try:
                raw = self.path.read_text(encoding="utf-8")
                if not raw.endswith("\n"):
                    raise TrialError("Trial journal has an incomplete record")
                records = [json.loads(line) for line in raw.splitlines()]
            except (OSError, UnicodeError, ValueError) as error:
                raise TrialError("Trial journal cannot be read") from error
        previous = "0" * 64
        for index, record in enumerate(records):
            if not isinstance(record, dict) or record.get("sequence") != index \
                    or record.get("previous_sha256") != previous or \
                    record.get("record_sha256") != _digest(_canonical({
                        key: value for key, value in record.items() if key != "record_sha256"})):
                raise TrialError("Trial journal hash chain is invalid")
            previous = record["record_sha256"]
        if not records or {key: value for key, value in records[0].items()
                           if key not in {"sequence", "previous_sha256", "record_sha256"}} != expected_start:
            raise TrialError("Trial journal frozen identities changed")
        ids = {case["id"] for case in cohort["cases"]}
        slots: dict[tuple[str, str, int], dict] = {}
        pending = None
        for record in records[1:]:
            slot = (record.get("arm"), record.get("case_id"), record.get("repetition"))
            if slot[0] not in _ARMS or slot[1] not in ids or type(slot[2]) is not int \
                    or slot[2] not in (1, 2, 3) or \
                    not _HASH.fullmatch(str(record.get("request_sha256", ""))):
                raise TrialError("Trial journal slot or request identity is invalid")
            if record.get("event") == "intent" and pending is None and slot not in slots \
                    and set(record) == {"sequence", "previous_sha256", "event", "arm",
                                        "case_id", "repetition", "request_sha256",
                                        "source_sha256", "record_sha256"}:
                case = next(item for item in cohort["cases"] if item["id"] == slot[1])
                if record["source_sha256"] != case["source"]["sha256"]:
                    raise TrialError("Trial source differs from frozen image")
                slots[slot] = record
                pending = slot
            elif record.get("event") == "result" and pending == slot \
                    and record["request_sha256"] == slots[slot]["request_sha256"] \
                    and set(record) == {"sequence", "previous_sha256", "event", "arm",
                                        "case_id", "repetition", "request_sha256",
                                        "disposition", "effective_model", "evidence_file",
                                        "evidence_sha256",
                                        "record_sha256"} \
                    and record.get("disposition") in {"completed", "failed", "partial", "uncertain"} \
                    and isinstance(record.get("effective_model"), str) \
                    and (record["effective_model"] == "unknown" or
                         _ID.fullmatch(record["effective_model"])) \
                    and (record["evidence_file"] is None or
                         (isinstance(record["evidence_file"], str) and
                          record["evidence_file"] and
                          not Path(record["evidence_file"]).is_absolute() and
                          ".." not in Path(record["evidence_file"]).parts)) \
                    and (record["evidence_sha256"] is None or
                         _HASH.fullmatch(str(record["evidence_sha256"]))) \
                    and ((record["evidence_file"] is None) ==
                         (record["evidence_sha256"] is None)) \
                    and (record["disposition"] == "uncertain" or
                         record["evidence_file"] is not None) \
                    and (record["disposition"] != "completed" or
                         record["effective_model"] == self.requested_model):
                if record["evidence_file"] is not None:
                    evidence = (self.path.parent / record["evidence_file"]).resolve(strict=False)
                    if not evidence.is_relative_to(self.path.parent.resolve(strict=True)) \
                            or _file_sha(evidence) != record["evidence_sha256"]:
                        raise TrialError("Trial evidence changed after recording")
                slots[slot] = record
                pending = None
            else:
                raise TrialError("Trial journal transition is invalid")
        return records, slots, pending

    @_locked
    def reserve(self, arm: str, case_id: str, repetition: int, request_id: str) -> dict:
        if arm not in _ARMS or not isinstance(case_id, str) or type(repetition) is not int \
                or repetition not in (1, 2, 3) or not isinstance(request_id, str) \
                or not _ID.fullmatch(request_id):
            raise TrialError("Trial slot or request ID is invalid")
        start, cohort = self._identity()  # Fresh source/oracle preflight before intent.
        case = next((item for item in cohort["cases"] if item["id"] == case_id), None)
        if case is None:
            raise TrialError("Case is outside frozen cohort")
        records, slots, pending = self._read(start, cohort)
        slot = (arm, case_id, repetition)
        if pending is not None:
            raise TrialError("Prior model attempt is uncertain; reconcile it before another")
        if slot in slots:
            raise TrialError("Trial slot already consumed; do not repeat it")
        self._append(records, {"event": "intent", "arm": arm, "case_id": case_id,
                               "repetition": repetition,
                               "request_sha256": _digest(request_id.encode("utf-8")),
                               "source_sha256": case["source"]["sha256"]})
        return {"status": "reserved", "arm": arm, "case_id": case_id,
                "repetition": repetition, "journal_sha256": _file_sha(self.path),
                "source_sha256": case["source"]["sha256"],
                "protocol_sha256": start["arm_contracts"][arm]["protocol_sha256"],
                "cad_binary_sha256": start["arm_contracts"][arm]["cad_binary_sha256"],
                "supervisor_contract": start.get("supervisor_contract")}

    @_locked
    def record_result(self, arm: str, case_id: str, repetition: int, request_id: str,
                      *, disposition: str, effective_model: str,
                      evidence_path: Path | None = None) -> dict:
        start, cohort = self._identity()
        records, slots, pending = self._read(start, cohort)
        slot = (arm, case_id, repetition)
        request_hash = (_digest(request_id.encode("utf-8")) if isinstance(request_id, str)
                        and _ID.fullmatch(request_id) else None)
        if disposition not in {"completed", "failed", "partial", "uncertain"} \
                or not isinstance(effective_model, str) \
                or (effective_model != "unknown" and not _ID.fullmatch(effective_model)) \
                or (disposition == "completed" and effective_model != self.requested_model) \
                or (disposition != "uncertain" and evidence_path is None):
            raise TrialError("Trial disposition, effective model or evidence is invalid")
        if evidence_path is not None and (not evidence_path.is_absolute() or
                not evidence_path.resolve(strict=False).is_relative_to(
                    self.path.parent.resolve(strict=True)) or
                evidence_path.resolve(strict=False) == self.path.resolve(strict=True) or
                evidence_path.resolve(strict=False) == self.path.with_suffix(
                    self.path.suffix + ".lock").resolve(strict=True) or
                evidence_path.suffix.lower() != ".json"):
            raise TrialError("Trial evidence must be a separate file in the run directory")
        evidence_sha = _file_sha(evidence_path) if evidence_path is not None else None
        evidence_file = (evidence_path.resolve(strict=True).relative_to(
            self.path.parent.resolve(strict=True)).as_posix() if evidence_path is not None else None)
        prior = slots.get(slot)
        if prior and prior["event"] == "result" and pending is None \
                and request_hash == prior["request_sha256"] \
                and prior["disposition"] == disposition \
                and prior["effective_model"] == effective_model \
                and prior["evidence_file"] == evidence_file \
                and prior["evidence_sha256"] == evidence_sha:
            return {"status": "already_recorded", "disposition": disposition,
                    "journal_sha256": _file_sha(self.path)}
        if pending != slot or request_hash != slots.get(slot, {}).get("request_sha256"):
            raise TrialError("No matching pending attempt to reconcile")
        self._append(records, {"event": "result", "arm": arm, "case_id": case_id,
                               "repetition": repetition, "request_sha256": request_hash,
                               "disposition": disposition, "effective_model": effective_model,
                               "evidence_file": evidence_file,
                               "evidence_sha256": evidence_sha})
        return {"status": "recorded", "disposition": disposition,
                "journal_sha256": _file_sha(self.path)}

    @_locked
    def verify_pending(self, arm: str, case_id: str, repetition: int,
                       request_id: str) -> dict:
        """Read-only proof that this exact reserved request is still pending."""
        if not self.path.is_file():
            raise TrialError("No matching pending request for model invocation")
        start, cohort = self._identity()
        records, slots, pending = self._read(start, cohort)
        slot = (arm, case_id, repetition)
        expected_request = (_digest(request_id.encode("utf-8"))
                            if isinstance(request_id, str) and _ID.fullmatch(request_id)
                            else None)
        if pending != slot or slots.get(slot, {}).get("event") != "intent" or \
                slots[slot]["request_sha256"] != expected_request:
            raise TrialError("No matching pending request for model invocation")
        return {"source_sha256": slots[slot]["source_sha256"],
                "protocol_sha256": start["arm_contracts"][arm]["protocol_sha256"],
                "cad_binary_sha256": start["arm_contracts"][arm]["cad_binary_sha256"],
                "requested_model": start["requested_model"], "effort": start["effort"],
                "supervisor_contract": start.get("supervisor_contract"),
                "journal_sha256": _file_sha(self.path)}

    @_locked
    def snapshot(self) -> dict:
        start, cohort = self._identity()
        records, slots, pending = self._read(start, cohort)
        dispositions = {name: 0 for name in ("completed", "failed", "partial", "uncertain")}
        for record in slots.values():
            if record["event"] == "result":
                dispositions[record["disposition"]] += 1
        return {"schema_version": "m7-trial-snapshot-1", "run_id": self.run_id,
                "slots_total": 36, "slots_reserved": len(slots),
                "slots_remaining": 36 - len(slots), "pending_uncertain": pending is not None,
                "dispositions": dispositions, "journal_sha256": _file_sha(self.path)}

    @_locked
    def verified_slot(self, arm: str, case_id: str, repetition: int) -> dict:
        """Return a journal-verified slot bound to its frozen run identity."""
        if arm not in _ARMS or not isinstance(case_id, str) or type(repetition) is not int \
                or repetition not in (1, 2, 3):
            raise TrialError("Trial slot identity is invalid")
        start, cohort = self._identity()
        records, slots, pending = self._read(start, cohort)
        if case_id not in {case["id"] for case in cohort["cases"]}:
            raise TrialError("Case is outside frozen cohort")
        slot = (arm, case_id, repetition)
        result = slots.get(slot)
        if result is None or result["event"] != "result":
            raise TrialError("Trial slot has no sealed result")
        intent = next(record for record in records[1:] if record["event"] == "intent"
                      and (record["arm"], record["case_id"], record["repetition"]) == slot)
        return {"start": start, "intent": intent, "result": result,
                "journal_sha256": _file_sha(self.path),
                "pending_uncertain": pending is not None}
