import importlib.util
import io
import json
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("usage_evidence", Path(__file__).with_name("usage_evidence.py"))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def record(response_id: str, *, input_tokens: int = 8, output_tokens: int = 2) -> str:
    return json.dumps({"type": "token_usage_record", "payload": {
        "response_id": response_id, "turn_id": "turn-1", "usage": {
            "input_tokens": input_tokens, "cached_input_tokens": 3,
            "cache_write_input_tokens": 0, "output_tokens": output_tokens,
            "reasoning_output_tokens": 1, "total_tokens": input_tokens + output_tokens,
        }}}) + "\n"


class UsageEvidenceTests(unittest.TestCase):
    def test_identical_duplicate_is_counted_once_and_private_ids_are_omitted(self):
        result = module.summarize(io.StringIO(record("private-id") * 2), expected_total=10)
        self.assertEqual(result["coverage"]["unique_responses"], 1)
        self.assertEqual(result["coverage"]["duplicate_records"], 1)
        self.assertEqual(result["usage"]["total_tokens"], 10)
        self.assertNotIn("private-id", json.dumps(result))
        self.assertIsNone(result["billed_cost"])

    def test_conflicting_duplicate_fails_closed(self):
        with self.assertRaises(module.EvidenceError):
            module.summarize(io.StringIO(record("same") + record("same", output_tokens=4)))

    def test_total_and_included_subcategories_are_checked(self):
        raw = json.loads(record("one"))
        raw["payload"]["usage"]["total_tokens"] = 11
        with self.assertRaises(module.EvidenceError):
            module.summarize([json.dumps(raw)])
        with self.assertRaises(module.EvidenceError):
            module.summarize([record("one")], expected_total=11)

    def test_missing_identity_or_usage_fails(self):
        raw = json.loads(record("one"))
        del raw["payload"]["response_id"]
        with self.assertRaises(module.EvidenceError):
            module.summarize([json.dumps(raw)])
        with self.assertRaises(module.EvidenceError):
            module.summarize(["{}"])


if __name__ == "__main__":
    unittest.main()
