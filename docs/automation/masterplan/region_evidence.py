"""Fenced, immutable pixel crops for regional review of a captured CAD viewport."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
from pathlib import Path

from PIL import Image

from artifact_evidence import EvidenceError, artifact_ref, verify_ref


def projected_door_regions(run_report: Path, margin_px: int = 12) -> list[dict]:
    """Derive two fixture crop boxes from the fenced CAD-to-pixel anchors."""
    if type(margin_px) is not int or not 0 <= margin_px <= 64:
        raise EvidenceError("Projection margin is invalid")
    report = json.loads(run_report.resolve(strict=True).read_text(encoding="utf-8"))
    parent = report.get("capture_artifact", {})
    projection = report.get("capture_projection", {})
    identity = ("document_id", "geometry_revision", "camera_revision")
    if report.get("status") != "passed" or projection.get("contract") != "viewport-rte-pixels-1" or \
            any(projection.get(key) != parent.get(key) for key in identity):
        raise EvidenceError("Projection does not belong to the passed capture")
    cad = projection.get("landmarks_cad")
    pixel = projection.get("landmarks_px")
    probes = projection.get("pixel_probes")
    if not isinstance(cad, list) or not isinstance(pixel, list) or len(cad) != 8 or len(pixel) != 8:
        raise EvidenceError("Two-door projection requires eight anchors")
    expected = [f"{door}-{part}" for door in ("door-south", "door-east")
                for part in ("hinge", "closed", "arc-mid", "open")]
    if [item.get("id") for item in cad] != expected or \
            [item.get("id") for item in pixel] != expected:
        raise EvidenceError("Projection anchor IDs differ from the fixture")
    if probes is not None and (not isinstance(probes, list) or
            [item.get("id") for item in probes] != expected or
            any(item.get("visible") is not True for item in probes)):
        raise EvidenceError("Projection ink probes differ or failed")
    if any(item.get("inside") is not True or not isinstance(item.get("pixel"), list) or
           len(item["pixel"]) != 2 or any(type(v) not in (int, float) or not math.isfinite(v)
           for v in item["pixel"]) for item in pixel):
        raise EvidenceError("Projection pixel is outside or invalid")
    regions = []
    for door, anchors in (("door-south", pixel[:4]), ("door-east", pixel[4:])):
        xs, ys = [p["pixel"][0] for p in anchors], [p["pixel"][1] for p in anchors]
        rect = [max(0, math.floor(min(xs)) - margin_px),
                max(0, math.floor(min(ys)) - margin_px),
                min(parent["width"], math.ceil(max(xs)) + margin_px + 1),
                min(parent["height"], math.ceil(max(ys)) + margin_px + 1)]
        if rect[0] >= rect[2] or rect[1] >= rect[3]:
            raise EvidenceError("Projected crop is empty")
        regions.append({"label": door, "rect_px": rect})
    return regions


def projected_anchor_regions(run_report: Path, groups: list[dict],
                             margin_px: int = 12) -> list[dict]:
    """Crop declared landmark groups from one fenced, visibly probed capture."""
    if type(margin_px) is not int or not 0 <= margin_px <= 64:
        raise EvidenceError("Projection margin is invalid")
    report = json.loads(run_report.resolve(strict=True).read_text(encoding="utf-8"))
    parent = report.get("capture_artifact")
    projection = report.get("capture_projection")
    if not isinstance(parent, dict) or not isinstance(projection, dict) or \
            report.get("status") != "passed" or \
            report.get("capture_overlay_policy") != "drawing_only" or \
            projection.get("contract") != "viewport-rte-pixels-1" or \
            any(projection.get(key) != parent.get(key) for key in
                ("document_id", "geometry_revision", "camera_revision")):
        raise EvidenceError("Projection does not belong to a passed drawing-only capture")
    width, height = parent.get("width"), parent.get("height")
    if type(width) is not int or type(height) is not int or width < 1 or height < 1:
        raise EvidenceError("Capture dimensions are invalid")
    cad, pixel, probes = (projection.get(key) for key in
                          ("landmarks_cad", "landmarks_px", "pixel_probes"))
    if not all(isinstance(value, list) for value in (cad, pixel, probes)) or \
            not 2 <= len(cad) <= 128 or len(cad) != len(pixel) or len(cad) != len(probes):
        raise EvidenceError("Projected landmark and probe counts differ")
    mapped = {}
    for cad_item, px_item, probe in zip(cad, pixel, probes):
        if not all(isinstance(value, dict) for value in (cad_item, px_item, probe)):
            raise EvidenceError("Projected landmark shape differs")
        name = cad_item.get("id")
        position = px_item.get("pixel")
        point = cad_item.get("point")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,48}", name) or \
                name in mapped or px_item.get("id") != name or probe.get("id") != name or \
                px_item.get("inside") is not True or probe.get("visible") is not True or \
                not isinstance(position, list) or len(position) != 2 or \
                not isinstance(point, list) or len(point) != 3 or \
                any(type(v) not in (int, float) or not math.isfinite(v)
                    for v in [*position, *point]) or \
                not (0 <= position[0] < width and 0 <= position[1] < height):
            raise EvidenceError("Projected landmark is invalid, hidden or outside capture")
        mapped[name] = position
    if not isinstance(groups, list) or not 1 <= len(groups) <= 12:
        raise EvidenceError("One to twelve projected groups are required")
    regions = []
    used_labels = set()
    for group in groups:
        if not isinstance(group, dict) or set(group) != {"label", "landmark_ids"}:
            raise EvidenceError("Projected group shape differs")
        label, names = group["label"], group["landmark_ids"]
        if not isinstance(label, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,48}", label) or \
                label in used_labels or not isinstance(names, list) or \
                not 2 <= len(names) <= 32 or \
                any(not isinstance(name, str) for name in names) or \
                len(names) != len(set(names)) or \
                any(name not in mapped for name in names):
            raise EvidenceError("Projected group label or anchors differ")
        used_labels.add(label)
        xs, ys = [mapped[name][0] for name in names], [mapped[name][1] for name in names]
        rect = [max(0, math.floor(min(xs)) - margin_px),
                max(0, math.floor(min(ys)) - margin_px),
                min(width, math.ceil(max(xs)) + margin_px + 1),
                min(height, math.ceil(max(ys)) + margin_px + 1)]
        if rect[0] >= rect[2] or rect[1] >= rect[3]:
            raise EvidenceError("Projected group crop is empty")
        regions.append({"label": label, "rect_px": rect})
    return regions


def build_regions(run_report: Path, regions: list[dict], output_name: str = "regions") -> dict:
    run_report = run_report.resolve(strict=True)
    root = run_report.parent
    report = json.loads(run_report.read_text(encoding="utf-8"))
    if report.get("status") != "passed" or report.get("capture_overlay_policy") != "drawing_only":
        raise EvidenceError("Only passed drawing-only captures can be cropped")
    parent = report["capture_artifact"]
    identity = {key: parent[key] for key in
                ("document_id", "geometry_revision", "camera_revision")}
    verify_ref(root, parent, **identity)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,48}", output_name):
        raise EvidenceError("Output name must be a safe slug")
    if not isinstance(regions, list) or not regions or len(regions) > 12:
        raise EvidenceError("One to twelve regions are required")
    prepared = []
    labels = set()
    for region in regions:
        if not isinstance(region, dict) or set(region) != {"label", "rect_px"}:
            raise EvidenceError("Region has unsupported fields")
        label, rect = region["label"], region["rect_px"]
        if not isinstance(label, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,48}", label) \
                or label in labels:
            raise EvidenceError("Region label is invalid or duplicated")
        if not isinstance(rect, list) or len(rect) != 4 or any(type(n) is not int for n in rect):
            raise EvidenceError("Region rectangle must contain four integers")
        left, top, right, bottom = rect
        if not (0 <= left < right <= parent["width"] and
                0 <= top < bottom <= parent["height"]):
            raise EvidenceError("Region rectangle escapes the captured viewport")
        labels.add(label)
        prepared.append((label, rect))
    output = root / output_name
    if output.exists():
        raise EvidenceError("Output already exists; historical crops are immutable")
    source = root / parent["path"]
    with Image.open(source) as opened:
        opened.load()
        if opened.format != "PNG" or opened.size != (parent["width"], parent["height"]):
            raise EvidenceError("Captured image format or size differs")
        encoded = []
        for label, rect in prepared:
            stream = io.BytesIO()
            opened.crop(tuple(rect)).save(stream, format="PNG")
            encoded.append((label, rect, stream.getvalue()))
    output.mkdir()
    children = []
    for label, rect, data in encoded:
        path = output / f"{label}.png"
        with path.open("xb") as target:
            target.write(data)
        child = artifact_ref(root, f"{output_name}/{label}.png", **identity,
                             region=f"pixel_crop:{label}")
        children.append({"label": label, "rect_px": rect, "artifact": child})
    manifest = {"schema_version": "m6-region-evidence-1", "parent": parent,
                "parent_report_sha256": hashlib.sha256(run_report.read_bytes()).hexdigest(),
                "regions": children, "human_review_status": "pending",
                "scope": "pixel_crops_of_one_fenced_viewport_no_cad_coordinate_mapping"}
    with (output / "manifest.json").open("x", encoding="utf-8") as target:
        json.dump(manifest, target, sort_keys=True, indent=2)
        target.write("\n")
    return manifest


def verify_regions(run_report: Path, manifest_path: Path) -> None:
    run_report = run_report.resolve(strict=True)
    manifest_path = manifest_path.resolve(strict=True)
    root = run_report.parent
    if not manifest_path.is_relative_to(root) or manifest_path.name != "manifest.json":
        raise EvidenceError("Region manifest must belong to the run")
    report = json.loads(run_report.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parent = report.get("capture_artifact")
    if (report.get("status") != "passed" or
            report.get("capture_overlay_policy") != "drawing_only" or
            manifest.get("schema_version") != "m6-region-evidence-1" or
            manifest.get("parent") != parent or
            manifest.get("parent_report_sha256") != hashlib.sha256(run_report.read_bytes()).hexdigest() or
            manifest.get("human_review_status") != "pending" or
            manifest.get("scope") != "pixel_crops_of_one_fenced_viewport_no_cad_coordinate_mapping"):
        raise EvidenceError("Region manifest does not match its source report")
    identity = {key: parent[key] for key in
                ("document_id", "geometry_revision", "camera_revision")}
    verify_ref(root, parent, **identity)
    children = manifest.get("regions")
    if not isinstance(children, list) or not 1 <= len(children) <= 12:
        raise EvidenceError("Region manifest has no children")
    labels = set()
    with Image.open(root / parent["path"]) as source:
        source.load()
        for child in children:
            if not isinstance(child, dict) or set(child) != {"label", "rect_px", "artifact"}:
                raise EvidenceError("Region child has unsupported fields")
            label, rect, reference = child["label"], child["rect_px"], child["artifact"]
            if not isinstance(label, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,48}", label) \
                    or label in labels or not isinstance(rect, list) or len(rect) != 4 \
                    or any(type(n) is not int for n in rect):
                raise EvidenceError("Region label or rectangle differs")
            left, top, right, bottom = rect
            if not (0 <= left < right <= parent["width"] and
                    0 <= top < bottom <= parent["height"]):
                raise EvidenceError("Region rectangle escapes the parent")
            labels.add(label)
            if (reference.get("path") != f"{manifest_path.parent.name}/{label}.png" or
                    reference.get("region") != f"pixel_crop:{label}" or
                    reference.get("width") != right - left or
                    reference.get("height") != bottom - top):
                raise EvidenceError("Region child identity or size differs")
            verify_ref(root, reference, **identity)
            with Image.open(root / reference["path"]) as cropped:
                cropped.load()
                if (cropped.format != "PNG" or
                        cropped.convert("RGBA").tobytes() !=
                        source.crop(tuple(rect)).convert("RGBA").tobytes()):
                    raise EvidenceError("Region pixels differ from the parent rectangle")


def verify_anchor_regions(run_report: Path, groups: list[dict],
                          manifest_path: Path, margin_px: int = 12) -> None:
    """Recompute group boxes as well as verifying the crop pixels and fence."""
    expected = projected_anchor_regions(run_report, groups, margin_px)
    verify_regions(run_report, manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    observed = [{"label": item["label"], "rect_px": item["rect_px"]}
                for item in manifest["regions"]]
    if observed != expected:
        raise EvidenceError("Region boxes differ from projected anchor groups")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_report", type=Path)
    parser.add_argument("regions_json", type=Path, nargs="?")
    parser.add_argument("--from-projection", action="store_true")
    parser.add_argument("--groups-json", type=Path)
    parser.add_argument("--output-name", default="regions")
    args = parser.parse_args()
    if sum((args.from_projection, args.regions_json is not None,
            args.groups_json is not None)) != 1:
        parser.error("Pass regions JSON, --from-projection or --groups-json")
    groups = None
    if args.from_projection:
        regions = projected_door_regions(args.run_report)
    elif args.groups_json is not None:
        groups = json.loads(args.groups_json.read_text(encoding="utf-8"))
        regions = projected_anchor_regions(args.run_report, groups)
    else:
        regions = json.loads(args.regions_json.read_text(encoding="utf-8"))
    result = build_regions(args.run_report, regions, args.output_name)
    manifest_path = args.run_report.parent / args.output_name / "manifest.json"
    if groups is not None:
        verify_anchor_regions(args.run_report, groups, manifest_path)
    else:
        verify_regions(args.run_report, manifest_path)
    print(json.dumps({"manifest": str(args.run_report.parent / args.output_name / "manifest.json"),
                      "regions": len(result["regions"]), "human_review_status": "pending"}))


if __name__ == "__main__":
    main()
