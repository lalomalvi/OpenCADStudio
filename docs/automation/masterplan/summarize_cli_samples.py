"""Reverify the five local development samples without calling a model or CAD."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cli_development_l4 import assess
from owned_cad_executor import verify_owned_cad_evidence
from reserved_trial import _file_sha


CASES = ("section-stair", "admin-hut", "bedroom-bay", "apartment-grid",
         "foundation-bay")
FROZEN_PROTOCOL_SHA256 = "52AC53F3CD2EE2C063677B6CFCF7EB555EA80AE24BCA91A2839B5B7004EFBF70"


def summarize(root: Path, external_root: Path, source_paths: dict[str, Path]) -> dict:
    protocol = root / "five-sample-protocol-frozen.md"
    protocol_sha = _file_sha(protocol)
    if protocol_sha != FROZEN_PROTOCOL_SHA256:
        raise ValueError("Frozen local protocol differs")
    records = []
    for case_id in CASES:
        run = root / case_id
        frozen = json.loads((run / "freeze.json").read_text(encoding="utf-8"))
        report_path = run / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        events = [json.loads(line) for line in
                  (run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        if frozen["case_id"] != case_id or report["case_id"] != case_id or \
                frozen["protocol_sha256"] != protocol_sha or \
                _file_sha(source_paths[case_id]) != frozen["source_sha256"] or \
                _file_sha(run / "prompt.txt") != frozen["prompt_sha256"] or \
                report["source_sha256"] != frozen["source_sha256"] or \
                report["prompt_sha256"] != frozen["prompt_sha256"] or \
                report["freeze_sha256"] != _file_sha(run / "freeze.json") or \
                report["events_sha256"] != _file_sha(run / "events.jsonl") or \
                events[0].get("type") != "thread.started" or \
                events[-1].get("type") != "turn.completed":
            raise ValueError(f"{case_id}: frozen input or CLI evidence differs")
        usage = events[-1].get("usage")
        if not isinstance(usage, dict):
            raise ValueError(f"{case_id}: CLI usage missing")
        item = {"case_id": case_id, "status": report["status"],
                "source_sha256": frozen["source_sha256"],
                "prompt_sha256": frozen["prompt_sha256"],
                "freeze_sha256": _file_sha(run / "freeze.json"),
                "events_sha256": _file_sha(run / "events.jsonl"),
                "report_sha256": _file_sha(report_path),
                "usage_cli_aggregate": usage, "external_l4": "not_run"}
        if report["status"] == "passed_scoped_cli_l3_cad_l2":
            files = list((run / "cad").glob("*.json"))
            if len(files) != 1:
                raise ValueError(f"{case_id}: CAD evidence count differs")
            cad = verify_owned_cad_evidence(files[0])
            if _file_sha(files[0]) != report["cad_evidence_sha256"] or \
                    cad["dwg"]["sha256"] != report["dwg_sha256"] or \
                    cad["capture"]["sha256"] != report["capture_sha256"] or \
                    report["gui_exited"] is not True:
                raise ValueError(f"{case_id}: CAD evidence differs")
            probe = json.loads((run / "autocad-stdout.json").read_text(encoding="utf-8"))
            external_path = external_root / probe["run_id"] / "report.json"
            result = assess(run / "model-plan.json", files[0], external_path)
            saved = json.loads((run / "external-verdict.json").read_text(encoding="utf-8"))
            if result != saved or result["status"] != "passed_scoped_l4" or \
                    result["geometry_matches"] != 4:
                raise ValueError(f"{case_id}: external geometry differs")
            item.update({"external_l4": "passed_scoped_l4",
                         "dwg_sha256": cad["dwg"]["sha256"],
                         "capture_sha256": cad["capture"]["sha256"],
                         "external_verdict_sha256": _file_sha(run / "external-verdict.json")})
        elif report["status"] not in {"failed_plan_gate", "abstained"}:
            raise ValueError(f"{case_id}: unrecognized disposition")
        records.append(item)
    counts = {status: sum(item["status"] == status for item in records)
              for status in ("passed_scoped_cli_l3_cad_l2", "failed_plan_gate",
                             "abstained")}
    if counts != {"passed_scoped_cli_l3_cad_l2": 3,
                  "failed_plan_gate": 1, "abstained": 1}:
        raise ValueError("Five-case count differs from frozen run")
    return {"schema_version": "m7-five-cli-samples-summary-1",
            "acceptance_m7": False, "model_requested": "gpt-6-luna",
            "effective_model": "unverified_by_cli_jsonl",
            "frozen_protocol_sha256": protocol_sha,
            "counts": counts, "cases": records,
            "m7_gates": {f"G{i}": "pending" for i in range(11)}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_map = json.loads(args.source_map.read_text(encoding="utf-8"))
    result = summarize(args.root.resolve(strict=True),
                       args.external_root.resolve(strict=True),
                       {key: Path(value).resolve(strict=True)
                        for key, value in source_map.items()})
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(result, target, sort_keys=True, indent=2)
        target.write("\n")
    print(json.dumps(result["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
