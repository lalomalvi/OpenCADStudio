"""Synthetic frozen supervisor requests; no provider or GUI runs."""

import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from reserved_runner import InvocationUncertain, Observation, run_once, verify_envelope
from supervisor_once_adapter import request_supervisor_once
from test_provider_response_receipt import response
from test_reserved_runner import USAGE
import test_reserved_trial


class FakeSupervisor:
    def __init__(self, journal, max_retries=0):
        self.journal = journal
        self.max_retries = max_retries
        self.responses = self
        self.calls = []

    def create(self, **payload):
        assert self.journal.snapshot()["slots_reserved"] == 1
        self.calls.append(payload)
        return response("resp-supervisor", "gpt-6-sol")


class SupervisorOnceAdapterTests(unittest.TestCase):
    def setup_case(self, directory):
        journal, _, run, _, _ = test_reserved_trial.ReservedTrialTests().make_journal(directory)
        protocol = (Path(directory) / "supervisor.txt").resolve()
        protocol.write_bytes(b"Synthetic frozen supervisor protocol\r\n")
        journal.supervisor_protocol_path = protocol
        journal.supervisor_model = "gpt-6-sol"
        journal.supervisor_effort = "low"
        dwg = run / "cad.dwg"
        dwg.write_bytes(b"synthetic-dwg")
        png = run / "cad.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic")
        sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest().upper()
        evidence = run / "cad.json"
        evidence.write_text(json.dumps({
            "schema_version": "m7-owned-cad-evidence-1", "status": "passed_l2_internal",
            "audit_ok": True, "session": {"document_id": 2},
            "dwg": {"file": dwg.name, "sha256": sha(dwg), "bytes": dwg.stat().st_size},
            "capture": {"file": png.name, "sha256": sha(png), "bytes": png.stat().st_size,
                        "document_id": 2, "geometry_revision": 4, "camera_revision": 3,
                        "render_fence": "shader_encoded_frame",
                        "overlay_policy": "drawing_only"}},
            sort_keys=True), encoding="utf-8")
        return journal, evidence, protocol, png

    def test_one_frozen_request_with_two_in_memory_images(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, evidence, protocol, png = self.setup_case(directory)
            client = FakeSupervisor(journal)

            def invoke(invocation):
                raw = request_supervisor_once(journal, invocation, evidence, client=client)
                generator = response("resp-generator")
                return Observation("gpt-6-luna", generator["id"], USAGE, USAGE,
                                   evidence, generator, raw)

            result = run_once(journal, "baseline", "case-0", 1, "request-1", invoke)
            self.assertEqual(result["disposition"], "completed")
            self.assertEqual(len(client.calls), 1)
            payload = client.calls[0]
            self.assertEqual((payload["model"], payload["reasoning"]),
                             ("gpt-6-sol", {"effort": "low"}))
            self.assertEqual(payload["instructions"], protocol.read_bytes().decode("utf-8"))
            images = payload["input"][0]["content"][1:]
            self.assertEqual(len(images), 2)
            self.assertEqual(base64.b64decode(images[1]["image_url"].split(",", 1)[1]),
                             png.read_bytes())
            envelope = verify_envelope(result["evidence_path"])
            self.assertEqual(envelope["gates"], "unevaluated")
            self.assertEqual(journal.verified_slot("baseline", "case-0", 1)
                             ["start"]["supervisor_contract"]["model"], "gpt-6-sol")
            self.assertNotIn("data:image", result["evidence_path"].read_text())

    def test_retrying_client_consumes_slot_without_provider_call(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, evidence, _, _ = self.setup_case(directory)
            client = FakeSupervisor(journal, max_retries=2)
            with self.assertRaises(InvocationUncertain):
                run_once(journal, "baseline", "case-0", 1, "request-1",
                         lambda invocation: request_supervisor_once(
                             journal, invocation, evidence, client=client))
            self.assertEqual(client.calls, [])
            self.assertEqual(journal.snapshot()["dispositions"]["uncertain"], 1)

    def test_capture_tamper_blocks_provider_call(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, evidence, _, png = self.setup_case(directory)
            client = FakeSupervisor(journal)

            def invoke(invocation):
                png.write_bytes(b"changed")
                return request_supervisor_once(journal, invocation, evidence, client=client)

            with self.assertRaises(InvocationUncertain):
                run_once(journal, "baseline", "case-0", 1, "request-1", invoke)
            self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
