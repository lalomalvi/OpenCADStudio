import unittest

from mcp_hatch_external_compare import compare


class HatchExternalCompareTests(unittest.TestCase):
    def setUp(self):
        edges = [
            {"Line": {"start": {"x": 20.0, "y": 0.0}, "end": {"x": 24.0, "y": 0.0}}},
            {"Line": {"start": {"x": 24.0, "y": 0.0}, "end": {"x": 24.0, "y": 4.0}}},
            {"Line": {"start": {"x": 24.0, "y": 4.0}, "end": {"x": 20.0, "y": 0.0}}},
        ]
        boundary = {"is_associative": True,
                    "paths": [{"boundary_handles": [100], "edges": edges}]}
        self.source = {"status": "passed", "first_save": {"sha256": "A"},
                       "second_save": {"sha256": "B"},
                       "association": {"hatch_handle": "65", "source_handle": "64",
                                       "initial_boundary": boundary,
                                       "edited_boundary_after_second_reopen": boundary}}
        self.external = {"verdict": "audit_and_census_passed", "source_report_match": True,
                         "input_unchanged": True, "audit_zero_errors_zero_fixes": True,
                         "census_sha256": "C", "input_sha256_before": "A"}
        self.census = [
            "HATCHEDGE|65|0|1|(20.000000000000 0.000000000000 0.000000000000)|(24.000000000000 0.000000000000 0.000000000000)",
            "HATCHEDGE|65|1|1|(24.000000000000 0.000000000000 0.000000000000)|(24.000000000000 4.000000000000 0.000000000000)",
            "HATCHEDGE|65|2|1|(24.000000000000 4.000000000000 0.000000000000)|(20.000000000000 0.000000000000 0.000000000000)",
            "HATCHREF|65|64",
        ]

    def test_frozen_triangle_matches(self):
        result = compare(self.source, self.external, self.census, "C")
        self.assertEqual(result["verdict"], "matched_scoped")
        self.assertEqual(len(result["edges"]), 3)

    def test_modified_edge_fails_even_with_updated_census_hash(self):
        rows = self.census.copy()
        rows[0] = rows[0].replace("24.000000000000", "25.000000000000")
        with self.assertRaisesRegex(ValueError, "end differs"):
            compare(self.source, self.external, rows, "C")

    def test_modified_reference_fails(self):
        rows = self.census.copy()
        rows[-1] = "HATCHREF|65|66"
        with self.assertRaisesRegex(ValueError, "reference differ"):
            compare(self.source, self.external, rows, "C")

    def test_census_hash_mismatch_fails(self):
        with self.assertRaisesRegex(ValueError, "integrity"):
            compare(self.source, self.external, self.census, "WRONG")


if __name__ == "__main__":
    unittest.main()
