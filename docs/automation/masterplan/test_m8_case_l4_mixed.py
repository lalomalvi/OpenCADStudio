import math
import unittest

from m8_case_l4_mixed import MixedL4Error, angle_close, circle3


class MixedL4GeometryTests(unittest.TestCase):
    def test_arc_center_radius_and_angles_from_three_points(self):
        center, radius, start, end = circle3(
            (0.0, 1.0), (-2 ** -0.5, 2 ** -0.5), (-1.0, 0.0))
        self.assertAlmostEqual(center[0], 0.0)
        self.assertAlmostEqual(center[1], 0.0)
        self.assertAlmostEqual(radius, 1.0)
        self.assertTrue(angle_close(start, math.pi / 2))
        self.assertTrue(angle_close(end, math.pi))

    def test_collinear_arc_rejected(self):
        with self.assertRaisesRegex(MixedL4Error, "collinear"):
            circle3((0.0, 0.0), (1.0, 0.0), (2.0, 0.0))


if __name__ == "__main__":
    unittest.main()
