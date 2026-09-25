"""Portable synthetic evidence tests for scoped independent L4 binding."""

import json
from pathlib import Path
import tempfile
import unittest

from external_l4_verdict import ExternalVerdictError, assess_synthetic_wall
from reserved_runner import Observation, run_once
from reserved_trial import _file_sha
from test_provider_response_receipt import response
from test_reserved_runner import USAGE
import test_supervisor_once_adapter


FIXTURE = Path(__file__).with_name("fixtures") / "synthetic-wall.planspec.json"


class ExternalL4VerdictTests(unittest.TestCase):
    def setup_case(self, directory):
        journal, evidence, _, _ = test_supervisor_once_adapter.SupervisorOnceAdapterTests() \
            .setup_case(directory)
        cad = json.loads(evidence.read_text(encoding="utf-8"))
        handles = {f"edge-{i}": f"{i + 1:X}" for i in range(4)}
        cad.update({"added_entities": 4, "handles_by_id": handles})
        evidence.write_text(json.dumps(cad), encoding="utf-8")
        generator = response("resp-generator")
        supervisor = response("resp-supervisor", "gpt-6-sol")
        run_once(journal, "baseline", "case-0", 1, "request-1",
                 lambda _: Observation("gpt-6-luna", generator["id"], USAGE, USAGE,
                                       evidence, generator, supervisor))
        run_root = journal.path.parent
        pipeline_path = run_root.parent / "report.json"
        pipeline_path.write_text(json.dumps({
            "schema_version": "m7-reserved-pipeline-l2-1", "status": "passed",
            "cad_evidence_sha256": _file_sha(evidence),
            "dwg_sha256": cad["dwg"]["sha256"],
            "fixture_sha256": _file_sha(FIXTURE)}), encoding="utf-8")
        bridge_path = run_root.parent / "bridge.json"
        bridge_path.write_text(json.dumps({
            "schema_version": "m7-l4-bridge-1", "status": "passed",
            "negative_seed": None,
            "source_pipeline_report_sha256": _file_sha(pipeline_path),
            "source_cad_evidence_sha256": _file_sha(evidence),
            "verified_output": {"sha256": cad["dwg"]["sha256"]},
            "planspec": {"fixture": FIXTURE.name, "fixture_sha256": _file_sha(FIXTURE),
                         "handles_by_id": handles}}), encoding="utf-8")
        external_path = run_root.parent / "autocad.json"
        external = {"schema_version": "mcp-autocad-audit-l4-17",
                    "product": "AutoCAD Core Console", "executable_version": "synthetic-1",
                    "executable_sha256": "A" * 64,
                    "input_sha256_before": cad["dwg"]["sha256"],
                    "input_sha256_after": cad["dwg"]["sha256"],
                    "input_unchanged": True, "audit_zero_errors_zero_fixes": True,
                    "census_done": True, "forced_termination": False,
                    "exit_code": 0, "verdict": "audit_and_census_passed",
                    "insunits": 6, "unit_match": True, "model_census_count": 4,
                    "model_types": {"LINE": 4},
                    "geometry_comparison": [{"planspec_id": key, "handle": value,
                                              "matched_1e_6": True}
                                             for key, value in handles.items()],
                    "source_report_match": True, "geometry_source_valid": True,
                    "wall_model_count_match": True,
                    "semantic_verdict": "matched_scoped"}
        external_path.write_text(json.dumps(external), encoding="utf-8")
        return journal, bridge_path, external_path, external

    def test_positive_scoped_l4_keeps_all_m7_gates_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, bridge, autocad, _ = self.setup_case(directory)
            result = assess_synthetic_wall(journal, "baseline", "case-0", 1,
                                           bridge_path=bridge, autocad_path=autocad)
            self.assertEqual(result["status"], "passed_scoped_l4")
            self.assertEqual(result["geometry_matches"], 4)
            self.assertEqual(set(result["m7_gates"].values()), {"pending"})

    def test_one_wrong_geometry_fails_without_reinterpreting_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, bridge, autocad, external = self.setup_case(directory)
            external["geometry_comparison"][0]["matched_1e_6"] = False
            autocad.write_text(json.dumps(external), encoding="utf-8")
            result = assess_synthetic_wall(journal, "baseline", "case-0", 1,
                                           bridge_path=bridge, autocad_path=autocad)
            self.assertEqual(result["status"], "failed_scoped_l4")
            self.assertEqual(result["geometry_matches"], 3)
            self.assertIn("external_geometry_or_provenance_differs", result["blockers"])

    def test_bridge_with_changed_source_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, bridge, autocad, _ = self.setup_case(directory)
            value = json.loads(bridge.read_text(encoding="utf-8"))
            value["source_cad_evidence_sha256"] = "0" * 64
            bridge.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ExternalVerdictError):
                assess_synthetic_wall(journal, "baseline", "case-0", 1,
                                      bridge_path=bridge, autocad_path=autocad)


if __name__ == "__main__":
    unittest.main()
