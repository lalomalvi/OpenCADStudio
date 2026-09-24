"""Adversarial 2D window contract tests, independent of local image artifacts."""

import unittest

from planspec import PlanError, dry_run


SOURCE = {"region_px": [0, 0, 100, 100], "confidence": 1,
          "classification": "measured"}


def fixture():
    positions = {"a": (0, 0), "b": (1, 0), "c": (2, 0), "d": (3, 0),
                 "e": (3, 2), "f": (0, 2), "g": (1, -0.1), "h": (2, -0.1)}
    nodes = [{"id": name, "x": x, "y": y, "source": SOURCE}
             for name, (x, y) in positions.items()]
    def line(name, start, end, layer="0"):
        return {"id": name, "start": start, "end": end, "layer": layer,
                "source": SOURCE}
    lines = [line("host-left", "a", "b"), line("host-right", "c", "d"),
             line("outer", "b", "c", "A-WINDOW"),
             line("inner", "g", "h", "A-WINDOW"),
             line("jamb-left", "b", "g", "A-WINDOW"),
             line("jamb-right", "c", "h", "A-WINDOW"),
             line("side-right", "d", "e"), line("top", "e", "f"),
             line("side-left", "f", "a")]
    return {"schema_version": "planspec-11", "units": "m",
            "origin": {"x": 0, "y": 0}, "nodes": nodes, "lines": lines,
            "circles": [], "dimensions": [],
            "topology": {"contours": [{"id": "outline", "role": "exterior",
                         "line_ids": ["host-left", "outer", "host-right",
                                      "side-right", "top", "side-left"],
                         "source": SOURCE}]},
            "walls": [], "openings": [], "joins": [], "dimension_bindings": [],
            "dimension_style": {"name": "OCS_METRIC", "text_height_m": 0.25,
                                "arrow_size_m": 0.08, "gap_m": 0.02,
                                "scale": 1, "measurement_factor": 1},
            "dimension_placements": [], "obstacles": [], "door_symbols": [],
            "window_symbols": [{"id": "window", "left_wall_line_id": "host-left",
                "right_wall_line_id": "host-right", "outer_rail_line_id": "outer",
                "inner_rail_line_id": "inner", "left_jamb_line_id": "jamb-left",
                "right_jamb_line_id": "jamb-right", "layer": "A-WINDOW",
                "elevation_status": "unverified", "frame_profile_status": "schematic",
                "source": SOURCE}]}


class PlanSpecV11WindowTests(unittest.TestCase):
    def test_valid_window_has_clear_gap_and_four_frame_lines(self):
        result = dry_run(fixture(), capabilities={"layer_assignment"})
        self.assertTrue(result["executable"])
        self.assertEqual(result["window_symbol_qa"]["status"], "clear")
        self.assertEqual(result["window_symbol_qa"]["elevation_status"], "unverified")
        self.assertEqual(len(result["commands"]), 9)

    def test_wall_line_bridging_window_blocks_cad(self):
        plan = fixture()
        plan["lines"].append({"id": "wall-through-glass", "start": "b", "end": "c",
                              "layer": "0", "source": SOURCE})
        result = dry_run(plan, capabilities={"layer_assignment"})
        self.assertFalse(result["executable"])
        self.assertIn("window_symbol_gap_intrusion", result["quality_blockers"])

    def test_crossing_line_blocks_cad(self):
        plan = fixture()
        plan["nodes"].extend([{"id": "cross-a", "x": 1.5, "y": -1,
                               "source": SOURCE},
                              {"id": "cross-b", "x": 1.5, "y": 1,
                               "source": SOURCE}])
        plan["lines"].append({"id": "cross", "start": "cross-a", "end": "cross-b",
                              "layer": "0", "source": SOURCE})
        result = dry_run(plan, capabilities={"layer_assignment"})
        self.assertFalse(result["executable"])
        self.assertEqual(result["window_symbol_qa"]["gap_intersections"][0]["line_id"],
                         "cross")

    def test_skewed_frame_rejected(self):
        plan = fixture()
        next(node for node in plan["nodes"] if node["id"] == "g")["x"] = 1.1
        with self.assertRaises(PlanError):
            dry_run(plan, capabilities={"layer_assignment"})

    def test_missing_reference_rejected(self):
        plan = fixture()
        plan["window_symbols"][0]["right_jamb_line_id"] = "missing"
        with self.assertRaises(PlanError):
            dry_run(plan, capabilities={"layer_assignment"})

    def test_false_elevation_claim_rejected(self):
        plan = fixture()
        plan["window_symbols"][0]["elevation_status"] = "verified"
        with self.assertRaises(PlanError):
            dry_run(plan, capabilities={"layer_assignment"})


if __name__ == "__main__":
    unittest.main()
