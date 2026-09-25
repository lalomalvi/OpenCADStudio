"""The pilot must score abstentions and the wrong short trace separately."""

import unittest

from m7_door_repeatability import assess_observation


class DoorRepeatabilityTests(unittest.TestCase):
    def test_three_observed_points_from_crop(self):
        result = {"schema_version": "ocs-door-observation-1", "status": "observed",
                  "upper_jamb_px": [400, 208], "lower_hinge_px": [400, 600],
                  "leaf_tip_px": [840, 600]}
        status, points = assess_observation(result)
        self.assertEqual(status, "passed_source_oracle")
        self.assertEqual(points, [[1090.0, 501.0], [1090.0, 550.0],
                                  [1145.0, 550.0]])

    def test_short_upper_trace_fails_oracle(self):
        result = {"schema_version": "ocs-door-observation-1", "status": "observed",
                  "upper_jamb_px": [400, 208], "lower_hinge_px": [400, 600],
                  "leaf_tip_px": [552, 208]}
        self.assertEqual(assess_observation(result)[0], "failed_source_oracle")

    def test_abstention_is_not_a_success(self):
        self.assertEqual(assess_observation({"status": "unsupported"}),
                         ("abstained", None))


if __name__ == "__main__":
    unittest.main()
