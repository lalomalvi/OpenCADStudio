"""Protocol smoke test for the native client-neutral MCP endpoint."""
import json
from pathlib import Path
import subprocess
import sys
import queue
import threading

TIMEOUT = 15


TOOLS = {"ocs_sessions", "ocs_read", "ocs_execute", "ocs_capture"}
MODERN = "2026-07-28"


def start(server: Path, *, env=None, cwd=None, command=None) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        command or [str(server), "--mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=cwd,
    )
    assert process.stdin and process.stdout
    process.responses = queue.Queue()
    process.diagnostics = []
    def read_stdout():
        for line in process.stdout:
            process.responses.put(line)
        process.responses.put(None)
    def read_stderr():
        for line in process.stderr:
            process.diagnostics.append(line)
    process.readers = [threading.Thread(target=read_stdout, daemon=True), threading.Thread(target=read_stderr, daemon=True)]
    for reader in process.readers:
        reader.start()
    return process


def request(process: subprocess.Popen[str], payload: dict) -> dict:
    assert process.stdin and process.stdout
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()
    try:
        line = process.responses.get(timeout=TIMEOUT)
        if line is None:
            process.readers[1].join(timeout=0.5)
            raise RuntimeError("MCP exited before responding: " + "".join(process.diagnostics)[-1200:])
        result = json.loads(line)
        assert result.get("jsonrpc") == "2.0" and result.get("id") == payload["id"], result
        return result
    except Exception:
        process.kill()
        process.wait(timeout=5)
        for reader in process.readers:
            reader.join(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
        raise


def close(process: subprocess.Popen[str]) -> None:
    assert process.stdin
    # request() already tears down all streams on timeout/protocol failure.
    if process.stdin.closed and process.stdout.closed and process.stderr.closed:
        return
    process.stdin.close()
    try:
        assert process.wait(timeout=5) == 0
    except Exception:
        process.kill()
        process.wait(timeout=5)
        raise
    finally:
        for reader in process.readers:
            reader.join(timeout=2)
        process.stdout.close()
        process.stderr.close()
    # EOF must be clean: any extra stdout is a protocol violation.
    while True:
        line = process.responses.get(timeout=5)
        if line is None:
            break
        raise AssertionError(f"Unsolicited stdout after final response: {line[:200]}")


def negotiation(server: Path) -> None:
    for version in ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"):
        process = start(server)
        result = request(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"protocolVersion": version, "capabilities": {},
                                             "clientInfo": {"name": "distribution-smoke", "version": "1"}}})
        assert result["result"]["protocolVersion"] == version, result
        close(process)


def legacy(server: Path) -> None:
    process = start(server)

    initialized = request(process, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}},
    })
    assert initialized["result"]["serverInfo"]["name"] == "OpenCADStudio"
    assert "state.command.accepts" in initialized["result"]["instructions"]
    process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    process.stdin.flush()
    tools = request(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    definitions = {tool["name"]: tool for tool in tools["result"]["tools"]}
    names = set(definitions)
    assert names == TOOLS, names
    execute_request = definitions["ocs_execute"]["inputSchema"]["properties"]["request"]
    advertised_ops = execute_request["properties"]["op"]["enum"]
    schema_ops = [branch["properties"]["op"]["const"] for branch in execute_request["oneOf"]]
    assert len(schema_ops) == len(set(schema_ops)), schema_ops
    assert set(schema_ops) == set(advertised_ops), (schema_ops, advertised_ops)
    assert {"run_script", "close_document", "shutdown_owned_session",
            "edit_wall_thickness", "edit_wall_length", "metric_plot_pdf",
            "set_metric_page_setup"} <= set(advertised_ops)
    op_enum = execute_request["properties"]["op"]["enum"]
    for shipped in ("entities_create", "entities_delete", "entities_transform",
                    "block_define", "block_delete", "file_identity", "xdata_set",
                    "view_focus", "wblock", "plot",
                    "entities_copy_to", "group_create", "selection_set_save",
                    "selection_set_load", "close", "sysvar", "layout_create",
                    "page_setup_set"):
        assert shipped in op_enum, shipped
    assert "xdata_get" in definitions["ocs_read"]["inputSchema"]["properties"]["op"]["enum"]
    assert execute_request["properties"]["commands"]["maxItems"] == 256
    assert execute_request["properties"]["steps"]["maxItems"] == 64
    assert execute_request["properties"]["cmd"]["examples"][0] == "LINE 0,0 10,10"
    assert "set_properties" in execute_request["properties"]["op"]["enum"]
    assert "save_verified" in execute_request["properties"]["op"]["enum"]
    assert "record_schema" in definitions["ocs_read"]["inputSchema"]["properties"]["op"]["enum"]
    assert "audit" in definitions["ocs_read"]["inputSchema"]["properties"]["op"]["enum"]
    read_parameters = definitions["ocs_read"]["inputSchema"]["properties"]["parameters"]["properties"]
    assert {"collection", "where", "paths", "target_format", "target_version"} <= set(read_parameters)
    assert execute_request["properties"]["target_version"]["enum"][0] == "R14"
    assert execute_request["properties"]["kind"]["enum"] == [
        "text", "token", "point", "entity", "structure", "selection", "enter"
    ]
    for name in {"ocs_sessions", "ocs_read", "ocs_execute"}:
        assert definitions[name]["outputSchema"]["type"] == "object"
    assert "resultType" not in tools["result"]
    sessions = request(process, {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "ocs_sessions", "arguments": {"launch_if_none": False}},
    })
    assert not sessions["result"].get("isError"), sessions
    close(process)


