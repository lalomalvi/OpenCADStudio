"""Copy a verified synthetic reserved DWG into the existing AutoCAD probe lane.

Only the versioned synthetic-wall fixture is supported here. The private
reserved cohort is never copied, and this helper refuses paths outside the
worktree's synthetic target tree.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import uuid

from owned_cad_executor import verify_owned_cad_evidence


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def bridge(run_root: Path, *, seed_bad_handle: bool = False) -> Path:
    repo = Path(__file__).resolve().parents[3]
    source_base = (repo / "target/mcp-reserved-pipeline").resolve(strict=True)
    target_base = (repo / "target/mcp-isolated").resolve(strict=True)
    root = run_root.resolve(strict=True)
    if not root.is_relative_to(source_base) or root.parent != source_base or \
            not (root / "run").is_dir():
        raise ValueError("Only a synthetic reserved pipeline run is accepted")
    report_path = root / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    fixture = repo / "docs/automation/masterplan/fixtures/synthetic-wall.planspec.json"
    if report.get("schema_version") != "m7-reserved-pipeline-l2-1" or \
            report.get("status") != "passed" or \
            report.get("fixture_sha256") != sha(fixture):
        raise ValueError("Synthetic pipeline report or fixture differs")
    evidence_files = list((root / "run").glob("cad-*.json"))
    if len(evidence_files) != 1 or sha(evidence_files[0]) != report.get("cad_evidence_sha256"):
        raise ValueError("Synthetic CAD evidence is absent or changed")
    cad = verify_owned_cad_evidence(evidence_files[0])
    handles = cad.get("handles_by_id")
    if not isinstance(handles, dict) or len(handles) != 4 or \
            report.get("dwg_sha256") != cad["dwg"]["sha256"] or \
            report.get("capture_sha256") != cad.get("capture", {}).get("sha256"):
        raise ValueError("Handle map or nested CAD artifacts differ")
    source = evidence_files[0].parent / cad["dwg"]["file"]
    output = target_base / (time.strftime("%Y%m%d-%H%M%S") + "-m7-l4-" +
                            uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    drawing = output / "synthetic-verified.dwg"
    shutil.copyfile(source, drawing)
    if sha(drawing) != cad["dwg"]["sha256"]:
        raise ValueError("L4 synthetic copy differs")
    probe_handles = handles.copy()
    negative_seed = None
    if seed_bad_handle:
        chosen = sorted(probe_handles)[0]
        probe_handles[chosen] = "FFFFFFFF"
        negative_seed = {"kind": "handle_mismatch", "planspec_id": chosen}
    provenance = {"schema_version": "m7-l4-bridge-1", "status": "passed",
                  "source_pipeline_report_sha256": sha(report_path),
                  "source_cad_evidence_sha256": sha(evidence_files[0]),
                  "verified_output": {"sha256": sha(drawing)},
                  "planspec": {"fixture": fixture.name,
                               "fixture_sha256": sha(fixture),
                               "handles_by_id": probe_handles},
                  "negative_seed": negative_seed}
    with (output / "report.json").open("x", encoding="utf-8") as target:
        json.dump(provenance, target, sort_keys=True, indent=2)
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--seed-bad-handle", action="store_true")
    arguments = parser.parse_args()
    print(bridge(arguments.run_root, seed_bad_handle=arguments.seed_bad_handle))
