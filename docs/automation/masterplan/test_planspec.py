import importlib.util
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("planspec", Path(__file__).with_name("planspec.py"))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


SOURCE = {"region_px": [0, 0, 10, 10], "confidence": 1, "classification": "measured"}


def plan():
    return {"schema_version": "planspec-1", "units": "m", "origin": {"x": 0, "y": 0},
            "nodes": [{"id": "a", "x": 0, "y": 0, "source": SOURCE},
                      {"id": "b", "x": 2.5, "y": 0, "source": SOURCE},
                      {"id": "c", "x": 5, "y": 0, "source": SOURCE}],
            "lines": [{"id": "wall-a", "start": "a", "end": "b", "layer": "0", "source": SOURCE},
                      {"id": "wall-b", "start": "b", "end": "c", "layer": "0", "source": SOURCE}],
            "circles": [], "dimensions": []}


class PlanSpecTests(unittest.TestCase):
    def test_same_plan_has_same_commands_hash_regardless_of_collection_order(self):
        first = module.dry_run(plan())
        reversed_plan = plan()
        reversed_plan["lines"].reverse()
        reversed_plan["nodes"].reverse()
        self.assertEqual(first["commands_sha256"], module.dry_run(reversed_plan)["commands_sha256"])
        self.assertEqual(first["commands"][0]["command"], "LINE 0,0 2.5,0")
        self.assertTrue(first["executable"])

    def test_different_references_do_not_create_false_conflict(self):
        value = plan()
        value["dimensions"] = [
            {"id": "d1", "start": "a", "end": "b", "axis": "x", "reference_type": "face",
             "value": 2.5, "text": "2.50", "source": SOURCE},
            {"id": "d2", "start": "b", "end": "c", "axis": "x", "reference_type": "axis",
             "value": 2.5, "text": "2.50", "source": SOURCE}]
        result = module.dry_run(value)
        self.assertEqual(result["unsupported"], ["native_dimension"])
        self.assertFalse(result["executable"])
        self.assertEqual(result["dimension_graph"]["status"], "satisfied")

    def test_cumulative_dimension_chain_conflict_is_localized(self):
        value = plan()
        value["nodes"][1]["x"] = 1.0009
        value["nodes"][2]["x"] = 2.0018
        value["dimensions"] = [
            {"id": "d-ab", "start": "a", "end": "b", "axis": "x", "reference_type": "face",
             "value": 1, "text": "1.00", "source": SOURCE},
            {"id": "d-ac", "start": "a", "end": "c", "axis": "x", "reference_type": "face",
             "value": 2.0027, "text": "2.0027", "source": SOURCE},
            {"id": "d-bc", "start": "b", "end": "c", "axis": "x", "reference_type": "face",
             "value": 1, "text": "1.00", "source": SOURCE}]
        report = module.analyze_dimension_graph(value)
        self.assertEqual(report["status"], "conflict")
        self.assertEqual(report["conflicts"][0]["dimension_id"], "d-bc")
        with self.assertRaisesRegex(module.PlanError, "Dimension chain conflict: d-bc"):
            module.dry_run(value)
        value["dimensions"][1]["reference_type"] = "axis"
        self.assertEqual(module.analyze_dimension_graph(value)["status"], "satisfied")

    def test_aligned_chain_is_explicitly_indeterminate(self):
        value = plan()
        value["dimensions"] = [{"id": "d-aligned", "start": "a", "end": "b", "axis": "aligned",
                                "reference_type": "face", "value": 2.5, "text": "2.50",
                                "source": SOURCE}]
        report = module.dry_run(value)["dimension_graph"]
        self.assertEqual(report["status"], "indeterminate")
        self.assertEqual(report["unresolved_aligned"], ["d-aligned"])

    def test_label_over_wrong_geometry_is_rejected(self):
        value = plan()
        value["nodes"][1]["x"] = 2.54
        value["dimensions"] = [{"id": "d1", "start": "a", "end": "b", "axis": "x",
                                 "reference_type": "face", "value": 2.5, "text": "2.50",
                                 "source": SOURCE}]
        with self.assertRaisesRegex(module.PlanError, "differs from referenced geometry"):
            module.dry_run(value)

    def test_mixed_units_unknown_fields_and_dangling_references_fail(self):
        value = plan()
        value["units"] = "mm"
        with self.assertRaises(module.PlanError):
            module.validate(value)
        value = plan()
        value["unexpected"] = True
        with self.assertRaises(module.PlanError):
            module.validate(value)
        value = plan()
        value["lines"][0]["end"] = "missing"
        with self.assertRaises(module.PlanError):
            module.validate(value)

    def test_nonfinite_duplicate_and_uncompiled_layer_fail_closed(self):
        value = plan()
        value["nodes"][0]["x"] = float("nan")
        with self.assertRaises(module.PlanError):
            module.validate(value)
        value = plan()
        value["lines"][1]["id"] = "wall-a"
        with self.assertRaises(module.PlanError):
            module.validate(value)
        value = plan()
        value["lines"][0]["layer"] = "A-WALL"
        self.assertEqual(module.dry_run(value)["unsupported"], ["layer_assignment"])
        compiled = module.dry_run(value, capabilities={"layer_assignment"})
        self.assertTrue(compiled["executable"])
        self.assertEqual([item["command"] for item in compiled["execution_steps"]],
                         ["LAYER NEW A-WALL", "CLAYER A-WALL", "LINE 0,0 2.5,0",
                          "CLAYER 0", "LINE 2.5,0 5,0"])


if __name__ == "__main__":
    unittest.main()
