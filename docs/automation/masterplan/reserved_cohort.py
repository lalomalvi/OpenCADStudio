"""Freeze an authorized six-image M7 cohort before the first model run.

The manifest contains hashes, dimensions and split labels only. Images and
private paths stay outside Git; the caller retains the path mapping locally.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re

from PIL import Image, UnidentifiedImageError


HISTORICAL_SOURCE_SHA256 = "A4D37BF7E653B9E581D71D7DBFE44400CC10C259CFAE20577ED3052AB9C00DF5"
ROLES = ("simple", "medium", "adversarial")


class CohortError(ValueError):
    pass


def _image_evidence(path: Path) -> dict:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            kind = image.format
    except (OSError, UnidentifiedImageError, ValueError) as error:
        raise CohortError("Cohort source is not a decodable image") from error
    if kind not in {"PNG", "JPEG"} or width < 64 or height < 64 or \
            width * height > 100_000_000:
        raise CohortError("Cohort image format or dimensions are unsupported")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            if size > 40_000_000:
                raise CohortError("Cohort image exceeds 40 MB")
            digest.update(chunk)
    return {"sha256": digest.hexdigest().upper(), "bytes": size,
            "width": width, "height": height, "format": kind}


def freeze(entries: list[dict], *, input_root: Path, forbidden_hashes: set[str],
           output: Path, cohort_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", cohort_id):
        raise CohortError("Invalid cohort ID")
    if not input_root.is_absolute() or not input_root.is_dir() or \
            not output.is_absolute() or output.suffix.lower() != ".json":
        raise CohortError("Absolute source root and new JSON manifest path are required")
    root = input_root.resolve(strict=True)
    if output.resolve(strict=False).is_relative_to(root):
        raise CohortError("Cohort manifest must be outside the source root")
    if output.exists():
        raise CohortError("Cohort manifest already exists; freeze a new version")
    if not isinstance(entries, list) or len(entries) != 6 or \
            not isinstance(forbidden_hashes, set) or \
            any(not re.fullmatch(r"[0-9A-Fa-f]{64}", value)
                for value in forbidden_hashes):
        raise CohortError("Six entries and valid development hashes are required")
    forbidden = {value.upper() for value in forbidden_hashes}
    forbidden.add(HISTORICAL_SOURCE_SHA256)
    ids: set[str] = set()
    hashes: set[str] = set()
    counts = {role: 0 for role in ROLES}
    cases = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"id", "role", "path"}:
            raise CohortError("Cohort entry fields are invalid")
        name, role, path = entry["id"], entry["role"], entry["path"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) \
                or name in ids or role not in ROLES or not isinstance(path, Path) or \
                not path.is_absolute():
            raise CohortError("Cohort entry identity, role or path is invalid")
        ids.add(name)
        counts[role] += 1
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise CohortError("Cohort image is missing") from error
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise CohortError("Cohort image escapes its authorized source root")
        evidence = _image_evidence(resolved)
        if evidence["sha256"] in forbidden or evidence["sha256"] in hashes:
            raise CohortError("Cohort source was used previously or is duplicated")
        hashes.add(evidence["sha256"])
        cases.append({"id": name, "role": role, "source": evidence,
                      "repetitions": [f"{name}-r{index}" for index in (1, 2, 3)],
                      "oracle_status": "pending"})
    if any(count != 2 for count in counts.values()):
        raise CohortError("Cohort requires two simple, two medium and two adversarial images")
    cases.sort(key=lambda case: (ROLES.index(case["role"]), case["id"]))
    manifest = {"schema_version": "m7-reserved-cohort-1", "cohort_id": cohort_id,
                "case_count": 6, "repetition_count": 18,
                "split": "reserved_unseen", "cases": cases}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as target:
        target.write(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        target.flush()
        os.fsync(target.fileno())
    return manifest


def verify_sources(manifest: dict, paths_by_id: dict[str, Path], *, input_root: Path) -> None:
    if manifest.get("schema_version") != "m7-reserved-cohort-1" or \
            set(paths_by_id) != {case["id"] for case in manifest["cases"]}:
        raise CohortError("Reserved cohort identity differs")
    root = input_root.resolve(strict=True)
    for case in manifest["cases"]:
        path = paths_by_id[case["id"]].resolve(strict=True)
        if not path.is_relative_to(root) or _image_evidence(path) != case["source"]:
            raise CohortError("Reserved cohort source changed after freeze")
