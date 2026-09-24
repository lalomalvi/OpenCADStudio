"""Make source-pixel crop evidence without printing expected metric values."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from cli_development_trial import parse_cli_events
from reserved_trial import _file_sha


def create(run: Path, image_path: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("Source crop output already exists")
    freeze_path, events_path = run / "freeze.json", run / "events.jsonl"
    frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
    if frozen.get("source_sha256") != _file_sha(image_path):
        raise ValueError("Source image differs from frozen run")
    measured, _ = parse_cli_events(events_path)
    regions = measured.get("source_regions")
    if isinstance(regions, dict):
        indexed = list(regions.items())
    elif isinstance(regions, list):
        indexed = [(str(index + 1), box) for index, box in enumerate(regions)]
    else:
        raise ValueError("Source regions are absent")
    if not 1 <= len(indexed) <= 32:
        raise ValueError("Source region count differs")
    output.mkdir(parents=True, exist_ok=False)
    entries = []
    with Image.open(image_path) as bitmap:
        source = bitmap.convert("RGB")
        sheet = Image.new("RGB", (560, len(indexed) * 120), "white")
        draw = ImageDraw.Draw(sheet)
        for index, (name, box) in enumerate(indexed):
            if not isinstance(box, list) or len(box) != 4 or \
                    any(type(value) is not int for value in box) or \
                    not (0 <= box[0] < box[2] <= source.width) or \
                    not (0 <= box[1] < box[3] <= source.height):
                raise ValueError("Source region escapes image")
            crop = source.crop(tuple(box))
            raw_sha = hashlib.sha256(crop.tobytes()).hexdigest().upper()
            scale = max(1, min(10, 520 // crop.width, 75 // crop.height))
            rendered = crop.resize((crop.width * scale, crop.height * scale),
                                   Image.Resampling.NEAREST)
            draw.text((10, index * 120 + 5), f"{index + 1}: {name} px={box}",
                      fill="black")
            sheet.paste(rendered, (10, index * 120 + 30))
            entries.append({"name": name, "region_px": box,
                            "rgb_pixels_sha256": raw_sha})
    sheet_path = output / "contact-sheet.png"
    sheet.save(sheet_path)
    manifest = {"schema_version": "m7-source-text-crops-1",
                "source_sha256": _file_sha(image_path),
                "freeze_sha256": _file_sha(freeze_path),
                "events_sha256": _file_sha(events_path),
                "contact_sheet_sha256": _file_sha(sheet_path),
                "regions": entries,
                "scope": "exact_model_boxes_no_ocr_or_text_verdict"}
    with (output / "manifest.json").open("x", encoding="utf-8") as target:
        json.dump(manifest, target, sort_keys=True, indent=2)
        target.write("\n")
    return manifest


def verify_review(run: Path, image_path: Path, review_path: Path) -> dict:
    """Bind a visual judgment to exact pixels; do not claim OCR or L5."""
    output = review_path.parent
    manifest_path = output / "manifest.json"
    sheet_path = output / "contact-sheet.png"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    frozen = json.loads((run / "freeze.json").read_text(encoding="utf-8"))
    measured, _ = parse_cli_events(run / "events.jsonl")
    regions = measured["source_regions"]
    indexed = list(regions.items()) if isinstance(regions, dict) else [
        (str(index + 1), box) for index, box in enumerate(regions)]
    if manifest.get("schema_version") != "m7-source-text-crops-1" or \
            frozen.get("source_sha256") != _file_sha(image_path) or \
            manifest.get("source_sha256") != _file_sha(image_path) or \
            manifest.get("freeze_sha256") != _file_sha(run / "freeze.json") or \
            manifest.get("events_sha256") != _file_sha(run / "events.jsonl") or \
            manifest.get("contact_sheet_sha256") != _file_sha(sheet_path) or \
            not isinstance(manifest.get("regions"), list) or \
            len(manifest["regions"]) != len(indexed):
        raise ValueError("Source crop manifest differs")
    with Image.open(image_path) as bitmap:
        source = bitmap.convert("RGB")
        for (name, box), entry in zip(indexed, manifest["regions"]):
            if entry.get("name") != name or entry.get("region_px") != box or \
                    entry.get("rgb_pixels_sha256") != hashlib.sha256(
                        source.crop(tuple(box)).tobytes()).hexdigest().upper():
                raise ValueError("Source crop pixels differ")
    judgments = review.get("regions")
    if review.get("schema_version") != "m7-source-text-visual-review-1" or \
            review.get("reviewer") != "assistant_visual_manual" or \
            review.get("independent_human_l5") is not False or \
            review.get("manifest_sha256") != _file_sha(manifest_path) or \
            review.get("contact_sheet_sha256") != _file_sha(sheet_path) or \
            not isinstance(judgments, list) or len(judgments) != len(indexed):
        raise ValueError("Source crop review binding differs")
    for (name, _), judgment in zip(indexed, judgments):
        if judgment.get("name") != name or \
                judgment.get("status") not in {"complete", "clipped"} or \
                not isinstance(judgment.get("observation"), str):
            raise ValueError("Source crop judgment differs")
    complete = sum(item["status"] == "complete" for item in judgments)
    expected_status = ("passed_assistant_visual_box_containment" if complete == len(indexed)
                       else "failed_source_box_containment")
    if review.get("status") != expected_status:
        raise ValueError("Source crop review status differs")
    return {"status": expected_status, "complete": complete,
            "total": len(indexed), "review_sha256": _file_sha(review_path),
            "independent_human_l5": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-review", type=Path)
    args = parser.parse_args()
    if (args.output is None) == (args.verify_review is None):
        parser.error("Specify exactly one of --output or --verify-review")
    if args.verify_review is not None:
        print(json.dumps(verify_review(args.run_root.resolve(strict=True),
                                       args.image.resolve(strict=True),
                                       args.verify_review.resolve(strict=True))))
    else:
        result = create(args.run_root.resolve(strict=True),
                        args.image.resolve(strict=True),
                        args.output.resolve(strict=False))
        print(json.dumps({"contact_sheet_sha256": result["contact_sheet_sha256"],
                          "regions": len(result["regions"])}))


if __name__ == "__main__":
    main()
