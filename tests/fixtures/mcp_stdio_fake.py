"""Synthetic MCP stdio peer. Never starts CAD or reads user drawings."""

import json
import os
import sys
import time

mode = os.environ.get("OCS_FIXTURE_MODE", "normal")
launches = 0
session_calls = 0
effects = 0
operation_reads = 0
held = None


def send(request, result=None, error=None):
    reply = {"jsonrpc": "2.0", "id": request["id"]}
    reply["error" if error else "result"] = error or result
    print(json.dumps(reply), flush=True)


for line in sys.stdin:
    request = json.loads(line)
    method = request["method"]
    if mode == "invalid_json":
        print("not-json", flush=True)
        continue
    if mode == "eof":
        sys.exit(0)
    if mode in {"bool_id", "float_id", "string_id"} and method == "ping":
        bad_id = {"bool_id": True, "float_id": 1.0, "string_id": "1"}[mode]
        print(json.dumps({"jsonrpc": "2.0", "id": bad_id, "result": {"wrong": True}}),
              flush=True)
        continue
    if mode == "out_of_order" and method == "ping":
        if held is None:
            held = request
            continue
        send(request, {"name": "second"})
        send(held, {"name": "first"})
        held = None
        continue
    if mode == "delayed_first_ping" and method == "ping" and request["params"].get("seq") == 1:
        time.sleep(0.5)
        send(request, {"name": "first"})
        continue
    if method == "server/discover":
        send(request, {"supportedVersions": ["2026-07-28"],
                       "capabilities": {"extensions": {"io.modelcontextprotocol/tasks": {}}}})
    elif method == "tools/call":
        params = request["params"]
        name = params["name"]
        arguments = params["arguments"]
        if name == "ocs_sessions":
            session_calls += 1
            launches += bool(arguments.get("launch_if_none"))
            if mode == "existing_starting" and session_calls == 1:
                send(request, {"structuredContent": {"ok": True, "status": "absent", "result": []}})
            elif mode == "starting" and session_calls == 1:
                send(request, {"structuredContent": {"ok": True, "status": "starting",
                    "reason": "editor_launch_requested", "retry_after_ms": 10,
                    "deadline_remaining_ms": 90000, "result": []}})
            else:
                sessions = [{"session_id": "s1", "document_id": 1, "revision": 0,
                             "documents": [{"id": 1, "start": False}]}]
                if mode == "ambiguous":
                    sessions.append({"session_id": "s2"})
                send(request, {"structuredContent": {"ok": True, "status": "ready", "result": sessions,
                                                      "launches": launches}})
        elif name == "ocs_execute":
            if arguments["request"]["op"] not in {"new", "open", "stop", "activate"} and (
                "document_id" not in arguments["request"] or "revision" not in arguments["request"]):
                send(request, {"structuredContent": {"ok": False, "status": "failed",
                    "code": "document_required"}, "isError": True})
                continue
            if mode == "explicit_failure":
                send(request, {"structuredContent": {"ok": False, "status": "failed",
                    "code": "invalid_arguments"}, "isError": True})
                continue
            effects += 1
            if mode not in {"lost_mutation", "lost_partial"}:
                send(request, {"structuredContent": {"ok": True,
                                  "status": ("running" if mode == "running_batch" else
                                             "waiting_input" if mode == "chained_modals" else "completed"),
                                  "request_id": arguments["request"]["request_id"], "effects": effects}})
        elif name == "ocs_read":
            operation_reads += 1
            if mode == "unknown_operation":
                send(request, {"structuredContent": {"ok": False, "status": "failed",
                    "code": "unknown_operation"}})
            elif mode == "lost_partial":
                send(request, {"structuredContent": {"ok": False, "status": "failed",
                    "request_id": arguments["parameters"]["request_id"],
                    "completed_commands": 1, "next_command": 1}})
            else:
                send(request, {"structuredContent": {"ok": True,
                    "status": "running" if mode == "running_batch" and operation_reads == 1 else "completed",
                    "request_id": arguments["parameters"]["request_id"], "effects": effects}})
        else:
            send(request, {"structuredContent": {"ok": True}})
    else:
        send(request, {})
    if mode == "stderr_flood":
        sys.stderr.write("x" * 1000 + "\n")
        sys.stderr.flush()
