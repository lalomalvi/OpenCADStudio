"""Synthetic L0 adapter tests; no GUI, CAD server or DWG user file."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from owned_cad_executor import CadExecutionError, OwnedCadExecutor, verify_owned_cad_evidence
from planspec import dry_run
from reserved_runner import Invocation
from test_luna_planspec_gate import FIXTURES


class FakeGui:
    pid = 41002
    args = ["synthetic-cad.exe", "--new-instance"]

    def poll(self):
        return None


class FakeClient:
    def __init__(self, binary, entity_count, *, dirty=False, script_timeout=False):
        self.binary = binary
        self.entity_count = entity_count
        self.dirty = dirty
        self.script_timeout = script_timeout
        self.calls = []

    def handshake(self):
        self.calls.append("handshake")
        return {}

    def tool(self, name, arguments):
        op = arguments.get("op") or arguments.get("request", {}).get("op")
        self.calls.append(op or name)
        if name == "ocs_sessions":
            return {"status": "ready", "result": [{"session_id": "synthetic-session",
                    "process_id": 41002, "process_started_at_unix_ms": 12345,
                    "executable_path": str(self.binary)}]}
        if op == "state":
            return {"document_id": 3, "revision": 0,
                    "geometry_revision": 4, "camera_revision": 2,
                    "modal": False, "active_command": False,
                    "documents": [{"dirty": self.dirty}]}
        if op == "new":
            return {"status": "completed"}
        if op == "run_script":
            if self.script_timeout:
                raise TimeoutError("synthetic lost reply")
            return {"completed_commands": len(arguments["request"]["commands"]),
                    "added_entities": self.entity_count}
        if op == "audit":
            return {"ok": True}
        if op == "run" and arguments["request"].get("cmd") == "ZOOM EXTENTS":
            return {"status": "completed"}
        if op == "save_verified":
            dwg = Path(arguments["request"]["path"])
            dwg.write_bytes(b"synthetic-dwg-bytes")
            return {"result": {"verified": True,
                    "sha256": hashlib.sha256(dwg.read_bytes()).hexdigest()}}
        raise AssertionError((name, arguments))

    def capture_artifact(self, session, path, *, document_id,
                         geometry_revision, camera_revision, max_dimension):
        self.calls.append("capture")
        path.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic-capture")
        return {"render_fence": "shader_encoded_frame",
                "overlay_policy": "drawing_only"}


class OwnedCadExecutorTests(unittest.TestCase):
    def setup_case(self, directory, **client_options):
        root = Path(directory).resolve()
        binary = root / "synthetic-cad.exe"
        binary.write_bytes(b"synthetic-binary")
        plan = json.loads((FIXTURES / "synthetic-wall.planspec.json")
                          .read_text(encoding="utf-8"))
        compiled = dry_run(plan)
        source = root / "image.png"
        source.write_bytes(b"synthetic-image")
        protocol = root / "protocol.txt"
        protocol.write_text("synthetic-protocol", encoding="utf-8")
        sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest().upper()
        invocation = Invocation("baseline", "case-0", 1, "request-1", source,
                                protocol, binary, "gpt-6-luna", "medium",
                                sha(source), sha(protocol), sha(binary))
        client = FakeClient(binary, len(compiled["commands"]), **client_options)
        return OwnedCadExecutor(client, FakeGui(), binary, root), invocation, compiled, client

    def test_owned_identity_script_audit_and_verified_save(self):
        with tempfile.TemporaryDirectory() as directory:
            executor, invocation, compiled, client = self.setup_case(directory)
            evidence = executor(invocation, compiled)
            report = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "passed_l2_internal")
            self.assertEqual(report["commands_sha256"], compiled["commands_sha256"])
            self.assertEqual(verify_owned_cad_evidence(evidence), report)
            self.assertEqual(client.calls,
                             ["handshake", "ocs_sessions", "state", "new", "state",
                              "run_script", "audit", "save_verified"])
            with self.assertRaises(CadExecutionError):
                executor(invocation, compiled)
            self.assertEqual(len(client.calls), 8)

    def test_nested_dwg_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            executor, invocation, compiled, _ = self.setup_case(directory)
            evidence = executor(invocation, compiled)
            report = json.loads(evidence.read_text(encoding="utf-8"))
            (evidence.parent / report["dwg"]["file"]).write_bytes(b"tampered")
            with self.assertRaisesRegex(CadExecutionError, "changed"):
                verify_owned_cad_evidence(evidence)

    def test_fenced_capture_is_bound_and_tamper_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            executor, invocation, compiled, client = self.setup_case(directory)
            executor = OwnedCadExecutor(client, executor.gui, executor.binary,
                                        executor.run_root, capture_viewport=True)
            evidence = executor(invocation, compiled)
            report = verify_owned_cad_evidence(evidence)
            self.assertEqual(report["capture"]["render_fence"], "shader_encoded_frame")
            self.assertEqual(client.calls[-3:], ["run", "state", "capture"])
            (evidence.parent / report["capture"]["file"]).write_bytes(b"tampered")
            with self.assertRaisesRegex(CadExecutionError, "changed"):
                verify_owned_cad_evidence(evidence)

    def test_binary_change_and_dirty_document_block_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            executor, invocation, compiled, client = self.setup_case(directory)
            executor.binary.write_bytes(b"changed-binary")
            with self.assertRaises(CadExecutionError):
                executor(invocation, compiled)
            self.assertEqual(client.calls, [])
        with tempfile.TemporaryDirectory() as directory:
            executor, invocation, compiled, client = self.setup_case(directory, dirty=True)
            with self.assertRaises(CadExecutionError):
                executor(invocation, compiled)
            self.assertNotIn("new", client.calls)

    def test_lost_script_reply_does_not_send_a_second_script_or_save(self):
        with tempfile.TemporaryDirectory() as directory:
            executor, invocation, compiled, client = self.setup_case(
                directory, script_timeout=True)
            with self.assertRaises(TimeoutError):
                executor(invocation, compiled)
            self.assertEqual(client.calls.count("run_script"), 1)
            self.assertNotIn("save_verified", client.calls)


if __name__ == "__main__":
    unittest.main()
