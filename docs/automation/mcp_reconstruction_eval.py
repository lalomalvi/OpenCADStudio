"""Black-box high-volume drawing check for the MCP reconstruction lane."""

import json
from pathlib import Path
import subprocess
import sys
import time
import uuid


META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientInfo": {"name": "ocs-reconstruction-eval", "version": "1"},
    "io.modelcontextprotocol/clientCapabilities": {
        "extensions": {"io.modelcontextprotocol/tasks": {}}
    },
}


class Client:
    def __init__(self, server: Path) -> None:
        self.process = subprocess.Popen(
            [str(server), "--mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.serial = 0

    def rpc(self, method: str, params: dict) -> dict:
        assert self.process.stdin and self.process.stdout
        self.serial += 1
        payload = {"jsonrpc": "2.0", "id": self.serial, "method": method, "params": params}
        self.process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        response = json.loads(self.process.stdout.readline())
        if "error" in response:
            raise RuntimeError(response["error"])
        return response["result"]

    def tool(self, name: str, arguments: dict) -> dict:
        result = self.rpc("tools/call", {"name": name, "arguments": arguments, "_meta": META})
        if result.get("resultType") == "task":
            task_id = result["taskId"]
            while True:
                time.sleep(result.get("pollIntervalMs", 250) / 1000)
                task = self.rpc("tasks/get", {"taskId": task_id, "_meta": META})
                if task["status"] in {"failed", "cancelled"}:
                    raise RuntimeError(task)
                if task["status"] == "completed":
                    result = task["result"]
                    break
        structured = result.get("structuredContent")
        if structured is None or structured.get("ok") is False:
            raise RuntimeError(structured or result)
        return structured

    def sessions(self, timeout_seconds: float = 90.0) -> list[dict]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                return self.tool("ocs_sessions", {"launch_if_none": True})["result"]
            except RuntimeError as error:
                if "still starting" not in str(error) or time.monotonic() >= deadline:
                    raise
                time.sleep(0.5)

    def close(self) -> None:
        assert self.process.stdin
        self.process.stdin.close()
        if self.process.wait(timeout=5) != 0:
            raise RuntimeError(self.process.stderr.read() if self.process.stderr else "MCP exited")


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
        sessions = client.sessions()
        session = sessions[0]["session_id"]
        while sessions[0].get("modal"):
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
            sessions = client.tool("ocs_sessions", {"launch_if_none": False})["result"]
        active = next(d for d in sessions[0]["documents"] if d["id"] == sessions[0]["document_id"])
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
