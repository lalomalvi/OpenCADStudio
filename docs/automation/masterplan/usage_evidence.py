"""Aggregate Codex response usage without exporting conversation or credentials.

The input is a local rollout JSONL. Output contains only numeric totals and
coverage counts; response IDs are kept in memory solely for deduplication.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


class EvidenceError(ValueError):
    pass


def _usage(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict) or any(key not in raw for key in FIELDS):
        raise EvidenceError("Usage record has missing fields")
    values = {key: raw[key] for key in FIELDS}
    if any(type(value) is not int or value < 0 for value in values.values()):
        raise EvidenceError("Usage fields must be nonnegative integers")
    if values["cached_input_tokens"] > values["input_tokens"]:
        raise EvidenceError("Cached input exceeds total input")
    if values["reasoning_output_tokens"] > values["output_tokens"]:
        raise EvidenceError("Reasoning output exceeds total output")
    if values["total_tokens"] != values["input_tokens"] + values["output_tokens"]:
        raise EvidenceError("Response token total is inconsistent")
    return values


def summarize(lines: Iterable[str], *, expected_total: int | None = None) -> dict[str, Any]:
    responses: dict[str, dict[str, int]] = {}
    turns: set[str] = set()
    seen_records = 0
    duplicate_records = 0
    for number, line in enumerate(lines, 1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise EvidenceError(f"Invalid JSONL at line {number}") from error
        if item.get("type") != "token_usage_record":
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            raise EvidenceError(f"Missing usage payload at line {number}")
        response_id = payload.get("response_id")
        if not isinstance(response_id, str) or not response_id:
            raise EvidenceError(f"Missing response identity at line {number}")
        usage = _usage(payload.get("usage"))
        seen_records += 1
        if response_id in responses:
            if responses[response_id] != usage:
                raise EvidenceError(f"Conflicting duplicate usage at line {number}")
            duplicate_records += 1
            continue
        responses[response_id] = usage
        turn_id = payload.get("turn_id")
        if isinstance(turn_id, str) and turn_id:
            turns.add(turn_id)
    if not responses:
        raise EvidenceError("No response usage records found")
    totals: Counter[str] = Counter()
    for usage in responses.values():
        totals.update(usage)
    if expected_total is not None and totals["total_tokens"] != expected_total:
        raise EvidenceError("Unique-response total differs from expected baseline")
    return {
        "schema_version": "m3-usage-summary-1",
        "source_kind": "token_usage_record",
        "coverage": {"records": seen_records, "unique_responses": len(responses),
                     "duplicate_records": duplicate_records, "turns_with_identity": len(turns)},
        "usage": {key: totals[key] for key in FIELDS},
        "noncached_input_tokens": totals["input_tokens"] - totals["cached_input_tokens"],
        "identity": {"effective_model": "unknown", "supervisor_usage": "unknown"},
        "billed_cost": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rollout", type=Path, help="Private local JSONL; never copied to output")
    parser.add_argument("--expected-total", type=int)
    args = parser.parse_args()
    with args.rollout.open(encoding="utf-8") as source:
        print(json.dumps(summarize(source, expected_total=args.expected_total), indent=2))


if __name__ == "__main__":
    main()
