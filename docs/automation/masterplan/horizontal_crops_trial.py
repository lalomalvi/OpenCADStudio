"""Run five frozen single-wall crop outputs on an owned synthetic CAD session."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from PIL import Image

from cli_development_trial import parse_cli_events
from owned_cad_executor import OwnedCadExecutor, verify_owned_cad_evidence
from pixel_horizontal_crops import compile_horizontal_crops
from planspec import dry_run
from reserved_runner import Invocation
from reserved_trial import _file_sha

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_client import Client, ProtocolError, UncertainMutation  # noqa: E402


class HorizontalTrialError(ValueError):
    pass


def _write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as target:
        json.dump(value, target, ensure_ascii=False, sort_keys=True, indent=2)
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())


def validate_bundle(root: Path, image: Path, binary: Path) -> tuple[dict, dict]:
    frozen = json.loads((root / "freeze.json").read_text(encoding="utf-8"))
    base = root.parent / "apartment-interior-walls-derived-v1"
    if frozen.get("schema_version") != "m7-horizontal-bundle-freeze-1" or \
            frozen.get("acceptance_m7") is not False or \
            frozen.get("source_sha256") != _file_sha(image) or \
            frozen.get("base_plan_sha256") != _file_sha(base / "model-plan.json") or \
            frozen.get("base_report_sha256") != _file_sha(base / "report.json") or \
            frozen.get("compiler_sha256") != _file_sha(
                Path(__file__).with_name("pixel_horizontal_crops.py")) or \
            frozen.get("runner_sha256") != _file_sha(Path(__file__)) or \
            frozen.get("cad_binary_sha256") != _file_sha(binary) or \
            not isinstance(frozen.get("case_refs"), list) or \
            len(frozen["case_refs"]) != 5:
        raise HorizontalTrialError("Frozen horizontal bundle differs")
    with Image.open(image) as bitmap:
        width, height = bitmap.size
        observations = []
        usage = []
        for index, ref in enumerate(frozen["case_refs"], 1):
            path = root.parent / f"apartment-horizontal-h{index}-v1"
            if ref.get("case_id") != path.name or \
                    ref.get("freeze_sha256") != _file_sha(path / "freeze.json") or \
                    ref.get("events_sha256") != _file_sha(path / "events.jsonl") or \
                    ref.get("crop_sha256") != _file_sha(path / "crop.png") or \
                    ref.get("prompt_sha256") != _file_sha(path / "prompt.txt"):
                raise HorizontalTrialError(f"Crop h{index} files differ")
            case = json.loads((path / "freeze.json").read_text(encoding="utf-8"))
            if case.get("source_sha256") != frozen["source_sha256"] or \
                    case.get("crop_sha256") != ref["crop_sha256"] or \
                    case.get("prompt_sha256") != ref["prompt_sha256"]:
                raise HorizontalTrialError(f"Crop h{index} source differs")
            box = case["crop_original_xyxy"]
            with Image.open(path / "crop.png") as crop:
                expected = bitmap.crop(tuple(box)).resize(crop.size)
                if crop.size != ((box[2]-box[0])*8, (box[3]-box[1])*8) or \
                        list(crop.convert("RGB").getdata()) != \
                        list(expected.convert("RGB").getdata()):
                    raise HorizontalTrialError(f"Crop h{index} pixels differ from source")
            observed, tokens = parse_cli_events(path / "events.jsonl")
            observations.append((observed, case))
            usage.append(tokens)
        base_plan = json.loads((base / "model-plan.json").read_text(encoding="utf-8"))
        plan = compile_horizontal_crops(observations, base_plan=base_plan,
                                        image_width=width, image_height=height)
    compiled = dry_run(plan)
    if not compiled["executable"] or compiled["unsupported"] or \
            compiled["quality_blockers"] or len(compiled["commands"]) != 21:
        raise HorizontalTrialError("Five horizontal walls do not compile")
    return plan, {"compiled": compiled, "usage_cli_by_crop": usage}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    root, image, binary = (value.resolve(strict=True) for value in
                           (args.run_root, args.image, args.binary))
    plan, result = validate_bundle(root, image, binary)
    compiled = result["compiled"]
    _write_new(root / "model-plan.json", plan)
    report = {"schema_version": "m7-horizontal-bundle-trial-1",
              "status": "failed", "acceptance_m7": False,
              "effective_model": "unverified_by_cli_jsonl",
              "selection": "five_pre_frozen_single_wall_crops",
              "source_sha256": _file_sha(image),
              "freeze_sha256": _file_sha(root / "freeze.json"),
              "plan_sha256": _file_sha(root / "model-plan.json"),
              "binary_sha256": _file_sha(binary),
              "usage_cli_by_crop": result["usage_cli_by_crop"],
              "l3_plan_gate": "passed_scoped", "cad_status": "pending"}
    profile, temporary, cad_root = (root / name for name in
                                    ("profile", "temp", "cad"))
    for path in (profile, temporary, cad_root):
        path.mkdir(exist_ok=False)
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    gui = subprocess.Popen([str(binary), "--new-instance"],
                           cwd=binary.parent.parent.parent, env=environment,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    client = Client(binary, environment=environment)
    try:
        client.handshake()
        selected = client.ready_session(wait_for_existing=True, timeout=90)
        if selected.get("process_id") != gui.pid:
            raise HorizontalTrialError("Owned CAD process identity differs")
        state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                          "op": "state"})
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": selected["session_id"],
                "request": {"op": "action", "request_id": "horizontal-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                              "op": "state"})
        if state.get("modal"):
            raise HorizontalTrialError("Owned CAD modal remained open")
        invocation = Invocation(
            "development", root.name, 1,
            "horizontal-" + hashlib.sha256(str(root).encode()).hexdigest()[:24],
            image, root / "freeze.json", binary, "gpt-6-luna", "medium",
            _file_sha(image), _file_sha(root / "freeze.json"), _file_sha(binary))
        evidence_path = OwnedCadExecutor(client, gui, binary, cad_root,
                                         capture_viewport=True)(invocation, compiled)
        evidence = verify_owned_cad_evidence(evidence_path)
        report.update({"cad_status": "passed_l2_internal",
                       "cad_evidence_sha256": _file_sha(evidence_path),
                       "dwg_sha256": evidence["dwg"]["sha256"],
                       "capture_sha256": evidence["capture"]["sha256"],
                       "added_entities": evidence["added_entities"],
                       "session_pid": gui.pid})
        state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                          "op": "state"})
        if any(doc.get("dirty") for doc in state.get("documents", [])):
            client.tool("ocs_execute", {"ocs_session_id": selected["session_id"],
                "request": {"op": "save", "request_id": "horizontal-clean-" + uuid.uuid4().hex,
                            "path": str(root / "cleanup-save.dwg"),
                            "target_format": "dwg", "target_version": "2018"}})
        try:
            report["quit_result"] = client.tool("ocs_execute", {
                "ocs_session_id": selected["session_id"],
                "request": {"op": "run", "request_id": "horizontal-quit-" + uuid.uuid4().hex,
                            "cmd": "QUIT"}})
        except (ProtocolError, UncertainMutation) as error:
            report["quit_error_type"] = type(error).__name__
        gui.wait(timeout=60)
        report["status"] = "passed_scoped_cli_l3_cad_l2"
        report["shutdown"] = "exited"
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
            gui.terminate()  # this owned child only
            try:
                gui.wait(timeout=5)
                report["cleanup"] = "terminated_owned_child"
            except subprocess.TimeoutExpired:
                report["cleanup"] = "owned_child_still_running"
        report["gui_exited"] = gui.poll() is not None
        _write_new(root / "report.json", report)
        print(json.dumps({"report": str(root / "report.json"), **report}, indent=2))


if __name__ == "__main__":
    main()
