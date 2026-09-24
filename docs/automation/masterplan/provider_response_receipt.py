"""Sanitize identity and usage from an in-memory Responses API object.

An adapter must pass the object returned directly by the provider. This parser
does not authenticate an adapter or make a network request. Raw output, input,
image and response IDs are never written by this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from usage_evidence import _usage


class ResponseReceiptError(ValueError):
    pass


_IDENTITY = re.compile(r"[A-Za-z0-9_.-]{1,256}")
_HASH = re.compile(r"[0-9A-F]{64}")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def from_response(response: Any) -> dict:
    """Extract a numeric receipt from one completed direct API response."""
    if not isinstance(response, dict) or response.get("object") != "response" or \
            response.get("status") != "completed" or \
            not isinstance(response.get("id"), str) or \
            not _IDENTITY.fullmatch(response["id"]) or \
            not isinstance(response.get("model"), str) or \
            not _IDENTITY.fullmatch(response["model"]):
        raise ResponseReceiptError("Completed response identity is missing")
    raw = response.get("usage")
    if not isinstance(raw, dict) or not isinstance(raw.get("input_tokens_details"), dict) \
            or not isinstance(raw.get("output_tokens_details"), dict):
        raise ResponseReceiptError("Direct response usage details are missing")
    details = raw["input_tokens_details"]
    output_details = raw["output_tokens_details"]
    fields = (raw.get("input_tokens"), details.get("cached_tokens"),
              details.get("cache_write_tokens"), raw.get("output_tokens"),
              output_details.get("reasoning_tokens"), raw.get("total_tokens"))
    if any(type(value) is not int for value in fields):
        raise ResponseReceiptError("Direct response usage is incomplete")
    usage = _usage(dict(zip(("input_tokens", "cached_input_tokens",
                             "cache_write_input_tokens", "output_tokens",
                             "reasoning_output_tokens", "total_tokens"), fields)))
    if usage["cached_input_tokens"] + usage["cache_write_input_tokens"] > \
            usage["input_tokens"]:
        raise ResponseReceiptError("Cache categories exceed input tokens")
    try:
        raw_hash = _hash(json.dumps(response, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8"))
    except (TypeError, ValueError) as error:
        raise ResponseReceiptError("Response object is not finite JSON") from error
    return {"schema_version": "m3-direct-response-receipt-1",
            "response_id_sha256": _hash(response["id"].encode("utf-8")),
            "response_object_sha256": raw_hash, "model": response["model"],
            "usage": usage, "source": "adapter_supplied_direct_response_object"}


def verify_receipt(receipt: Any) -> dict:
    if not isinstance(receipt, dict) or set(receipt) != {
            "schema_version", "response_id_sha256", "response_object_sha256",
            "model", "usage", "source"} or \
            receipt["schema_version"] != "m3-direct-response-receipt-1" or \
            receipt["source"] != "adapter_supplied_direct_response_object" or \
            not isinstance(receipt["model"], str) or \
            not _IDENTITY.fullmatch(receipt["model"]) or any(
                not isinstance(receipt[key], str) or not _HASH.fullmatch(receipt[key])
                for key in ("response_id_sha256", "response_object_sha256")):
        raise ResponseReceiptError("Direct response receipt shape is invalid")
    _usage(receipt["usage"])
    return receipt
