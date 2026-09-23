"""Synthetic MCP stdio peer. Never starts CAD or reads user drawings."""

import json
import os
import sys

mode = os.environ.get("OCS_FIXTURE_MODE", "normal")
launches = 0
session_calls = 0
effects = 0
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
    if mode == "out_of_order" and method == "ping":
        if held is None:
            held = request
            continue
        send(request, {"name": "second"})
        send(held, {"name": "first"})
        held = None
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
            if mode == "starting" and session_calls == 1:
                send(request, {"structuredContent": {"ok": False,
                    "error": "OpenCADStudio is still starting; call ocs_sessions again"}})
            else:
                sessions = [{"session_id": "s1", "document_id": 1, "documents": [{"id": 1}]}]
                if mode == "ambiguous":
                    sessions.append({"session_id": "s2"})
                send(request, {"structuredContent": {"ok": True, "result": sessions,
                                                      "launches": launches}})
        elif name == "ocs_execute":
            if mode == "explicit_failure":
                send(request, {"structuredContent": {"ok": False, "status": "failed",
                    "code": "invalid_arguments"}, "isError": True})
                continue
            effects += 1
            if mode != "lost_mutation":
                send(request, {"structuredContent": {"ok": True, "status": "completed",
                                  "request_id": arguments["request"]["request_id"], "effects": effects}})
        elif name == "ocs_read":
            if mode == "unknown_operation":
                send(request, {"structuredContent": {"ok": False, "status": "failed",
                    "code": "unknown_operation"}})
            else:
                send(request, {"structuredContent": {"ok": True, "status": "completed",
                    "request_id": arguments["parameters"]["request_id"], "effects": effects}})
        else:
            send(request, {"structuredContent": {"ok": True}})
    else:
        send(request, {})
    if mode == "stderr_flood":
        sys.stderr.write("x" * 1000 + "\n")
        sys.stderr.flush()
