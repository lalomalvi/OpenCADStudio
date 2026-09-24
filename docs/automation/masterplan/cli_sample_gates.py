"""Scope-aware gate matrix for already verified local CLI development samples.

This cannot promote the reserved M7 gate set: model identity, independent
oracles, full-plan fidelity, baseline and human review are absent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from summarize_cli_samples import CASES, summarize


class GateError(ValueError):
    pass


def evaluate(summary: dict) -> dict:
    if summary.get("schema_version") != "m7-five-cli-samples-summary-1" or \
            summary.get("acceptance_m7") is not False or \
            summary.get("effective_model") != "unverified_by_cli_jsonl" or \
            summary.get("counts") != {
                "passed_scoped_cli_l3_cad_l2": 3,
                "failed_plan_gate": 1, "abstained": 1} or \
            not isinstance(summary.get("cases"), list) or \
            {case.get("case_id") for case in summary["cases"]} != set(CASES):
        raise GateError("Verified five-case summary is required")
    cases = []
    for case in summary["cases"]:
        status = case["status"]
        if status == "passed_scoped_cli_l3_cad_l2":
            if case.get("external_l4") != "passed_scoped_l4" or \
                    not all(case.get(key) for key in
                            ("dwg_sha256", "capture_sha256", "external_verdict_sha256")):
                raise GateError("CAD and external evidence missing on positive case")
            scoped = {"G1": "partial_single_local_attempt",
                      "G2": "passed_scoped_assistant_oracle",
                      "G3": "passed_scoped_rectangle",
                      "G4": "passed_scoped_line_units_layer",
                      "G5": "passed_scoped_save_audit",
                      "G6": "capture_present_human_pending",
                      "G7": "passed_scoped_owned_gui_exit",
                      "G8": "passed_scoped_hashes_reverified",
                      "G9": "passed_scoped_autocad"}
            disposition = "partial_scoped"
        elif status == "failed_plan_gate":
            if case.get("external_l4") != "not_run":
                raise GateError("Failed metric case must not have L4")
            scoped = {"G2": "failed_frozen_metric", "G3": "not_run",
                      "G4": "not_run", "G5": "not_run", "G6": "not_run",
                      "G7": "not_run", "G8": "source_and_events_verified",
                      "G9": "not_run"}
            disposition = "failed"
        elif status == "abstained":
            if case.get("external_l4") != "not_run":
                raise GateError("Abstention must not have L4")
            scoped = {"G2": "abstained", "G3": "not_run", "G4": "not_run",
                      "G5": "not_run", "G6": "not_run", "G7": "not_run",
                      "G8": "source_and_events_verified", "G9": "not_run"}
            disposition = "abstained"
        else:
            raise GateError("Unexpected case disposition")
        scoped["G0"] = "pending_direct_effective_model"
        scoped["G1"] = "partial_single_local_attempt"
        scoped["G10"] = "pending_comparable_direct_usage"
        cases.append({"case_id": case["case_id"], "disposition": disposition,
                      "scoped_evidence": scoped,
                      "m7_acceptance": "pending" if disposition == "partial_scoped"
                                       else disposition})
    return {"schema_version": "m7-five-cli-gates-1", "acceptance_m7": False,
            "scope": "development_rectangles_only",
            "case_counts": {"partial_scoped": 3, "failed": 1, "abstained": 1},
            "cases": cases,
            "remaining": ["direct_provider_identity_and_usage",
                          "independent_oracle", "full_plan_fidelity",
                          "baseline_candidate_comparison", "human_L5_review"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_map = json.loads(args.source_map.read_text(encoding="utf-8"))
    verified = summarize(args.root.resolve(strict=True),
                         args.external_root.resolve(strict=True),
                         {key: Path(value).resolve(strict=True)
                          for key, value in source_map.items()})
    value = evaluate(verified)
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(value, target, indent=2, sort_keys=True)
        target.write("\n")
    print(json.dumps(value["case_counts"], sort_keys=True))


if __name__ == "__main__":
    main()
