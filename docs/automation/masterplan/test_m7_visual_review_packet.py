from pathlib import Path
import tempfile
import unittest

from m7_visual_review_packet import arc_points, build, to_pixel


class VisualReviewPacketTests(unittest.TestCase):
    def test_calibration_maps_cad_extents_to_frozen_image_axes(self):
        self.assertEqual(to_pixel((0, 0)), (392.0, 869.0))
        self.assertEqual(to_pixel((13.86, 8.0)), (1285.0, 365.0))

    def test_arc_contains_three_input_points(self):
        points = arc_points((1.0, 0.0), (2 ** -0.5, 2 ** -0.5), (0.0, 1.0))
        self.assertAlmostEqual(points[0][0], 1.0)
        self.assertAlmostEqual(points[-1][1], 1.0)
        self.assertLess(min((x - 2 ** -0.5) ** 2 + (y - 2 ** -0.5) ** 2
                            for x, y in points), 0.001)

    def test_wrong_source_is_rejected_before_output(self):
        allowed = Path(__file__).resolve().parents[3] / "target/mcp-review"
        allowed.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=allowed) as temporary:
            root = Path(temporary)
            source, plan, freeze = (root / name for name in ("source.jpg", "plan.json", "freeze.json"))
            for path in (source, plan, freeze):
                path.write_bytes(b"wrong")
            with self.assertRaisesRegex(ValueError, "SHA differs"):
                build(source, plan, freeze, root / "review")
            self.assertFalse((root / "review").exists())


if __name__ == "__main__":
    unittest.main()
