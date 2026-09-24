"""Offline one-call API adapter tests with a fake Responses client."""

import base64
from dataclasses import replace
import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from luna_once_adapter import DirectResponsesClient, LunaAdapterError, request_luna_once
from reserved_runner import Invocation, Observation, run_once, verify_envelope
from reserved_trial import TrialError
from test_provider_response_receipt import response
from test_reserved_runner import USAGE
import test_reserved_trial


class FakeResponses:
    def __init__(self, journal=None):
        self.calls = []
        self.journal = journal

    def create(self, **kwargs):
        if self.journal is not None:
            assert self.journal.snapshot()["slots_reserved"] == 1
        self.calls.append(kwargs)
        return response("resp-generator")


class FakeClient:
    def __init__(self, journal=None, max_retries=0):
        self.max_retries = max_retries
        self.responses = FakeResponses(journal)


class LunaOnceAdapterTests(unittest.TestCase):
    def test_missing_key_fails_client_preflight_before_reservation(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(LunaAdapterError, "not configured"):
                DirectResponsesClient()

    def test_default_transport_posts_once_without_persisting_response(self):
        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, _):
                return json.dumps(response("resp-generator")).encode("utf-8")

        class Opener:
            def __init__(self):
                self.calls = []

            def open(self, request, timeout):
                self.calls.append((request, timeout))
                return Reply()

        opener = Opener()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-test-key"}), \
                patch("luna_once_adapter.build_opener", return_value=opener):
            raw = DirectResponsesClient().create(model="gpt-6-luna", input="synthetic")
        self.assertEqual(raw["id"], "resp-generator")
        self.assertEqual(len(opener.calls), 1)
        sent, timeout = opener.calls[0]
        self.assertEqual(sent.full_url, "https://api.openai.com/v1/responses")
        self.assertEqual((sent.get_method(), timeout), ("POST", 120.0))
        self.assertEqual(json.loads(sent.data), {"model": "gpt-6-luna", "input": "synthetic"})

    def test_default_transport_does_not_retry_http_failure(self):
        class Opener:
            def __init__(self):
                self.calls = 0

            def open(self, request, timeout):
                self.calls += 1
                raise HTTPError(request.full_url, 429, "private provider error", {}, None)

        opener = Opener()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-test-key"}), \
                patch("luna_once_adapter.build_opener", return_value=opener):
            with self.assertRaisesRegex(LunaAdapterError, "HTTP 429") as raised:
                DirectResponsesClient().create(model="gpt-6-luna")
        self.assertEqual(opener.calls, 1)
        self.assertNotIn("private provider error", str(raised.exception))

    def test_reserved_run_makes_one_request_with_frozen_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, _, run, _, _ = test_reserved_trial.ReservedTrialTests().make_journal(directory)
            evidence = run / "cad-evidence.json"
            evidence.write_text('{"synthetic":true}\n', encoding="utf-8")
            client = FakeClient(journal)
            expected_image_sha = hashlib.sha256(journal.image_paths["case-0"].read_bytes()) \
                .hexdigest().upper()

            def invoke(request):
                raw = request_luna_once(journal, request, client=client)
                return Observation("gpt-6-luna", raw["id"], USAGE, USAGE, evidence,
                                   raw, response("resp-supervisor", "gpt-6-sol"))

            result = run_once(journal, "baseline", "case-0", 1, "request-1", invoke)
            self.assertEqual(result["disposition"], "completed")
            self.assertEqual(len(client.responses.calls), 1)
            call = client.responses.calls[0]
            self.assertEqual(call["model"], "gpt-6-luna")
            self.assertEqual(call["reasoning"], {"effort": "medium"})
            self.assertEqual((call["store"], call["stream"]), (False, False))
            self.assertEqual(call["instructions"],
                             journal.arm_protocols["baseline"].read_bytes().decode("utf-8"))
            image_url = call["input"][0]["content"][1]["image_url"]
            self.assertTrue(image_url.startswith("data:image/png;base64,"))
            self.assertEqual(hashlib.sha256(base64.b64decode(image_url.split(",", 1)[1]))
                             .hexdigest().upper(), expected_image_sha)
            envelope = verify_envelope(result["evidence_path"])
            self.assertEqual(envelope["usage_provenance"],
                             "adapter_supplied_direct_response_objects")
            self.assertNotIn("data:image", result["evidence_path"].read_text())

    def test_retry_enabled_client_or_changed_frozen_input_rejected_before_create(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, _, _, _, _ = test_reserved_trial.ReservedTrialTests().make_journal(directory)
            request = Invocation("baseline", "case-0", 1, "request-1",
                                 journal.image_paths["case-0"],
                                 journal.arm_protocols["baseline"],
                                 journal.arm_binaries["baseline"],
                                 "gpt-6-luna", "medium", "0" * 64, "0" * 64, "0" * 64)
            client = FakeClient()
            with self.assertRaisesRegex(TrialError, "No matching pending request"):
                request_luna_once(journal, request, client=client)
            reserved = journal.reserve("baseline", "case-0", 1, "request-1")
            request = replace(request, source_sha256=reserved["source_sha256"],
                              protocol_sha256=reserved["protocol_sha256"],
                              cad_binary_sha256=reserved["cad_binary_sha256"])
            retrying = FakeClient(max_retries=2)
            with self.assertRaisesRegex(LunaAdapterError, "disable automatic retries"):
                request_luna_once(journal, request, client=retrying)
            self.assertEqual(retrying.responses.calls, [])
            with self.assertRaisesRegex(LunaAdapterError, "differs"):
                request_luna_once(journal, replace(request, source_sha256="0" * 64),
                                  client=client)
            self.assertEqual(client.responses.calls, [])


if __name__ == "__main__":
    unittest.main()
