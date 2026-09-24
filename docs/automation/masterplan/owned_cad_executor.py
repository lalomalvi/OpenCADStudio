"""Execute a compiled PlanSpec only in an explicitly launched isolated GUI.

The caller owns the GUI child, persistent MCP client and private run directory.
This executor never discovers or launches a user session. It neither retries a
mutation nor discards an uncertain result; Client reconciles by the same ID.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re

from reserved_runner import Invocation
from reserved_trial import _file_sha


class CadExecutionError(ValueError):
    pass


def verify_owned_cad_evidence(path: Path) -> dict:
    """Rehash the nested DWG before sealing or consuming its JSON evidence."""
    if not isinstance(path, Path) or not path.is_absolute() or not path.is_file():
        raise CadExecutionError("Absolute CAD evidence path is required")
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("schema_version") != \
            "m7-owned-cad-evidence-1" or report.get("status") != "passed_l2_internal" \
            or report.get("audit_ok") is not True:
        raise CadExecutionError("Owned CAD evidence schema is invalid")
    ref = report.get("dwg")
    if not isinstance(ref, dict) or set(ref) != {"file", "sha256", "bytes"} or \
            not isinstance(ref["file"], str) or Path(ref["file"]).name != ref["file"] or \
            not ref["file"].lower().endswith(".dwg") or \
            not isinstance(ref["sha256"], str) or \
            not re.fullmatch(r"[0-9A-F]{64}", ref["sha256"]) or \
            type(ref["bytes"]) is not int or ref["bytes"] <= 0:
        raise CadExecutionError("Owned DWG reference is invalid")
    dwg = (path.parent / ref["file"]).resolve(strict=True)
    if not dwg.is_relative_to(path.parent.resolve(strict=True)) or \
            not dwg.is_file() or dwg.stat().st_size != ref["bytes"] or \
            _file_sha(dwg) != ref["sha256"]:
        raise CadExecutionError("Nested DWG changed after verified save")
    capture = report.get("capture")
    if capture is not None:
        if not isinstance(capture, dict) or set(capture) != {
                "file", "sha256", "bytes", "document_id", "geometry_revision",
                "camera_revision", "render_fence", "overlay_policy"} or \
                not isinstance(capture["file"], str) or \
                Path(capture["file"]).name != capture["file"] or \
                not capture["file"].lower().endswith(".png") or \
                not isinstance(capture["sha256"], str) or \
                not re.fullmatch(r"[0-9A-F]{64}", capture["sha256"]) or \
                type(capture["bytes"]) is not int or capture["bytes"] <= 0 or \
                any(type(capture[key]) is not int or capture[key] < 0 for key in
                    ("document_id", "geometry_revision", "camera_revision")) or \
                capture["document_id"] != report.get("session", {}).get("document_id") or \
                capture["render_fence"] != "shader_encoded_frame" or \
                capture["overlay_policy"] != "drawing_only":
            raise CadExecutionError("Fenced CAD capture reference is invalid")
        png = (path.parent / capture["file"]).resolve(strict=True)
        if not png.is_relative_to(path.parent.resolve(strict=True)) or \
                not png.is_file() or png.stat().st_size != capture["bytes"] or \
                not png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") or \
                _file_sha(png) != capture["sha256"]:
            raise CadExecutionError("Fenced CAD capture changed after render")
    return report


def _request_id(invocation: Invocation, phase: str) -> str:
    return "m7-" + hashlib.sha256(
        (invocation.request_id + ":" + phase).encode("utf-8")
    ).hexdigest()[:48]


class OwnedCadExecutor:
    """L2-ready executor; GUI and MCP client must be prebuilt by the caller."""

    def __init__(self, client, gui, binary: Path, run_root: Path, *,
                 capture_viewport: bool = False, max_dimension: int = 1024):
        if not isinstance(binary, Path) or not binary.is_absolute() or not binary.is_file() or \
                not isinstance(run_root, Path) or not run_root.is_absolute() or \
                not run_root.is_dir() or not isinstance(getattr(gui, "pid", None), int) or \
                gui.pid <= 0 or not isinstance(getattr(gui, "args", None), (list, tuple)) or \
                "--new-instance" not in gui.args or gui.poll() is not None or \
                not callable(getattr(client, "tool", None)) or \
                not callable(getattr(client, "handshake", None)) or \
                type(capture_viewport) is not bool or \
                type(max_dimension) is not int or not 256 <= max_dimension <= 4096 or \
                (capture_viewport and not callable(getattr(client, "capture_artifact", None))):
            raise CadExecutionError("Owned GUI, persistent client or run root is invalid")
        self.client = client
        self.gui = gui
        self.binary = binary.resolve(strict=True)
        self.run_root = run_root.resolve(strict=True)
        self.capture_viewport = capture_viewport
        self.max_dimension = max_dimension

    def __call__(self, invocation: Invocation, compiled: dict) -> Path:
        if not isinstance(invocation, Invocation) or \
                invocation.cad_binary_path.resolve(strict=True) != self.binary or \
                _file_sha(self.binary) != invocation.cad_binary_sha256 or \
                self.gui.poll() is not None or \
                not isinstance(compiled, dict) or compiled.get("executable") is not True or \
                compiled.get("unsupported") or compiled.get("quality_blockers"):
            raise CadExecutionError("Frozen binary, owned process or PlanSpec differs")
        steps = compiled.get("execution_steps")
        entities = compiled.get("commands")
        if not isinstance(steps, list) or not isinstance(entities, list) or \
                not steps or len(entities) > 1000 or len(steps) > 2000 or \
                any(not isinstance(step, dict) or not isinstance(step.get("command"), str)
                    for step in steps):
            raise CadExecutionError("Compiled CAD script is invalid")
        wire = json.dumps(steps, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8")
        if hashlib.sha256(wire).hexdigest() != compiled.get("commands_sha256"):
            raise CadExecutionError("Compiled CAD commands changed after validation")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", invocation.request_id):
            raise CadExecutionError("Trial request ID is invalid")
        output = self.run_root / ("cad-" + hashlib.sha256(
            invocation.request_id.encode("utf-8")).hexdigest()[:32])
        dwg = output.with_suffix(".dwg")
        evidence = output.with_suffix(".json")
        capture_path = output.with_suffix(".png")
        if dwg.exists() or evidence.exists() or capture_path.exists():
            raise CadExecutionError("CAD output already exists; reconcile previous attempt")

        self.client.handshake()
        discovered = self.client.tool("ocs_sessions", {"launch_if_none": False})
        if discovered.get("status") != "ready" or not isinstance(discovered.get("result"), list):
            raise CadExecutionError("Owned GUI is not ready")
        matches = [item for item in discovered["result"]
                   if item.get("process_id") == self.gui.pid and
                   Path(item.get("executable_path", "")).resolve(strict=False) == self.binary]
        if len(matches) != 1 or \
                not isinstance(matches[0].get("process_started_at_unix_ms"), int) or \
                not isinstance(matches[0].get("session_id"), str):
            raise CadExecutionError("Owned GUI identity is ambiguous")
        selected = matches[0]
        session = selected["session_id"]
        state = self.client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        if state.get("modal") or state.get("active_command") or \
                any(doc.get("dirty") for doc in state.get("documents", [])):
            raise CadExecutionError("Owned GUI is not clean before CAD")

        self.client.tool("ocs_execute", {"ocs_session_id": session, "request": {
            "op": "new", "request_id": _request_id(invocation, "new")}})
        state = self.client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        if not isinstance(state.get("document_id"), int):
            raise CadExecutionError("New document identity is missing")
        document_id = state["document_id"]
        script = self.client.tool("ocs_execute", {"ocs_session_id": session, "request": {
            "op": "run_script", "request_id": _request_id(invocation, "script"),
            "strict": True, "commands": [item["command"] for item in steps]}})
        if script.get("completed_commands") != len(steps) or \
                script.get("added_entities") != len(entities):
            raise CadExecutionError("CAD script result differs from PlanSpec")
        audit = self.client.tool("ocs_read", {"ocs_session_id": session,
                                               "op": "audit", "parameters": {
            "target_format": "dwg", "target_version": "2018"}})
        if audit.get("ok") is not True:
            raise CadExecutionError("CAD audit failed")
        saved = self.client.tool("ocs_execute", {"ocs_session_id": session, "request": {
            "op": "save_verified", "request_id": _request_id(invocation, "save"),
            "path": str(dwg), "target_format": "dwg", "target_version": "2018"}})
        verified = saved.get("result", saved)
        if verified.get("verified") is not True or not dwg.is_file():
            raise CadExecutionError("Verified DWG save failed")
        actual_sha = _file_sha(dwg)
        if verified.get("sha256", "").upper() != actual_sha:
            raise CadExecutionError("Saved DWG hash differs from backend")
        report = {"schema_version": "m7-owned-cad-evidence-1", "status": "passed_l2_internal",
                  "session": {"process_id": self.gui.pid,
                              "process_started_at_unix_ms":
                                  selected["process_started_at_unix_ms"],
                              "document_id": document_id},
                  "binary_sha256": invocation.cad_binary_sha256,
                  "commands_sha256": compiled["commands_sha256"],
                  "completed_commands": script["completed_commands"],
                  "added_entities": script["added_entities"],
                  "audit_ok": True,
                  "dwg": {"file": dwg.name, "sha256": actual_sha,
                          "bytes": dwg.stat().st_size}}
        if self.capture_viewport:
            zoom = self.client.tool("ocs_execute", {"ocs_session_id": session, "request": {
                "op": "run", "request_id": _request_id(invocation, "zoom"),
                "cmd": "ZOOM EXTENTS"}})
            if zoom.get("status") != "completed":
                raise CadExecutionError("Owned viewport framing failed")
            state = self.client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
            if state.get("document_id") != document_id or \
                    any(type(state.get(key)) is not int or state[key] < 0 for key in
                        ("geometry_revision", "camera_revision")):
                raise CadExecutionError("Viewport revision identity is missing")
            captured = self.client.capture_artifact(
                session, capture_path, document_id=document_id,
                geometry_revision=state["geometry_revision"],
                camera_revision=state["camera_revision"],
                max_dimension=self.max_dimension)
            report["capture"] = {"file": capture_path.name,
                                 "sha256": _file_sha(capture_path),
                                 "bytes": capture_path.stat().st_size,
                                 "document_id": document_id,
                                 "geometry_revision": state["geometry_revision"],
                                 "camera_revision": state["camera_revision"],
                                 "render_fence": captured.get("render_fence"),
                                 "overlay_policy": captured.get("overlay_policy")}
        with evidence.open("x", encoding="utf-8") as target:
            json.dump(report, target, sort_keys=True, separators=(",", ":"))
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        verify_owned_cad_evidence(evidence)
        return evidence
