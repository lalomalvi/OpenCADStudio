"""Black-box high-volume drawing check for the MCP reconstruction lane."""

import json
from pathlib import Path
import sys
import time
import uuid

from mcp_client import Client


def plan_commands(origin: int) -> list[str]:
    commands: list[str] = []
    # Twenty adjacent 10 x 8 rooms: 80 explicit wall entities, deliberately
    # above the generic batch limit of 64.
    for room in range(20):
        x = origin + room * 12
        commands.extend(
            [
                f"LINE {x},0 {x + 10},0",
                f"LINE {x + 10},0 {x + 10},8",
                f"LINE {x + 10},8 {x},8",
                f"LINE {x},8 {x},0",
            ]
        )
    commands.extend(f"CIRCLE {origin + room * 12 + 5},4 1" for room in range(20))
    return commands


def main() -> None:
    server = Path(sys.argv[1] if len(sys.argv) > 1 else "target/debug/OpenCADStudio").resolve()
    client = Client(server)
    session = None
    handles: list[str] = []
    started = time.perf_counter()
    try:
        client.handshake()
        selected = client.ready_session(launch_if_none=True)
        session = selected["session_id"]
        while selected.get("modal"):
            client.tool(
                "ocs_execute",
                {
                    "ocs_session_id": session,
                    "request": {
                        "op": "action",
                        "request_id": f"reconstruction-close-{uuid.uuid4().hex}",
                        "name": "close_modal",
                    },
                },
            )
            selected = client.ready_session(session_id=session)
        active = next(d for d in selected["documents"] if d["id"] == selected["document_id"])
        if active.get("start"):
            client.tool(
                "ocs_execute",
                {"ocs_session_id": session, "request": {"op": "new", "request_id": f"reconstruction-new-{uuid.uuid4().hex}"}},
            )

        origin = 2_000_000 + int(time.time()) % 100_000
        commands = plan_commands(origin)
        result = client.tool(
            "ocs_execute",
            {
                "ocs_session_id": session,
                "response_detail": "full",
                "wait_seconds": 60,
                "request": {
                    "op": "run_script",
                    "request_id": f"reconstruction-{origin}",
                    "strict": True,
                    "commands": commands,
                },
            },
        )
        assert result["completed_commands"] == len(commands), result
        assert result["next_command"] is None, result
        handles = sorted({change["handle"] for change in result["changes"]})
        assert result["added_entities"] == len(commands), result
        assert len(handles) == len(commands), (len(handles), len(commands))

        query = client.tool(
            "ocs_read",
            {
                "ocs_session_id": session,
                "op": "query",
                "parameters": {"handles": handles, "detail": "summary", "limit": len(handles)},
            },
        )
        types: dict[str, int] = {}
        for entity in query["entities"]:
            types[entity["type"]] = types.get(entity["type"], 0) + 1
        assert types == {"Circle": 20, "Line": 80}, types

        print(
            json.dumps(
                {
                    "ok": True,
                    "commands": len(commands),
                    "entities": len(handles),
                    "types": types,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                },
                indent=2,
            )
        )
    finally:
        if session and handles:
            try:
                client.tool(
                    "ocs_execute",
                    {
                        "ocs_session_id": session,
                        "request": {
                            "op": "batch",
                            "request_id": f"reconstruction-clean-{uuid.uuid4().hex}",
                            "steps": [
                                {"op": "select", "handles": handles},
                                {"op": "run", "cmd": "ERASE"},
                            ],
                        },
                    },
                )
            except Exception:
                pass
        client.close()


if __name__ == "__main__":
    main()
