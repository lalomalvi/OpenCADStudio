import copy
import unittest

from pixel_horizontal_crops import HorizontalCropError, compile_horizontal_crops


class HorizontalCropTests(unittest.TestCase):
    def setUp(self):
        self.base = {"schema_version": "planspec-1", "units": "m",
                     "nodes": [{"id": f"n{i}"} for i in range(19)],
                     "lines": [{"id": f"e{i}"} for i in range(16)]}
        self.cases = []
        specs = [((625, 680, 755, 740), (650, 709), (735, 709)),
                 ((725, 680, 855, 740), (750, 709), (838, 709)),
                 ((895, 680, 965, 740), (915, 709), (948, 709)),
                 ((980, 715, 1110, 775), (996, 744), (1090, 744)),
                 ((890, 785, 1110, 845), (908, 812), (1090, 812))]
        for index, (box, a, b) in enumerate(specs, 1):
            frozen = {"schema_version": "m7-single-wall-crop-freeze-1",
                      "case_id": f"apartment-horizontal-h{index}-v1",
                      "acceptance_m7": False, "scale": 8,
                      "tolerance_original_px": 10,
                      "crop_original_xyxy": list(box),
                      "expected_original_start": list(a),
                      "expected_original_end": list(b)}
            observed = {"schema_version": "ocs-single-wall-crop-1",
                        "status": "observed", "confidence": .9,
                        "start_px": [(a[0]-box[0])*8, (a[1]-box[1])*8],
                        "end_px": [(b[0]-box[0])*8, (b[1]-box[1])*8]}
            self.cases.append((observed, frozen))

    def compile(self, cases):
        return compile_horizontal_crops(cases, base_plan=self.base,
                                        image_width=1650, image_height=1275)

    def test_five_segments(self):
        plan = self.compile(self.cases)
        self.assertEqual(len(plan["lines"]), 21)
        self.assertEqual(len(plan["nodes"]), 29)

    def test_crossed_opening_rejected(self):
        bad = copy.deepcopy(self.cases)
        bad[1][0]["start_px"][0] = (739-725)*8
        bad[1][1]["expected_original_start"] = [739, 709]
        with self.assertRaises(HorizontalCropError):
            self.compile(bad)

    def test_vertical_and_outside_oracle_rejected(self):
        bad = copy.deepcopy(self.cases)
        bad[2][0]["end_px"][1] += 80
        with self.assertRaises(HorizontalCropError):
            self.compile(bad)


if __name__ == "__main__":
    unittest.main()
