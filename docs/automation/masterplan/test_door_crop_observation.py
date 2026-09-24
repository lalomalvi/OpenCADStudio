import unittest

from door_crop_observation import geometry_issues


class DoorGeometryTests(unittest.TestCase):
    def test_short_leaf_is_rejected(self):
        self.assertEqual(
            geometry_issues({"A": [263, 510], "B": [606, 510], "C": [610, 445]}),
            ["leaf_length_differs_from_opening"])

    def test_consistent_leaf_is_observation_only(self):
        self.assertEqual(
            geometry_issues({"A": [263, 510], "B": [606, 510], "C": [610, 167]}),
            [])


if __name__ == "__main__":
    unittest.main()
