"""Read-only provenance chain for the northeast door observation and CAD run."""

import argparse
import json
from pathlib import Path

from apartment_northeast_door_compiler import BASE_SHA, compose
from northeast_door_observation_v2 import (CROP, EXPECTED, SCALE, TOLERANCE,
                                           digest, validate)
from m8_case_cli import validate as validate_release, verify as verify_release
from m8_case_l4_mixed import assess as assess_external


class DoorEvidenceError(ValueError):
    pass


def assess(source: Path, cli: Path, base_path: Path, observed_root: Path,
           release_root: Path, binary: Path, external_path: Path) -> dict:
    freeze = validate(observed_root, source, cli)
    intent = json.loads((observed_root / "intent.json").read_text(encoding="utf-8"))
    result = json.loads((observed_root / "result.json").read_text(encoding="utf-8"))
    verdict = json.loads((observed_root / "verdict.json").read_text(encoding="utf-8"))
    if (intent.get("freeze_sha256") != digest(observed_root / "freeze.json")
            or intent.get("prompt_sha256") != freeze["prompt_sha256"]
            or intent.get("crop_sha256") != freeze["crop_sha256"]
            or result.get("intent_sha256") != digest(observed_root / "intent.json")
            or result.get("events_sha256") != digest(observed_root / "events.jsonl")
            or result.get("stderr_sha256") != digest(observed_root / "stderr.txt")
            or result.get("exit_code") != 0):
        raise DoorEvidenceError("Frozen observation invocation differs")
    events = [json.loads(line) for line in
              (observed_root / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    answers = [event["item"]["text"] for event in events
               if event.get("type") == "item.completed"
               and event.get("item", {}).get("type") == "agent_message"]
    completed = [event for event in events if event.get("type") == "turn.completed"]
    if len(answers) != 1 or len(completed) != 1:
        raise DoorEvidenceError("CLI completion differs")
    observation = json.loads(answers[0])
    points = [observation.get(field) for field in
              ("upper_jamb_px", "lower_hinge_px", "leaf_tip_px")]
    if (observation.get("schema_version") != "ocs-door-observation-1"
            or observation.get("status") != "observed"
            or any(not isinstance(point, list) or len(point) != 2
                   or any(type(value) is not int for value in point) for point in points)):
        raise DoorEvidenceError("Observed door schema differs")
    actual = [[CROP[0] + point[0] / SCALE, CROP[1] + point[1] / SCALE]
              for point in points]
    if (not all(abs(point[axis] - expected[axis]) <= TOLERANCE
                for point, expected in zip(actual, EXPECTED) for axis in range(2))
            or abs(actual[0][0] - actual[1][0]) > 5
            or abs(actual[1][1] - actual[2][1]) > 5
            or abs((actual[1][1] - actual[0][1])
                   - (actual[2][0] - actual[1][0])) > 12
            or verdict.get("schema_version") != "m7-northeast-door-verdict-2"
            or verdict.get("status") != "passed_observation_only"
            or verdict.get("cad_permitted") is not True
            or verdict.get("freeze_sha256") != digest(observed_root / "freeze.json")
            or verdict.get("events_sha256") != digest(observed_root / "events.jsonl")
            or verdict.get("observation") != observation
            or verdict.get("observed_original_px") != actual
            or verdict.get("usage_cli_aggregate") != completed[0].get("usage")):
        raise DoorEvidenceError("Observation verdict differs from raw events")
    if digest(base_path) != BASE_SHA:
        raise DoorEvidenceError("Base PlanSpec bytes differ")
    plan, compiled = compose(json.loads(base_path.read_text(encoding="utf-8")), verdict)
    plan_path = observed_root / "model-plan.json"
    if plan != json.loads(plan_path.read_text(encoding="utf-8")):
        raise DoorEvidenceError("Saved PlanSpec differs from observed geometry")
    contract, recompiled = validate_release(release_root, plan_path, binary)
    local = verify_release(release_root, plan_path, binary)
    external = assess_external(release_root, plan_path, binary, external_path)
    if (compiled["commands_sha256"] != recompiled["commands_sha256"]
            or contract["commands_sha256"] != compiled["commands_sha256"]
            or local["entity_count"] != 60
            or external["status"] != "passed_scoped_l4"
            or external["geometry_matches"] != 60
            or external["geometry_total"] != 60
            or external["dwg_sha256"] != local["dwg_sha256"]):
        raise DoorEvidenceError("CAD or external verdict differs")
    return {"schema_version": "m7-northeast-door-evidence-chain-1",
            "status": "passed_scoped_l3_l4",
            "acceptance_m7": False,
            "effective_model": "unverified_by_cli_jsonl",
            "source_sha256": digest(source),
            "observation_v2_freeze_sha256": digest(observed_root / "freeze.json"),
            "observation_v2_events_sha256": digest(observed_root / "events.jsonl"),
            "observation_v2_verdict_sha256": digest(observed_root / "verdict.json"),
            "base_plan_sha256": digest(base_path),
            "derived_plan_sha256": digest(plan_path),
            "commands_sha256": compiled["commands_sha256"],
            "m8_contract_sha256": digest(release_root / "contract.json"),
            "m8_report_sha256": local["report_sha256"],
            "dwg_sha256": local["dwg_sha256"],
            "capture_sha256": local["capture_sha256"],
            "external_report_sha256": external["external_report_sha256"],
            "external_census_sha256": external["census_sha256"],
            "geometry_matches": external["geometry_matches"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("source", "cli", "base", "observed-root", "release-root",
                 "binary", "external", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.source.resolve(strict=True), args.cli.resolve(strict=True),
                    args.base.resolve(strict=True), args.observed_root.resolve(strict=True),
                    args.release_root.resolve(strict=True), args.binary.resolve(strict=True),
                    args.external.resolve(strict=True))
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(result["status"], result["geometry_matches"])


if __name__ == "__main__":
    main()
