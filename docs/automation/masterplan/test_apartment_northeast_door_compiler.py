import unittest
from unittest.mock import patch

from apartment_northeast_door_compiler import NortheastDoorError, compose


def base_plan():
    return {"schema_version": "planspec-11",
            "nodes": [{"id": "upper-start", "x": 10.83346, "y": 7.984127},
                      {"id": "upper-jamb", "x": 10.83346, "y": 5.84127},
                      {"id": "lower-hinge", "x": 10.83346, "y": 5.031746},
                      {"id": "lower-end", "x": 10.83346, "y": 3.996032}],
            "lines": [{"id": "wall1", "start": "upper-start", "end": "upper-jamb",
                       "layer": "0"},
                      {"id": "wall3-upper", "start": "lower-hinge",
                       "end": "lower-end", "layer": "0"}],
            "door_symbols": []}


def observed():
    return {"schema_version": "m7-northeast-door-verdict-2",
            "status": "passed_observation_only", "cad_permitted": True,
            "freeze_sha256": "4DD0850E0FD1EB110DF3C4649E263A1C4E1614A0020514ED8792A1FAAE65F248",
            "events_sha256": "571AD38CFF8FD6942508C631ACD26BA6E0C15C2B7F4B93E452F9D78787A98F2A",
            "observed_original_px": [[1090.5, 500.25], [1089.875, 549.0],
                                     [1144.75, 549.0]]}


class NortheastDoorCompilerTests(unittest.TestCase):
    def test_binds_to_both_existing_hosts_without_changing_base(self):
        base = base_plan()
        with patch("apartment_northeast_door_compiler.dry_run", return_value={
                "executable": True, "unsupported": [], "quality_blockers": [],
                "commands": [None] * 60}):
            plan, _ = compose(base, observed())
        self.assertEqual(len(base["door_symbols"]), 0)
        self.assertEqual(plan["door_symbols"][0]["opposite_line_id"], "wall1")
        self.assertEqual(plan["door_symbols"][0]["hinge_line_id"], "wall3-upper")
        self.assertEqual(plan["lines"][-1]["start"], "lower-hinge")
        self.assertAlmostEqual(plan["nodes"][-1]["x"], 11.642984, places=6)

    def test_rejects_v1_short_upper_trace_as_leaf_before_compiling(self):
        bad = observed()
        bad["observed_original_px"][2] = [1109.0, 501.375]
        with patch("apartment_northeast_door_compiler.dry_run") as compile_mock:
            with self.assertRaises(NortheastDoorError):
                compose(base_plan(), bad)
        compile_mock.assert_not_called()

    def test_rejects_host_revision_before_compiling(self):
        base = base_plan()
        base["nodes"][1]["y"] = 5.7
        with patch("apartment_northeast_door_compiler.dry_run") as compile_mock:
            with self.assertRaisesRegex(NortheastDoorError, "Host gap"):
                compose(base, observed())
        compile_mock.assert_not_called()

    def test_rejects_unfrozen_verdict_before_compiling(self):
        bad = observed()
        bad["events_sha256"] = "0" * 64
        with patch("apartment_northeast_door_compiler.dry_run") as compile_mock:
            with self.assertRaisesRegex(NortheastDoorError, "ineligible"):
                compose(base_plan(), bad)
        compile_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
