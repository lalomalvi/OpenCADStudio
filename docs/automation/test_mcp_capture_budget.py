"""Synthetic capture quota tests; no GUI, CAD document, or private file."""

from pathlib import Path
import tempfile
import unittest

from mcp_budgeted_run import CheckpointError
from mcp_capture_budget import CaptureBudget


PNG = b"\x89PNG\r\n\x1a\nsynthetic-image-bytes"


class FakeCaptureClient:
    def __init__(self, *, uncertain=False):
        self.calls = 0
        self.uncertain = uncertain

    def capture_artifact(self, session_id, path, *, document_id, geometry_revision,
                         camera_revision, max_dimension):
        assert session_id == "fixture-session"
        self.calls += 1
        path.write_bytes(PNG)
        if self.uncertain:
            raise RuntimeError("response lost after artifact write")
        return {"document_id": document_id, "geometry_revision": geometry_revision,
                "camera_revision": camera_revision, "max_dimension": max_dimension}


class CaptureBudgetTests(unittest.TestCase):
    def make_budget(self, client, directory, *, count=1, bytes_limit=100):
        return CaptureBudget(client, "fixture-session", Path(directory) / "captures.jsonl",
                             "synthetic-run", max_captures=count, max_bytes=bytes_limit)

    def capture(self, budget, path, **overrides):
        values = {"document_id": 7, "geometry_revision": 4, "camera_revision": 2}
        values.update(overrides)
        return budget.capture(path, **values)

    def test_count_budget_survives_restart_without_recapturing(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeCaptureClient()
            path = Path(directory) / "first.png"
            result = self.capture(self.make_budget(client, directory), path)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["bytes"], len(PNG))
            resumed = self.capture(self.make_budget(client, directory), path)
            self.assertEqual(resumed["status"], "already_completed")
            with self.assertRaisesRegex(CheckpointError, "budget is exhausted"):
                self.capture(self.make_budget(client, directory), Path(directory) / "second.png")
            self.assertEqual(client.calls, 1)
            self.assertNotIn("synthetic-image-bytes",
                             (Path(directory) / "captures.jsonl").read_text())

    def test_byte_overrun_is_recorded_and_artifact_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeCaptureClient()
            path = Path(directory) / "large.png"
            budget = self.make_budget(client, directory, count=2, bytes_limit=len(PNG) - 1)
            with self.assertRaisesRegex(CheckpointError, "exceeded artifact-byte"):
                self.capture(budget, path)
            self.assertEqual(path.read_bytes(), PNG)
            with self.assertRaisesRegex(CheckpointError, "exceeded artifact-byte"):
                self.capture(budget, path)
            with self.assertRaisesRegex(CheckpointError, "budget is exhausted"):
                self.capture(budget, Path(directory) / "next.png")
            self.assertEqual(client.calls, 1)

    def test_uncertain_capture_blocks_replay_even_if_file_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeCaptureClient(uncertain=True)
            budget = self.make_budget(client, directory, count=2)
            path = Path(directory) / "pending.png"
            with self.assertRaisesRegex(RuntimeError, "response lost"):
                self.capture(budget, path)
            with self.assertRaisesRegex(CheckpointError, "uncertain"):
                self.capture(self.make_budget(client, directory, count=2), path)
            with self.assertRaisesRegex(CheckpointError, "uncertain"):
                self.capture(budget, Path(directory) / "next.png")
            self.assertEqual(client.calls, 1)

    def test_tamper_and_revision_change_fail_before_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeCaptureClient()
            path = Path(directory) / "first.png"
            self.capture(self.make_budget(client, directory), path)
            with self.assertRaisesRegex(CheckpointError, "revision identity differs"):
                self.capture(self.make_budget(client, directory), path, geometry_revision=5)
            checkpoint = Path(directory) / "captures.jsonl"
            checkpoint.write_text(checkpoint.read_text().replace('"max_bytes":100',
                                                                  '"max_bytes":99'))
            with self.assertRaisesRegex(CheckpointError, "hash differs"):
                self.capture(self.make_budget(client, directory), path)
            self.assertEqual(client.calls, 1)


if __name__ == "__main__":
    unittest.main()
