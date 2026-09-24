"""One frozen supervisor Responses call after a verified CAD capture.

The raw response and both images remain in memory. The supervisor is an
observer; its output is not a fidelity oracle and never authorizes CAD edits.
"""

from __future__ import annotations

import base64
from pathlib import Path

from luna_once_adapter import _bytes, _image_mime
from owned_cad_executor import verify_owned_cad_evidence
from provider_response_receipt import from_response
from reserved_runner import Invocation
from reserved_trial import TrialJournal


class SupervisorAdapterError(ValueError):
    pass


def request_supervisor_once(journal: TrialJournal, invocation: Invocation,
                            cad_evidence: Path, *, client,
                            max_output_tokens: int = 4096) -> dict:
    """Create one response; any transport uncertainty consumes the reserved slot."""
    if not isinstance(journal, TrialJournal) or not isinstance(invocation, Invocation) or \
            getattr(client, "max_retries", None) != 0 or \
            type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 128000:
        raise SupervisorAdapterError("Supervisor client or budget is invalid")
    pending = journal.verify_pending(invocation.arm, invocation.case_id,
                                     invocation.repetition, invocation.request_id)
    frozen = pending.get("supervisor_contract")
    if not isinstance(frozen, dict) or \
            invocation.supervisor_protocol_path != journal.supervisor_protocol_path or \
            invocation.supervisor_protocol_sha256 != frozen.get("protocol_sha256") or \
            invocation.supervisor_model != frozen.get("model") or \
            invocation.supervisor_effort != frozen.get("effort") or \
            invocation.image_path != journal.image_paths[invocation.case_id] or \
            invocation.source_sha256 != pending["source_sha256"]:
        raise SupervisorAdapterError("Supervisor differs from frozen journal intent")
    root = journal.path.parent.resolve(strict=True)
    if not isinstance(cad_evidence, Path) or not cad_evidence.is_absolute() or \
            not cad_evidence.resolve(strict=True).is_relative_to(root):
        raise SupervisorAdapterError("CAD evidence must remain inside trial run")
    report = verify_owned_cad_evidence(cad_evidence)
    capture = report.get("capture")
    if capture is None:
        raise SupervisorAdapterError("Fenced CAD capture is required")
    try:
        protocol = _bytes(invocation.supervisor_protocol_path,
                          invocation.supervisor_protocol_sha256, 262144).decode("utf-8")
    except UnicodeDecodeError:
        raise SupervisorAdapterError("Supervisor protocol is not UTF-8") from None
    if not protocol.strip():
        raise SupervisorAdapterError("Supervisor protocol is empty")
    source = _bytes(invocation.image_path, invocation.source_sha256, 25_000_000)
    cad_png = _bytes(cad_evidence.parent / capture["file"],
                     capture["sha256"], 20_000_000)
    if _image_mime(cad_png) != "image/png":
        raise SupervisorAdapterError("CAD capture is not PNG")
    raw = client.responses.create(
        model=invocation.supervisor_model,
        reasoning={"effort": invocation.supervisor_effort},
        instructions=protocol,
        input=[{"role": "user", "content": [
            {"type": "input_text", "text": "Compara la imagen fuente y la captura CAD; declara incertidumbres. No ordenes cambios CAD."},
            {"type": "input_image", "image_url":
             f"data:{_image_mime(source)};base64,{base64.b64encode(source).decode('ascii')}",
             "detail": "original"},
            {"type": "input_image", "image_url":
             f"data:image/png;base64,{base64.b64encode(cad_png).decode('ascii')}",
             "detail": "original"}]}],
        max_output_tokens=max_output_tokens,
        store=False,
        stream=False,
    )
    response = raw if isinstance(raw, dict) else raw.model_dump(mode="json")
    receipt = from_response(response)
    if receipt["model"] != invocation.supervisor_model:
        raise SupervisorAdapterError("Supervisor response model differs from frozen scope")
    return response
