"""L2 synthetic integration: fake model calls, real owned CAD/MCP process."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from luna_pipeline import run_reserved_pipeline
from owned_cad_executor import OwnedCadExecutor
from reserved_runner import verify_envelope
from supervisor_once_adapter import request_supervisor_once
import test_reserved_trial
from test_luna_planspec_gate import wrapped
from test_provider_response_receipt import response

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_client import Client, ProtocolError, UncertainMutation  # noqa: E402


class SyntheticLuna:
    max_retries = 0

    def __init__(self, plan):
        self.responses = self
        self.raw = wrapped(json.dumps(plan))
        self.calls = 0

    def create(self, **_payload):
        self.calls += 1
        return self.raw


class SyntheticSupervisor:
    max_retries = 0

    def __init__(self):
        self.responses = self
        self.calls = 0

    def create(self, **_payload):
        self.calls += 1
        return response("resp-synthetic-supervisor", "gpt-6-sol")


def main():
    repo = Path(__file__).resolve().parents[3]
    binary = Path(sys.argv[1] if len(sys.argv) > 1 else repo / "target/debug/OpenCADStudio.exe").resolve()
    if not binary.is_file():
        raise FileNotFoundError(binary)
    root = repo / "target" / "mcp-reserved-pipeline" / (
        time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True, exist_ok=False)
    journal, _, run, _, _ = test_reserved_trial.ReservedTrialTests().make_journal(str(root))
    journal.arm_binaries = {"baseline": binary, "candidate": binary}
    supervisor_protocol = root / "synthetic-supervisor.txt"
    supervisor_protocol.write_text("Compare synthetic source and CAD capture.\n",
                                   encoding="utf-8")
    journal.supervisor_protocol_path = supervisor_protocol
    journal.supervisor_model = "gpt-6-sol"
    journal.supervisor_effort = "low"
    profile = root / "profile"
    profile.mkdir()
    temporary = root / "temp"
    temporary.mkdir()
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    fixture = Path(__file__).with_name("fixtures") / "synthetic-wall.planspec.json"
    luna = SyntheticLuna(json.loads(fixture.read_text(encoding="utf-8")))
    supervisor = SyntheticSupervisor()
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest().upper()
    report = {"schema_version": "m7-reserved-pipeline-l2-1", "status": "failed",
              "binary_sha256": sha(binary), "fixture_sha256": sha(fixture)}
    gui = subprocess.Popen([str(binary), "--new-instance"], cwd=repo, env=environment,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    client = Client(binary, environment=environment)
    try:
        client.handshake()
        selected = client.ready_session(wait_for_existing=True, timeout=90)
        if selected.get("process_id") != gui.pid:
            raise ProtocolError("Synthetic GUI identity differs from child")
        state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                          "op": "state"})
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": selected["session_id"],
                "request": {"op": "action", "request_id": "pipeline-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                              "op": "state"})
        executor = OwnedCadExecutor(client, gui, binary, run,
                                    capture_viewport=True)
        result = run_reserved_pipeline(
            journal, "baseline", "case-0", 1, "synthetic-pipeline-1",
            luna_client=luna, cad_execute=executor,
            supervisor_request=lambda invocation, evidence: request_supervisor_once(
                journal, invocation, evidence, client=supervisor),
            allowed_versions=frozenset({"planspec-3"}))
        envelope = verify_envelope(result["evidence_path"])
        cad = json.loads((run / envelope["cad_evidence"]["file"]).read_text(encoding="utf-8"))
        if result["disposition"] != "completed" or luna.calls != 1 or \
                supervisor.calls != 1 or cad["audit_ok"] is not True or \
                cad["completed_commands"] != 5 or cad["added_entities"] != 4 or \
                envelope["gates"] != "unevaluated":
            raise ProtocolError("Synthetic reserved pipeline did not complete as expected")
        report.update({"status": "passed", "luna_calls": luna.calls,
                       "supervisor_calls": supervisor.calls,
                       "journal_sha256": journal.snapshot()["journal_sha256"],
                       "envelope_sha256": sha(result["evidence_path"]),
                       "cad_evidence_sha256": sha(run / envelope["cad_evidence"]["file"]),
                       "dwg_sha256": cad["dwg"]["sha256"],
                       "capture_sha256": cad["capture"]["sha256"],
                       "gates": envelope["gates"], "session_pid": gui.pid})
        state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                          "op": "state"})
        if any(doc.get("dirty") for doc in state.get("documents", [])):
            client.tool("ocs_execute", {"ocs_session_id": selected["session_id"],
                "request": {"op": "save", "request_id": "pipeline-clean-save-" + uuid.uuid4().hex,
                            "path": str(root / "cleanup-save.dwg"),
                            "target_format": "dwg", "target_version": "2018"}})
        try:
            client.tool("ocs_execute", {"ocs_session_id": selected["session_id"],
                "request": {"op": "run", "request_id": "pipeline-quit-" + uuid.uuid4().hex,
                            "cmd": "QUIT"}})
        except (ProtocolError, UncertainMutation) as error:
            report["quit_error_type"] = type(error).__name__
        try:
            gui.wait(timeout=10)
            report["shutdown"] = "exited"
        except subprocess.TimeoutExpired:
            report["status"] = "partial"
            report["shutdown"] = "unclosed"
    except Exception as error:
        report["error_type"] = type(error).__name__
        raise
    finally:
        try:
            client.close()
        except ProtocolError:
            report["mcp_close"] = "error"
        if report["status"] in {"failed", "partial"} and gui.poll() is None:
            gui.terminate()  # This synthetic child only.
            try:
                gui.wait(timeout=5)
                report["cleanup"] = "terminated_own_child"
            except subprocess.TimeoutExpired:
                report["cleanup"] = "child_still_running"
        report["gui_exited"] = gui.poll() is not None
        with (root / "report.json").open("x", encoding="utf-8") as target:
            json.dump(report, target, sort_keys=True, indent=2)
            target.write("\n")
        print(json.dumps({"report": str(root / "report.json"), **report}, indent=2))


if __name__ == "__main__":
    main()
