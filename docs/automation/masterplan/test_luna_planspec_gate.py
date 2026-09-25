"""Synthetic Luna output validation; no model, image or CAD process."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from luna_planspec_gate import PlanSpecOutputError, interpret_response
from test_provider_response_receipt import response


FIXTURES = Path(__file__).with_name("fixtures")


def wrapped(text):
    value = response("resp-synthetic")
    value["output"] = [{"type": "reasoning", "summary": []},
                       {"type": "message", "role": "assistant", "status": "completed",
                        "phase": "final", "content": [
                            {"type": "output_text", "text": text}]}]
    value["output_text"] = text
    return value


class LunaPlanSpecGateTests(unittest.TestCase):
    def test_single_final_json_compiles_without_cad(self):
        plan = json.loads((FIXTURES /
            "synthetic-three-wall-middle-door-clear-v8.planspec.json").read_text(encoding="utf-8"))
        raw = wrapped(json.dumps(plan))
        first = interpret_response(raw, allowed_versions=frozenset({"planspec-8"}))
        second = interpret_response(raw, allowed_versions=frozenset({"planspec-8"}))
        self.assertEqual(first["plan_sha256"], second["plan_sha256"])
        self.assertEqual(first["commands_sha256"], second["commands_sha256"])
        self.assertEqual(first["command_count"], 18)
        self.assertTrue(first["compiled"]["executable"])
        self.assertNotIn("resp-synthetic", str(first["provider_receipt"]))

    def test_duplicate_key_markdown_and_wrong_version_fail_before_cad(self):
        plan = json.loads((FIXTURES / "synthetic-wall.planspec.json").read_text(encoding="utf-8"))
        text = json.dumps(plan)
        with self.assertRaises(PlanSpecOutputError):
            interpret_response(wrapped(text.replace('"units": "m",',
                '"units": "m", "units": "mm",', 1)),
                allowed_versions=frozenset({"planspec-3"}))
        with self.assertRaises(PlanSpecOutputError):
            interpret_response(wrapped("```json\n" + text + "\n```"),
                               allowed_versions=frozenset({"planspec-3"}))
        with self.assertRaisesRegex(PlanSpecOutputError, "version"):
            interpret_response(wrapped(text), allowed_versions=frozenset({"planspec-8"}))

    def test_extra_message_tool_or_mismatched_summary_is_rejected(self):
        plan = json.loads((FIXTURES / "synthetic-wall.planspec.json").read_text(encoding="utf-8"))
        valid = wrapped(json.dumps(plan))
        extra = deepcopy(valid)
        extra["output"].append(deepcopy(extra["output"][-1]))
        with self.assertRaises(PlanSpecOutputError):
            interpret_response(extra, allowed_versions=frozenset({"planspec-3"}))
        tool = deepcopy(valid)
        tool["output"].append({"type": "function_call", "name": "ocs_execute"})
        with self.assertRaises(PlanSpecOutputError):
            interpret_response(tool, allowed_versions=frozenset({"planspec-3"}))
        mismatch = deepcopy(valid)
        mismatch["output_text"] = "{}"
        with self.assertRaises(PlanSpecOutputError):
            interpret_response(mismatch, allowed_versions=frozenset({"planspec-3"}))

    def test_blocked_plan_and_nonfinite_json_are_rejected(self):
        blocked = json.loads((FIXTURES /
            "synthetic-three-wall-middle-door-obstacle-v8.planspec.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(PlanSpecOutputError, "blocked"):
            interpret_response(wrapped(json.dumps(blocked)),
                               allowed_versions=frozenset({"planspec-8"}))
        text = json.dumps(blocked).replace('"offset_m": 1.05', '"offset_m": NaN', 1)
        with self.assertRaises(PlanSpecOutputError):
            interpret_response(wrapped(text), allowed_versions=frozenset({"planspec-8"}))


if __name__ == "__main__":
    unittest.main()
