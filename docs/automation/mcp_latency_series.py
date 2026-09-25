"""Measure repeated synthetic L2 runs against one pinned OCS binary.

Each run keeps its own isolated profile, DWG, PNG, and report. The aggregate
contains measurements and references only; it does not copy artifacts.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import uuid


REPO = Path(__file__).resolve().parents[2]
METRICS = {
    "client_script_rpc_ms": ("client_timings_ms", "planspec_script_rpc"),
    "client_save_rpc_ms": ("client_timings_ms", "save_verified_rpc"),
    "client_capture_rpc_and_artifact_ms": ("client_timings_ms", "capture_rpc_and_artifact"),
    "gui_commands_sum_ms": ("command_timings_ms", "sum"),
    "gui_save_total_ms": ("verified_output", "engine_timings_ms", "total_ms"),
    "gui_capture_total_ms": ("capture_engine_timings_ms", "total_ms"),
    "gui_capture_frame_wait_ms": ("capture_engine_timings_ms", "wait_for_encoded_frame_ms"),
    "gui_capture_png_encode_write_ms": ("capture_engine_timings_ms", "encode_and_write_png_ms"),
}


def percentile_nearest_rank(values: list[float], fraction: float) -> float:
    if not values or not 0 < fraction <= 1:
        raise ValueError("Percentile requires samples and a fraction in (0, 1]")
    return sorted(values)[math.ceil(len(values) * fraction) - 1]


def extract_metrics(report: dict) -> dict[str, float]:
    result = {}
    for name, path in METRICS.items():
        value = report
        for key in path:
            value = value[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or \
                not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid metric: {name}")
        result[name] = float(value)
    return result


def check_run(report: dict, binary_sha: str, identity: tuple | None) -> tuple:
    if report["status"] != "passed" or report["gui_exited"] is not True or \
            report["binary_sha256"].upper() != binary_sha:
        raise ValueError("L2 run did not pass with the pinned binary and clean GUI exit")
    if report["command_timings_ms"]["scope"] != "gui_operation_elapsed" or \
            report["verified_output"]["engine_timings_ms"]["scope"] != "gui_process_monotonic" or \
            report["capture_engine_timings_ms"]["scope"] != "gui_process_monotonic":
        raise ValueError("L2 phase clock scope changed")
    if report["audit_ok"] is not True or report["planspec"]["fixture"] != "synthetic-room.planspec.json":
        raise ValueError("L2 audit or fixture changed")
    current = (report["planspec"]["fixture_sha256"],
               report["planspec"]["commands_sha256"])
    if identity is not None and current != identity:
        raise ValueError("Fixture or compiled commands changed during series")
    extract_metrics(report)
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--binary", type=Path, default=REPO / "target/debug/OpenCADStudio.exe")
    args = parser.parse_args()
    if not 2 <= args.runs <= 20:
        parser.error("--runs must be between 2 and 20")
    binary = args.binary.resolve()
    if not binary.is_file():
        parser.error(f"Missing binary: {binary}")
    binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest().upper()
    output = REPO / "target/mcp-latency-series" / \
        (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    aggregate = {"schema_version": "mcp-l2-latency-series-1", "status": "failed",
                 "scope": "synthetic-room_l2_one_machine_one_binary_sequential",
                 "percentile_method": "nearest_rank", "requested_runs": args.runs,
                 "binary_sha256": binary_sha, "runs": []}
    identity = None
    try:
        for index in range(args.runs):
            started = time.monotonic_ns()
            completed = subprocess.run([sys.executable,
                                        str(REPO / "docs/automation/mcp_isolated_smoke.py"),
                                        str(binary)], cwd=REPO, capture_output=True, text=True)
            wall_ms = round((time.monotonic_ns() - started) / 1_000_000, 3)
            report = json.loads(completed.stdout)
            if completed.returncode != 0:
                aggregate["failed_report"] = str((Path(report["output"]) / "report.json").relative_to(REPO))
                raise RuntimeError(f"L2 smoke failed in run {index + 1}")
            identity = check_run(report, binary_sha, identity)
            report_path = Path(report["output"]) / "report.json"
            if not report_path.is_file():
                raise ValueError("L2 report is missing")
            aggregate["runs"].append({
                "index": index + 1, "report": str(report_path.relative_to(REPO)),
                "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest().upper(),
                "dwg_sha256": report["verified_output"]["sha256"],
                "png_sha256": report["capture_artifact"]["sha256"],
                "wall_ms": wall_ms, "metrics_ms": extract_metrics(report)})
            print(f"L2 {index + 1}/{args.runs}: passed, {wall_ms:.0f} ms", flush=True)
        aggregate["fixture_sha256"], aggregate["commands_sha256"] = identity
        aggregate["measurements_ms"] = {
            name: {"n": len(aggregate["runs"]),
                   "min": min(values), "p50": percentile_nearest_rank(values, 0.50),
                   "p95": percentile_nearest_rank(values, 0.95), "max": max(values)}
            for name in ("wall_ms", *METRICS)
            for values in [[float(run["wall_ms"] if name == "wall_ms" else
                            run["metrics_ms"][name]) for run in aggregate["runs"]]]}
        aggregate["distinct_dwg_hashes"] = len({run["dwg_sha256"] for run in aggregate["runs"]})
        aggregate["status"] = "passed"
    except Exception as error:
        aggregate["error_type"] = type(error).__name__
        aggregate["completed_runs"] = len(aggregate["runs"])
        raise
    finally:
        (output / "series.json").write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")
        print(f"Aggregate: {output / 'series.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
