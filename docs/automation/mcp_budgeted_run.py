"""Budgeted, resumable MCP command sequence with an append-only intent journal.

The journal stores hashes and identities, never CAD commands or RPC payloads.
After an interrupted mutation, resume queries its request_id; it never sends
that mutation again. Keep this file in an isolated run directory.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any

from mcp_client import Client, ProtocolError, UncertainMutation


class CheckpointError(ProtocolError):
    pass


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


class BudgetedRun:
    """Execute one strict command per request with durable precommit intent."""

    def __init__(self, client: Client, session_id: str, commands: list[str],
                 checkpoint: Path, run_id: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id):
            raise ValueError("run_id must be short and path safe")
        if not commands or any(not isinstance(command, str) or not command.strip()
                               for command in commands):
            raise ValueError("A nonempty list of CAD commands is required")
        if not checkpoint.is_absolute() or checkpoint.suffix.lower() != ".jsonl":
            raise ValueError("Checkpoint must be an absolute JSONL path")
        self.client = client
        self.session_id = session_id
        self.commands = commands
        self.path = checkpoint
        self.run_id = run_id
        self.plan_sha256 = canonical_sha(commands)

    def _read(self) -> list[dict]:
        try:
            raw = self.path.read_text(encoding="utf-8")
            if not raw.endswith("\n"):
                raise CheckpointError("Checkpoint ends with an incomplete record")
            records = [json.loads(line) for line in raw.splitlines()]
        except (OSError, ValueError) as error:
            raise CheckpointError("Checkpoint cannot be read") from error
        previous = "0" * 64
        for sequence, record in enumerate(records):
            if not isinstance(record, dict) or record.get("sequence") != sequence or \
                    record.get("previous_sha256") != previous:
                raise CheckpointError("Checkpoint sequence or chain is invalid")
            claimed = record.get("record_sha256")
            body = {key: value for key, value in record.items() if key != "record_sha256"}
            if claimed != canonical_sha(body):
                raise CheckpointError("Checkpoint record hash differs")
            previous = claimed
        if not records or records[0].get("event") != "start":
            raise CheckpointError("Checkpoint start record is missing")
        start = records[0]
        if (start.get("schema_version") != "mcp-budget-checkpoint-1" or
                start.get("run_id") != self.run_id or
                start.get("session_id") != self.session_id or
                start.get("plan_sha256") != self.plan_sha256 or
                start.get("command_count") != len(self.commands)):
            raise CheckpointError("Checkpoint identity or plan differs")
        expected_step = 0
        intent = False
        for record in records[1:]:
            event = record.get("event")
            if (event == "intent" and not intent and expected_step < len(self.commands)
                    and record.get("step") == expected_step):
                if record.get("command_sha256") != canonical_sha(self.commands[expected_step]) or \
                        record.get("request_id") != self._request_id(expected_step):
                    raise CheckpointError("Checkpoint step payload differs")
                intent = True
            elif event == "done" and intent and record.get("step") == expected_step:
                if not isinstance(record.get("revision"), int):
                    raise CheckpointError("Completed step has no revision")
                expected_step += 1
                intent = False
            elif event == "paused" and not intent and record.get("next_step") == expected_step:
                continue
            else:
                raise CheckpointError("Checkpoint transition is invalid")
        return records

    def _append(self, records: list[dict], event: dict) -> None:
        record = {"sequence": len(records), "previous_sha256": records[-1]["record_sha256"]
                  if records else "0" * 64, **event}
        record["record_sha256"] = canonical_sha(record)
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with self.path.open("a", encoding="utf-8") as target:
            target.write(line)
            target.flush()
            os.fsync(target.fileno())
        records.append(record)

    def _request_id(self, step: int) -> str:
        return f"{self.run_id}-{step:05d}"

    def _state(self) -> dict:
        selected = self.client.ready_session(session_id=self.session_id,
                                             wait_for_existing=True, timeout=15)
        if selected.get("session_id") != self.session_id or \
                not isinstance(selected.get("document_id"), int) or \
                not isinstance(selected.get("revision"), int):
            raise CheckpointError("Session document identity is unavailable")
        return selected

    def _progress(self, records: list[dict]) -> tuple[int, bool, int, int]:
        start = records[0]
        completed = [record for record in records if record["event"] == "done"]
        step = len(completed)
        pending = bool(step < len(self.commands) and records[-1]["event"] == "intent")
        document_id = start["document_id"]
        revision = completed[-1]["revision"] if completed else start["revision"]
        return step, pending, document_id, revision

    def _confirm(self, result: dict, document_id: int) -> int:
        if result.get("ok") is False or result.get("status") != "completed" or \
                result.get("completed_commands") not in (None, 1):
            raise CheckpointError("Mutation did not complete one command")
        state = result.get("state")
        if not isinstance(state, dict) or state.get("document_id") != document_id or \
                not isinstance(state.get("revision"), int):
            raise CheckpointError("Mutation returned no matching document revision")
        return state["revision"]

    def run(self, *, max_steps: int, max_elapsed_seconds: float) -> dict:
        if max_steps < 1 or max_elapsed_seconds <= 0:
            raise ValueError("Positive step and time budgets are required")
        started = time.monotonic()
        if self.path.exists():
            records = self._read()
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("x", encoding="utf-8"):
                pass
            records = []
            state = self._state()
            self._append(records, {"event": "start", "schema_version": "mcp-budget-checkpoint-1",
                                   "run_id": self.run_id, "session_id": self.session_id,
                                   "document_id": state["document_id"],
                                   "revision": state["revision"],
                                   "plan_sha256": self.plan_sha256,
                                   "command_count": len(self.commands)})
        step, pending, document_id, revision = self._progress(records)
        if pending:
            # An intent may have reached CAD before the process stopped.
            result = self.client.recover(self.session_id, self._request_id(step))
            recovered_revision = self._confirm(result, document_id)
            self._append(records, {"event": "done", "step": step,
                                   "revision": recovered_revision, "recovered": True})
            step += 1
            revision = recovered_revision
        state = self._state()
        if state["document_id"] != document_id or state["revision"] != revision:
            raise CheckpointError("Document changed outside this checkpointed run")
        executed = 0
        while step < len(self.commands):
            if executed >= max_steps or time.monotonic() - started >= max_elapsed_seconds:
                self._append(records, {"event": "paused", "next_step": step,
                                       "reason": "budget"})
                return {"status": "paused", "next_step": step,
                        "completed_steps": step, "total_steps": len(self.commands)}
            self._append(records, {"event": "intent", "step": step,
                                   "request_id": self._request_id(step),
                                   "command_sha256": canonical_sha(self.commands[step])})
            result = self.client.mutate(self.session_id,
                {"op": "run_script", "request_id": self._request_id(step),
                 "document_id": document_id, "revision": revision,
                 "strict": True, "commands": [self.commands[step]]})
            revision = self._confirm(result, document_id)
            self._append(records, {"event": "done", "step": step,
                                   "revision": revision, "recovered": False})
            step += 1
            executed += 1
        return {"status": "completed", "next_step": step,
                "completed_steps": step, "total_steps": len(self.commands)}
