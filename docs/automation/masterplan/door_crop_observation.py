"""Reject physically inconsistent door observations before CAD compilation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


class DoorObservationError(ValueError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def geometry_issues(points: dict) -> list[str]:
    a, b, c = (points[name] for name in "ABC")
    width = b[0] - a[0]
    leaf_height = b[1] - c[1]
    issues = []
    if width < 100 or abs(b[1] - a[1]) > 25:
        issues.append("opening_endpoints_inconsistent")
    if abs(c[0] - b[0]) > 30 or leaf_height <= 0:
        issues.append("open_leaf_orientation_inconsistent")
    if width > 0 and not 0.75 <= leaf_height / width <= 1.25:
        issues.append("leaf_length_differs_from_opening")
    return issues


def evaluate(run: Path, source: Path) -> dict:
    freeze = json.loads((run / "freeze.json").read_text(encoding="utf-8"))
    if (freeze.get("schema_version") not in {
            "m7-door-discovery-freeze-3", "m7-door-discovery-freeze-4"} or
            freeze.get("cohort") != "development_seen" or
            freeze.get("acceptance_m7") is not False or
            freeze.get("cad_permitted") is not False or
            freeze.get("crop_original_xyxy") != [915, 640, 1020, 725] or
            freeze.get("scale") != 8 or
            freeze.get("source_sha256") != sha(source) or
            freeze.get("crop_sha256") != sha(run / "crop.png") or
            freeze.get("prompt_sha256") != sha(run / "prompt.txt")):
        raise DoorObservationError("Frozen source or protocol differs")
    events = [json.loads(line) for line in
              (run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    messages = [event["item"]["text"] for event in events if
                event.get("type") == "item.completed" and
                event.get("item", {}).get("type") == "agent_message"]
    if len(messages) != 1 or sum(event.get("type") == "turn.completed"
                                 for event in events) != 1:
        raise DoorObservationError("One terminal model message required")
    observation = json.loads(messages[0])
    if set(observation) != {"schema_version", "points", "tolerance_px", "status"} or \
            observation["schema_version"] != "ocs-door-three-points-1" or \
            observation["status"] not in {"estimated", "unsupported"}:
        raise DoorObservationError("Door observation schema differs")
    issues = []
    if observation["status"] == "unsupported":
        issues.append("model_abstained")
    else:
        points = observation["points"]
        tolerance = observation["tolerance_px"]
        if set(points) != {"A", "B", "C"} or set(tolerance) != set(points):
            raise DoorObservationError("Door point IDs differ")
        for name, point in points.items():
            if (not isinstance(point, list) or len(point) != 2 or
                    any(type(coordinate) is not int for coordinate in point) or
                    not 0 <= point[0] < 840 or not 0 <= point[1] < 680 or
                    type(tolerance[name]) is not int or
                    not 0 <= tolerance[name] <= 30):
                raise DoorObservationError("Door point or tolerance out of bounds")
        issues.extend(geometry_issues(points))
    return {"schema_version": "m7-door-observation-verdict-1",
            "status": "passed_observation_only" if not issues else "failed_plan_gate",
            "acceptance_m7": False, "cad_permitted": False,
            "issues": sorted(set(issues)), "freeze_sha256": sha(run / "freeze.json"),
            "events_sha256": sha(run / "events.jsonl"),
            "source_sha256": sha(source)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verdict = evaluate(args.run_root, args.source)
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(verdict, target, sort_keys=True, indent=2)
        target.write("\n")
    print(json.dumps({"status": verdict["status"], "issues": verdict["issues"]}))
    if verdict["status"] != "passed_observation_only":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
