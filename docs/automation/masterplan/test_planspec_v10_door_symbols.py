import copy
import unittest

from planspec import PlanError, dry_run


def source():
    return {"region_px": [0, 0, 100, 100], "confidence": 0.9,
            "classification": "measured"}


def plan():
    points = {"left-start": (-2, 0), "left-jamb": (-0.8, 0),
              "hinge": (0, 0), "right-end": (0, -2), "tip": (0, 0.8)}
    nodes = [{"id": name, "x": x, "y": y, "source": source()}
             for name, (x, y) in points.items()]
    lines = [
        {"id": "left-wall", "start": "left-start", "end": "left-jamb",
         "layer": "0", "source": source()},
        {"id": "right-wall", "start": "hinge", "end": "right-end",
         "layer": "0", "source": source()},
        {"id": "door-leaf", "start": "hinge", "end": "tip",
         "layer": "A-DOOR", "source": source()}]
    return {"schema_version": "planspec-10", "units": "m",
            "origin": {"x": 0, "y": 0}, "nodes": nodes, "lines": lines,
            "circles": [], "dimensions": [], "topology": {"contours": []},
            "walls": [], "openings": [], "joins": [], "dimension_bindings": [],
            "dimension_style": {"name": "OCS_METRIC_TEST", "text_height_m": 0.25,
                                "arrow_size_m": 0.08, "gap_m": 0.02,
                                "scale": 1, "measurement_factor": 1},
            "dimension_placements": [], "obstacles": [],
            "door_symbols": [{"id": "swing", "opposite_line_id": "left-wall",
                              "hinge_line_id": "right-wall",
                              "leaf_line_id": "door-leaf", "layer": "A-DOOR",
                              "source": source()}]}


class V10DoorSymbolTests(unittest.TestCase):
    def test_native_arc_and_open_gap(self):
        result = dry_run(plan(), capabilities={"layer_assignment"})
        self.assertTrue(result["executable"])
        self.assertEqual(result["door_symbol_qa"]["status"], "clear")
        self.assertEqual(len(result["commands"]), 4)
        self.assertTrue(result["commands"][-1]["command"].startswith("ARC "))

    def test_short_leaf_rejected_before_commands(self):
        item = plan()
        next(node for node in item["nodes"] if node["id"] == "tip")["y"] = 0.4
        with self.assertRaisesRegex(PlanError, "quarter turn"):
            dry_run(item, capabilities={"layer_assignment"})

    def test_line_bridging_open_gap_blocks_execution(self):
        item = plan()
        item["lines"].append({"id": "bridge", "start": "left-jamb",
                              "end": "hinge", "layer": "0", "source": source()})
        result = dry_run(item, capabilities={"layer_assignment"})
        self.assertFalse(result["executable"])
        self.assertIn({"door_id": "swing", "line_id": "bridge",
                       "kind": "gap_bridge"},
                      result["door_symbol_qa"]["intersections"])

    def test_host_wall_pointing_into_sweep_rejected(self):
        item = plan()
        next(node for node in item["nodes"] if node["id"] == "right-end")["y"] = 2
        with self.assertRaisesRegex(PlanError, "host lines enter"):
            dry_run(item, capabilities={"layer_assignment"})

    def test_physical_obstacle_in_sweep_blocks_execution(self):
        item = plan()
        item["obstacles"].append({"id": "cabinet", "kind": "furniture",
                                  "min_x_m": -0.5, "min_y_m": 0.2,
                                  "max_x_m": -0.3, "max_y_m": 0.4,
                                  "base_z_m": 0, "height_m": 1,
                                  "source": source()})
        result = dry_run(item, capabilities={"layer_assignment"})
        self.assertFalse(result["executable"])
        self.assertEqual(result["door_symbol_qa"]["intersections"],
                         [{"door_id": "swing", "obstacle_id": "cabinet",
                           "kind": "typed_obstacle"}])

    def test_source_line_in_sweep_blocks_execution(self):
        item = plan()
        item["nodes"].extend([
            {"id": "cross-a", "x": -0.5, "y": 0.1, "source": source()},
            {"id": "cross-b", "x": -0.5, "y": 0.6, "source": source()}])
        item["lines"].append({"id": "partition", "start": "cross-a",
                              "end": "cross-b", "layer": "0", "source": source()})
        result = dry_run(item, capabilities={"layer_assignment"})
        self.assertFalse(result["executable"])
        self.assertIn({"door_id": "swing", "line_id": "partition",
                       "kind": "sweep"},
                      result["door_symbol_qa"]["intersections"])


if __name__ == "__main__":
    unittest.main()
