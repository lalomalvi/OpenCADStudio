"""Frozen pixel-to-CAD perimeter checks on a synthetic source canvas."""

import copy
import unittest

from pixel_perimeter import PixelPerimeterError, compile_visible_perimeter
from planspec import dry_run


POINTS = [[392, 365], [905, 365], [905, 315], [1090, 315],
          [1090, 365], [1285, 365], [1285, 869], [1090, 869],
          [1090, 975], [905, 975], [905, 869], [450, 869], [392, 708]]
FROZEN = {"expected_vertices_px": POINTS, "vertex_tolerance_px": 12,
          "pixel_calibration": {"left_px": 392, "right_px": 1285,
                                "top_px": 365, "bottom_px": 869,
                                "width_m": 13.86, "height_m": 8.0}}


class PixelPerimeterTests(unittest.TestCase):
    def test_visible_outline_compiles_closed_reference_contour(self):
        observation = {"schema_version": "ocs-visible-perimeter-pixels-1",
                       "status": "traced", "vertices_px": copy.deepcopy(POINTS),
                       "confidence": 0.9}
        plan = compile_visible_perimeter(observation, frozen=FROZEN,
                                         image_width=1650, image_height=1275)
        self.assertEqual((len(plan["nodes"]), len(plan["lines"])), (13, 13))
        self.assertEqual(len(dry_run(plan)["commands"]), 13)
        self.assertEqual(plan["nodes"][0]["x"], 0)
        self.assertEqual(plan["nodes"][0]["y"], 8)
        self.assertEqual(plan["nodes"][6]["x"], 13.86)
        self.assertEqual(plan["nodes"][6]["y"], 0)
        self.assertEqual(plan["lines"][-1]["end"], "p0")

    def test_wrong_corner_rejected_before_cad(self):
        observation = {"schema_version": "ocs-visible-perimeter-pixels-1",
                       "status": "traced", "vertices_px": copy.deepcopy(POINTS),
                       "confidence": 0.9}
        observation["vertices_px"][8][1] -= 30
        with self.assertRaisesRegex(PixelPerimeterError, "frozen visual oracle"):
            compile_visible_perimeter(observation, frozen=FROZEN,
                                      image_width=1650, image_height=1275)
        observation["vertices_px"] = copy.deepcopy(POINTS)
        observation["vertices_px"][2][0] = 1650
        with self.assertRaisesRegex(PixelPerimeterError, "invalid"):
            compile_visible_perimeter(observation, frozen=FROZEN,
                                      image_width=1650, image_height=1275)

    def test_self_crossing_polygon_rejected(self):
        points = [[10, 10], [110, 110], [10, 110], [110, 10]]
        frozen = {"expected_vertices_px": points, "vertex_tolerance_px": 1,
                  "pixel_calibration": {"left_px": 10, "right_px": 110,
                                        "top_px": 10, "bottom_px": 110,
                                        "width_m": 1, "height_m": 1}}
        observation = {"schema_version": "ocs-visible-perimeter-pixels-1",
                       "status": "traced", "vertices_px": points,
                       "confidence": 0.9}
        with self.assertRaisesRegex(PixelPerimeterError, "self-intersects"):
            compile_visible_perimeter(observation, frozen=frozen,
                                      image_width=200, image_height=200)


if __name__ == "__main__":
    unittest.main()
