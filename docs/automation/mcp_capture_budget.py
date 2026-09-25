"""Durable capture-count and artifact-byte budget for one isolated MCP run.

An unresolved capture intent consumes its slot and blocks further captures.
The local PNG is preserved for diagnosis; an uncertain RPC is never replayed.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from mcp_budgeted_run import CheckpointError, canonical_sha


class CaptureBudget:
    def __init__(self, client: Any, session_id: str, checkpoint: Path, run_id: str,
                 *, max_captures: int, max_bytes: int) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id):
            raise ValueError("Invalid capture run ID")
        if not checkpoint.is_absolute() or checkpoint.suffix.lower() != ".jsonl":
            raise ValueError("Capture checkpoint must be an absolute JSONL path")
        if type(max_captures) is not int or max_captures < 1 or \
                type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("Capture and byte limits must be positive integers")
        self.client = client
        self.session_id = session_id
        self.path = checkpoint
        self.run_id = run_id
        self.max_captures = max_captures
        self.max_bytes = max_bytes

    def _append(self, records: list[dict], event: dict) -> None:
        record = {"sequence": len(records),
                  "previous_sha256": records[-1]["record_sha256"] if records else "0" * 64,
                  **event}
        record["record_sha256"] = canonical_sha(record)
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            output.flush()
            os.fsync(output.fileno())
        records.append(record)

    def _read(self, document_id: int) -> list[dict]:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("x", encoding="utf-8"):
                pass
            records: list[dict] = []
            self._append(records, {"event": "start", "schema_version": "mcp-capture-budget-1",
                                   "run_id": self.run_id, "session_id": self.session_id,
                                   "document_id": document_id,
                                   "max_captures": self.max_captures,
                                   "max_bytes": self.max_bytes})
            return records
        try:
            raw = self.path.read_text(encoding="utf-8")
            if not raw.endswith("\n"):
                raise CheckpointError("Capture checkpoint ends with an incomplete record")
            records = [json.loads(line) for line in raw.splitlines()]
        except (OSError, ValueError) as error:
            raise CheckpointError("Capture checkpoint cannot be read") from error
        previous = "0" * 64
        for sequence, record in enumerate(records):
            if not isinstance(record, dict) or record.get("sequence") != sequence or \
                    record.get("previous_sha256") != previous:
                raise CheckpointError("Capture checkpoint chain is invalid")
            body = {key: value for key, value in record.items() if key != "record_sha256"}
            if record.get("record_sha256") != canonical_sha(body):
                raise CheckpointError("Capture checkpoint hash differs")
            previous = record["record_sha256"]
        if not records or any(records[0].get(key) != expected for key, expected in {
            "event": "start", "schema_version": "mcp-capture-budget-1",
            "run_id": self.run_id, "session_id": self.session_id,
            "document_id": document_id, "max_captures": self.max_captures,
            "max_bytes": self.max_bytes}.items()):
            raise CheckpointError("Capture checkpoint identity or limits differ")
        count = 0
        pending = False
        names: set[str] = set()
        for record in records[1:]:
            if record.get("event") == "intent" and not pending and count < self.max_captures:
                name = record.get("artifact_name")
                if record.get("capture_index") != count or not isinstance(name, str) or \
                        not re.fullmatch(r"[A-Za-z0-9_-]{1,80}\.png", name) or name in names:
                    raise CheckpointError("Capture intent is invalid")
                if any(type(record.get(key)) is not int or record[key] < 0 for key in
                       ("geometry_revision", "camera_revision")):
                    raise CheckpointError("Capture intent has no revision identity")
                names.add(name)
                pending = True
            elif record.get("event") == "done" and pending and \
                    record.get("capture_index") == count:
                if type(record.get("bytes")) is not int or record["bytes"] < 1 or \
                        type(record.get("over_budget")) is not bool or \
                        not isinstance(record.get("sha256"), str) or \
                        not re.fullmatch(r"[0-9A-F]{64}", record["sha256"]):
                    raise CheckpointError("Capture completion is invalid")
                count += 1
                pending = False
            else:
                raise CheckpointError("Capture checkpoint transition is invalid")
        return records

    def capture(self, path: Path, *, document_id: int, geometry_revision: int,
                camera_revision: int, max_dimension: int = 1024,
                landmarks: list[dict] | None = None) -> dict:
        if not path.is_absolute() or path.parent.resolve() != self.path.parent.resolve() or \
                not re.fullmatch(r"[A-Za-z0-9_-]{1,80}\.png", path.name):
            raise ValueError("Capture must be a new PNG beside its checkpoint")
        if any(type(value) is not int or value < 0 for value in
               (document_id, geometry_revision, camera_revision)):
            raise ValueError("Capture identity is required")
        records = self._read(document_id)
        completed = [record for record in records if record["event"] == "done"]
        for index, record in enumerate(records):
            if record["event"] != "intent" or record["artifact_name"] != path.name:
                continue
            if index + 1 >= len(records) or records[index + 1]["event"] != "done":
                raise CheckpointError("Capture outcome is uncertain; do not replay")
            done = records[index + 1]
            if record["geometry_revision"] != geometry_revision or \
                    record["camera_revision"] != camera_revision:
                raise CheckpointError("Capture revision identity differs")
            if not path.is_file() or path.stat().st_size != done["bytes"] or \
                    hashlib.sha256(path.read_bytes()).hexdigest().upper() != done["sha256"]:
                raise CheckpointError("Completed capture artifact differs from checkpoint")
            if done["over_budget"]:
                raise CheckpointError("Capture exceeded artifact-byte budget; artifact preserved")
            return {"status": "already_completed", "capture_index": done["capture_index"],
                    "bytes": done["bytes"], "sha256": done["sha256"]}
        if records[-1]["event"] == "intent":
            raise CheckpointError("Prior capture outcome is uncertain; do not replay")
        used_bytes = sum(record["bytes"] for record in completed)
        if len(completed) >= self.max_captures or used_bytes >= self.max_bytes:
            raise CheckpointError("Capture or artifact-byte budget is exhausted")
        if path.exists():
            raise CheckpointError("Untracked capture path already exists")
        capture_index = len(completed)
        self._append(records, {"event": "intent", "capture_index": capture_index,
                               "artifact_name": path.name, "geometry_revision": geometry_revision,
                               "camera_revision": camera_revision})
        metadata = self.client.capture_artifact(self.session_id, path,
            document_id=document_id, geometry_revision=geometry_revision,
            camera_revision=camera_revision, max_dimension=max_dimension,
            **({"landmarks": landmarks} if landmarks is not None else {}))
        if not path.is_file() or metadata.get("document_id") != document_id or \
                metadata.get("geometry_revision") != geometry_revision or \
                metadata.get("camera_revision") != camera_revision:
            raise CheckpointError("Capture artifact or identity is absent after RPC")
        size = path.stat().st_size
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        self._append(records, {"event": "done", "capture_index": capture_index,
                               "bytes": size, "sha256": digest,
                               "over_budget": used_bytes + size > self.max_bytes})
        if used_bytes + size > self.max_bytes:
            raise CheckpointError("Capture exceeded artifact-byte budget; artifact preserved")
        return {"status": "completed", "capture_index": capture_index,
                "bytes": size, "sha256": digest, "metadata": metadata}
