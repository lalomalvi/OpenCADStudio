"""Overlay the 60-entity apartment PlanSpec on its authorized source image."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from PIL import Image, ImageDraw

from planspec import dry_run


SOURCE_SHA = "0CD0B310FC337C18704B658B41DF49ABB63E2F398893273BBFCFD503B2134057"
PLAN_SHA = "343386E669B7CB633AE331113D80844583C3E10167BF0106D74C12D71A6E13AD"
CALIBRATION = {"left_px": 392, "right_px": 1285, "top_px": 365,
               "bottom_px": 869, "width_m": 13.86, "height_m": 8.0}
LINE = re.compile(r"^LINE ([-+\d.eE]+),([-+\d.eE]+) ([-+\d.eE]+),([-+\d.eE]+)$")
ARC = re.compile(r"^ARC ([-+\d.eE]+),([-+\d.eE]+) "
                 r"([-+\d.eE]+),([-+\d.eE]+) "
                 r"([-+\d.eE]+),([-+\d.eE]+)$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def to_pixel(point: tuple[float, float]) -> tuple[float, float]:
    c = CALIBRATION
    return (c["left_px"] + point[0] * (c["right_px"] - c["left_px"]) / c["width_m"],
            c["bottom_px"] - point[1] * (c["bottom_px"] - c["top_px"]) / c["height_m"])


def arc_points(a, mid, b) -> list[tuple[float, float]]:
    ax, ay = a
    mx, my = mid
    bx, by = b
    denominator = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
    if abs(denominator) < 1e-10:
        raise ValueError("ARC points are collinear")
    a2, m2, b2 = ax * ax + ay * ay, mx * mx + my * my, bx * bx + by * by
    center = ((a2 * (my - by) + m2 * (by - ay) + b2 * (ay - my)) / denominator,
              (a2 * (bx - mx) + m2 * (ax - bx) + b2 * (mx - ax)) / denominator)
    radius = math.dist(center, a)
    angles = [math.atan2(point[1] - center[1], point[0] - center[0])
              for point in (a, mid, b)]
    sweep = (angles[2] - angles[0]) % (2 * math.pi)
    mid_sweep = (angles[1] - angles[0]) % (2 * math.pi)
    if mid_sweep > sweep:
        sweep -= 2 * math.pi
    return [(center[0] + radius * math.cos(angles[0] + sweep * index / 64),
             center[1] + radius * math.sin(angles[0] + sweep * index / 64))
            for index in range(65)]


def build(source: Path, plan_path: Path, calibration_freeze: Path,
          output_root: Path) -> dict:
    allowed = (Path(__file__).resolve().parents[3] / "target/mcp-review").resolve()
    root = output_root.resolve()
    if root == allowed or not root.is_relative_to(allowed) or root.exists():
        raise ValueError("Review output must be a new child of target/mcp-review")
    if digest(source) != SOURCE_SHA or digest(plan_path) != PLAN_SHA:
        raise ValueError("Review source or PlanSpec SHA differs")
    freeze = json.loads(calibration_freeze.read_text(encoding="utf-8"))
    if (freeze.get("source_sha256") != SOURCE_SHA or
            freeze.get("pixel_calibration") != CALIBRATION):
        raise ValueError("Frozen pixel calibration differs")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    compiled = dry_run(plan, capabilities={"layer_assignment"})
    if not compiled["executable"] or compiled["unsupported"] or compiled["quality_blockers"]:
        raise ValueError("PlanSpec does not compile cleanly")
    base = Image.open(source).convert("RGBA")
    overlay = Image.new("RGBA", base.size)
    drawing = ImageDraw.Draw(overlay)
    counts = {"structure_lines": 0, "window_lines": 0, "door_lines": 0,
              "door_arcs": 0, "hidden_reference_lines": 0, "dimensions_omitted": 0}
    for item in compiled["commands"]:
        command = item["command"]
        layer = item["layer"]
        if command.startswith("DIMLINEAR "):
            counts["dimensions_omitted"] += 1
            continue
        if layer == "OCS_DIM_REF":
            counts["hidden_reference_lines"] += 1
            continue
        line = LINE.fullmatch(command)
        if line:
            values = [float(value) for value in line.groups()]
            points = [to_pixel((values[0], values[1])),
                      to_pixel((values[2], values[3]))]
            if layer == "A-WINDOW":
                color = (210, 0, 180, 235)
                counts["window_lines"] += 1
            elif layer == "A-DOOR":
                color = (255, 140, 0, 235)
                counts["door_lines"] += 1
            else:
                color = (0, 145, 230, 215)
                counts["structure_lines"] += 1
            drawing.line(points, fill=color, width=4)
            continue
        arc = ARC.fullmatch(command)
        if arc and layer == "A-DOOR":
            values = [float(value) for value in arc.groups()]
            points = arc_points(tuple(values[:2]), tuple(values[2:4]),
                                tuple(values[4:6]))
            drawing.line([to_pixel(point) for point in points],
                         fill=(255, 140, 0, 235), width=4)
            counts["door_arcs"] += 1
            continue
        raise ValueError(f"Unsupported visual overlay command {item['planspec_id']}")
    if sum(counts.values()) != len(compiled["commands"]):
        raise ValueError("Overlay command census differs")
    if counts != {"structure_lines": 29, "window_lines": 16, "door_lines": 2,
                  "door_arcs": 2, "hidden_reference_lines": 4,
                  "dimensions_omitted": 7}:
        raise ValueError("Expected partial PlanSpec census differs")
    combined = Image.alpha_composite(base, overlay).convert("RGB")
    crop_box = (330, 270, 1380, 1020)
    original_crop = base.convert("RGB").crop(crop_box)
    overlay_crop = combined.crop(crop_box)
    comparison = Image.new("RGB", (original_crop.width * 2, original_crop.height + 36),
                           "white")
    comparison.paste(original_crop, (0, 36))
    comparison.paste(overlay_crop, (original_crop.width, 36))
    labels = ImageDraw.Draw(comparison)
    labels.text((12, 10), "FUENTE", fill="black")
    labels.text((original_crop.width + 12, 10),
                "SUPERPOSICION: azul estructura, magenta ventanas, naranja puertas",
                fill="black")
    root.mkdir(parents=True)
    combined.save(root / "overlay-full.png")
    comparison.save(root / "review-side-by-side.png")
    result = {"schema_version": "m7-partial-visual-review-packet-2",
              "cohort": "development_seen", "acceptance_m7": False,
              "source_sha256": SOURCE_SHA, "plan_sha256": PLAN_SHA,
              "calibration_freeze_sha256": digest(calibration_freeze),
              "renderer_sha256": digest(Path(__file__)),
              "commands_sha256": compiled["commands_sha256"],
              "entity_census": counts,
              "full_overlay_sha256": digest(root / "overlay-full.png"),
              "comparison_sha256": digest(root / "review-side-by-side.png"),
              "human_l5": "pending"}
    (root / "manifest.json").write_text(json.dumps(result, indent=2) + "\n",
                                        encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--calibration-freeze", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source.resolve(strict=True), args.plan.resolve(strict=True),
                           args.calibration_freeze.resolve(strict=True),
                           args.output_root.resolve()), indent=2))


if __name__ == "__main__":
    main()