def modern(server: Path) -> None:
    process = start(server)
    meta = {
        "io.modelcontextprotocol/protocolVersion": MODERN,
        "io.modelcontextprotocol/clientInfo": {"name": "smoke", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    discovered = request(process, {
        "jsonrpc": "2.0",
        "id": "discover",
        "method": "server/discover",
        "params": {"_meta": meta},
    })
    assert discovered["result"]["resultType"] == "complete"
    assert set(discovered["result"]["supportedVersions"]) == {MODERN, "2025-11-25"}
    assert discovered["result"]["ttlMs"] >= 0
    assert discovered["result"]["cacheScope"] in {"public", "private"}
    assert "io.modelcontextprotocol/tasks" in discovered["result"]["capabilities"]["extensions"]

    tools = request(process, {
        "jsonrpc": "2.0",
        "id": "tools",
        "method": "tools/list",
        "params": {"_meta": meta},
    })
    assert {tool["name"] for tool in tools["result"]["tools"]} == TOOLS
    assert tools["result"]["resultType"] == "complete"
    assert tools["result"]["ttlMs"] >= 0
    assert tools["result"]["cacheScope"] in {"public", "private"}
    definitions = {tool["name"]: tool for tool in tools["result"]["tools"]}
    assert definitions["ocs_execute"]["inputSchema"]["properties"]["response_detail"]["default"] == "compact"
    assert definitions["ocs_capture"]["inputSchema"]["properties"]["scope"]["default"] == "viewport"

    missing_cmd = request(process, {
        "jsonrpc": "2.0",
        "id": "missing-cmd",
        "method": "tools/call",
        "params": {
            "name": "ocs_execute",
            "arguments": {
                "ocs_session_id": "missing",
                "request": {"op": "run", "request_id": "run-1"},
            },
            "_meta": meta,
        },
    })
    error = missing_cmd["result"]["structuredContent"]
    assert error["code"] == "invalid_arguments"
    assert "LINE 0,0 10,10" in error["error"]

    invalid_mutation = request(process, {
        "jsonrpc": "2.0",
        "id": "invalid-mutation",
        "method": "tools/call",
        "params": {
            "name": "ocs_execute",
            "arguments": {"ocs_session_id": "missing", "request": {"op": "undo"}},
            "_meta": meta,
        },
    })
    assert invalid_mutation["result"]["isError"] is True
    assert "request_id" in invalid_mutation["result"]["structuredContent"]["error"]

    rejected = request(process, {
        "jsonrpc": "2.0",
        "id": "unsupported",
        "method": "tools/list",
        "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2099-01-01"}},
    })
    assert rejected["error"]["code"] == -32022
    close(process)


def main() -> None:
    server = Path(sys.argv[1] if len(sys.argv) > 1 else "target/debug/OpenCADStudio").resolve()
    negotiation(server)
    legacy(server)
    modern(server)

if __name__ == "__main__":
    main()
