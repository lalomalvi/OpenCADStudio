"""L2 isolated probe: same mutation ID from two MCP client processes."""

import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / "docs/automation"))
from mcp_client import Client, ProtocolError  # noqa: E402
from mcp_isolated_smoke import read_state  # noqa: E402

server = (repo / "target/debug/OpenCADStudio.exe").resolve()
run = repo / "target/mcp-isolated" / (time.strftime("%Y%m%d-%H%M%S") + "-cross-client-" + uuid.uuid4().hex[:8])
run.mkdir(parents=True, exist_ok=False)
profile = run / "profile"
temp = run / "temp"
profile.mkdir()
temp.mkdir()
env = os.environ.copy()
env.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
            "TEMP": str(temp), "TMP": str(temp)})
gui = subprocess.Popen([str(server), "--new-instance"], cwd=repo, env=env,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
clients = [Client(server, environment=env), Client(server, environment=env)]
report = {"schema_version": "cross-client-mutation-l2-1", "status": "failed",
          "run": str(run), "binary_sha256": hashlib.sha256(server.read_bytes()).hexdigest().upper(),
          "gui_pid": gui.pid}
try:
    for client in clients:
        client.handshake()
    selected = clients[0].ready_session(wait_for_existing=True, timeout=90)
    session = selected["session_id"]
    if selected.get("process_id") != gui.pid or Path(selected["executable_path"]).resolve() != server:
        raise ProtocolError("Selected GUI is not the isolated child")
    second = clients[1].ready_session(session_id=session, wait_for_existing=True,
                                      launch_if_none=False, timeout=10)
    if second.get("process_id") != gui.pid:
        raise ProtocolError("Two clients did not select the same GUI")
    report["session_id"] = session
    state = read_state(clients[0], session)
    for _ in range(6):
        if not state.get("modal"):
            break
        clients[0].tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "action", "request_id": "cross-modal-" + uuid.uuid4().hex,
                        "name": "close_modal"}})
        state = read_state(clients[0], session)
    if state.get("modal"):
        raise ProtocolError("Startup modal remains")
    clients[0].tool("ocs_execute", {"ocs_session_id": session,
        "request": {"op": "new", "request_id": "cross-new-" + uuid.uuid4().hex}})
    state = read_state(clients[0], session)
    request_id = "cross-line-" + uuid.uuid4().hex
    request = {"op": "run", "request_id": request_id, "cmd": "LINE 0,0 10,0",
               "document_id": state["document_id"], "revision": state["revision"]}
    barrier = threading.Barrier(3)

    def invoke(client):
        barrier.wait()
        try:
            value = client.mutate(session, request)
            return {"outcome": "result", "status": value.get("status"),
                    "code": value.get("code"), "request_id": value.get("request_id")}
        except Exception as error:
            return {"outcome": "error", "type": type(error).__name__,
                    "code": getattr(error, "result", {}).get("code")}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(invoke, clients[0])
        two = pool.submit(invoke, clients[1])
        barrier.wait()
        report["calls"] = [one.result(timeout=90), two.result(timeout=90)]
    # Use a fresh reader so a blocked mutation journal in either client cannot
    # be mistaken for the GUI's actual entity census.
    audit = clients[0].tool("ocs_read", {"ocs_session_id": session, "op": "audit",
                                        "parameters": {"target_format": "dwg", "target_version": "2018"}})
    report["audit"] = {"status": audit.get("status"), "summary": audit.get("summary"),
                       "manifest": audit.get("manifest")}
    if audit.get("ok") is not True or audit.get("manifest", {}).get("total") != 1 or \
            audit.get("manifest", {}).get("by_type", {}).get("Line") != 1:
        raise ProtocolError("Concurrent clients produced a missing or duplicate line")
    report["status"] = "passed_no_duplicate"
except Exception as error:
    report["error_type"] = type(error).__name__
    report["error"] = str(error)
    raise
finally:
    if gui.poll() is None:
        gui.kill()
        gui.wait(timeout=10)
    for client in clients:
        try:
            client.close()
        except ProtocolError:
            report.setdefault("mcp_close_errors", 0)
            report["mcp_close_errors"] += 1
    report["gui_exited"] = gui.poll() is not None
    (run / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
