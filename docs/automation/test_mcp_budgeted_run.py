"""Synthetic checkpoint tests; no CAD process or private drawing is opened."""

import json
from pathlib import Path
import tempfile
import unittest

from mcp_budgeted_run import BudgetedRun, CheckpointError, canonical_sha
from mcp_client import UncertainMutation


class FakeClient:
    def __init__(self):
        self.document_id = 7
        self.revision = 2
        self.mutations = []
        self.journal = {}

    def ready_session(self, *, session_id, **_options):
        return {"session_id": session_id, "document_id": self.document_id,
                "revision": self.revision}

    def mutate(self, session_id, request):
        assert session_id == "fixture-session"
        assert request["revision"] == self.revision
        self.revision += 1
        result = {"ok": True, "status": "completed", "completed_commands": 1,
                  "state": {"document_id": self.document_id, "revision": self.revision}}
        self.mutations.append(request["request_id"])
        self.journal[request["request_id"]] = result
        return result

    def recover(self, session_id, request_id):
        assert session_id == "fixture-session"
        return self.journal[request_id]


class BudgetedRunTests(unittest.TestCase):
    def make_run(self, client, directory, commands=None):
        return BudgetedRun(client, "fixture-session",
                           commands or ["LINE 0,0 1,0", "LINE 1,0 2,0"],
                           (Path(directory) / "checkpoint.jsonl").resolve(), "synthetic-run")

    def test_budget_pause_then_resume_without_replaying_completed_step(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            runner = self.make_run(client, directory)
            self.assertEqual(runner.run(max_steps=1, max_elapsed_seconds=10)["status"], "paused")
            self.assertEqual(client.mutations, ["synthetic-run-00000"])
            resumed = self.make_run(client, directory).run(max_steps=1, max_elapsed_seconds=10)
            self.assertEqual(resumed["status"], "completed")
            self.assertEqual(client.mutations, ["synthetic-run-00000", "synthetic-run-00001"])
            self.assertEqual(self.make_run(client, directory).run(
                max_steps=1, max_elapsed_seconds=10)["completed_steps"], 2)
            self.assertEqual(len(client.mutations), 2)
            payload = (Path(directory) / "checkpoint.jsonl").read_text()
            self.assertNotIn("LINE", payload)

    def test_pending_intent_is_reconciled_without_mutation_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            runner = self.make_run(client, directory)
            runner.run(max_steps=1, max_elapsed_seconds=10)
            records = runner._read()
            runner._append(records, {"event": "intent", "step": 1,
                "request_id": runner._request_id(1),
                "command_sha256": canonical_sha(runner.commands[1])})
            # Simulate CAD committing after the durable intent, then process loss.
            client.mutate("fixture-session", {"request_id": runner._request_id(1),
                                               "revision": client.revision})
            result = self.make_run(client, directory).run(max_steps=1, max_elapsed_seconds=10)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(len(client.mutations), 2)
            self.assertTrue(runner._read()[-1]["recovered"])

    def test_changed_plan_and_external_edit_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            self.make_run(client, directory).run(max_steps=1, max_elapsed_seconds=10)
            with self.assertRaisesRegex(CheckpointError, "plan differs"):
                self.make_run(client, directory, ["CIRCLE 0,0 1"]).run(
                    max_steps=1, max_elapsed_seconds=10)
            client.revision += 1
            with self.assertRaisesRegex(CheckpointError, "outside"):
                self.make_run(client, directory).run(max_steps=1, max_elapsed_seconds=10)
            self.assertEqual(client.mutations, ["synthetic-run-00000"])

    def test_unreconciled_intent_stops_before_another_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            runner = self.make_run(client, directory)
            runner.run(max_steps=1, max_elapsed_seconds=10)
            records = runner._read()
            runner._append(records, {"event": "intent", "step": 1,
                "request_id": runner._request_id(1),
                "command_sha256": canonical_sha(runner.commands[1])})
            def uncertain(_session_id, _request_id):
                raise UncertainMutation("synthetic outcome unknown")
            client.recover = uncertain
            with self.assertRaisesRegex(UncertainMutation, "unknown"):
                self.make_run(client, directory).run(max_steps=1, max_elapsed_seconds=10)
            self.assertEqual(client.mutations, ["synthetic-run-00000"])

    def test_tampered_checkpoint_fails_before_next_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            runner = self.make_run(client, directory)
            runner.run(max_steps=1, max_elapsed_seconds=10)
            path = Path(directory) / "checkpoint.jsonl"
            lines = path.read_text().splitlines()
            altered = json.loads(lines[1])
            altered["command_sha256"] = "0" * 64
            lines[1] = json.dumps(altered)
            path.write_text("\n".join(lines) + "\n")
            with self.assertRaisesRegex(CheckpointError, "hash differs"):
                self.make_run(client, directory).run(max_steps=1, max_elapsed_seconds=10)
            self.assertEqual(len(client.mutations), 1)


if __name__ == "__main__":
    unittest.main()
