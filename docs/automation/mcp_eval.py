"""Repeatable black-box speed and capability check for the native MCP server."""

import json
from pathlib import Path
import sys
import time
import uuid

from mcp_client import Client


def main() -> None:
    server = Path(sys.argv[1] if len(sys.argv) > 1 else "target/debug/OpenCADStudio").resolve()
    client = Client(server)
    started = time.perf_counter()
    handles: list[str] = []
    session: str | None = None
    base = 0
    succeeded = False
    try:
        discovery = client.handshake()
        assert "io.modelcontextprotocol/tasks" in discovery["capabilities"]["extensions"]
        selected = client.ready_session(launch_if_none=True)
        session = selected["session_id"]
        while selected.get("modal"):
            client.tool(
                "ocs_execute",
                {
                    "ocs_session_id": session,
                    "request": {
                        "op": "action",
                        "request_id": f"eval-close-modal-{uuid.uuid4().hex}",
                        "name": "close_modal",
                    },
                },
            )
            selected = client.ready_session(session_id=session)
        active = next(
            document for document in selected["documents"]
            if document["id"] == selected["document_id"]
        )
        if active.get("start"):
            client.tool(
                "ocs_execute",
                {"ocs_session_id": session, "request": {"op": "new", "request_id": f"eval-new-{uuid.uuid4().hex}"}},
            )

        base = 1_000_000 + int(time.time()) % 100_000
        draw = client.tool(
            "ocs_execute",
            {
                "ocs_session_id": session,
                "response_detail": "changed_entities",
                "wait_seconds": 0,
                "request": {
                    "op": "batch",
                    "request_id": f"eval-draw-{base}",
                    "steps": [
                        {"op": "run", "cmd": f"LINE {base-5},0 {base+5},0"},
                        {"op": "run", "cmd": f"LINE {base},-5 {base},5"},
                        {"op": "run", "cmd": f"CIRCLE {base+20},0 2"},
                    ],
                },
            },
        )
        assert draw["completed_steps"] == 3, draw
        assert client.tasks > 0, "wait_seconds=0 did not exercise MCP Tasks"
        changed = draw["changed_entities"]
        line_handles = [entity["handle"] for entity in changed if entity["type"] == "Line"]
        circle_handles = [entity["handle"] for entity in changed if entity["type"] == "Circle"]
        assert len(line_handles) == 2 and len(circle_handles) == 1, changed
        handles = line_handles + circle_handles

        crossings = client.tool(
            "ocs_read",
            {"ocs_session_id": session, "op": "query", "parameters": {"intersections": line_handles}},
        )
        assert crossings["count"] == 1 and crossings["intersections"][0]["point"] == [base, 0.0]

        nearest = client.tool(
            "ocs_read",
            {"ocs_session_id": session, "op": "query", "parameters": {"near": [base + 20, 0], "handles": handles, "limit": 1}},
        )
        assert nearest["entities"][0]["handle"] == circle_handles[0]

        measured = client.tool(
            "ocs_read",
            {"ocs_session_id": session, "op": "measure", "parameters": {"handles": circle_handles}},
        )
        assert abs(measured["measurements"][0]["curve"]["area"] - 12.566370614359172) < 1e-9
        succeeded = True
    finally:
        if handles and session:
            try:
                client.tool(
                    "ocs_execute",
                    {
                        "ocs_session_id": session,
                        "request": {
                            "op": "batch",
                            "request_id": f"eval-clean-{base}",
                            "steps": [
                                {"op": "select", "handles": handles},
                                {"op": "run", "cmd": "ERASE"},
                            ],
                        },
                    },
                )
            except Exception:
                pass
        elapsed = (time.perf_counter() - started) * 1000
        metrics = {
            "ok": succeeded,
            "elapsed_ms": round(elapsed, 1),
            "tool_calls": client.tool_calls,
            "tasks": client.tasks,
            "rpc_calls": client.rpc_calls,
            "request_bytes": client.request_bytes,
            "response_bytes": client.response_bytes,
        }
        client.close()
        print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
