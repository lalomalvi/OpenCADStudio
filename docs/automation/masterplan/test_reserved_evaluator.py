"""Synthetic M7 binding tests; no model, CAD or reserved image is used."""

import tempfile
import unittest

from reserved_evaluator import inspect_slot
from reserved_runner import InvocationUncertain, Observation, run_once
from reserved_trial import TrialError
from test_reserved_runner import USAGE
import test_reserved_trial


class ReservedEvaluatorTests(unittest.TestCase):
    def setup(self, directory):
        journal, _, run, _, _ = test_reserved_trial.ReservedTrialTests().make_journal(directory)
        evidence = run / "cad-evidence.json"
        evidence.write_text('{"synthetic":true}\n', encoding="utf-8")
        return journal, evidence

    def test_completed_invocation_still_has_eleven_pending_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, evidence = self.setup(directory)
            run_once(journal, "baseline", "case-0", 1, "private-request",
                     lambda _: Observation("gpt-6-luna", "provider-response", USAGE,
                                           USAGE, evidence))
            result = inspect_slot(journal, "baseline", "case-0", 1)
            self.assertEqual(result["disposition"], "completed")
            self.assertEqual(result["status"], "needs_independent_evidence")
            self.assertEqual(result["gates"], {f"G{i}": "pending" for i in range(11)})
            self.assertIn("provider_identity_and_usage_unverified", result["blockers"])
            self.assertEqual(len(result["invocation_envelope_sha256"]), 64)
            self.assertNotIn("private-request", str(result))
            self.assertNotIn(str(journal.input_root), str(result))

    def test_uncertain_slot_cannot_be_accepted_as_evaluated(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, _ = self.setup(directory)
            with self.assertRaises(InvocationUncertain):
                run_once(journal, "baseline", "case-0", 1, "request-1",
                         lambda _: (_ for _ in ()).throw(TimeoutError("lost")))
            result = inspect_slot(journal, "baseline", "case-0", 1)
            self.assertIn("invocation_not_completed", result["blockers"])
            self.assertIn("invocation_envelope_missing", result["blockers"])
            self.assertEqual(result["gates"]["G5"], "pending")

    def test_nested_cad_tamper_and_other_slot_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, evidence = self.setup(directory)
            run_once(journal, "candidate", "case-0", 2, "request-1",
                     lambda _: Observation("gpt-6-luna", "response", USAGE,
                                           USAGE, evidence))
            with self.assertRaisesRegex(TrialError, "no sealed result"):
                inspect_slot(journal, "candidate", "case-0", 1)
            evidence.write_text('{"synthetic":false}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed"):
                inspect_slot(journal, "candidate", "case-0", 2)


if __name__ == "__main__":
    unittest.main()
