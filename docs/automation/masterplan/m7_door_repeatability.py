"""Exploratory interleaved prompt repeatability on a previously seen door crop."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import time

from m7_window_repeatability import _events, digest, write_new


ORDER = ("baseline", "candidate") * 3
SOURCE_SHA = "0CD0B310FC337C18704B658B41DF49ABB63E2F398893273BBFCFD503B2134057"
CROP_SHA = "0E153FE5A1B8B923446C2AEC62CEC4713274564EC5759BD91DD8B7E750C73ED2"
PROMPT_SHAS = {
    "baseline": "372044ABBB3EACBA094A79D14B9144337A1D4887A217983EA203AB2CC1C67A24",
    "candidate": "704526C008F4D699D295AD1EFC36CB9044539B814231BFFCBE9F78CCD90D67AD",
}
ORIGIN = (1040, 475)
SCALE = 8
EXPECTED = ((1090, 501), (1090, 550), (1145, 550))
TOLERANCE = 8
POINT_KEYS = ("upper_jamb_px", "lower_hinge_px", "leaf_tip_px")


def hardware_sha() -> str:
    value = json.dumps({"platform": platform.platform(),
                        "machine": platform.machine(),
                        "processor": platform.processor(),
                        "logical_cpus": os.cpu_count()}, sort_keys=True)
    return hashlib.sha256(value.encode()).hexdigest().upper()


def prepare(root: Path, source: Path, crop: Path, baseline: Path,
            candidate: Path, cli: Path) -> dict:
    if digest(source) != SOURCE_SHA or digest(crop) != CROP_SHA:
        raise ValueError("Source or frozen crop differs")
    if (digest(baseline) != PROMPT_SHAS["baseline"] or
            digest(candidate) != PROMPT_SHAS["candidate"]):
        raise ValueError("Historical prompts differ")
    root.mkdir(parents=True, exist_ok=False)
    for incoming, name in ((crop, "crop.png"), (baseline, "baseline.txt"),
                           (candidate, "candidate.txt")):
        shutil.copyfile(incoming, root / name)
    freeze = {"schema_version": "m7-door-repeatability-freeze-1",
              "cohort": "development_seen", "source_sha256": SOURCE_SHA,
              "crop_sha256": CROP_SHA,
              "prompt_sha256": PROMPT_SHAS,
              "runner_sha256": digest(Path(__file__)),
              "cli_sha256": digest(cli), "hardware_sha256": hardware_sha(),
              "requested_model": "gpt-6-luna", "effort": "medium",
              "order": ORDER, "expected_original_px": EXPECTED,
              "tolerance_original_px": TOLERANCE,
              "oracle_provenance": "assistant_visual_before_original_v1_call",
              "candidate_previously_tuned_on_baseline_failure": True,
              "acceptance_m7": False}
    write_new(root / "freeze.json", freeze)
    return freeze


def validate(root: Path, source: Path, cli: Path) -> dict:
    freeze = json.loads((root / "freeze.json").read_text(encoding="utf-8"))
    if (freeze.get("schema_version") != "m7-door-repeatability-freeze-1"
            or digest(source) != SOURCE_SHA
            or digest(root / "crop.png") != CROP_SHA
            or any(digest(root / f"{arm}.txt") != expected
                   for arm, expected in PROMPT_SHAS.items())
            or freeze.get("source_sha256") != SOURCE_SHA
            or freeze.get("crop_sha256") != CROP_SHA
            or freeze.get("prompt_sha256") != PROMPT_SHAS
            or freeze.get("runner_sha256") != digest(Path(__file__))
            or freeze.get("cli_sha256") != digest(cli)
            or freeze.get("hardware_sha256") != hardware_sha()
            or tuple(freeze.get("order", ())) != ORDER
            or freeze.get("requested_model") != "gpt-6-luna"
            or freeze.get("effort") != "medium"
            or freeze.get("expected_original_px") != [list(p) for p in EXPECTED]
            or freeze.get("tolerance_original_px") != TOLERANCE):
        raise ValueError("Frozen door pilot inputs differ")
    return freeze


def run_slot(root: Path, source: Path, cli: Path, index: int) -> dict:
    freeze = validate(root, source, cli)
    if not 0 <= index < len(ORDER):
        raise ValueError("Slot index outside frozen schedule")
    for earlier in range(index):
        if not (root / f"slot-{earlier:02d}" / "result.json").is_file():
            raise ValueError("Earlier slot incomplete; never replay uncertainty")
    slot = root / f"slot-{index:02d}"
    slot.mkdir(exist_ok=False)
    arm = ORDER[index]
    prompt_path = root / f"{arm}.txt"
    intent = {"schema_version": "m7-door-repeatability-intent-1",
              "slot": index, "arm": arm,
              "freeze_sha256": digest(root / "freeze.json"),
              "prompt_sha256": digest(prompt_path),
              "crop_sha256": freeze["crop_sha256"],
              "cli_sha256": freeze["cli_sha256"]}
    write_new(slot / "intent.json", intent)
    command = [str(cli), "exec", "-m", "gpt-6-luna",
               "-c", 'model_reasoning_effort="medium"',
               "-s", "read-only", "--skip-git-repo-check", "--json",
               "--image", str(root / "crop.png"), "-"]
    started = time.monotonic_ns()
    with (slot / "events.jsonl").open("xb") as output, \
            (slot / "stderr.txt").open("xb") as error:
        process = subprocess.Popen(
            command, cwd=Path(__file__).resolve().parents[3],
            stdin=subprocess.PIPE, stdout=output, stderr=error)
        process.communicate(prompt_path.read_bytes())
    result = {"schema_version": "m7-door-repeatability-slot-1",
              "slot": index, "arm": arm, "exit_code": process.returncode,
              "elapsed_seconds": round((time.monotonic_ns() - started) / 1e9, 6),
              "intent_sha256": digest(slot / "intent.json"),
              "events_sha256": digest(slot / "events.jsonl"),
              "stderr_sha256": digest(slot / "stderr.txt")}
    write_new(slot / "result.json", result)
    return result


def assess_observation(observed: dict) -> tuple[str, list[list[float]] | None]:
    points = [observed.get(key) for key in POINT_KEYS]
    shape_ok = (observed.get("schema_version") == "ocs-door-observation-1"
                and observed.get("status") == "observed"
                and all(isinstance(point, list) and len(point) == 2 and
                        all(type(value) is int for value in point)
                        for point in points))
    actual = ([[ORIGIN[0] + point[0] / SCALE,
                ORIGIN[1] + point[1] / SCALE] for point in points]
              if shape_ok else None)
    passed = bool(shape_ok and all(
        abs(point[axis] - expected[axis]) <= TOLERANCE
        for point, expected in zip(actual, EXPECTED) for axis in range(2)))
    status = ("passed_source_oracle" if passed else
              "abstained" if observed.get("status") == "unsupported" else
              "failed_source_oracle")
    return status, actual


def summarize(root: Path, source: Path, cli: Path) -> dict:
    freeze = validate(root, source, cli)
    records = []
    for index, arm in enumerate(ORDER):
        slot = root / f"slot-{index:02d}"
        intent = json.loads((slot / "intent.json").read_text(encoding="utf-8"))
        result = json.loads((slot / "result.json").read_text(encoding="utf-8"))
        if (intent.get("slot") != index or intent.get("arm") != arm
                or intent.get("freeze_sha256") != digest(root / "freeze.json")
                or intent.get("prompt_sha256") != digest(root / f"{arm}.txt")
                or intent.get("crop_sha256") != freeze["crop_sha256"]
                or intent.get("cli_sha256") != freeze["cli_sha256"]
                or result.get("slot") != index or result.get("arm") != arm
                or result.get("intent_sha256") != digest(slot / "intent.json")
                or result.get("events_sha256") != digest(slot / "events.jsonl")
                or result.get("stderr_sha256") != digest(slot / "stderr.txt")
                or result.get("exit_code") != 0
                or not isinstance(result.get("elapsed_seconds"), (int, float))
                or result["elapsed_seconds"] <= 0):
            raise ValueError(f"Slot {index} integrity or completion differs")
        observed, usage = _events(slot / "events.jsonl")
        status, points = assess_observation(observed)
        records.append({"slot": index, "arm": arm, "status": status,
                        "observed_original_px": points,
                        "usage_cli_aggregate": usage,
                        "elapsed_seconds": result["elapsed_seconds"],
                        "events_sha256": result["events_sha256"],
                        "result_sha256": digest(slot / "result.json")})
    arms = {}
    for arm in ("baseline", "candidate"):
        subset = [item for item in records if item["arm"] == arm]
        times = sorted(item["elapsed_seconds"] for item in subset)
        arms[arm] = {
            "passed": sum(item["status"] == "passed_source_oracle" for item in subset),
            "abstained": sum(item["status"] == "abstained" for item in subset),
            "total": len(subset),
            "latency_median_seconds": statistics.median(times),
            "latency_p95_nearest_rank_seconds": times[math.ceil(.95 * len(times)) - 1],
            "input_tokens_sum": sum(item["usage_cli_aggregate"]["input_tokens"]
                                    for item in subset),
            "output_tokens_sum": sum(item["usage_cli_aggregate"]["output_tokens"]
                                     for item in subset),
        }
    return {"schema_version": "m7-door-repeatability-summary-1",
            "cohort": "development_seen", "acceptance_m7": False,
            "requested_model": "gpt-6-luna",
            "effective_model": "unverified_by_cli_jsonl",
            "freeze_sha256": digest(root / "freeze.json"),
            "arms": arms, "records": records,
            "limitations": ["single_seen_crop", "candidate_tuned_on_baseline_failure",
                            "three_repetitions_per_arm", "cli_usage_not_provider_receipt",
                            "no_cad_or_human_review_in_this_pilot"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "run-slot", "summarize"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--crop", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--slot", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root, source, cli = (args.root.resolve(), args.source.resolve(strict=True),
                         args.cli.resolve(strict=True))
    if args.mode == "prepare":
        if not all((args.crop, args.baseline, args.candidate)):
            raise ValueError("Crop and two historical prompts required")
        result = prepare(root, source, args.crop.resolve(strict=True),
                         args.baseline.resolve(strict=True),
                         args.candidate.resolve(strict=True), cli)
    elif args.mode == "run-slot":
        if args.slot is None:
            raise ValueError("Slot index required")
        result = run_slot(root, source, cli, args.slot)
    else:
        result = summarize(root, source, cli)
        if args.output:
            write_new(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
