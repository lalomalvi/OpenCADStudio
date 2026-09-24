"""Check frozen six-span observations before any native CAD mutation."""

import copy
import unittest

from measurement_axis_chain import AxisChainError, compile_bottom_chain
from planspec import PlanError, dry_run


FROZEN = {"expected_widths_m": [2.58, 2.85, 2.58, 2.85, 1.0, 2.0]}


def observation():
    return {"schema_version": "ocs-bottom-chain-1", "status": "measured",
            "units": "m", "widths_m": [2.58, 2.85, 2.58, 2.85, 1.0, 2.0],
            "source_regions": [[100 * i, 200, 100 * i + 30, 220]
                               for i in range(6)], "confidence": 0.9}


class AxisChainTests(unittest.TestCase):
    def test_six_spans_and_total_compile_as_native_dimensions(self):
        plan = compile_bottom_chain(observation(), frozen=FROZEN,
                                    image_width=1000, image_height=500)
        result = dry_run(plan)
        self.assertTrue(result["executable"])
        self.assertEqual(len(plan["dimensions"]), 7)
        self.assertEqual(len(result["commands"]), 11)
        self.assertEqual(plan["dimensions"][-1]["value"], 13.86)
        self.assertEqual(result["dimension_graph"]["status"], "satisfied")
        self.assertEqual(plan["walls"][0]["source"]["classification"], "inferred")

    def test_wrong_span_and_disordered_source_fail_before_cad(self):
        bad = copy.deepcopy(observation())
        bad["widths_m"][1] = 2.9
        with self.assertRaisesRegex(AxisChainError, "frozen criterion"):
            compile_bottom_chain(bad, frozen=FROZEN,
                                 image_width=1000, image_height=500)
        bad = copy.deepcopy(observation())
        bad["source_regions"][1][0] = 0
        with self.assertRaisesRegex(AxisChainError, "ordered"):
            compile_bottom_chain(bad, frozen=FROZEN,
                                 image_width=1000, image_height=500)

    def test_large_text_style_keeps_geometry_and_compiles(self):
        original = compile_bottom_chain(observation(), frozen=FROZEN,
                                        image_width=1000, image_height=500)
        variant = compile_bottom_chain(
            observation(), frozen={**FROZEN, "style_variant": "legible_25cm_v1"},
            image_width=1000, image_height=500)
        self.assertEqual(variant["nodes"], original["nodes"])
        self.assertEqual(variant["dimensions"], original["dimensions"])
        self.assertEqual(variant["dimension_style"]["text_height_m"], 0.25)
        self.assertTrue(dry_run(variant)["executable"])
        fixed = compile_bottom_chain(
            observation(), frozen={**FROZEN, "style_variant": "legible_fixed_25cm_v2"},
            image_width=1000, image_height=500)
        self.assertEqual(fixed["dimension_style"]["decimal_format"], "fixed_2")
        commands = [item["command"] for item in dry_run(fixed)["execution_steps"]]
        self.assertIn("DIMSTYLE SET OCS_AXIS_METRIC_FIXED dimdec 2", commands)
        self.assertIn("DIMSTYLE SET OCS_AXIS_METRIC_FIXED dimzin 0", commands)
        bad = copy.deepcopy(fixed)
        bad["dimension_style"]["decimal_format"] = "fixed_3"
        with self.assertRaises(PlanError):
            dry_run(bad)


if __name__ == "__main__":
    unittest.main()
