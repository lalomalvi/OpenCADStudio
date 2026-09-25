"""Ensure scoped CLI evidence cannot become reserved M7 acceptance."""

import unittest

from cli_sample_gates import GateError, evaluate


def summary():
    ids = ("section-stair", "admin-hut", "bedroom-bay",
           "apartment-grid", "foundation-bay")
    cases = []
    for case_id in ids:
        if case_id == "section-stair":
            cases.append({"case_id": case_id, "status": "failed_plan_gate",
                          "external_l4": "not_run"})
        elif case_id == "apartment-grid":
            cases.append({"case_id": case_id, "status": "abstained",
                          "external_l4": "not_run"})
        else:
            cases.append({"case_id": case_id,
                          "status": "passed_scoped_cli_l3_cad_l2",
                          "external_l4": "passed_scoped_l4",
                          "dwg_sha256": "A" * 64,
                          "capture_sha256": "B" * 64,
                          "external_verdict_sha256": "C" * 64})
    return {"schema_version": "m7-five-cli-samples-summary-1",
            "acceptance_m7": False,
            "effective_model": "unverified_by_cli_jsonl",
            "counts": {"passed_scoped_cli_l3_cad_l2": 3,
                       "failed_plan_gate": 1, "abstained": 1},
            "cases": cases}


class CliSampleGateTests(unittest.TestCase):
    def test_positive_scoped_evidence_keeps_reserved_acceptance_pending(self):
        result = evaluate(summary())
        self.assertFalse(result["acceptance_m7"])
        self.assertEqual(result["case_counts"]["partial_scoped"], 3)
        positive = next(case for case in result["cases"]
                        if case["case_id"] == "admin-hut")
        self.assertEqual(positive["m7_acceptance"], "pending")
        self.assertEqual(positive["scoped_evidence"]["G0"],
                         "pending_direct_effective_model")
        self.assertEqual(positive["scoped_evidence"]["G9"],
                         "passed_scoped_autocad")

    def test_missing_external_evidence_rejected(self):
        value = summary()
        value["cases"][1]["external_verdict_sha256"] = None
        with self.assertRaises(GateError):
            evaluate(value)


if __name__ == "__main__":
    unittest.main()
