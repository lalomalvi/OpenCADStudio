import copy
import unittest

from measurement_axis_chain import compile_bottom_chain
from planspec import PlanError, dry_run


class IntegratedAxisChainTests(unittest.TestCase):
    def setUp(self):
        widths = [2.58, 2.85, 2.58, 2.85, 1.0, 2.0]
        source_regions = [[100+index*30, 100, 125+index*30, 120]
                          for index in range(6)]
        observation = {"schema_version": "ocs-bottom-chain-1",
                       "status": "measured", "units": "m",
                       "widths_m": widths, "source_regions": source_regions,
                       "confidence": .9}
        self.plan = compile_bottom_chain(observation,
                    frozen={"expected_widths_m": widths,
                            "style_variant": "legible_fixed_25cm_v2"},
                    image_width=500, image_height=200)
        source = {"region_px": [100, 100, 125, 120],
                  "confidence": .9, "classification": "inferred"}
        self.plan["nodes"].extend([{"id": "architecture-a", "x": 1, "y": 2,
                                    "source": source},
                                   {"id": "architecture-b", "x": 2, "y": 2,
                                    "source": source}])
        self.plan["lines"].append({"id": "architecture-line",
                                    "start": "architecture-a",
                                    "end": "architecture-b", "layer": "0",
                                    "source": source})

    def test_native_dimensions_coexist_with_separated_architecture(self):
        result = dry_run(self.plan)
        self.assertTrue(result["executable"])
        self.assertEqual(result["dimension_compilation"]["status"],
                         "compiled_multi_axis_spans")
        self.assertEqual(len(result["commands"]), 12)

    def test_near_architecture_rejects_dimensions(self):
        bad = copy.deepcopy(self.plan)
        for node in bad["nodes"]:
            if node["id"].startswith("architecture-"):
                node["y"] = 1.0
        result = dry_run(bad)
        self.assertFalse(result["executable"])
        self.assertIn("native_dimension", result["unsupported"])

    def test_reference_layer_is_hidden_after_dimensions(self):
        self.plan["walls"][0]["layer"] = "OCS_DIM_REF"
        result = dry_run(self.plan, capabilities={"layer_assignment"})
        self.assertTrue(result["executable"])
        self.assertEqual(result["execution_steps"][-1]["command"],
                         "LAYER OFF OCS_DIM_REF")

    def test_architecture_on_reference_layer_is_rejected(self):
        self.plan["walls"][0]["layer"] = "OCS_DIM_REF"
        self.plan["lines"][0]["layer"] = "OCS_DIM_REF"
        with self.assertRaises(PlanError):
            dry_run(self.plan, capabilities={"layer_assignment"})


if __name__ == "__main__":
    unittest.main()
