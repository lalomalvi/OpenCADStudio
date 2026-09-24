"""Freeze the third development window before invoking the owned CAD session."""

import argparse
import json
from pathlib import Path

from reserved_trial import _file_sha


def prepare(root: Path, image: Path, binary: Path) -> dict:
    if root.exists():
        raise FileExistsError(root)
    parent = root.parent
    base = parent / "apartment-integrated-two-windows-v1"
    observed = parent / "apartment-south-window-v1"
    code = Path(__file__).parent
    freeze = {
        "schema_version": "m7-apartment-three-window-trial-freeze-1",
        "source_sha256": _file_sha(image),
        "base_plan_sha256": _file_sha(base / "model-plan.json"),
        "base_report_sha256": _file_sha(base / "report.json"),
        "observation_freeze_sha256": _file_sha(observed / "freeze.json"),
        "observation_events_sha256": _file_sha(observed / "events.jsonl"),
        "observation_verdict_sha256": _file_sha(observed / "verdict.json"),
        "compiler_sha256": _file_sha(code / "apartment_south_window_compiler.py"),
        "runner_sha256": _file_sha(code / "apartment_three_window_trial.py"),
        "planspec_sha256": _file_sha(code / "planspec.py"),
        "schema_sha256": _file_sha(code / "planspec-v11.schema.json"),
        "observation_gate_sha256": _file_sha(code / "south_window_observation.py"),
        "cad_binary_sha256": _file_sha(binary),
        "cad_permitted": True,
        "cohort": "development_seen",
        "acceptance_m7": False,
    }
    root.mkdir(parents=True)
    (root / "freeze.json").write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    return freeze


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.run_root.resolve(), args.image.resolve(strict=True),
                             args.binary.resolve(strict=True)), indent=2))
