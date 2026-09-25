"""Turn one Luna output_text into a validated, executable PlanSpec in memory.

Model output is untrusted data. No CAD command is sent by this module.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from planspec import PlanError, dry_run
from provider_response_receipt import from_response


class PlanSpecOutputError(ValueError):
    pass


def _unique_pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise PlanSpecOutputError("Duplicate JSON key in model output")
        result[key] = value
    return result


def _invalid_constant(_):
    raise PlanSpecOutputError("Nonfinite JSON number in model output")


def interpret_response(raw: dict, *, allowed_versions: frozenset[str],
                       max_commands: int = 1000) -> dict:
    """Validate a single final text and compile without mutating CAD."""
    if not isinstance(allowed_versions, frozenset) or not allowed_versions or \
            any(not isinstance(value, str) for value in allowed_versions) or \
            type(max_commands) is not int or not 1 <= max_commands <= 10000:
        raise PlanSpecOutputError("Frozen PlanSpec scope is invalid")
    receipt = from_response(raw)
    output = raw.get("output")
    if not isinstance(output, list) or not output:
        raise PlanSpecOutputError("Model output has no final message")
    messages = []
    for item in output:
        if not isinstance(item, dict):
            raise PlanSpecOutputError("Model output item is invalid")
        if item.get("type") == "reasoning":
            continue  # Never inspect or persist reasoning content.
        if item.get("type") != "message" or item.get("role") != "assistant" or \
                item.get("status", "completed") != "completed" or \
                item.get("phase", "final") != "final":
            raise PlanSpecOutputError("Model output contains a nonfinal or tool item")
        messages.append(item)
    if len(messages) != 1 or not isinstance(messages[0].get("content"), list) or \
            len(messages[0]["content"]) != 1:
        raise PlanSpecOutputError("Exactly one final output_text is required")
    content = messages[0]["content"][0]
    if not isinstance(content, dict) or content.get("type") != "output_text" or \
            not isinstance(content.get("text"), str):
        raise PlanSpecOutputError("Final content must be output_text")
    text = content["text"]
    if not text.strip() or len(text.encode("utf-8")) > 1_000_000 or \
            ("output_text" in raw and raw["output_text"] != text):
        raise PlanSpecOutputError("Final output_text is empty, oversized or inconsistent")
    try:
        plan = json.loads(text, object_pairs_hook=_unique_pairs,
                          parse_constant=_invalid_constant)
    except (UnicodeError, ValueError) as error:
        raise PlanSpecOutputError("Final output_text is not strict JSON") from None
    if not isinstance(plan, dict) or plan.get("schema_version") not in allowed_versions:
        raise PlanSpecOutputError("PlanSpec version differs from frozen scope")
    try:
        compiled = dry_run(plan)
    except (PlanError, KeyError, TypeError, ValueError):
        raise PlanSpecOutputError("PlanSpec validation or compilation failed") from None
    if not compiled["executable"] or compiled["unsupported"] or \
            compiled["quality_blockers"] or \
            not 1 <= len(compiled["commands"]) <= max_commands:
        raise PlanSpecOutputError("PlanSpec is unsupported or blocked before CAD")
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
    return {"schema_version": "m3-luna-planspec-gate-1",
            "plan_sha256": hashlib.sha256(canonical).hexdigest().upper(),
            "commands_sha256": compiled["commands_sha256"],
            "command_count": len(compiled["commands"]),
            "provider_receipt": receipt, "plan": plan, "compiled": compiled}
