"""Freeze six private case oracles against an immutable M7 image cohort.

Only hashes and case IDs enter the manifest. The images, reviewer references and
oracle contents remain under caller-controlled private roots.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from reserved_cohort import verify_sources


class OracleError(ValueError):
    pass


_HASH = re.compile(r"[0-9A-F]{64}")
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_CATEGORIES = ("metric", "topology", "semantic", "visual")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _read_cohort(path: Path) -> tuple[dict, str]:
    if not path.is_absolute() or not path.is_file():
        raise OracleError("Absolute frozen cohort manifest is required")
    raw = path.read_bytes()
    try:
        cohort = json.loads(raw)
    except (UnicodeError, ValueError) as error:
        raise OracleError("Cohort manifest is not JSON") from error
    if not isinstance(cohort, dict) or set(cohort) != {
            "schema_version", "cohort_id", "case_count", "repetition_count", "split", "cases"} \
            or not isinstance(cohort.get("cohort_id"), str) \
            or not _ID.fullmatch(cohort["cohort_id"]) \
            or cohort.get("schema_version") != "m7-reserved-cohort-1" \
            or cohort.get("case_count") != 6 or cohort.get("repetition_count") != 18 \
            or cohort.get("split") != "reserved_unseen" or \
            not isinstance(cohort.get("cases"), list) or len(cohort["cases"]) != 6:
        raise OracleError("Frozen cohort shape differs")
    ids = set()
    hashes = set()
    roles = {"simple": 0, "medium": 0, "adversarial": 0}
    repetitions = set()
    for case in cohort["cases"]:
        if not isinstance(case, dict) or set(case) != {
                "id", "role", "source", "repetitions", "oracle_status"} \
                or not isinstance(case.get("id"), str) or not _ID.fullmatch(case["id"]) \
                or case["id"] in ids or case.get("oracle_status") != "pending" \
                or not isinstance(case.get("role"), str) or case["role"] not in roles \
                or not isinstance(case.get("source"), dict) or \
                set(case["source"]) != {"sha256", "bytes", "width", "height", "format"} \
                or not _HASH.fullmatch(str(case["source"].get("sha256", ""))) \
                or case["source"]["sha256"] in hashes \
                or any(type(case["source"].get(key)) is not int or case["source"][key] <= 0
                       for key in ("bytes", "width", "height")) \
                or not isinstance(case["source"].get("format"), str) \
                or case["source"]["format"] not in {"PNG", "JPEG"} or \
                case.get("repetitions") != [f"{case['id']}-r{i}" for i in (1, 2, 3)]:
            raise OracleError("Frozen cohort case identity differs")
        ids.add(case["id"])
        hashes.add(case["source"]["sha256"])
        roles[case["role"]] += 1
        repetitions.update(case["repetitions"])
    if len(repetitions) != 18 or any(count != 2 for count in roles.values()):
        raise OracleError("Frozen cohort repetition identities differ")
    return cohort, _digest(raw)


def _private_file(root: Path, path: Path) -> Path:
    if not root.is_absolute() or not root.is_dir() or not path.is_absolute():
        raise OracleError("Absolute private oracle root and paths are required")
    base = root.resolve(strict=True)
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise OracleError("Oracle file is missing") from error
    if not resolved.is_relative_to(base) or not resolved.is_file() \
            or resolved.suffix.lower() != ".json":
        raise OracleError("Oracle file escapes its private root or is not JSON")
    return resolved


def _oracle_file(root: Path, path: Path, case: dict) -> dict[str, Any]:
    resolved = _private_file(root, path)
    if resolved.stat().st_size > 1_000_000:
        raise OracleError("Oracle file exceeds 1 MB")
    raw = resolved.read_bytes()
    try:
        oracle = json.loads(raw)
    except (UnicodeError, ValueError) as error:
        raise OracleError("Oracle file is not JSON") from error
    if not isinstance(oracle, dict) or set(oracle) != {
            "schema_version", "case_id", "source_sha256", "verification", "checks"} \
            or oracle["schema_version"] != "m7-case-oracle-1" \
            or oracle["case_id"] != case["id"] \
            or oracle["source_sha256"] != case["source"]["sha256"]:
        raise OracleError("Oracle identity or source hash differs")
    verification = oracle["verification"]
    if not isinstance(verification, dict) or set(verification) != {"kind", "reference"} \
            or verification["kind"] not in {"human_verified", "independent_tool"} \
            or not isinstance(verification["reference"], str) \
            or not 1 <= len(verification["reference"].strip()) <= 256:
        raise OracleError("Oracle verification provenance is missing")
    checks = oracle["checks"]
    if not isinstance(checks, dict) or set(checks) != set(_CATEGORIES):
        raise OracleError("Oracle must specify all four fidelity categories")
    all_ids = set()
    for category in _CATEGORIES:
        items = checks[category]
        if not isinstance(items, list) or not items:
            raise OracleError(f"Oracle {category} checks are missing")
        for item in items:
            if not isinstance(item, dict) or set(item) != {"id", "criterion"} \
                    or not isinstance(item["id"], str) or not _ID.fullmatch(item["id"]) \
                    or item["id"] in all_ids or not isinstance(item["criterion"], str) \
                    or not 1 <= len(item["criterion"].strip()) <= 1000:
                raise OracleError("Oracle check identity or criterion is invalid")
            all_ids.add(item["id"])
    return {"sha256": _digest(raw), "bytes": len(raw),
            "check_count": len(all_ids)}


def _sources(cohort: dict, paths_by_id: dict[str, Path], input_root: Path) -> None:
    if not input_root.is_absolute() or not input_root.is_dir() or \
            set(paths_by_id) != {case["id"] for case in cohort["cases"]}:
        raise OracleError("Private image mapping differs from frozen cohort")
    try:
        verify_sources(cohort, paths_by_id, input_root=input_root)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise OracleError("Reserved images changed after cohort freeze") from error


def freeze(cohort_path: Path, image_paths: dict[str, Path], *, input_root: Path,
           oracle_paths: dict[str, Path], oracle_root: Path, output: Path) -> dict:
    cohort, cohort_sha = _read_cohort(cohort_path)
    _sources(cohort, image_paths, input_root)
    if not output.is_absolute() or output.suffix.lower() != ".json" \
            or output.exists() or output.resolve(strict=False).is_relative_to(input_root.resolve()) \
            or output.resolve(strict=False).is_relative_to(oracle_root.resolve(strict=True)):
        raise OracleError("New oracle manifest must be outside private roots")
    if set(oracle_paths) != {case["id"] for case in cohort["cases"]}:
        raise OracleError("One oracle file per frozen case is required")
    entries = []
    for case in cohort["cases"]:
        evidence = _oracle_file(oracle_root, oracle_paths[case["id"]], case)
        entries.append({"case_id": case["id"], "source_sha256": case["source"]["sha256"],
                        "oracle_sha256": evidence["sha256"], "oracle_bytes": evidence["bytes"],
                        "check_count": evidence["check_count"]})
    manifest = {"schema_version": "m7-oracle-freeze-1", "cohort_sha256": cohort_sha,
                "cohort_id": cohort["cohort_id"], "case_count": 6, "repetition_count": 18,
                "cases": entries}
    output.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                   "w", encoding="utf-8") as target:
        json.dump(manifest, target, sort_keys=True, indent=2)
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())
    return manifest


def verify_ready(cohort_path: Path, image_paths: dict[str, Path], *, input_root: Path,
                 oracle_manifest_path: Path, oracle_paths: dict[str, Path],
                 oracle_root: Path) -> dict:
    cohort, cohort_sha = _read_cohort(cohort_path)
    _sources(cohort, image_paths, input_root)
    try:
        raw = oracle_manifest_path.read_bytes()
        manifest = json.loads(raw)
    except (OSError, UnicodeError, ValueError) as error:
        raise OracleError("Frozen oracle manifest is missing or invalid") from error
    if not isinstance(manifest, dict) or set(manifest) != {
            "schema_version", "cohort_sha256", "cohort_id", "case_count", "repetition_count", "cases"} \
            or manifest["schema_version"] != "m7-oracle-freeze-1" \
            or manifest["cohort_sha256"] != cohort_sha \
            or manifest["cohort_id"] != cohort["cohort_id"] \
            or manifest["case_count"] != 6 or manifest["repetition_count"] != 18 \
            or not isinstance(manifest["cases"], list) or len(manifest["cases"]) != 6 \
            or set(oracle_paths) != {case["id"] for case in cohort["cases"]}:
        raise OracleError("Oracle manifest no longer matches frozen cohort")
    expected = []
    for case in cohort["cases"]:
        evidence = _oracle_file(oracle_root, oracle_paths[case["id"]], case)
        expected.append({"case_id": case["id"], "source_sha256": case["source"]["sha256"],
                         "oracle_sha256": evidence["sha256"], "oracle_bytes": evidence["bytes"],
                         "check_count": evidence["check_count"]})
    if manifest["cases"] != expected:
        raise OracleError("Oracle files changed after freeze")
    return {"schema_version": "m7-preflight-1", "status": "ready_for_L3",
            "cohort_sha256": cohort_sha, "oracle_manifest_sha256": _digest(raw),
            "case_count": 6, "repetition_count": 18}


def _path_map(path: Path) -> dict[str, Path]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise OracleError("Private path map is missing or invalid") from error
    if not isinstance(value, dict) or not value or any(
            not isinstance(key, str) or not _ID.fullmatch(key)
            or not isinstance(item, str) or not Path(item).is_absolute()
            for key, item in value.items()):
        raise OracleError("Private path map needs IDs and absolute paths")
    return {key: Path(item) for key, item in value.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "verify"))
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--image-map", type=Path, required=True)
    parser.add_argument("--oracle-root", type=Path, required=True)
    parser.add_argument("--oracle-map", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    images, oracles = _path_map(args.image_map), _path_map(args.oracle_map)
    if args.mode == "freeze":
        value = freeze(args.cohort, images, input_root=args.image_root,
                       oracle_paths=oracles, oracle_root=args.oracle_root,
                       output=args.manifest)
        print(json.dumps({"status": "frozen", "cohort_id": value["cohort_id"],
                          "cases": value["case_count"], "repetitions": value["repetition_count"],
                          "oracle_manifest_sha256": _digest(args.manifest.read_bytes())}))
    else:
        print(json.dumps(verify_ready(args.cohort, images, input_root=args.image_root,
                                      oracle_manifest_path=args.manifest,
                                      oracle_paths=oracles, oracle_root=args.oracle_root)))


if __name__ == "__main__":
    main()
