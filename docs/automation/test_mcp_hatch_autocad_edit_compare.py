import copy
import unittest

from mcp_hatch_autocad_edit_compare import compare


class HatchAutoCadEditCompareTests(unittest.TestCase):
    def setUp(self):
        edges = [
            {"Line": {"start": {"x": 20.0, "y": 0.0}, "end": {"x": 25.0, "y": 0.0}}},
            {"Line": {"start": {"x": 25.0, "y": 0.0}, "end": {"x": 24.0, "y": 4.0}}},
            {"Line": {"start": {"x": 24.0, "y": 4.0}, "end": {"x": 20.0, "y": 0.0}}},
        ]
        self.source = {"status": "passed", "first_save": {"sha256": "ORIGINAL"},
                       "association": {"hatch_handle": "65", "source_handle": "64",
                                       "edited_boundary_after_second_reopen":
                                           {"paths": [{"boundary_handles": [100],
                                                       "edges": edges}]},
                                       "edited_vertices": [[20.0, 0.0], [25.0, 0.0],
                                                           [24.0, 4.0]]}}
        self.edit = {"source_sha256_before": "ORIGINAL",
                     "source_sha256_after": "ORIGINAL", "copy_sha256_before": "ORIGINAL",
                     "copy_sha256_after": "EDITED", "source_unchanged": True,
                     "copy_changed": True, "status": "edited_copy_needs_external_reopen",
                     "edit_rows": ["EDIT|64|24,0|25,0"],
                     "forced_termination": False, "exit_code": 0}
        self.probe = {"input_sha256_before": "EDITED", "input_sha256_after": "EDITED",
                      "input_unchanged": True, "audit_zero_errors_zero_fixes": True,
                      "verdict": "audit_and_census_passed",
                      "model_types": {"HATCH": 1, "LWPOLYLINE": 1},
                      "census_sha256": "CENSUS"}
        self.rows = [
            "HATCHEDGE|65|0|1|(20.000000000000 0.000000000000 0.000000000000)|(25.000000000000 0.000000000000 0.000000000000)",
            "HATCHEDGE|65|1|1|(25.000000000000 0.000000000000 0.000000000000)|(24.000000000000 4.000000000000 0.000000000000)",
            "HATCHEDGE|65|2|1|(24.000000000000 4.000000000000 0.000000000000)|(20.000000000000 0.000000000000 0.000000000000)",
            "HATCHREF|65|64",
            "PLINEVERTEX|64|0|(20.000000000000 0.000000000000 0.000000000000)",
            "PLINEVERTEX|64|1|(25.000000000000 0.000000000000 0.000000000000)",
            "PLINEVERTEX|64|2|(24.000000000000 4.000000000000 0.000000000000)",
        ]

    def run_compare(self, rows=None, edit=None, probe=None):
        return compare(self.source, edit or self.edit, probe or self.probe,
                       rows or self.rows, "CENSUS", "ORIGINAL", "EDITED")

    def test_external_edit_and_hatch_match(self):
        result = self.run_compare()
        self.assertEqual((result["matched_edges"], result["matched_vertices"]), (3, 3))

    def test_unchanged_source_required(self):
        edit = copy.deepcopy(self.edit)
        edit["source_sha256_after"] = "CHANGED"
        with self.assertRaisesRegex(ValueError, "untouched source"):
            self.run_compare(edit=edit)

    def test_modified_hatch_edge_rejected(self):
        rows = self.rows.copy()
        rows[0] = rows[0].replace("25.000000000000", "26.000000000000")
        with self.assertRaisesRegex(ValueError, "edge 0 differs"):
            self.run_compare(rows=rows)

    def test_modified_polyline_vertex_rejected(self):
        rows = self.rows.copy()
        rows[5] = rows[5].replace("25.000000000000", "26.000000000000")
        with self.assertRaisesRegex(ValueError, "vertex 1 differs"):
            self.run_compare(rows=rows)


if __name__ == "__main__":
    unittest.main()
