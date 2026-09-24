"""Durable token quota from provider usage records; no model call is made here.

Reserve a local request ID before invoking a model. After a lost response, reconcile
the same request from trusted usage telemetry or stop; never invoke it again.
Only hashed identities and numeric usage are written to the journal.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from usage_evidence import _usage


class TokenBudgetError(ValueError):
    pass


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def _record_hash(record: dict[str, Any]) -> str:
    body = {key: value for key, value in record.items() if key != "record_sha256"}
    return _hash(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


class TokenBudget:
    def __init__(self, checkpoint: Path, run_id: str, *, max_total_tokens: int,
                 max_responses: int) -> None:
        if not checkpoint.is_absolute() or checkpoint.suffix.lower() != ".jsonl":
            raise ValueError("Token checkpoint must be an absolute JSONL path")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id):
            raise ValueError("Invalid token run ID")
        if type(max_total_tokens) is not int or max_total_tokens < 1 or \
                type(max_responses) is not int or max_responses < 1:
            raise ValueError("Token limits must be positive integers")
        self.path = checkpoint
        self.run_id = run_id
        self.max_total_tokens = max_total_tokens
        self.max_responses = max_responses

    def _append(self, records: list[dict], event: dict) -> None:
        record = {"sequence": len(records),
                  "previous_sha256": records[-1]["record_sha256"] if records else "0" * 64,
                  **event}
        record["record_sha256"] = _record_hash(record)
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            output.flush()
            os.fsync(output.fileno())
        records.append(record)

    def _read(self) -> tuple[list[dict], dict[str, dict], int]:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("x", encoding="utf-8"):
                pass
            records: list[dict] = []
            self._append(records, {"event": "start", "schema_version": "mcp-token-budget-1",
                                   "run_id": self.run_id, "source_kind": "token_usage_record",
                                   "max_total_tokens": self.max_total_tokens,
                                   "max_responses": self.max_responses})
            return records, {}, 0
        try:
            raw = self.path.read_text(encoding="utf-8")
            if not raw.endswith("\n"):
                raise TokenBudgetError("Token checkpoint ends with incomplete record")
            records = [json.loads(line) for line in raw.splitlines()]
        except (OSError, ValueError) as error:
            raise TokenBudgetError("Token checkpoint cannot be read") from error
        previous = "0" * 64
        for index, record in enumerate(records):
            if not isinstance(record, dict) or record.get("sequence") != index or \
                    record.get("previous_sha256") != previous or \
                    record.get("record_sha256") != _record_hash(record):
                raise TokenBudgetError("Token checkpoint chain is invalid")
            previous = record["record_sha256"]
        if not records or any(records[0].get(key) != value for key, value in {
            "event": "start", "schema_version": "mcp-token-budget-1",
            "run_id": self.run_id, "source_kind": "token_usage_record",
            "max_total_tokens": self.max_total_tokens,
            "max_responses": self.max_responses}.items()):
            raise TokenBudgetError("Token checkpoint identity or limits differ")
        requests: dict[str, dict] = {}
        responses: set[str] = set()
        total = 0
        pending = None
        for record in records[1:]:
            request_hash = record.get("request_sha256")
            if not isinstance(request_hash, str) or not re.fullmatch(r"[0-9A-F]{64}", request_hash):
                raise TokenBudgetError("Token checkpoint request identity is invalid")
            if record.get("event") == "intent" and pending is None and \
                    request_hash not in requests and len(requests) < self.max_responses and \
                    total < self.max_total_tokens:
                requests[request_hash] = record
                pending = request_hash
            elif record.get("event") == "done" and pending == request_hash:
                try:
                    usage = _usage(record.get("usage"))
                except ValueError as error:
                    raise TokenBudgetError("Token checkpoint usage is invalid") from error
                response_hash = record.get("response_sha256")
                if not isinstance(response_hash, str) or \
                        not re.fullmatch(r"[0-9A-F]{64}", response_hash) or \
                        response_hash in responses or \
                        record.get("over_budget") != (total + usage["total_tokens"] >
                                                      self.max_total_tokens):
                    raise TokenBudgetError("Token checkpoint completion is invalid")
                responses.add(response_hash)
                requests[request_hash] = record
                total += usage["total_tokens"]
                pending = None
            else:
                raise TokenBudgetError("Token checkpoint transition is invalid")
        return records, requests, total

    def reserve(self, request_id: str) -> dict:
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            raise ValueError("Request identity is required")
        records, requests, total = self._read()
        identity = _hash(request_id)
        if identity in requests:
            if requests[identity]["event"] == "done":
                return {"status": "already_completed", "total_tokens": total}
            raise TokenBudgetError("Prior model request is uncertain; reconcile usage, do not replay")
        if records[-1]["event"] == "intent":
            raise TokenBudgetError("Prior model request is uncertain; reconcile usage, do not replay")
        if len(requests) >= self.max_responses or total >= self.max_total_tokens:
            raise TokenBudgetError("Token or response budget is exhausted")
        self._append(records, {"event": "intent", "request_sha256": identity})
        return {"status": "reserved", "total_tokens": total}

    def complete(self, request_id: str, response_id: str, usage: dict[str, int]) -> dict:
        if not isinstance(request_id, str) or not request_id or \
                not isinstance(response_id, str) or not response_id:
            raise ValueError("Request and response identities are required")
        numeric = _usage(usage)
        records, requests, total = self._read()
        identity, response = _hash(request_id), _hash(response_id)
        if identity not in requests:
            raise TokenBudgetError("No reserved model request")
        prior = requests[identity]
        if prior["event"] == "done":
            if prior["response_sha256"] != response or prior["usage"] != numeric:
                raise TokenBudgetError("Completed response identity or usage differs")
            if prior["over_budget"]:
                raise TokenBudgetError("Token budget exceeded; completion retained")
            return {"status": "already_completed", "total_tokens": total}
        if records[-1]["event"] != "intent" or records[-1]["request_sha256"] != identity:
            raise TokenBudgetError("A different model request is pending")
        if any(record.get("response_sha256") == response for record in records):
            raise TokenBudgetError("Response identity was already counted")
        exceeded = total + numeric["total_tokens"] > self.max_total_tokens
        self._append(records, {"event": "done", "request_sha256": identity,
                               "response_sha256": response, "usage": numeric,
                               "over_budget": exceeded})
        if exceeded:
            raise TokenBudgetError("Token budget exceeded; completion retained")
        return {"status": "completed", "total_tokens": total + numeric["total_tokens"],
                "response_count": sum(record["event"] == "done" for record in records)}

    def snapshot(self) -> dict:
        records, requests, total = self._read()
        completed = sum(record["event"] == "done" for record in requests.values())
        return {"schema_version": "mcp-token-budget-snapshot-1",
                "run_id": self.run_id, "source_kind": "token_usage_record",
                "total_tokens": total, "max_total_tokens": self.max_total_tokens,
                "responses_completed": completed, "max_responses": self.max_responses,
                "pending_uncertain": records[-1]["event"] == "intent",
                "exhausted": len(requests) >= self.max_responses or
                total >= self.max_total_tokens,
                "checkpoint_sha256": hashlib.sha256(self.path.read_bytes()).hexdigest().upper()}
