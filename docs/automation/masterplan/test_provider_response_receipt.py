"""Synthetic Responses objects; no API key, model call or private image."""

import json
import tempfile
import unittest

from provider_response_receipt import ResponseReceiptError, from_response
from reserved_runner import InvocationUncertain, Observation, run_once, verify_envelope
from test_reserved_runner import USAGE
import test_reserved_trial


def response(identity, model="gpt-6-luna", usage=USAGE):
    return {"object": "response", "status": "completed", "id": identity,
            "model": model, "usage": {
                "input_tokens": usage["input_tokens"],
                "input_tokens_details": {
                    "cached_tokens": usage["cached_input_tokens"],
                    "cache_write_tokens": usage["cache_write_input_tokens"]},
                "output_tokens": usage["output_tokens"],
                "output_tokens_details": {
                    "reasoning_tokens": usage["reasoning_output_tokens"]},
                "total_tokens": usage["total_tokens"]},
            "output": [{"private_text": "DO_NOT_PERSIST"}]}


class DirectResponseReceiptTests(unittest.TestCase):
    def setup(self, directory):
        journal, _, run, _, _ = test_reserved_trial.ReservedTrialTests().make_journal(directory)
        evidence = run / "cad-evidence.json"
        evidence.write_text('{"synthetic":true}\n', encoding="utf-8")
        return journal, evidence

    def test_complete_objects_bind_identity_usage_without_raw_output(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, evidence = self.setup(directory)
            result = run_once(journal, "baseline", "case-0", 1, "request-1",
                lambda _: Observation("gpt-6-luna", "resp-generator", USAGE, USAGE,
                                      evidence, response("resp-generator"),
                                      response("resp-supervisor", "gpt-6-sol")))
            envelope = verify_envelope(result["evidence_path"])
            self.assertEqual(result["disposition"], "completed")
            self.assertEqual(envelope["usage_provenance"],
                             "adapter_supplied_direct_response_objects")
            self.assertEqual(envelope["direct_response_receipts"]["supervisor"]["model"],
                             "gpt-6-sol")
            self.assertNotIn("resp-generator", result["evidence_path"].read_text())
            self.assertNotIn("DO_NOT_PERSIST", result["evidence_path"].read_text())
            self.assertNotIn(str(journal.input_root), result["evidence_path"].read_text())

    def test_declared_usage_mismatch_consumes_slot_as_uncertain(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, evidence = self.setup(directory)
            wrong = dict(USAGE, input_tokens=9, total_tokens=12)
            with self.assertRaises(InvocationUncertain):
                run_once(journal, "candidate", "case-0", 1, "request-1",
                    lambda _: Observation("gpt-6-luna", "resp-generator", wrong,
                                          USAGE, evidence, response("resp-generator"),
                                          response("resp-supervisor", "gpt-6-sol")))
            self.assertEqual(journal.snapshot()["dispositions"]["uncertain"], 1)

    def test_incomplete_usage_or_unfinished_response_rejected(self):
        missing = response("resp-one")
        del missing["usage"]["input_tokens_details"]["cache_write_tokens"]
        with self.assertRaises(ResponseReceiptError):
            from_response(missing)
        unfinished = response("resp-two")
        unfinished["status"] = "in_progress"
        with self.assertRaises(ResponseReceiptError):
            from_response(unfinished)
        overlap = response("resp-three")
        overlap["usage"]["input_tokens_details"].update(
            cached_tokens=8, cache_write_tokens=2)
        with self.assertRaises(ResponseReceiptError):
            from_response(overlap)

    def test_receipt_mismatch_detected_when_envelope_is_reopened(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, evidence = self.setup(directory)
            result = run_once(journal, "baseline", "case-0", 2, "request-2",
                lambda _: Observation("gpt-6-luna", "resp-generator", USAGE, USAGE,
                                      evidence, response("resp-generator"),
                                      response("resp-supervisor", "gpt-6-sol")))
            copied = result["evidence_path"].with_name("tampered-envelope.json")
            envelope = json.loads(result["evidence_path"].read_text(encoding="utf-8"))
            envelope["direct_response_receipts"]["generator"]["model"] = "gpt-6-sol"
            copied.write_text(json.dumps(envelope) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs"):
                verify_envelope(copied)


if __name__ == "__main__":
    unittest.main()
