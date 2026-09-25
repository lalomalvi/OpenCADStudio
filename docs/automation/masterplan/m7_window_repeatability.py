"""Interleaved, one-call-per-slot Codex CLI pilot on a seen window crop."""

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

from west_window_observation import PROMPT as CANDIDATE_PROMPT


ORDER = ("baseline", "candidate") * 3
CROP_ORIGIN = (360, 535)
SCALE = 8
EXPECTED = ((393, 564), (393, 654))
TOLERANCE = 5
BASELINE_PROMPT = (
    "En esta planta hay una ventana vertical. Identifica sus remates superior e "
    "inferior en el recorte de 560x1200 píxeles. Responde SOLO JSON estricto "
    "con schema_version='ocs-window-endpoints-1', status='observed', top_px, "
    "bottom_px y confidence. Usa coordenadas enteras [x,y]. Si no puedes "
    "identificar ambos remates, responde status='unsupported' sin coordenadas. "
    "No uses herramientas."
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def hardware_sha() -> str:
    value = json.dumps({"platform": platform.platform(),
                        "machine": platform.machine(),
                        "processor": platform.processor(),
                        "logical_cpus": os.cpu_count()}, sort_keys=True)
    return hashlib.sha256(value.encode()).hexdigest().upper()


def prepare(root: Path, source: Path, crop: Path, cli: Path) -> dict:
    if root.exists():
        raise FileExistsError(root)
    root.mkdir(parents=True)
    shutil.copyfile(crop, root / "crop.png")
    (root / "baseline.txt").write_text(BASELINE_PROMPT + "\n", encoding="utf-8")
    (root / "candidate.txt").write_text(CANDIDATE_PROMPT + "\n", encoding="utf-8")
    freeze = {
        "schema_version": "m7-window-repeatability-freeze-1",
        "cohort": "development_seen",
        "source_sha256": digest(source),
        "crop_sha256": digest(root / "crop.png"),
        "baseline_prompt_sha256": digest(root / "baseline.txt"),
        "candidate_prompt_sha256": digest(root / "candidate.txt"),
        "runner_sha256": digest(Path(__file__)),
        "cli_sha256": digest(cli),
        "hardware_sha256": hardware_sha(),
        "requested_model": "gpt-6-luna",
        "effort": "medium",
        "order": ORDER,
        "expected_original_px": EXPECTED,
        "tolerance_original_px": TOLERANCE,
        "oracle_provenance": "assistant_visual_before_pilot",
        "candidate_previously_seen": True,
        "acceptance_m7": False,
    }
    write_new(root / "freeze.json", freeze)
    return freeze


def validate(root: Path, source: Path, cli: Path) -> dict:
    freeze = json.loads((root / "freeze.json").read_text(encoding="utf-8"))
    expected_hashes = {
        "source_sha256": digest(source),
        "crop_sha256": digest(root / "crop.png"),
        "baseline_prompt_sha256": digest(root / "baseline.txt"),
        "candidate_prompt_sha256": digest(root / "candidate.txt"),
        "runner_sha256": digest(Path(__file__)),
        "cli_sha256": digest(cli),
        "hardware_sha256": hardware_sha(),
    }
    if (freeze.get("schema_version") != "m7-window-repeatability-freeze-1"
            or any(freeze.get(key) != value for key, value in expected_hashes.items())
            or tuple(freeze.get("order", [])) != ORDER
            or freeze.get("requested_model") != "gpt-6-luna"
            or freeze.get("effort") != "medium"
            or freeze.get("expected_original_px") != [[393, 564], [393, 654]]
            or freeze.get("tolerance_original_px") != 5):
        raise ValueError("Frozen pilot inputs differ")
    return freeze


def _events(path: Path) -> tuple[dict, dict]:
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    messages = [event["item"]["text"] for event in events
                if event.get("type") == "item.completed"
                and event.get("item", {}).get("type") == "agent_message"]
    completed = [event for event in events if event.get("type") == "turn.completed"]
    if len(messages) != 1 or len(completed) != 1:
        raise ValueError("CLI event stream lacks one completed answer")
    usage = completed[0].get("usage")
    if not isinstance(usage, dict) or any(
            type(usage.get(key)) is not int or usage[key] < 0
            for key in ("input_tokens", "cached_input_tokens", "output_tokens")):
        raise ValueError("CLI usage is missing")
    return json.loads(messages[0]), usage


def run_slot(root: Path, source: Path, cli: Path, index: int) -> dict:
    freeze = validate(root, source, cli)
    if not 0 <= index < len(ORDER):
        raise ValueError("Slot index outside frozen schedule")
    for earlier in range(index):
        if not (root / f"slot-{earlier:02d}" / "result.json").is_file():
            raise ValueError("Earlier slot is not complete; never replay uncertainty")
    slot = root / f"slot-{index:02d}"
    slot.mkdir(exist_ok=False)
    arm = ORDER[index]
    prompt_path = root / f"{arm}.txt"
    intent = {"schema_version": "m7-window-repeatability-intent-1",
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
    elapsed = (time.monotonic_ns() - started) / 1e9
    result = {"schema_version": "m7-window-repeatability-slot-1",
              "slot": index, "arm": arm, "exit_code": process.returncode,
              "elapsed_seconds": round(elapsed, 6),
              "intent_sha256": digest(slot / "intent.json"),
              "events_sha256": digest(slot / "events.jsonl"),
              "stderr_sha256": digest(slot / "stderr.txt")}
    write_new(slot / "result.json", result)
    return result


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
        points = [observed.get("top_px"), observed.get("bottom_px")]
        shape_ok = (observed.get("schema_version") == "ocs-window-endpoints-1"
                    and observed.get("status") == "observed"
                    and all(isinstance(item, list) and len(item) == 2 and
                            all(type(value) is int for value in item)
                            for item in points))
        actual = ([[CROP_ORIGIN[0] + item[0] / SCALE,
                    CROP_ORIGIN[1] + item[1] / SCALE] for item in points]
                  if shape_ok else None)
        passed = bool(shape_ok and all(
            abs(point[axis] - expected[axis]) <= TOLERANCE
            for point, expected in zip(actual, EXPECTED) for axis in range(2)))
        records.append({"slot": index, "arm": arm,
                        "status": "passed_source_oracle" if passed else
                                  ("abstained" if observed.get("status") == "unsupported"
                                   else "failed_source_oracle"),
                        "observed_original_px": actual,
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
            "total": 3,
            "latency_median_seconds": statistics.median(times),
            "latency_p95_nearest_rank_seconds": times[math.ceil(.95 * len(times)) - 1],
            "input_tokens_sum": sum(item["usage_cli_aggregate"]["input_tokens"]
                                    for item in subset),
            "output_tokens_sum": sum(item["usage_cli_aggregate"]["output_tokens"]
                                     for item in subset),
        }
    return {"schema_version": "m7-window-repeatability-summary-1",
            "cohort": "development_seen", "acceptance_m7": False,
            "requested_model": "gpt-6-luna",
            "effective_model": "unverified_by_cli_jsonl",
            "freeze_sha256": digest(root / "freeze.json"),
            "arms": arms, "records": records,
            "limitations": ["single_seen_crop", "candidate_previously_seen",
                            "three_repetitions_per_arm", "cli_usage_not_provider_receipt",
                            "no_cad_or_human_review_in_this_pilot"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "run-slot", "summarize"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--crop", type=Path)
    parser.add_argument("--slot", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root, source, cli = (args.root.resolve(), args.source.resolve(strict=True),
                         args.cli.resolve(strict=True))
    if args.mode == "prepare":
        if args.crop is None:
            raise ValueError("Crop path required for prepare")
        result = prepare(root, source, args.crop.resolve(strict=True), cli)
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
