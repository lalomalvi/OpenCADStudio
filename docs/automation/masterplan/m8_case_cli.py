"""Prepare, execute and verify one deterministic PlanSpec case in an owned GUI."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from owned_cad_executor import OwnedCadExecutor, verify_owned_cad_evidence
from planspec import dry_run
from reserved_runner import Invocation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_client import Client, ProtocolError, UncertainMutation  # noqa: E402


class ReleaseCaseError(ValueError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def allowed_root(root: Path) -> Path:
    repo = Path(__file__).resolve().parents[3]
    allowed = (repo / "target/mcp-release").resolve()
    candidate = root.resolve()
    if candidate == allowed or not candidate.is_relative_to(allowed):
        raise ReleaseCaseError("Run root must be a child of worktree target/mcp-release")
    return candidate


def compile_plan(plan_path: Path) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    compiled = dry_run(plan, capabilities={"layer_assignment"})
    if not compiled["executable"] or compiled["unsupported"] or \
            compiled["quality_blockers"] or not compiled["commands"]:
        raise ReleaseCaseError("PlanSpec is not executable without blockers")
    return compiled


def expected_contract(plan_path: Path, binary: Path, compiled: dict) -> dict:
    code = Path(__file__).parent
    return {
        "schema_version": "m8-deterministic-case-contract-1",
        "plan_sha256": digest(plan_path),
        "binary_sha256": digest(binary),
        "commands_sha256": compiled["commands_sha256"],
        "entity_count": len(compiled["commands"]),
        "planspec_code_sha256": digest(code / "planspec.py"),
        "executor_code_sha256": digest(code / "owned_cad_executor.py"),
        "cli_code_sha256": digest(Path(__file__)),
        "model_call": False,
        "target_format": "dwg",
        "target_version": "2018",
        "capture_viewport": True,
        "scope": "synthetic_or_authorized_input_only",
    }


def prepare(root: Path, plan_path: Path, binary: Path) -> dict:
    root = allowed_root(root)
    if root.exists():
        raise FileExistsError(root)
    compiled = compile_plan(plan_path)
    contract = expected_contract(plan_path, binary, compiled)
    root.mkdir(parents=True)
    write_new(root / "contract.json", contract)
    return {"run_root": str(root), "contract_sha256": digest(root / "contract.json"),
            "commands_sha256": contract["commands_sha256"],
            "entity_count": contract["entity_count"]}


def validate(root: Path, plan_path: Path, binary: Path) -> tuple[dict, dict]:
    root = allowed_root(root)
    if not root.is_dir():
        raise ReleaseCaseError("Prepared run root is absent")
    contract = json.loads((root / "contract.json").read_text(encoding="utf-8"))
    compiled = compile_plan(plan_path)
    if contract != expected_contract(plan_path, binary, compiled):
        raise ReleaseCaseError("Frozen contract differs from plan, code or binary")
    return contract, compiled


def run(root: Path, plan_path: Path, binary: Path) -> dict:
    root = allowed_root(root)
    contract, compiled = validate(root, plan_path, binary)
    if (root / "report.json").exists() or (root / "profile").exists() or \
            (root / "cad").exists():
        raise ReleaseCaseError("Run already started; verify or reconcile, never replay")
    profile, temporary, cad_root = (root / name for name in ("profile", "temp", "cad"))
    for path in (profile, temporary, cad_root):
        path.mkdir(exist_ok=False)
    marker = root / "synthetic-source.marker"
    marker.write_text("Deterministic PlanSpec case; no model request.\n", encoding="utf-8")
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    gui = subprocess.Popen([str(binary), "--new-instance"],
                           cwd=Path(__file__).resolve().parents[3], env=environment,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    client = Client(binary, environment=environment)
    report = {"schema_version": "m8-deterministic-case-report-1", "status": "failed",
              "contract_sha256": digest(root / "contract.json"),
              "plan_sha256": digest(plan_path), "binary_sha256": digest(binary),
              "model_call": False, "cad_status": "pending"}
    try:
        client.handshake()
        selected = client.ready_session(wait_for_existing=True, timeout=90)
        if selected.get("process_id") != gui.pid or \
                Path(selected.get("executable_path", "")).resolve() != binary:
            raise ReleaseCaseError("Owned GUI identity differs")
        session = selected["session_id"]
        state = client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "action", "request_id": "m8-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        if state.get("modal") or state.get("active_command") or \
                any(doc.get("dirty") for doc in state.get("documents", [])):
            raise ReleaseCaseError("Owned GUI is not clean")
        invocation = Invocation(
            "development", root.name, 1,
            "m8-case-" + hashlib.sha256(str(root).encode()).hexdigest()[:24],
            marker, root / "contract.json", binary, "none", "none",
            digest(marker), digest(root / "contract.json"), contract["binary_sha256"])
        evidence_path = OwnedCadExecutor(client, gui, binary, cad_root,
                                         capture_viewport=True)(invocation, compiled)
        evidence = verify_owned_cad_evidence(evidence_path)
        report.update({"cad_status": "passed_l2_internal",
                       "evidence_sha256": digest(evidence_path),
                       "evidence_file": evidence_path.name,
                       "dwg_sha256": evidence["dwg"]["sha256"],
                       "capture_sha256": evidence["capture"]["sha256"],
                       "added_entities": evidence["added_entities"],
                       "session_pid": gui.pid})
        state = client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        if any(doc.get("dirty") for doc in state.get("documents", [])):
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "save", "request_id": "m8-clean-" + uuid.uuid4().hex,
                            "path": str(root / "cleanup-save.dwg"),
                            "target_format": "dwg", "target_version": "2018"}})
        try:
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run", "request_id": "m8-quit-" + uuid.uuid4().hex,
                            "cmd": "QUIT"}})
        except (ProtocolError, UncertainMutation):
            pass
        gui.wait(timeout=60)
        report.update({"status": "passed_scoped_l2", "shutdown": "exited"})
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["error_message"] = str(error)[:300]
        raise
    finally:
        try:
            client.close()
        except ProtocolError:
            report["mcp_close"] = "error"
        if gui.poll() is None:
            gui.terminate()
            try:
                gui.wait(timeout=5)
                report["cleanup"] = "terminated_owned_child"
            except subprocess.TimeoutExpired:
                report["cleanup"] = "owned_child_still_running"
        report["gui_exited"] = gui.poll() is not None
        write_new(root / "report.json", report)
    return report


def verify(root: Path, plan_path: Path, binary: Path) -> dict:
    root = allowed_root(root)
    contract, compiled = validate(root, plan_path, binary)
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    files = list((root / "cad").glob("*.json"))
    if len(files) != 1:
        raise ReleaseCaseError("Owned CAD evidence count differs")
    evidence = verify_owned_cad_evidence(files[0])
    if (report.get("status") != "passed_scoped_l2" or
            report.get("gui_exited") is not True or
            report.get("contract_sha256") != digest(root / "contract.json") or
            report.get("plan_sha256") != contract["plan_sha256"] or
            report.get("binary_sha256") != contract["binary_sha256"] or
            report.get("evidence_sha256") != digest(files[0]) or
            report.get("dwg_sha256") != evidence["dwg"]["sha256"] or
            report.get("capture_sha256") != evidence["capture"]["sha256"] or
            evidence.get("commands_sha256") != compiled["commands_sha256"] or
            evidence.get("added_entities") != contract["entity_count"]):
        raise ReleaseCaseError("Release case evidence differs")
    return {"schema_version": "m8-deterministic-case-verify-1",
            "status": "passed_scoped_l2", "model_call": False,
            "contract_sha256": digest(root / "contract.json"),
            "report_sha256": digest(root / "report.json"),
            "dwg_sha256": evidence["dwg"]["sha256"],
            "capture_sha256": evidence["capture"]["sha256"],
            "entity_count": contract["entity_count"],
            "external_l4": "pending"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "run", "verify"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_root.resolve()
    plan = args.plan.resolve(strict=True)
    binary = args.binary.resolve(strict=True)
    result = {"prepare": prepare, "run": run, "verify": verify}[args.mode](
        root, plan, binary)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
