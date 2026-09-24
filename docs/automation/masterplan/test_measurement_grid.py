"""Measurement contract rejects invented or source-free two-bay geometry."""

import copy
import unittest

from cli_development_trial import check_explicit_line_graph
from measurement_grid import MeasurementGridError, compile_five_bay, compile_two_bay


FROZEN = {"expected_left_width_m": 2.0,
          "expected_right_width_m": 3.0,
          "expected_height_m": 1.5}
VERTICES = [[0, 0], [2, 0], [5, 0], [5, 1.5], [2, 1.5], [0, 1.5]]
EDGES = [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 0], [1, 4]]


def measurement():
    return {"schema_version": "ocs-measurements-two-bay-1",
            "status": "measured", "units": "m",
            "left_width_m": 2.0, "right_width_m": 3.0,
            "height_m": 1.5, "confidence": 0.9,
            "source_regions": {"left_width_px": [100, 400, 450, 460],
                               "right_width_px": [440, 400, 800, 460],
                               "height_px": [0, 100, 100, 390]}}


class MeasurementGridTests(unittest.TestCase):
    def test_five_bay_compiles_connected_metric_grid(self):
        value = {"schema_version": "ocs-measurements-five-bay-1",
                 "status": "measured", "units": "m",
                 "bay_widths_m": [3.5, 4.0, 4.0, 3.5, 2.85],
                 "depth_m": 3.7, "confidence": 0.9,
                 "source_regions": {**{f"width_{i}_px": [i * 100, 20, i * 100 + 40, 45]
                                       for i in range(1, 6)},
                                    "depth_px": [700, 200, 730, 250]}}
        frozen = {"expected_widths_m": [3.5, 4.0, 4.0, 3.5, 2.85],
                  "expected_depth_m": 3.7}
        plan = compile_five_bay(value, frozen=frozen,
                                image_width=1000, image_height=500)
        self.assertEqual((len(plan["nodes"]), len(plan["lines"])), (12, 16))
        self.assertEqual(plan["nodes"][-1]["x"], 17.85)
        self.assertEqual(plan["nodes"][-1]["y"], 3.7)
        self.assertEqual(plan["lines"][-1]["end"], "n1_5")
        bad = copy.deepcopy(value)
        bad["bay_widths_m"][2] = 4.1
        with self.assertRaisesRegex(MeasurementGridError, "frozen criterion"):
            compile_five_bay(bad, frozen=frozen,
                             image_width=1000, image_height=500)
        bad = copy.deepcopy(value)
        bad["source_regions"]["depth_px"][2] = 1001
        with self.assertRaisesRegex(MeasurementGridError, "escapes"):
            compile_five_bay(bad, frozen=frozen,
                             image_width=1000, image_height=500)

    def test_compiles_two_closed_reference_regions(self):
        plan = compile_two_bay(measurement(), frozen=FROZEN,
                               image_width=1200, image_height=800)
        self.assertEqual(len(plan["lines"]), 7)
        self.assertEqual(len(check_explicit_line_graph(
            plan, 1200, 800, VERTICES, EDGES, 2)["commands"]), 7)
        self.assertEqual({item["source"]["classification"]
                          for item in plan["lines"]}, {"inferred"})

    def test_wrong_measurement_rejected_before_cad(self):
        value = measurement()
        value["right_width_m"] = 3.2
        with self.assertRaises(MeasurementGridError):
            compile_two_bay(value, frozen=FROZEN,
                            image_width=1200, image_height=800)

    def test_source_region_outside_image_rejected(self):
        value = measurement()
        value["source_regions"]["height_px"][3] = 801
        with self.assertRaises(MeasurementGridError):
            compile_two_bay(value, frozen=FROZEN,
                            image_width=1200, image_height=800)

    def test_duplicate_or_missing_contract_field_rejected(self):
        value = copy.deepcopy(measurement())
        del value["source_regions"]["right_width_px"]
        with self.assertRaises(MeasurementGridError):
            compile_two_bay(value, frozen=FROZEN,
                            image_width=1200, image_height=800)


if __name__ == "__main__":
    unittest.main()
