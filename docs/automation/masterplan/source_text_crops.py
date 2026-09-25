"""Make source-pixel crop evidence without printing expected metric values."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from cli_development_trial import parse_cli_events
from reserved_trial import _file_sha


def _expanded(box: list[int], width: int, height: int, padding: int) -> list[int]:
    if type(padding) is not int or not 0 <= padding <= 100:
        raise ValueError("Source crop padding differs")
    return [max(0, box[0] - padding), max(0, box[1] - padding),
            min(width, box[2] + padding), min(height, box[3] + padding)]


def _overlap(a: list[int], b: list[int]) -> bool:
    return max(a[0], b[0]) < min(a[2], b[2]) and \
        max(a[1], b[1]) < min(a[3], b[3])


def create(run: Path, image_path: Path, output: Path, *, padding_px: int = 0) -> dict:
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
    entries = []
    with Image.open(image_path) as bitmap:
        source = bitmap.convert("RGB")
        expanded_boxes = []
        for _, box in indexed:
            if not isinstance(box, list) or len(box) != 4 or \
                    any(type(value) is not int for value in box) or \
                    not (0 <= box[0] < box[2] <= source.width) or \
                    not (0 <= box[1] < box[3] <= source.height):
                raise ValueError("Source region escapes image")
            expanded_boxes.append(_expanded(box, source.width, source.height,
                                            padding_px))
        if padding_px and any(_overlap(a, b)
                              for index, a in enumerate(expanded_boxes)
                              for b in expanded_boxes[index + 1:]):
            raise ValueError("Derived source crops overlap neighboring claims")
        output.mkdir(parents=True, exist_ok=False)
        row_height = 300 if padding_px else 120
        sheet = Image.new("RGB", (560, len(indexed) * row_height), "white")
        draw = ImageDraw.Draw(sheet)
        for index, ((name, box), expanded) in enumerate(zip(indexed, expanded_boxes)):
            crop = source.crop(tuple(expanded))
            raw_sha = hashlib.sha256(crop.tobytes()).hexdigest().upper()
            scale = max(1, min(10, 520 // crop.width,
                               (row_height - 45) // crop.height))
            rendered = crop.resize((crop.width * scale, crop.height * scale),
                                   Image.Resampling.NEAREST)
            draw.text((10, index * row_height + 5), f"{index + 1}: {name} px={expanded}",
                      fill="black")
            sheet.paste(rendered, (10, index * row_height + 30))
            entry = {"name": name, "region_px": expanded,
                     "rgb_pixels_sha256": raw_sha}
            if padding_px:
                entry["model_region_px"] = box
            entries.append(entry)
    sheet_path = output / "contact-sheet.png"
    sheet.save(sheet_path)
    manifest = {"schema_version": ("m7-source-text-crops-derived-2" if padding_px
                                    else "m7-source-text-crops-1"),
                "source_sha256": _file_sha(image_path),
                "freeze_sha256": _file_sha(freeze_path),
                "events_sha256": _file_sha(events_path),
                "contact_sheet_sha256": _file_sha(sheet_path),
                "regions": entries,
                "scope": ("fixed_padding_derived_boxes_no_ocr_or_text_verdict" if padding_px
                          else "exact_model_boxes_no_ocr_or_text_verdict")}
    if padding_px:
        manifest["padding_px"] = padding_px
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
    schema = manifest.get("schema_version")
    if schema not in {"m7-source-text-crops-1", "m7-source-text-crops-derived-2"} or \
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
        boxes = []
        for (name, box), entry in zip(indexed, manifest["regions"]):
            expected = (_expanded(box, source.width, source.height,
                                  manifest.get("padding_px", 0))
                        if schema == "m7-source-text-crops-derived-2" else box)
            if entry.get("name") != name or entry.get("region_px") != expected or \
                    (schema == "m7-source-text-crops-derived-2" and
                     entry.get("model_region_px") != box) or \
                    entry.get("rgb_pixels_sha256") != hashlib.sha256(
                        source.crop(tuple(expected)).tobytes()).hexdigest().upper():
                raise ValueError("Source crop pixels differ")
            boxes.append(expected)
        if schema == "m7-source-text-crops-derived-2" and any(
                _overlap(a, b) for index, a in enumerate(boxes)
                for b in boxes[index + 1:]):
            raise ValueError("Derived source crops overlap neighboring claims")
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
    parser.add_argument("--padding", type=int, default=0)
    args = parser.parse_args()
    if (args.output is None) == (args.verify_review is None):
        parser.error("Specify exactly one of --output or --verify-review")
    if args.verify_review is not None:
        if args.padding != 0:
            parser.error("--padding is only valid when creating crops")
        print(json.dumps(verify_review(args.run_root.resolve(strict=True),
                                       args.image.resolve(strict=True),
                                       args.verify_review.resolve(strict=True))))
    else:
        result = create(args.run_root.resolve(strict=True),
                        args.image.resolve(strict=True),
                        args.output.resolve(strict=False), padding_px=args.padding)
        print(json.dumps({"contact_sheet_sha256": result["contact_sheet_sha256"],
                          "regions": len(result["regions"])}))


if __name__ == "__main__":
    main()
