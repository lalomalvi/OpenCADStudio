"""Strict local artifact references and a deterministic, sanitized evidence seal."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any


class EvidenceError(ValueError):
    pass


def _inside(root: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
        raise EvidenceError("Artifact path must be relative and contained")
    base = root.resolve(strict=True)
    path = (base / relative_path).resolve(strict=True)
    if not path.is_relative_to(base) or not path.is_file():
        raise EvidenceError("Artifact escapes run root or is not a file")
    return path


def artifact_ref(root: Path, relative_path: str, *, document_id: int,
                 geometry_revision: int, camera_revision: int, region: str = "full") -> dict[str, Any]:
    path = _inside(root, relative_path)
    if path.suffix.lower() != ".png":
        raise EvidenceError("Only PNG artifacts are supported by this contract")
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise EvidenceError("PNG header is invalid")
    width, height = struct.unpack(">II", data[16:24])
    if width == 0 or height == 0:
        raise EvidenceError("PNG dimensions must be positive")
    if any(type(value) is not int or value < 0 for value in
           (document_id, geometry_revision, camera_revision)):
        raise EvidenceError("Document and revision identities must be nonnegative integers")
    if not isinstance(region, str) or not region:
        raise EvidenceError("Region identity is required")
    return {
        "schema_version": "artifact-ref-1", "path": relative_path.replace("\\", "/"),
        "mime": "image/png", "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data), "width": width, "height": height,
        "document_id": document_id, "geometry_revision": geometry_revision,
        "camera_revision": camera_revision, "region": region,
    }


def verify_ref(root: Path, reference: dict[str, Any], *, document_id: int,
               geometry_revision: int, camera_revision: int) -> None:
    if (reference.get("document_id"), reference.get("geometry_revision"),
            reference.get("camera_revision")) != (document_id, geometry_revision, camera_revision):
        raise EvidenceError("Capture is stale for the requested document/render revision")
    expected = artifact_ref(root, reference["path"], document_id=document_id,
                            geometry_revision=geometry_revision,
                            camera_revision=camera_revision, region=reference["region"])
    if expected != reference:
        raise EvidenceError("Artifact content or metadata changed")


def seal(run_id: str, usage: dict[str, Any], references: list[dict[str, Any]],
         *, verdict: str, model_identity: str | None = None) -> dict[str, Any]:
    if not run_id or not run_id.isascii() or not all(c.isalnum() or c in "-_" for c in run_id) \
            or verdict not in {"passed", "failed", "partial", "pending"}:
        raise EvidenceError("Run identity or verdict is invalid")
    usage_keys = {"schema_version", "source_kind", "coverage", "usage", "noncached_input_tokens",
                  "identity", "billed_cost"}
    if set(usage) != usage_keys or usage.get("schema_version") != "m3-usage-summary-1":
        raise EvidenceError("Usage summary version is unsupported")
    if set(usage["coverage"]) != {"records", "unique_responses", "duplicate_records", "turns_with_identity"} \
            or set(usage["usage"]) != {"input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                                            "output_tokens", "reasoning_output_tokens", "total_tokens"} \
            or set(usage["identity"]) != {"effective_model", "supervisor_usage"} \
            or usage["billed_cost"] is not None or usage["source_kind"] != "token_usage_record" \
            or usage["identity"] != {"effective_model": "unknown", "supervisor_usage": "unknown"} \
            or any(type(number) is not int or number < 0 for number in
                   (*usage["coverage"].values(), *usage["usage"].values(),
                    usage["noncached_input_tokens"])) \
            or usage["usage"]["total_tokens"] != (usage["usage"]["input_tokens"]
                                                    + usage["usage"]["output_tokens"]) \
            or usage["noncached_input_tokens"] != (usage["usage"]["input_tokens"]
                                                     - usage["usage"]["cached_input_tokens"]):
        raise EvidenceError("Usage summary contains unapproved fields")
    reference_keys = {"schema_version", "path", "mime", "sha256", "bytes", "width", "height",
                      "document_id", "geometry_revision", "camera_revision", "region"}
    if any(set(ref) != reference_keys or ref.get("schema_version") != "artifact-ref-1"
           or ref.get("mime") != "image/png" for ref in references):
        raise EvidenceError("Artifact reference version is unsupported")
    if model_identity is not None and (not model_identity.isascii() or len(model_identity) > 128
                                       or not all(c.isalnum() or c in "-_/.:" for c in model_identity)):
        raise EvidenceError("Model identity contains unsupported characters")
    payload = {"schema_version": "m3-evidence-seal-1", "run_id": run_id,
               "usage": usage, "artifacts": references, "verdict": verdict,
               "model_identity": model_identity or "unknown", "billed_cost": None}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {"payload": payload, "sha256": hashlib.sha256(canonical).hexdigest()}


def verify_seal(value: dict[str, Any]) -> None:
    payload = value["payload"]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != value["sha256"]:
        raise EvidenceError("Evidence seal hash differs")
