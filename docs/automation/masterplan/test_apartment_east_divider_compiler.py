import unittest
from unittest.mock import patch

from apartment_east_divider_compiler import EastDividerError, compose


def base_plan():
    return {"schema_version": "planspec-11", "nodes": [
        {"id": "w0", "x": 10.83346, "y": 5.031746},
        {"id": "w1", "x": 10.83346, "y": 2.873016},
        {"id": "e0", "x": 13.891041, "y": 8.095238},
        {"id": "e1", "x": 13.891041, "y": -0.015873}],
        "lines": [{"id": "wall3", "start": "w0", "end": "w1", "layer": "0"},
                  {"id": "edge5", "start": "e0", "end": "e1", "layer": "0"}],
        "topology": {"contours": [{"line_ids": ["edge5"]}]}}


def observed():
    return {"schema_version": "m7-east-divider-verdict-1",
            "status": "passed_observation_only", "cad_permitted": True,
            "observed_original_px": [[1090.375, 617.25], [1282.75, 617.25]]}


class EastDividerCompilerTests(unittest.TestCase):
    def test_splits_both_hosts_and_preserves_original(self):
        original = base_plan()
        with patch("apartment_east_divider_compiler.dry_run", return_value={
                "executable": True, "unsupported": [], "quality_blockers": [],
                "commands": [None] * 58}) as compile_mock:
            plan, _ = compose(original, observed())
        self.assertEqual([line["id"] for line in plan["lines"]],
                         ["wall3-upper", "wall3-lower", "edge5-upper",
                          "edge5-lower", "east-bedroom-divider"])
        self.assertEqual(plan["topology"]["contours"][0]["line_ids"],
                         ["edge5-upper", "edge5-lower"])
        self.assertEqual([line["id"] for line in original["lines"]], ["wall3", "edge5"])
        self.assertEqual(compile_mock.call_count, 1)

    def test_rejects_observation_outside_frozen_region_before_compiling(self):
        bad = observed()
        bad["observed_original_px"][1] = [1250, 617]
        with patch("apartment_east_divider_compiler.dry_run") as compile_mock:
            with self.assertRaisesRegex(EastDividerError, "Divider endpoints"):
                compose(base_plan(), bad)
        compile_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
