"""L1 synthetic fault tests for the persistent MCP client."""

import concurrent.futures
import os
from pathlib import Path
import sys
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

    def test_lost_reply_queries_operation_once(self):
        client = self.client("lost_mutation", timeout=0.5)
        request = {"op": "run", "request_id": "synthetic-1", "cmd": "LINE 0,0 1,0"}
        result = client.mutate("s1", request)
        self.assertEqual(result["effects"], 1)
        self.assertEqual(client.mutate("s1", request)["effects"], 1)
        self.assertEqual(client.tool_calls, 2)  # execute + read operation
        with self.assertRaisesRegex(ValueError, "reused"):
            client.mutate("s1", {**request, "cmd": "CIRCLE 0,0 1"})

    def test_unknown_operation_stops_without_replay(self):
        client = self.client("unknown_operation", timeout=0.05)
        request = {"op": "run", "request_id": "synthetic-uncertain", "cmd": "LINE 0,0 1,0"}
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

    def test_explicit_server_failure_is_reported(self):
        client = self.client("explicit_failure")
        with self.assertRaises(ToolError):
            client.mutate("s1", {"op": "run", "request_id": "bad-1", "cmd": "INVALID"})
        self.assertEqual(client.tool_calls, 1)

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


if __name__ == "__main__":
    unittest.main()
