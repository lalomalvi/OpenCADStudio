"""Single Responses API creation for a reserved synthetic or authorized image.

Call only inside reserved_runner.run_once's callback. The raw response remains
in memory for PlanSpec interpretation and receipt extraction; no file is saved.
CAD execution and supervisor accounting are separate callback responsibilities.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from provider_response_receipt import from_response
from reserved_runner import Invocation
from reserved_trial import TrialJournal


class LunaAdapterError(ValueError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class DirectResponsesClient:
    """One direct HTTPS POST; no SDK retries, redirects or raw logging."""

    max_retries = 0

    def __init__(self):
        if not os.environ.get("OPENAI_API_KEY"):
            raise LunaAdapterError("OPENAI_API_KEY is not configured")
        self.responses = self

    def create(self, **payload):
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise LunaAdapterError("OPENAI_API_KEY is not configured")
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
        request = Request("https://api.openai.com/v1/responses", data=body,
                          headers={"Content-Type": "application/json",
                                   "Authorization": f"Bearer {key}"}, method="POST")
        try:
            with build_opener(_NoRedirect()).open(request, timeout=120.0) as received:
                raw = received.read(32_000_001)
        except HTTPError as error:
            raise LunaAdapterError(f"Provider HTTP {error.code}; outcome uncertain") from None
        except (URLError, TimeoutError, OSError):
            raise LunaAdapterError("Provider transport failed; outcome uncertain") from None
        if len(raw) > 32_000_000:
            raise LunaAdapterError("Provider response exceeds in-memory limit")
        try:
            return json.loads(raw)
        except (UnicodeError, ValueError):
            raise LunaAdapterError("Provider response is not JSON; outcome uncertain") from None


def _bytes(path: Path, expected_sha256: str, limit: int) -> bytes:
    if not isinstance(path, Path) or not path.is_absolute() or not path.is_file():
        raise LunaAdapterError("Frozen input path is missing")
    if path.stat().st_size > limit:
        raise LunaAdapterError("Frozen input exceeds adapter limit")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest().upper() != expected_sha256:
        raise LunaAdapterError("Frozen input changed after trial reservation")
    return data


def _image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise LunaAdapterError("Only frozen PNG/JPEG images are accepted")


def request_luna_once(journal: TrialJournal, invocation: Invocation, *, client: Any,
                      max_output_tokens: int = 8192) -> dict:
    """Send one non-streamed model request, with SDK retries disabled.

    Any exception after `responses.create` may hide a completed request. The
    caller must let run_once consume the slot as uncertain; never retry here.
    """
    if not isinstance(journal, TrialJournal) or not isinstance(invocation, Invocation) or \
            invocation.requested_model != "gpt-6-luna" or \
            type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 128000:
        raise LunaAdapterError("Frozen model or output budget is invalid")
    pending = journal.verify_pending(invocation.arm, invocation.case_id,
                                     invocation.repetition, invocation.request_id)
    if any(getattr(invocation, key) != pending[key] for key in (
            "source_sha256", "protocol_sha256", "cad_binary_sha256",
            "requested_model", "effort")) or \
            invocation.image_path != journal.image_paths[invocation.case_id] or \
            invocation.protocol_path != journal.arm_protocols[invocation.arm] or \
            invocation.cad_binary_path != journal.arm_binaries[invocation.arm]:
        raise LunaAdapterError("Invocation differs from frozen journal identity")
    if getattr(client, "max_retries", None) != 0:
        raise LunaAdapterError("Provider client must disable automatic retries")
    protocol = _bytes(invocation.protocol_path, invocation.protocol_sha256, 262144)
    image = _bytes(invocation.image_path, invocation.source_sha256, 25_000_000)
    try:
        instructions = protocol.decode("utf-8")
    except UnicodeDecodeError as error:
        raise LunaAdapterError("Frozen protocol is not UTF-8") from error
    if not instructions.strip():
        raise LunaAdapterError("Frozen protocol is empty")
    mime = _image_mime(image)
    response = client.responses.create(
        model=invocation.requested_model,
        reasoning={"effort": invocation.effort},
        instructions=instructions,
        input=[{"role": "user", "content": [
            {"type": "input_text", "text": "Interpreta este plano conforme al protocolo congelado."},
            {"type": "input_image", "image_url":
             f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}",
             "detail": "original"}]}],
        max_output_tokens=max_output_tokens,
        store=False,
        stream=False,
    )
    raw = response if isinstance(response, dict) else response.model_dump(mode="json")
    from_response(raw)  # Fail before any CAD mutation if identity/usage is incomplete.
    return raw
