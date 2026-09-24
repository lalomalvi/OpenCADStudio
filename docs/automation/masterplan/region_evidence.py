"""Fenced, immutable pixel crops for regional review of a captured CAD viewport."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from pathlib import Path

from PIL import Image

from artifact_evidence import EvidenceError, artifact_ref, verify_ref


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_report", type=Path)
    parser.add_argument("regions_json", type=Path)
    parser.add_argument("--output-name", default="regions")
    args = parser.parse_args()
    regions = json.loads(args.regions_json.read_text(encoding="utf-8"))
    result = build_regions(args.run_report, regions, args.output_name)
    verify_regions(args.run_report, args.run_report.parent / args.output_name / "manifest.json")
    print(json.dumps({"manifest": str(args.run_report.parent / args.output_name / "manifest.json"),
                      "regions": len(result["regions"]), "human_review_status": "pending"}))


if __name__ == "__main__":
    main()
