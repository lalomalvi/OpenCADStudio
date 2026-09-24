"""Synthetic callback ordering and no-replay tests."""

import json
from pathlib import Path
import tempfile
import unittest

from luna_pipeline import PipelineError, run_reserved_pipeline
from reserved_runner import InvocationUncertain, verify_envelope
from reserved_trial import TrialError
from test_luna_planspec_gate import FIXTURES, wrapped
from test_provider_response_receipt import response
import test_reserved_trial


class FakeLuna:
    max_retries = 0

    def __init__(self, raw, events):
        self.raw = raw
        self.events = events
        self.responses = self

    def create(self, **_payload):
        self.events.append("luna")
        return self.raw


class LunaPipelineTests(unittest.TestCase):
    def fixture(self, directory):
        journal, _, run, _, _ = test_reserved_trial.ReservedTrialTests().make_journal(directory)
        plan = json.loads((FIXTURES / "synthetic-wall.planspec.json")
                          .read_text(encoding="utf-8"))
        return journal, run, wrapped(json.dumps(plan))

    def test_single_ordered_callback_seals_only_receipts_and_cad_ref(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, run, raw = self.fixture(directory)
            events = []
            client = FakeLuna(raw, events)
            evidence = run / "cad.json"

            def cad(invocation, compiled):
                self.assertEqual(journal.snapshot()["slots_reserved"], 1)
                self.assertGreater(len(compiled["execution_steps"]), 0)
                events.append("cad")
                evidence.write_text('{"synthetic":true}\n', encoding="utf-8")
                return evidence

            def supervisor(invocation, cad_path):
                self.assertEqual(cad_path, evidence)
                events.append("supervisor")
                return response("resp-supervisor", "gpt-6-sol")

            result = run_reserved_pipeline(
                journal, "baseline", "case-0", 1, "request-1", luna_client=client,
                cad_execute=cad, supervisor_request=supervisor,
                allowed_versions=frozenset({"planspec-3"}))
            self.assertEqual(events, ["luna", "cad", "supervisor"])
            self.assertEqual(result["disposition"], "completed")
            envelope = verify_envelope(result["evidence_path"])
            self.assertEqual(envelope["gates"], "unevaluated")
            self.assertNotIn("data:image", result["evidence_path"].read_text())
            self.assertNotIn('"elements"', result["evidence_path"].read_text())

    def test_invalid_plan_consumes_slot_without_cad_or_supervisor(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, _, raw = self.fixture(directory)
            raw["output"][1]["content"][0]["text"] = "not JSON"
            raw["output_text"] = "not JSON"
            events = []
            with self.assertRaises(InvocationUncertain):
                run_reserved_pipeline(journal, "baseline", "case-0", 1, "request-1",
                    luna_client=FakeLuna(raw, events),
                    cad_execute=lambda *_: events.append("cad"),
                    supervisor_request=lambda *_: events.append("supervisor"),
                    allowed_versions=frozenset({"planspec-3"}))
            self.assertEqual(events, ["luna"])
            self.assertEqual(journal.snapshot()["dispositions"]["uncertain"], 1)

    def test_lost_cad_result_is_never_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, _, raw = self.fixture(directory)
            events = []

            def timeout(*_):
                events.append("cad")
                raise TimeoutError("synthetic lost CAD reply")

            with self.assertRaises(InvocationUncertain):
                run_reserved_pipeline(journal, "baseline", "case-0", 1, "request-1",
                    luna_client=FakeLuna(raw, events), cad_execute=timeout,
                    supervisor_request=None,
                    allowed_versions=frozenset({"planspec-3"}))
            with self.assertRaises((TrialError, InvocationUncertain)):
                run_reserved_pipeline(journal, "baseline", "case-0", 1, "request-2",
                    luna_client=FakeLuna(raw, events), cad_execute=timeout,
                    supervisor_request=None,
                    allowed_versions=frozenset({"planspec-3"}))
            self.assertEqual(events, ["luna", "cad"])

    def test_bad_client_is_rejected_before_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, _, raw = self.fixture(directory)
            client = FakeLuna(raw, [])
            client.max_retries = 2
            with self.assertRaises(PipelineError):
                run_reserved_pipeline(journal, "baseline", "case-0", 1, "request-1",
                    luna_client=client, cad_execute=lambda *_: None,
                    supervisor_request=None,
                    allowed_versions=frozenset({"planspec-3"}))
            self.assertEqual(journal.snapshot()["slots_reserved"], 0)


if __name__ == "__main__":
    unittest.main()
