"""One reserved Luna -> PlanSpec -> CAD -> supervisor callback.

The CAD and supervisor adapters are injected. They must be constructed before
reservation and never retry an operation whose outcome is unknown. No private
model text or image is written by this module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from luna_once_adapter import request_luna_once
from luna_planspec_gate import interpret_response
from provider_response_receipt import from_response
from reserved_runner import Invocation, Observation, run_once
from reserved_trial import TrialJournal


class PipelineError(ValueError):
    pass


def run_reserved_pipeline(
    journal: TrialJournal, arm: str, case_id: str, repetition: int,
    request_id: str, *, luna_client: object,
    cad_execute: Callable[[Invocation, dict], Path],
    supervisor_request: Callable[[Invocation, Path], dict] | None,
    allowed_versions: frozenset[str], max_commands: int = 1000,
) -> dict:
    """Reserve once and run the prebuilt adapters in a fixed order.

    A CAD executor must bind commands to the selected owned GUI/document and
    use stable request IDs; this wrapper cannot certify an injected adapter.
    Any exception after reserve consumes the slot as uncertain via run_once.
    """
    if getattr(luna_client, "max_retries", None) != 0 or \
            not callable(cad_execute) or \
            (supervisor_request is not None and not callable(supervisor_request)):
        raise PipelineError("Pipeline adapters are not ready before reservation")

    def invoke(invocation: Invocation) -> Observation:
        raw = request_luna_once(journal, invocation, client=luna_client)
        parsed = interpret_response(raw, allowed_versions=allowed_versions,
                                    max_commands=max_commands)
        receipt = parsed["provider_receipt"]
        if receipt["model"] != invocation.requested_model:
            raise PipelineError("Luna response model differs from frozen request")
        evidence = cad_execute(invocation, parsed["compiled"])
        if not isinstance(evidence, Path):
            raise PipelineError("CAD adapter did not return an evidence path")
        supervisor_raw = (supervisor_request(invocation, evidence)
                          if supervisor_request is not None else None)
        supervisor = (from_response(supervisor_raw)
                      if supervisor_raw is not None else None)
        return Observation(receipt["model"], raw["id"], receipt["usage"],
                           supervisor["usage"] if supervisor else None,
                           evidence, raw, supervisor_raw)

    return run_once(journal, arm, case_id, repetition, request_id, invoke)
