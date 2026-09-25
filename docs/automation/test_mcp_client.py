"""L1 synthetic fault tests for the persistent MCP client."""

import concurrent.futures
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from mcp_client import Client, ProtocolError, ToolError, UncertainMutation


FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/mcp_stdio_fake.py"


class ClientTests(unittest.TestCase):
    def client(self, mode="normal", timeout=1.0):
        # Test transport over stdio without launching the CAD executable.
        environment = os.environ.copy()
        environment["OCS_FIXTURE_MODE"] = mode
        patcher = patch.dict(os.environ, environment)
        patcher.start()
        self.addCleanup(patcher.stop)
        client = Client(FIXTURE, timeout=timeout, command=[sys.executable, str(FIXTURE)])
        self.addCleanup(client.close)
        return client

    def test_handshake_and_readiness_poll_launch_once(self):
        client = self.client("starting")
        client.handshake()
        selected = client.ready_session(launch_if_none=True, timeout=2)
        self.assertEqual(selected["session_id"], "s1")
        self.assertEqual(client.tool("ocs_sessions", {"launch_if_none": False})["launches"], 1)

    def test_waits_for_existing_session_without_launch(self):
        client = self.client("existing_starting")
        selected = client.ready_session(wait_for_existing=True, timeout=2)
        self.assertEqual(selected["session_id"], "s1")
        self.assertEqual(client.tool("ocs_sessions", {"launch_if_none": False})["launches"], 0)

    def test_selected_session_supplies_document_preconditions(self):
        client = self.client()
        client.ready_session()
        result = client.mutate("s1", {"op": "run", "request_id": "bound-1", "cmd": "LINE 0,0 1,0"})
        self.assertEqual(result["status"], "completed")

    def test_ambiguous_session_rejected(self):
        client = self.client("ambiguous")
        with self.assertRaisesRegex(ProtocolError, "specify session_id"):
            client.ready_session()
        self.assertEqual(client.ready_session(session_id="s2")["session_id"], "s2")

    def test_out_of_order_replies_are_correlated(self):
        client = self.client("out_of_order", timeout=2)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(client.rpc, "ping", {"seq": 1})
            second = pool.submit(client.rpc, "ping", {"seq": 2})
            self.assertEqual({first.result()["name"], second.result()["name"]},
                             {"first", "second"})

    def test_blocked_stdin_write_does_not_hold_reply_dispatch_lock(self):
        client = self.client("delayed_first_ping", timeout=4)
        original = client.process.stdin
        first_written = threading.Event()
        entered = threading.Event()
        release = threading.Event()

        class BlockedWriter:
            def write(self, wire):
                if '"seq":2' in wire:
                    entered.set()
                    if not release.wait(3):
                        raise TimeoutError("synthetic write remained blocked")
                written = original.write(wire)
                if '"seq":1' in wire:
                    first_written.set()
                return written

            def flush(self):
                return original.flush()

        client.process.stdin = BlockedWriter()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(client.rpc, "ping", {"seq": 1})
                self.assertTrue(first_written.wait(1))
                second = pool.submit(client.rpc, "ping", {"seq": 2})
                self.assertTrue(entered.wait(1))
                # The first reply must be delivered while the second write is blocked.
                self.assertEqual(first.result(timeout=2), {"name": "first"})
                release.set()
                self.assertEqual(second.result(timeout=3), {})
        finally:
            release.set()
            client.process.stdin = original

    def test_lost_reply_queries_operation_once(self):
        client = self.client("lost_mutation", timeout=0.5)
        request = {"op": "run", "request_id": "synthetic-1", "cmd": "LINE 0,0 1,0",
                   "document_id": 1, "revision": 0}
        result = client.mutate("s1", request)
        self.assertEqual(result["effects"], 1)
        self.assertEqual(client.mutate("s1", request)["effects"], 1)
        self.assertEqual(client.tool_calls, 2)  # execute + read operation
        with self.assertRaisesRegex(ValueError, "reused"):
            client.mutate("s1", {**request, "cmd": "CIRCLE 0,0 1"})

    def test_running_batch_progresses_by_operation_query_without_replay(self):
        client = self.client("running_batch")
        request = {"op": "run_script", "request_id": "batch-progress", "document_id": 1,
                   "revision": 0, "commands": ["LINE 0,0 1,0"]}
        result = client.mutate("s1", request)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["effects"], 1)
        self.assertEqual(client.tool_calls, 3)  # execute, operation, operation
        self.assertEqual(client.mutate("s1", request)["effects"], 1)

    def test_close_modal_can_reveal_another_modal(self):
        client = self.client("chained_modals")
        request = {"op": "action", "name": "close_modal", "request_id": "modal-1",
                   "document_id": 1, "revision": 0}
        self.assertEqual(client.mutate("s1", request)["status"], "waiting_input")
        self.assertEqual(client.mutate("s1", request)["status"], "waiting_input")
        self.assertEqual(client.tool_calls, 1)

    def test_lost_partial_batch_reports_progress(self):
        client = self.client("lost_partial", timeout=0.5)
        request = {"op": "run_script", "request_id": "synthetic-partial",
                   "commands": ["LINE 0,0 1,0", "INVALID"], "document_id": 1, "revision": 0}
        with self.assertRaises(ToolError) as caught:
            client.mutate("s1", request)
        self.assertEqual(caught.exception.result["completed_commands"], 1)
        self.assertEqual(caught.exception.result["next_command"], 1)
        self.assertEqual(client.tool_calls, 2)  # No execute replay.
        with self.assertRaisesRegex(UncertainMutation, "unresolved mutation"):
            client.mutate("s1", {"op": "run", "request_id": "next-after-partial",
                                 "cmd": "LINE 1,0 2,0", "document_id": 1, "revision": 1})

    def test_unknown_operation_stops_without_replay(self):
        client = self.client("unknown_operation", timeout=0.05)
        request = {"op": "run", "request_id": "synthetic-uncertain", "cmd": "LINE 0,0 1,0",
                   "document_id": 1, "revision": 0}
        # A successful immediate reply cannot exercise recovery; simulate loss.
        with patch.object(client, "_tool_raw", side_effect=[ProtocolError("lost"),
                     ProtocolError("unknown_operation")]) as calls:
            with self.assertRaises(UncertainMutation):
                client.mutate("s1", request)
            self.assertEqual(calls.call_count, 2)
        with patch.object(client, "_tool_raw", side_effect=ProtocolError("unknown_operation")) as calls:
            with self.assertRaises(ProtocolError):
                client.mutate("s1", request)
            self.assertEqual(calls.call_count, 1)  # Only an operation query.
        with self.assertRaisesRegex(UncertainMutation, "unresolved mutation"):
            client.mutate("s1", {**request, "request_id": "another-id"})

    def test_lost_reply_then_unknown_operation_blocks_new_mutation(self):
        client = self.client()
        request = {"op": "run", "request_id": "lost-journal", "cmd": "LINE 0,0 1,0",
                   "document_id": 1, "revision": 0}
        with patch.object(client, "_tool_raw", side_effect=[ProtocolError("lost"),
                     ToolError({"ok": False, "code": "unknown_operation", "status": "failed"})]):
            with self.assertRaises(ToolError):
                client.mutate("s1", request)
        with self.assertRaisesRegex(UncertainMutation, "unresolved mutation"):
            client.mutate("s1", {**request, "request_id": "next"})

    def test_standalone_recovery_failure_blocks_session_after_restart(self):
        client = self.client()
        with patch.object(client, "_tool_raw", side_effect=ProtocolError("journal corrupt")):
            with self.assertRaisesRegex(UncertainMutation, "cannot be reconciled"):
                client.recover("s1", "original-batch")
        with self.assertRaisesRegex(UncertainMutation, "unresolved mutation"):
            client.mutate("s1", {"op": "run", "request_id": "new-edit",
                                 "cmd": "LINE 0,0 1,0", "document_id": 1, "revision": 0})

    def test_explicit_server_failure_is_reported(self):
        client = self.client("explicit_failure")
        with self.assertRaises(ToolError):
            client.mutate("s1", {"op": "run", "request_id": "bad-1", "cmd": "INVALID",
                                 "document_id": 1, "revision": 0})
        self.assertEqual(client.tool_calls, 1)

    def test_mutation_requires_document_state(self):
        client = self.client()
        with self.assertRaisesRegex(ValueError, "document_id and revision required"):
            client.mutate("s1", {"op": "run", "request_id": "missing-state", "cmd": "LINE 0,0 1,0"})
        self.assertEqual(client.tool_calls, 0)

    def test_invalid_json_and_eof_fail_closed(self):
        for mode in ("invalid_json", "eof"):
            with self.subTest(mode=mode):
                client = self.client(mode)
                with self.assertRaises(ProtocolError):
                    client.rpc("ping", {})

    def test_stderr_is_drained(self):
        client = self.client("stderr_flood")
        for _ in range(100):
            self.assertEqual(client.rpc("ping", {}), {})

    def test_rpc_trace_is_append_only_and_omits_private_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "rpc.jsonl"
            client = Client(FIXTURE, timeout=1, command=[sys.executable, str(FIXTURE)],
                            trace_path=trace, run_id="synthetic-trace")
            try:
                self.assertEqual(client.rpc("ping", {"token": "private-fixture"}), {})
                self.assertEqual(client.rpc("ping", {"token": "another-private-fixture"}), {})
                events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
                self.assertEqual([event["sequence"] for event in events], [1, 2])
                self.assertTrue(all(event["status"] == "completed" and event["elapsed_ms"] >= 0
                                    for event in events))
                self.assertFalse(client.trace.failed)
                self.assertNotIn("private-fixture", trace.read_text(encoding="utf-8"))
                self.assertNotIn("token", trace.read_text(encoding="utf-8"))
            finally:
                client.close()

    def test_capture_artifact_rejects_stale_revision_without_writing(self):
        client = self.client()
        fake = {"structuredContent": {"ok": True, "document_id": 1,
                                      "geometry_revision": 3, "camera_revision": 4,
                                      "rendered_geometry_revision": 3,
                                      "rendered_camera_revision": 4,
                                      "render_fence": "shader_encoded_frame", "scope": "viewport",
                                      "overlay_policy": "drawing_only",
                                      "projection_contract": "viewport-rte-pixels-1",
                                      "landmarks_px": []},
                "content": [{"type": "image", "mimeType": "image/png",
                             "data": base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()}]}
        with tempfile.TemporaryDirectory() as directory:
            path = (Path(directory) / "capture.png").resolve()
            with patch.object(client, "_tool_result", return_value=fake):
                with self.assertRaisesRegex(ProtocolError, "revision differs"):
                    client.capture_artifact("s1", path, document_id=1,
                                            geometry_revision=2, camera_revision=4)
                self.assertFalse(path.exists())
                metadata = client.capture_artifact("s1", path, document_id=1,
                                                    geometry_revision=3, camera_revision=4)
                self.assertEqual(metadata["geometry_revision"], 3)
                self.assertEqual(path.read_bytes(), b"\x89PNG\r\n\x1a\nfixture")
                fake["structuredContent"]["overlay_policy"] = "interactive"
                rejected = (Path(directory) / "rejected.png").resolve()
                with self.assertRaisesRegex(ProtocolError, "interactive overlays"):
                    client.capture_artifact("s1", rejected, document_id=1,
                                            geometry_revision=3, camera_revision=4)
                self.assertFalse(rejected.exists())

    def test_capture_artifact_landmarks_are_fenced_before_write(self):
        client = self.client()
        fake = {"structuredContent": {"ok": True, "document_id": 1,
                                      "geometry_revision": 3, "camera_revision": 4,
                                      "rendered_geometry_revision": 3,
                                      "rendered_camera_revision": 4,
                                      "render_fence": "shader_encoded_frame", "scope": "viewport",
                                      "overlay_policy": "drawing_only",
                                      "projection_contract": "viewport-rte-pixels-1",
                                      "landmarks_px": [{"id": "hinge", "pixel": [10.5, 20.25],
                                                        "inside": True}]},
                "content": [{"type": "image", "mimeType": "image/png",
                             "data": base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()}]}
        with tempfile.TemporaryDirectory() as directory:
            path = (Path(directory) / "capture.png").resolve()
            landmarks = [{"id": "hinge", "point": [1.0, 0.1, 0.0]}]
            with patch.object(client, "_tool_result", return_value=fake) as rpc:
                metadata = client.capture_artifact("s1", path, document_id=1,
                    geometry_revision=3, camera_revision=4, landmarks=landmarks)
                self.assertEqual(metadata["landmarks_px"][0]["pixel"], [10.5, 20.25])
                self.assertEqual(rpc.call_args.args[1]["landmarks"], landmarks)
                fake["structuredContent"]["landmarks_px"][0]["id"] = "other"
                rejected = (Path(directory) / "rejected.png").resolve()
                with self.assertRaisesRegex(ProtocolError, "landmark projection"):
                    client.capture_artifact("s1", rejected, document_id=1,
                        geometry_revision=3, camera_revision=4, landmarks=landmarks)
                self.assertFalse(rejected.exists())

    def test_capture_artifact_rejects_window_fallback(self):
        client = self.client()
        fake = {"structuredContent": {"ok": True, "document_id": 1,
                                      "geometry_revision": 3, "camera_revision": 4,
                                      "rendered_geometry_revision": 3,
                                      "rendered_camera_revision": 4,
                                      "render_fence": "shader_encoded_frame", "scope": "window"},
                "content": [{"type": "image", "mimeType": "image/png",
                             "data": base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()}]}
        with tempfile.TemporaryDirectory() as directory:
            path = (Path(directory) / "capture.png").resolve()
            with patch.object(client, "_tool_result", return_value=fake):
                with self.assertRaisesRegex(ProtocolError, "scope differs"):
                    client.capture_artifact("s1", path, document_id=1,
                                            geometry_revision=3, camera_revision=4)
            self.assertFalse(path.exists())

    def test_capture_artifact_rejects_missing_render_fence(self):
        client = self.client()
        fake = {"structuredContent": {"ok": True, "document_id": 1,
                                      "geometry_revision": 3, "camera_revision": 4},
                "content": [{"type": "image", "mimeType": "image/png",
                             "data": base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()}]}
        with tempfile.TemporaryDirectory() as directory:
            path = (Path(directory) / "capture.png").resolve()
            with patch.object(client, "_tool_result", return_value=fake):
                with self.assertRaisesRegex(ProtocolError, "render revision differs"):
                    client.capture_artifact("s1", path, document_id=1,
                                            geometry_revision=3, camera_revision=4)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
