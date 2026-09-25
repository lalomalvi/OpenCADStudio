"""Synthetic one-shot invocation gate tests. No Luna or CAD call is made."""

import json
from pathlib import Path
import tempfile
import unittest

from reserved_runner import InvocationUncertain, Observation, run_once, verify_envelope
from reserved_trial import TrialError
import test_reserved_trial


USAGE = {"input_tokens": 8, "cached_input_tokens": 2,
         "cache_write_input_tokens": 0, "output_tokens": 3,
         "reasoning_output_tokens": 1, "total_tokens": 11}


class ReservedRunnerTests(unittest.TestCase):
    def setup(self, directory):
        journal, _, run, _, _ = test_reserved_trial.ReservedTrialTests().make_journal(directory)
        evidence = run / "cad-evidence.json"
        evidence.write_text('{"synthetic":true}\n', encoding="utf-8")
        return journal, run, evidence

    def test_reservation_precedes_one_call_and_oracle_is_not_passed(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, run, evidence = self.setup(directory)
            calls = []

            def invoke(request):
                calls.append(request)
                self.assertEqual(journal.snapshot()["slots_reserved"], 1)
                self.assertTrue(journal.snapshot()["pending_uncertain"])
                self.assertFalse(hasattr(request, "oracle_path"))
                self.assertTrue(request.image_path.is_file())
                return Observation("gpt-6-luna", "provider-response-1", USAGE, USAGE, evidence)

            result = run_once(journal, "baseline", "case-0", 1, "private-request", invoke)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result["disposition"], "completed")
            envelope = json.loads(result["evidence_path"].read_text(encoding="utf-8"))
            self.assertEqual(verify_envelope(result["evidence_path"]), envelope)
            self.assertEqual(envelope["usage_provenance"], "adapter_reported_unverified")
            self.assertEqual(envelope["gates"], "unevaluated")
            self.assertNotIn("private-request", result["evidence_path"].read_text())
            self.assertNotIn(str(journal.oracle_root), result["evidence_path"].read_text())
            self.assertEqual(journal.snapshot()["dispositions"]["completed"], 1)
            with self.assertRaisesRegex(TrialError, "already consumed"):
                run_once(journal, "baseline", "case-0", 1, "another-request", invoke)
            self.assertEqual(len(calls), 1)

    def test_callback_error_is_uncertain_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, _, _ = self.setup(directory)
            calls = 0

            def failed(_):
                nonlocal calls
                calls += 1
                raise TimeoutError("response lost after possible mutation")

            with self.assertRaises(InvocationUncertain):
                run_once(journal, "baseline", "case-0", 1, "request-1", failed)
            self.assertEqual(calls, 1)
            self.assertEqual(journal.snapshot()["dispositions"]["uncertain"], 1)
            with self.assertRaisesRegex(TrialError, "already consumed"):
                run_once(journal, "baseline", "case-0", 1, "request-2", failed)
            self.assertEqual(calls, 1)

    def test_invalid_adapter_usage_is_uncertain(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, _, evidence = self.setup(directory)
            bad = dict(USAGE, total_tokens=99)
            with self.assertRaises(InvocationUncertain):
                run_once(journal, "candidate", "case-0", 2, "request-1",
                         lambda _: Observation("gpt-6-luna", "response", bad, USAGE, evidence))
            self.assertEqual(journal.snapshot()["dispositions"]["uncertain"], 1)

    def test_missing_supervisor_usage_stays_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, _, evidence = self.setup(directory)
            result = run_once(journal, "baseline", "case-0", 3, "request-1",
                              lambda _: Observation("gpt-6-luna", "response", USAGE, None, evidence))
            self.assertEqual(result["disposition"], "partial")
            self.assertEqual(journal.snapshot()["dispositions"]["partial"], 1)

    def test_private_or_missing_cad_evidence_stays_partial_or_uncertain(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, _, _ = self.setup(directory)
            result = run_once(journal, "baseline", "case-0", 1, "request-1",
                              lambda _: Observation("gpt-6-luna", "response", USAGE, USAGE, None))
            self.assertEqual(result["disposition"], "partial")
            private = Path(directory) / "private.json"
            private.write_text("{}", encoding="utf-8")
            with self.assertRaises(InvocationUncertain):
                run_once(journal, "candidate", "case-0", 1, "request-2",
                         lambda _: Observation("gpt-6-luna", "response", USAGE, USAGE, private))
            self.assertEqual(journal.snapshot()["dispositions"]["uncertain"], 1)

    def test_nested_cad_evidence_tamper_fails_on_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, _, evidence = self.setup(directory)
            result = run_once(journal, "candidate", "case-0", 1, "request-1",
                              lambda _: Observation("gpt-6-luna", "response", USAGE, USAGE, evidence))
            evidence.write_text('{"synthetic":false}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed"):
                verify_envelope(result["evidence_path"])


if __name__ == "__main__":
    unittest.main()
