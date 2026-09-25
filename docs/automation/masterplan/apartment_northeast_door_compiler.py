"""Add the northeast swing door to the observed partial apartment PlanSpec."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from planspec import dry_run


BASE_SHA = "E30DF07438F03474E613A4908856AA680F9828903A01F0673CE297A906EBE367"
VERDICT_SHA = "8B6A8FA0839DBB08698DFAF5C9520B60D5D59F14A256FA32B027F82212E137B7"
FREEZE_SHA = "4DD0850E0FD1EB110DF3C4649E263A1C4E1614A0020514ED8792A1FAAE65F248"
EVENTS_SHA = "571AD38CFF8FD6942508C631ACD26BA6E0C15C2B7F4B93E452F9D78787A98F2A"
SOURCE_REGION = [1040, 475, 1170, 575]
EXPECTED = ((1090, 501), (1090, 550), (1145, 550))
TOLERANCE = 8


class NortheastDoorError(ValueError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def compose(base: dict, verdict: dict) -> tuple[dict, dict]:
    if (base.get("schema_version") != "planspec-11"
            or verdict.get("schema_version") != "m7-northeast-door-verdict-2"
            or verdict.get("status") != "passed_observation_only"
            or verdict.get("cad_permitted") is not True
            or verdict.get("freeze_sha256") != FREEZE_SHA
            or verdict.get("events_sha256") != EVENTS_SHA):
        raise NortheastDoorError("Base or source observation is ineligible")
    observed = verdict.get("observed_original_px")
    if (not isinstance(observed, list) or len(observed) != 3
            or any(not isinstance(point, list) or len(point) != 2
                   or any(type(value) not in (int, float) for value in point)
                   for point in observed)
            or any(abs(point[axis] - expected[axis]) > TOLERANCE
                   for point, expected in zip(observed, EXPECTED)
                   for axis in range(2))):
        raise NortheastDoorError("Observation differs from frozen source oracle")
    plan = deepcopy(base)
    nodes = {node["id"]: node for node in plan["nodes"]}
    lines = {line["id"]: line for line in plan["lines"]}
    if "wall1" not in lines or "wall3-upper" not in lines:
        raise NortheastDoorError("Expected host walls absent")
    opposite, hinge = lines["wall1"], lines["wall3-upper"]
    upper = nodes[opposite["end"]]
    lower = nodes[hinge["start"]]
    if (abs(upper["x"] - 10.83346) > 1e-6
            or abs(lower["x"] - upper["x"]) > 1e-6
            or abs(upper["y"] - 5.84127) > 1e-6
            or abs(lower["y"] - 5.031746) > 1e-6):
        raise NortheastDoorError("Host gap differs from the observed opening")
    gap = upper["y"] - lower["y"]
    if not 0.45 <= gap <= 1.5:
        raise NortheastDoorError("Door opening outside supported range")
    # The native symbol requires equal opening and leaf length. Pixel observation
    # locates the direction and tip; metric length is tied to the host gap.
    projected_tip_x = lower["x"] + gap
    predicted_tip_px = 1090 + gap * (1285 - 1090) / (13.891041 - 10.83346)
    if (abs(observed[0][0] - 1090) > 5
            or abs(observed[1][0] - 1090) > 5
            or abs(observed[1][1] - observed[2][1]) > 5
            or observed[2][0] <= observed[1][0]
            or abs(observed[2][0] - predicted_tip_px) > TOLERANCE):
        raise NortheastDoorError("Door leaf disagrees with host geometry")
    ids = set(nodes) | set(lines) | {item["id"] for item in plan["door_symbols"]}
    new = {"northeast-door-leaf-tip", "northeast-door-leaf", "northeast-door-swing"}
    if ids & new:
        raise NortheastDoorError("Northeast door IDs already exist")
    source = {"classification": "inferred", "confidence": 0.91,
              "region_px": SOURCE_REGION}
    plan["nodes"].append({"id": "northeast-door-leaf-tip",
                          "x": round(projected_tip_x, 6), "y": lower["y"],
                          "source": source})
    plan["lines"].append({"id": "northeast-door-leaf",
                          "start": hinge["start"],
                          "end": "northeast-door-leaf-tip",
                          "layer": "A-DOOR", "source": source})
    plan["door_symbols"].append({"id": "northeast-door-swing",
                                 "opposite_line_id": "wall1",
                                 "hinge_line_id": "wall3-upper",
                                 "leaf_line_id": "northeast-door-leaf",
                                 "layer": "A-DOOR", "source": source})
    compiled = dry_run(plan, capabilities={"layer_assignment"})
    if (not compiled["executable"] or compiled["unsupported"]
            or compiled["quality_blockers"] or len(compiled["commands"]) != 60):
        raise NortheastDoorError("Extended PlanSpec failed QA")
    return plan, compiled


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--verdict", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base_path = args.base.resolve(strict=True)
    if digest(base_path) != BASE_SHA:
        raise NortheastDoorError("Base PlanSpec bytes differ")
    verdict_path = args.verdict.resolve(strict=True)
    if digest(verdict_path) != VERDICT_SHA:
        raise NortheastDoorError("Frozen observation verdict bytes differ")
    plan, compiled = compose(json.loads(base_path.read_text(encoding="utf-8")),
                             json.loads(verdict_path.read_text(encoding="utf-8")))
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"commands_sha256": compiled["commands_sha256"],
                      "entities": len(compiled["commands"])}, indent=2))


if __name__ == "__main__":
    main()
