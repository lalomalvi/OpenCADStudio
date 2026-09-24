"""Seeded persistence defects for the synthetic native-geometry comparator."""

import copy
import unittest

from mcp_isolated_smoke import same_geometry


class GeometryQATests(unittest.TestCase):
    def test_coordinate_radius_angle_and_closed_flag_defects_fail(self):
        original = {"Arc": {"radius": 5.0, "start_angle": 0.0, "end_angle": 1.5},
                    "Polyline": {"vertices": [[0, 0], [4, 0], [4, 4]], "is_closed": True}}
        self.assertTrue(same_geometry(original, copy.deepcopy(original)))
        for category, key, replacement in (("Arc", "radius", 5.01),
                                           ("Arc", "end_angle", 1.501),
                                           ("Polyline", "is_closed", False),
                                           ("Polyline", "vertices", [[0, 0], [4, 0]])):
            with self.subTest(category=category, key=key):
                changed = copy.deepcopy(original)
                changed[category][key] = replacement
                self.assertFalse(same_geometry(original, changed))

    def test_small_roundtrip_noise_passes_but_nonfinite_fails(self):
        self.assertTrue(same_geometry({"x": 1.0}, {"x": 1.0 + 5e-7}))
        self.assertFalse(same_geometry({"x": 1.0}, {"x": float("nan")}))


if __name__ == "__main__":
    unittest.main()
