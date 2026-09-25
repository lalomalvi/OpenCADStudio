"""Synthetic L2 MCP/PDF proof of one A4 landscape 1:100 metre plot."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from PIL import Image
from pypdf import PdfReader

from mcp_client import Client, ProtocolError, ToolError, UncertainMutation
from mcp_face_dimension_smoke import request, save_verified
from mcp_isolated_smoke import read_state


def main():
    repo = Path(__file__).resolve().parents[2]
    server = Path(sys.argv[1] if len(sys.argv) > 1 else repo / "target/debug/OpenCADStudio.exe").resolve()
    page_setup = len(sys.argv) > 2 and sys.argv[2] == "--page-setup"
    if len(sys.argv) > 2 and not page_setup:
        raise ValueError("Only --page-setup is supported")
    if not server.is_file():
        raise FileNotFoundError(server)
    output = repo / "target/mcp-isolated" / (time.strftime("%Y%m%d-%H%M%S") +
                                               "-metric-plot-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    profile, temporary = output / "profile", output / "temp"
    profile.mkdir(); temporary.mkdir()
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    report = {"schema_version": "mcp-metric-page-setup-l2-1" if page_setup else
              "mcp-metric-plot-l2-1", "status": "failed",
              "binary_sha256": hashlib.sha256(server.read_bytes()).hexdigest().upper(),
              "output": str(output), "fixture_commands": ["SETVAR INSUNITS 6",
                  "LINE 0,0 4,0", "LINE 4,0 4,1"]}
    gui = subprocess.Popen([str(server), "--new-instance"], cwd=repo, env=environment,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    client = Client(server, environment=environment)
    try:
        client.handshake()
        selected = client.ready_session(wait_for_existing=True, timeout=90)
        session = selected["session_id"]
        if selected.get("process_id") != gui.pid or Path(selected["executable_path"]).resolve() != server:
            raise ProtocolError("Isolated GUI identity differs")
        report["session"] = {"id": session, "pid": gui.pid}
        state = read_state(client, session)
        for _ in range(6):
            if not state.get("modal"):
                break
            request(client, session, "action", name="close_modal")
            state = read_state(client, session)
        if state.get("modal"):
            raise ProtocolError("Startup modal remains")
        request(client, session, "new")
        created = request(client, session, "run_script", strict=True,
                          commands=report["fixture_commands"])
        report["creation"] = created
        if created.get("completed_commands") != 3:
            raise ProtocolError("Synthetic drawing was not completed")
        lines = [change["handle"] for change in created.get("changes", [])
                 if change.get("kind") == "Added"]
        if len(lines) != 2:
            raise ProtocolError("Synthetic drawing did not create two LINEs")
        report["line_handles"] = lines
        report["line_entities"] = [client.tool("ocs_read", {"ocs_session_id": session,
            "op": "query", "parameters": {"handle": handle, "detail": "full"}})["entities"][0]
            for handle in lines]
        if page_setup:
            configured = request(client, session, "set_metric_page_setup", scale_denominator=100)
            if configured.get("status") != "completed":
                raise ProtocolError("Metric Model page setup did not complete")
            before_setup = client.tool("ocs_read", {"ocs_session_id": session,
                "op": "metric_page_setup"})
            saved = save_verified(client, session, output / "metric-model-setup.dwg")
            request(client, session, "open", path=saved["path"])
            after_setup = client.tool("ocs_read", {"ocs_session_id": session,
                "op": "metric_page_setup"})
            for field in ("paper_size", "paper_mm", "printer", "paper_units", "rotation",
                          "plot_type", "scale_numerator", "scale_denominator", "scale_factor",
                          "use_standard_scale", "plot_centered", "print_lineweights",
                          "margins_mm", "metric_scale_denominator", "insertion_units"):
                if before_setup.get(field) != after_setup.get(field):
                    raise ProtocolError(f"DWG reopen changed page setup {field}")
            if after_setup["metric_scale_denominator"] != 100 or \
                    after_setup["scale_numerator"] != 10:
                raise ProtocolError("Reopened Model page setup has wrong metric scale")
            report["page_setup_before"] = before_setup
            report["page_setup_after"] = after_setup
            report["verified_dwg"] = saved
        state = read_state(client, session)
        pdf = output / "metric-a4-1-100.pdf"
        operation_id = "metric-plot-" + uuid.uuid4().hex
        payload = {"op": "metric_plot_pdf", "request_id": operation_id,
                   "document_id": state["document_id"], "revision": state["revision"],
                   "path": str(pdf), "scale_denominator": 100,
                   **({"require_page_setup": True} if page_setup else {})}
        first = client.tool("ocs_execute", {"ocs_session_id": session, "request": payload})
        if first.get("status") != "completed" or not pdf.is_file():
            raise ProtocolError("Metric PDF plot did not complete")
        reconciled = client.tool("ocs_read", {"ocs_session_id": session, "op": "operation",
            "parameters": {"request_id": operation_id}})
        if reconciled.get("status") != "completed":
            raise ProtocolError("Committed plot was not recoverable")
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest().upper()
        if first.get("result", {}).get("sha256") != digest:
            raise ProtocolError("PDF digest differs from MCP result")
        revision_after = read_state(client, session)["revision"]
        replay = client.tool("ocs_execute", {"ocs_session_id": session, "request": payload})
        if replay != first or read_state(client, session)["revision"] != revision_after or \
                hashlib.sha256(pdf.read_bytes()).hexdigest().upper() != digest:
            raise ProtocolError("Repeated request rewrote or changed the plot")
        try:
            client.tool("ocs_execute", {"ocs_session_id": session, "request":
                {**payload, "request_id": "duplicate-path-" + uuid.uuid4().hex}})
        except ToolError as error:
            if "destination_exists" not in str(error):
                raise
        else:
            raise ProtocolError("Fresh request overwrote existing PDF")
        if page_setup:
            try:
                client.tool("ocs_execute", {"ocs_session_id": session, "request":
                    {**payload, "request_id": "wrong-scale-" + uuid.uuid4().hex,
                     "path": str(output / "wrong-scale.pdf"), "scale_denominator": 50}})
            except ToolError as error:
                if "page_setup_mismatch" not in str(error):
                    raise
            else:
                raise ProtocolError("PDF accepted a scale different from stored DWG setup")
        reader = PdfReader(str(pdf))
        if len(reader.pages) != 1:
            raise ProtocolError("Metric plot has wrong page count")
        box = reader.pages[0].mediabox
        width_mm = float(box.width) * 25.4 / 72
        height_mm = float(box.height) * 25.4 / 72
        if abs(width_mm - 297) > 0.2 or abs(height_mm - 210) > 0.2:
            raise ProtocolError("PDF MediaBox is not A4 landscape")
        render_prefix = output / "metric-render"
        subprocess.run(["pdftoppm", "-f", "1", "-singlefile", "-png", "-r", "100",
                        str(pdf), str(render_prefix)], check=True, stdout=subprocess.DEVNULL)
        image = Image.open(render_prefix.with_suffix(".png")).convert("RGB")
        ink = [(x, y) for y in range(image.height) for x in range(image.width)
               if max(image.getpixel((x, y))) < 120]
        if not ink:
            raise ProtocolError("Rendered PDF has no synthetic linework")
        x0, x1 = min(x for x, _ in ink), max(x for x, _ in ink)
        y0, y1 = min(y for _, y in ink), max(y for _, y in ink)
        actual_width = x1 - x0
        actual_height = y1 - y0
        expected_width = 40 * 100 / 25.4
        expected_height = 10 * 100 / 25.4
        if abs(actual_width - expected_width) > 3 or \
                abs(actual_height - expected_height) > 3:
            raise ProtocolError("Rendered linework is not at 1:100 scale")
        report.update({"status": "passed", "pdf_sha256": digest,
                       "pdf_bytes": pdf.stat().st_size,
                       "page_mm": [width_mm, height_mm],
                       "raster_100dpi": {"size_px": [image.width, image.height],
                                         "ink_bbox_px": [x0, y0, x1, y1],
                                         "ink_size_px": [actual_width, actual_height]},
                       "recovered": True, "replay_without_rewrite": True,
                       "duplicate_path_rejected": True, "mcp_result": first["result"]})
        for _ in range(3):
            if gui.poll() is not None:
                break
            try:
                request(client, session, "run", cmd="QUIT")
            except (ProtocolError, ToolError, UncertainMutation):
                break
            try:
                gui.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["error"] = str(error)
        raise
    finally:
        client.close()
        if gui.poll() is None:
            gui.terminate()
            try:
                gui.wait(timeout=5)
            except subprocess.TimeoutExpired:
                gui.kill(); gui.wait(timeout=5)
        report["gui_exited"] = gui.poll() is not None
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
