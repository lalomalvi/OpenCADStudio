import copy
import unittest

from pixel_interior_walls import PixelInteriorError, compile_interior_walls


class PixelInteriorTests(unittest.TestCase):
    def setUp(self):
        self.frozen = {
            "expected_walls_px": [[[1090, 366], [1090, 501]],
                                  [[907, 552], [907, 704]],
                                  [[1090, 552], [1090, 688]]],
            "wall_tolerance_px": 10,
            "pixel_calibration": {"left_px": 392, "right_px": 1285,
                                  "top_px": 365, "bottom_px": 869,
                                  "width_m": 13.86, "height_m": 8.0}}
        self.perimeter = {"schema_version": "planspec-1", "units": "m",
                          "nodes": [{"id": f"p{i}"} for i in range(13)],
                          "lines": [{"id": f"edge{i}"} for i in range(13)]}
        self.observed = {"schema_version": "ocs-interior-wall-segments-1",
                         "status": "observed", "confidence": 0.9,
                         "segments": [
                             {"id": f"s{i}", "start_px": pair[0],
                              "end_px": pair[1], "orientation": "vertical",
                              "confidence": 0.9}
                             for i, pair in enumerate(
                                 self.frozen["expected_walls_px"], 1)]}

    def compile(self, observed):
        return compile_interior_walls(observed, perimeter=self.perimeter,
                                      frozen=self.frozen, image_width=1650,
                                      image_height=1275)

    def test_three_source_bound_segments(self):
        plan = self.compile(self.observed)
        self.assertEqual(len(plan["lines"]), 16)
        self.assertEqual(len(plan["nodes"]), 19)

    def test_reject_extra_wall_across_opening(self):
        bad = copy.deepcopy(self.observed)
        bad["segments"].append({"id": "s4", "start_px": [742, 709],
                                "end_px": [903, 709],
                                "orientation": "horizontal", "confidence": .95})
        with self.assertRaises(PixelInteriorError):
            self.compile(bad)

    def test_reject_overlapping_exterior_extension(self):
        bad = copy.deepcopy(self.observed)
        bad["segments"][1]["end_px"] = [907, 968]
        with self.assertRaises(PixelInteriorError):
            self.compile(bad)


if __name__ == "__main__":
    unittest.main()
