import importlib.util
import json
import unittest
from copy import deepcopy
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
        self.assertEqual(first["geometry_qa"], module.dry_run(reversed_plan)["geometry_qa"])
        self.assertEqual(first["commands"][0]["command"], "LINE 0,0 2.5,0")
        self.assertEqual(first["execution_steps"][0]["command"], "SETVAR INSUNITS 6")
        self.assertEqual(first["dwg_unit_profile"], {"plan_units": "m", "insunits": 6})
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
                         ["SETVAR INSUNITS 6", "LAYER NEW A-WALL", "CLAYER A-WALL", "LINE 0,0 2.5,0",
                          "CLAYER 0", "LINE 2.5,0 5,0"])

    def test_geometry_qa_detects_reversed_duplicate_overlap_and_open_ends(self):
        value = plan()
        value["lines"].extend([
            {"id": "wall-reversed", "start": "b", "end": "a", "layer": "0", "source": SOURCE},
            {"id": "wall-overlap", "start": "a", "end": "c", "layer": "0", "source": SOURCE}])
        value["circles"] = [
            {"id": "circle-a", "center": "a", "radius": 1, "layer": "0", "source": SOURCE},
            {"id": "circle-b", "center": "a", "radius": 1, "layer": "0", "source": SOURCE}]
        report = module.dry_run(value)["geometry_qa"]
        self.assertEqual(report["status"], "review_required")
        self.assertIn(["wall-a", "wall-reversed"], report["duplicate_lines"])
        self.assertIn(["wall-a", "wall-overlap"], report["overlapping_lines"])
        self.assertEqual(report["duplicate_circles"], [["circle-a", "circle-b"]])
        self.assertEqual(report["open_line_endpoints"], [])

    def test_geometry_qa_separates_crossing_t_junction_and_open_chain(self):
        value = plan()
        value["nodes"].extend([
            {"id": "d", "x": 1, "y": -1, "source": SOURCE},
            {"id": "e", "x": 1, "y": 1, "source": SOURCE},
            {"id": "f", "x": 1.25, "y": 1, "source": SOURCE},
            {"id": "g", "x": 1.25, "y": 0, "source": SOURCE}])
        value["lines"].extend([
            {"id": "cross", "start": "d", "end": "e", "layer": "0", "source": SOURCE},
            {"id": "tee", "start": "g", "end": "f", "layer": "0", "source": SOURCE}])
        report = module.analyze_geometry(value)
        self.assertIn(["cross", "wall-a"], report["interior_crossings"])
        self.assertIn(["tee", "wall-a"], report["t_junctions"])
        self.assertGreater(len(report["open_line_endpoints"]), 0)
        self.assertEqual(report["scope"], "2d_line_circle_primitives_no_contour_semantics")

    def test_geometry_qa_classifies_line_circle_and_circle_circle_contacts(self):
        value = plan()
        value["lines"] = value["lines"][:1]
        value["nodes"].extend([
            {"id": "on", "x": 1, "y": 0, "source": SOURCE},
            {"id": "above", "x": 1, "y": 1, "source": SOURCE},
            {"id": "edge", "x": 3.5, "y": 0, "source": SOURCE},
            {"id": "near", "x": 1.5, "y": 0, "source": SOURCE},
            {"id": "touch", "x": 2, "y": 0, "source": SOURCE},
            {"id": "far", "x": 10, "y": 0, "source": SOURCE}])
        value["circles"] = [
            {"id": identifier, "center": center, "radius": radius,
             "layer": "0", "source": SOURCE}
            for identifier, center, radius in (
                ("c-secant", "on", 0.5), ("c-tangent", "above", 1),
                ("c-endpoint", "edge", 1), ("c-overlap", "near", 0.5),
                ("c-touch", "touch", 0.5), ("c-away", "far", 0.5))]
        report = module.analyze_geometry(value)
        self.assertEqual(report["schema_version"], "planspec-geometry-qa-2")
        self.assertIn({"line_id": "wall-a", "circle_id": "c-secant", "kind": "secant"},
                      report["line_circle_intersections"])
        self.assertIn({"line_id": "wall-a", "circle_id": "c-tangent", "kind": "tangent"},
                      report["line_circle_intersections"])
        self.assertIn({"line_id": "wall-a", "circle_id": "c-endpoint", "kind": "one_on_segment"},
                      report["line_circle_intersections"])
        self.assertNotIn("c-away", [item["circle_id"] for item in report["line_circle_intersections"]])
        self.assertIn({"circle_ids": ["c-overlap", "c-secant"], "kind": "secant"},
                      report["circle_circle_intersections"])
        self.assertIn({"circle_ids": ["c-secant", "c-touch"], "kind": "tangent"},
                      report["circle_circle_intersections"])
        reverse = deepcopy(value)
        reverse["nodes"].reverse()
        reverse["circles"].reverse()
        self.assertEqual(report, module.analyze_geometry(reverse))

    def test_v2_explicit_contour_preserves_compiled_geometry(self):
        value = plan()
        value["nodes"].append({"id": "d", "x": 0, "y": 2, "source": SOURCE})
        value["nodes"][2]["x"] = 2.5
        value["nodes"][2]["y"] = 2
        value["lines"].extend([
            {"id": "wall-c", "start": "c", "end": "d", "layer": "0", "source": SOURCE},
            {"id": "wall-d", "start": "d", "end": "a", "layer": "0", "source": SOURCE}])
        value["schema_version"] = "planspec-2"
        value["topology"] = {"contours": [{"id": "room-1", "role": "room",
            "line_ids": ["wall-a", "wall-b", "wall-c", "wall-d"], "source": SOURCE}]}
        result = module.dry_run(value)
        self.assertTrue(result["executable"])
        self.assertEqual(result["topology"]["contours"][0]["signed_area_m2"], "5.0")
        self.assertEqual(len(result["commands"]), 4)
        reversed_nodes = dict(value)
        reversed_nodes["nodes"] = list(reversed(value["nodes"]))
        self.assertEqual(result["commands_sha256"], module.dry_run(reversed_nodes)["commands_sha256"])

        broken = dict(value)
        broken["topology"] = {"contours": [{**value["topology"]["contours"][0],
            "line_ids": ["wall-a", "wall-c", "wall-b", "wall-d"]}]}
        with self.assertRaisesRegex(module.PlanError, "not a closed ordered chain"):
            module.dry_run(broken)

    def test_v2_contour_rejects_crossing_and_missing_reference(self):
        value = plan()
        value["nodes"][1]["x"] = 3
        value["nodes"][2]["x"] = 0
        value["nodes"][2]["y"] = 2
        value["nodes"].append({"id": "d", "x": 2, "y": 2, "source": SOURCE})
        value["lines"].extend([
            {"id": "wall-c", "start": "c", "end": "d", "layer": "0", "source": SOURCE},
            {"id": "wall-d", "start": "d", "end": "a", "layer": "0", "source": SOURCE}])
        value["schema_version"] = "planspec-2"
        value["topology"] = {"contours": [{"id": "room-1", "role": "room",
            "line_ids": ["wall-a", "wall-b", "wall-c", "wall-d"], "source": SOURCE}]}
        with self.assertRaisesRegex(module.PlanError, "crosses itself"):
            module.validate(value)
        value["topology"]["contours"][0]["line_ids"][2] = "unknown"
        with self.assertRaisesRegex(module.PlanError, "dangling line"):
            module.validate(value)

    def test_v3_wall_openings_validate_but_do_not_emit_unproven_cad(self):
        value = plan()
        value["schema_version"] = "planspec-3"
        value["topology"] = {"contours": []}
        value["walls"] = [{"id": "wall-1", "start": "a", "end": "c",
                           "thickness_m": 0.2, "layer": "0", "source": SOURCE}]
        value["openings"] = [
            {"id": "door-1", "wall_id": "wall-1", "offset_m": 1,
             "width_m": 0.9, "kind": "door", "source": SOURCE},
            {"id": "window-1", "wall_id": "wall-1", "offset_m": 3,
             "width_m": 1, "kind": "window", "source": SOURCE}]
        result = module.dry_run(value)
        self.assertEqual(result["architecture"]["status"], "validated")
        self.assertEqual(result["architecture"]["walls"][0]["length_m"], "5.0")
        self.assertEqual(result["unsupported"], ["opening_compilation", "wall_compilation"])
        self.assertFalse(result["executable"])
        self.assertEqual(len(result["commands"]), 2)

    def test_v3_rejects_opening_overlap_outside_and_dangling_wall(self):
        value = plan()
        value["schema_version"] = "planspec-3"
        value["topology"] = {"contours": []}
        value["walls"] = [{"id": "wall-1", "start": "a", "end": "c",
                           "thickness_m": 0.2, "layer": "0", "source": SOURCE}]
        value["openings"] = [
            {"id": "door-1", "wall_id": "wall-1", "offset_m": 1,
             "width_m": 1, "kind": "door", "source": SOURCE},
            {"id": "door-2", "wall_id": "wall-1", "offset_m": 1.5,
             "width_m": 1, "kind": "door", "source": SOURCE}]
        with self.assertRaisesRegex(module.PlanError, "overlap or touch"):
            module.validate(value)
        value["openings"][1]["offset_m"] = 4.5
        with self.assertRaisesRegex(module.PlanError, "beyond wall"):
            module.validate(value)
        value["openings"][1]["offset_m"] = 3
        value["openings"][1]["wall_id"] = "absent"
        with self.assertRaisesRegex(module.PlanError, "Opening reference"):
            module.validate(value)

    def test_v3_single_unopened_wall_compiles_four_traceable_edges(self):
        value = plan()
        value["schema_version"] = "planspec-3"
        value["lines"] = []
        value["topology"] = {"contours": []}
        value["walls"] = [{"id": "wall-1", "start": "a", "end": "c",
                           "thickness_m": 0.2, "layer": "0", "source": SOURCE}]
        value["openings"] = []
        result = module.dry_run(value)
        self.assertTrue(result["executable"])
        self.assertEqual(result["wall_compilation"],
                         {"status": "compiled_single_unopened_wall", "generated_parts": 4})
        self.assertEqual([item["command"] for item in result["commands"]], [
            "LINE 0,0.1 5,0.1", "LINE 5,0.1 5,-0.1",
            "LINE 5,-0.1 0,-0.1", "LINE 0,-0.1 0,0.1"])
        self.assertEqual([item["source_id"] for item in result["commands"]], ["wall-1"] * 4)
        self.assertEqual(len({item["planspec_id"] for item in result["commands"]}), 4)

    def test_v3_clear_opening_compiles_gap_and_jambs_without_door_symbol(self):
        value = plan()
        value["schema_version"] = "planspec-3"
        value["lines"] = []
        value["topology"] = {"contours": []}
        value["walls"] = [{"id": "wall-1", "start": "a", "end": "c",
                           "thickness_m": 0.2, "layer": "0", "source": SOURCE}]
        value["openings"] = [{"id": "gap-1", "wall_id": "wall-1", "offset_m": 1,
                              "width_m": 0.9, "kind": "clear", "source": SOURCE}]
        result = module.dry_run(value)
        self.assertTrue(result["executable"])
        self.assertEqual(result["wall_compilation"],
                         {"status": "compiled_single_clear_opening_wall", "generated_parts": 8})
        self.assertEqual([item["command"] for item in result["commands"]], [
            "LINE 0,0.1 1,0.1", "LINE 1.9,0.1 5,0.1",
            "LINE 0,-0.1 1,-0.1", "LINE 1.9,-0.1 5,-0.1",
            "LINE 0,0.1 0,-0.1", "LINE 5,0.1 5,-0.1",
            "LINE 1,0.1 1,-0.1", "LINE 1.9,0.1 1.9,-0.1"])
        self.assertEqual([item["source_id"] for item in result["commands"]][-2:],
                         ["gap-1", "gap-1"])
        value["openings"][0]["kind"] = "door"
        self.assertFalse(module.dry_run(value)["executable"])
        self.assertEqual(module.dry_run(value)["unsupported"],
                         ["opening_compilation", "wall_compilation"])

    def test_v4_door_swing_is_explicit_and_compiles_one_symbol(self):
        fixture = Path(__file__).with_name("fixtures") / "synthetic-door-swing.planspec.json"
        value = json.loads(fixture.read_text(encoding="utf-8"))
        result = module.dry_run(value)
        self.assertEqual(result["architecture"]["openings"][0]["swing"],
                         {"hinge": "start", "side": "left", "angle_deg": 90})
        self.assertEqual(result["unsupported"], [])
        self.assertTrue(result["executable"])
        self.assertEqual(result["wall_compilation"],
                         {"status": "compiled_single_door_wall", "generated_parts": 10})
        self.assertEqual([item["command"] for item in result["commands"][-2:]],
                         ["LINE 1,0.1 1,1", "ARC 1.9,0.1 1.636396,0.736396 1,1"])
        self.assertEqual([item["source_id"] for item in result["commands"][-2:]],
                         ["door-south", "door-south"])
        self.assertEqual(len({item["planspec_id"] for item in result["commands"]}),
                         len(result["commands"]))
        for bad in ({"hinge": "middle", "side": "left", "angle_deg": 90},
                    {"hinge": "start", "side": "inside", "angle_deg": 90},
                    {"hinge": "start", "side": "left", "angle_deg": 120},
                    {"hinge": "start", "side": "left", "angle_deg": "90"}):
            changed = deepcopy(value)
            changed["openings"][0]["swing"] = bad
            with self.assertRaises(module.PlanError):
                module.validate(changed)
        changed = deepcopy(value)
        del changed["openings"][0]["swing"]
        with self.assertRaises(module.PlanError):
            module.validate(changed)

    def test_door_open_leaf_crossing_is_reviewed_by_source_category(self):
        fixture = Path(__file__).with_name("fixtures") / "synthetic-door-swing.planspec.json"
        value = json.loads(fixture.read_text(encoding="utf-8"))
        clear = module.dry_run(value)["door_clearance_qa"]
        self.assertEqual(clear["status"], "clear")
        value["nodes"] += [
            {"id": "obstacle-a", "x": 0.5, "y": 0.5, "source": SOURCE},
            {"id": "obstacle-b", "x": 1.5, "y": 0.5, "source": SOURCE}]
        value["lines"].append({"id": "candidate-obstacle", "start": "obstacle-a",
                               "end": "obstacle-b", "layer": "0", "source": SOURCE})
        report = module.dry_run(value)["door_clearance_qa"]
        self.assertEqual(report["status"], "review_required")
        self.assertEqual(report["strict_crossings"], [{"door_id": "door-south",
            "line_id": "candidate-obstacle", "line_category": "unclassified"}])
        value["lines"].pop()
        value["nodes"][2]["y"] = 0.5
        value["nodes"][3]["y"] = 0.5
        result = module.dry_run(value)
        contour = result["door_clearance_qa"]
        self.assertEqual(contour["strict_crossings"], [{"door_id": "door-south",
            "line_id": "outline-c", "line_category": "contour"}])
        self.assertEqual(result["quality_blockers"], ["door_open_leaf_crosses_contour"])
        self.assertFalse(result["executable"])

    def test_v4_window_elevation_and_kind_specific_fields(self):
        fixture = Path(__file__).with_name("fixtures") / "synthetic-door-swing.planspec.json"
        value = json.loads(fixture.read_text(encoding="utf-8"))
        opening = value["openings"][0]
        opening["kind"] = "window"
        opening["elevation"] = {"sill_m": 0.8, "head_m": 2.1}
        del opening["swing"]
        result = module.dry_run(value)
        self.assertEqual(result["architecture"]["openings"][0]["elevation"],
                         {"sill_m": 0.8, "head_m": 2.1})
        self.assertTrue(result["executable"])
        self.assertEqual(result["wall_compilation"],
                         {"status": "compiled_single_window_wall", "generated_parts": 10})
        self.assertEqual([item["command"] for item in result["commands"][-2:]],
                         ["LINE 1,0.05,0.8 1.9,0.05,0.8",
                          "LINE 1,-0.05,2.1 1.9,-0.05,2.1"])
        changed_height = deepcopy(value)
        changed_height["openings"][0]["elevation"]["head_m"] = 2.2
        self.assertNotEqual(module.dry_run(changed_height)["commands_sha256"],
                            result["commands_sha256"])
        multi = deepcopy(value)
        second = deepcopy(multi["openings"][0])
        second.update(id="window-second", offset_m=2.2, width_m=0.8)
        multi["openings"].append(second)
        self.assertFalse(module.dry_run(multi)["executable"])
        for sill, head in ((-0.1, 2.1), (1.2, 1.2), (2.2, 1.2)):
            changed = deepcopy(value)
            changed["openings"][0]["elevation"] = {"sill_m": sill, "head_m": head}
            with self.assertRaises(module.PlanError):
                module.validate(changed)
        opening["kind"] = "clear"
        with self.assertRaises(module.PlanError):
            module.validate(value)

    def test_v4_door_hinge_and_side_select_open_leaf_endpoint(self):
        fixture = Path(__file__).with_name("fixtures") / "synthetic-door-swing.planspec.json"
        base = json.loads(fixture.read_text(encoding="utf-8"))
        expected = {("start", "left"): "LINE 1,0.1 1,1",
                    ("start", "right"): "LINE 1,-0.1 1,-1",
                    ("end", "left"): "LINE 1.9,0.1 1.9,1",
                    ("end", "right"): "LINE 1.9,-0.1 1.9,-1"}
        for (hinge, side), leaf in expected.items():
            value = deepcopy(base)
            value["openings"][0]["swing"].update(hinge=hinge, side=side)
            result = module.dry_run(value)
            self.assertTrue(result["executable"])
            self.assertEqual(result["commands"][-2]["command"], leaf)
            self.assertTrue(result["commands"][-1]["command"].startswith("ARC "))
        multi = deepcopy(base)
        second = deepcopy(multi["openings"][0])
        second.update(id="door-second", offset_m=2.2, width_m=0.8)
        multi["openings"].append(second)
        self.assertFalse(module.dry_run(multi)["executable"])
        self.assertEqual(module.dry_run(multi)["unsupported"],
                         ["opening_compilation", "wall_compilation"])

    def test_v5_explicit_orthogonal_join_compiles_closed_union_outline(self):
        fixture = Path(__file__).with_name("fixtures") / "synthetic-wall-join.planspec.json"
        value = json.loads(fixture.read_text(encoding="utf-8"))
        result = module.dry_run(value)
        self.assertEqual(result["architecture"]["joins"][0]["id"], "join-corner")
        self.assertEqual(result["unsupported"], [])
        self.assertTrue(result["executable"])
        self.assertEqual(result["wall_compilation"],
                         {"status": "compiled_orthogonal_union_two_walls", "generated_parts": 8})
        edges = [item["command"].split()[1:] for item in result["commands"]]
        self.assertEqual(len(edges), 8)
        self.assertTrue(all(end == edges[(index + 1) % 8][0]
                            for index, (_, end) in enumerate(edges)))
        vertices = [tuple(map(float, start.split(","))) for start, _ in edges]
        doubled_area = sum(vertices[index][0] * vertices[(index + 1) % 8][1] -
                           vertices[(index + 1) % 8][0] * vertices[index][1]
                           for index in range(8))
        self.assertAlmostEqual(abs(doubled_area) / 2, 1.39, places=6)
        self.assertEqual([item["source_id"] for item in result["commands"]],
                         ["wall-horizontal"] * 3 + ["wall-vertical"] * 3 + ["join-corner"] * 2)
        changed = deepcopy(value)
        changed["nodes"][2]["x"] = 4.1
        with self.assertRaisesRegex(module.PlanError, "perpendicular"):
            module.validate(changed)
        changed = deepcopy(value)
        changed["walls"][1]["thickness_m"] = 0.3
        with self.assertRaisesRegex(module.PlanError, "equal thickness"):
            module.validate(changed)
        changed = deepcopy(value)
        changed["joins"][0]["wall_b_end"] = "end"
        with self.assertRaisesRegex(module.PlanError, "do not coincide"):
            module.validate(changed)
        changed = deepcopy(value)
        changed["joins"][0]["wall_a_id"] = "missing"
        with self.assertRaisesRegex(module.PlanError, "reference"):
            module.validate(changed)
        changed = deepcopy(value)
        changed["nodes"][2]["y"] = 0.05
        with self.assertRaisesRegex(module.PlanError, "too short"):
            module.dry_run(changed)

    def test_v6_wall_face_binding_validates_without_emitting_native_dimension(self):
        fixture = Path(__file__).with_name("fixtures") / "synthetic-wall-face-dimension.planspec.json"
        value = json.loads(fixture.read_text(encoding="utf-8"))
        result = module.dry_run(value)
        self.assertEqual(result["unsupported"], ["native_dimension"])
        self.assertFalse(result["executable"])
        self.assertEqual(result["wall_compilation"],
                         {"status": "compiled_single_unopened_wall", "generated_parts": 4})
        self.assertEqual(len(result["commands"]), 4)
        self.assertTrue(all("DIM" not in item["command"] for item in result["commands"]))
        self.assertEqual(result["dimension_graph"]["status"], "satisfied")

        changed = deepcopy(value)
        changed["dimension_bindings"][0]["end_ref"]["side"] = "left"
        with self.assertRaisesRegex(module.PlanError, "node differs"):
            module.validate(changed)
        changed = deepcopy(value)
        changed["dimension_bindings"][0]["start_ref"]["station_m"] = 4
        with self.assertRaisesRegex(module.PlanError, "outside"):
            module.validate(changed)
        changed = deepcopy(value)
        changed["dimension_bindings"][0]["start_ref"]["wall_id"] = "missing"
        with self.assertRaisesRegex(module.PlanError, "reference is invalid"):
            module.validate(changed)
        changed = deepcopy(value)
        changed["dimension_bindings"] = []
        with self.assertRaisesRegex(module.PlanError, "requires exactly one"):
            module.validate(changed)
        changed = deepcopy(value)
        changed["dimension_bindings"].append(deepcopy(changed["dimension_bindings"][0]))
        with self.assertRaisesRegex(module.PlanError, "duplicated"):
            module.validate(changed)
        changed = deepcopy(value)
        changed["dimension_bindings"][0]["start_ref"]["side"] = "axis"
        with self.assertRaisesRegex(module.PlanError, "reference type"):
            module.validate(changed)
        changed = deepcopy(value)
        changed["openings"] = [{"id": "gap", "wall_id": "wall-1", "offset_m": 1.5,
                                "width_m": 1, "kind": "clear", "source": SOURCE}]
        with self.assertRaisesRegex(module.PlanError, "wall opening"):
            module.validate(changed)

    def test_v6_axis_binding_recomputes_from_wall_geometry(self):
        fixture = Path(__file__).with_name("fixtures") / "synthetic-wall-face-dimension.planspec.json"
        value = json.loads(fixture.read_text(encoding="utf-8"))
        value["nodes"][2].update(x=1, y=0)
        value["nodes"][3].update(x=3, y=0)
        value["dimensions"][0].update(axis="x", reference_type="axis", value=2,
                                        text="2.00 m")
        value["dimension_bindings"][0]["start_ref"].update(side="axis", station_m=1)
        value["dimension_bindings"][0]["end_ref"].update(side="axis", station_m=3)
        self.assertEqual(module.dry_run(value)["unsupported"], ["native_dimension"])
        changed = deepcopy(value)
        changed["walls"][0]["end"] = "right-face"
        with self.assertRaises(module.PlanError):
            module.validate(changed)

    def test_v7_single_face_thickness_compiles_with_explicit_metric_style(self):
        fixture = Path(__file__).with_name("fixtures") / "synthetic-wall-face-dimension-v7.planspec.json"
        value = json.loads(fixture.read_text(encoding="utf-8"))
        result = module.dry_run(value)
        self.assertFalse(result["executable"])
        self.assertEqual(result["unsupported"], [])
        self.assertEqual(result["quality_blockers"], ["dimension_line_inside_wall_bounds"])
        self.assertEqual(result["dimension_compilation"],
                         {"status": "compiled_single_horizontal_face_thickness",
                          "generated_parts": 1})
        self.assertEqual(len(result["commands"]), 5)
        self.assertEqual(result["commands"][-1]["command"],
                         "DIMLINEAR 2,0.1 2,-0.1 2.5,0")
        self.assertEqual(result["commands"][-1]["planspec_id"], "wall-thickness")
        self.assertEqual(result["dimension_placement_qa"]["status"], "inside_wall_bounds")
        self.assertIn("DIMSTYLE SET OCS_WALL_METRIC dimtxt 0.035",
                      [step["command"] for step in result["execution_steps"]])
        self.assertEqual(result["commands_sha256"], module.dry_run(value)["commands_sha256"])

        changed = deepcopy(value)
        changed["dimension_placements"][0]["offset_m"] = 0.6
        self.assertNotEqual(result["commands_sha256"], module.dry_run(changed)["commands_sha256"])
        changed = deepcopy(value)
        changed["dimension_style"]["text_height_m"] = 0.04
        self.assertNotEqual(result["commands_sha256"], module.dry_run(changed)["commands_sha256"])
        changed = deepcopy(value)
        changed["dimension_bindings"][0]["start_ref"]["station_m"] = 1
        changed["nodes"][2]["x"] = 1
        changed["nodes"][3]["x"] = 1
        changed["dimension_bindings"][0]["end_ref"]["station_m"] = 1
        self.assertEqual(module.dry_run(changed)["unsupported"], ["native_dimension"])

        for key, bad in (("scale", 2), ("measurement_factor", 1000),
                         ("text_height_m", 0), ("arrow_size_m", 0.6)):
            changed = deepcopy(value)
            changed["dimension_style"][key] = bad
            with self.assertRaises(module.PlanError):
                module.validate(changed)
        changed = deepcopy(value)
        changed["dimension_placements"] = []
        with self.assertRaises(module.PlanError):
            module.validate(changed)

    def test_v7_exterior_dimension_line_clears_wall_bounds(self):
        fixture = Path(__file__).with_name("fixtures") / \
            "synthetic-wall-face-dimension-exterior-v7.planspec.json"
        value = json.loads(fixture.read_text(encoding="utf-8"))
        result = module.dry_run(value)
        self.assertTrue(result["executable"])
        self.assertEqual(result["dimension_placement_qa"],
                         {"status": "outside_wall_bounds", "wall_id": "wall-1",
                          "dimension_id": "wall-thickness", "wall_end_x_m": "4",
                          "dimension_line_x_m": "4.5",
                          "scope": "2d_dimension_line_position_only_no_text_extents"})
        self.assertEqual(result["commands"][-1]["command"],
                         "DIMLINEAR 2,0.1 2,-0.1 4.5,0")
        bounds = result["source_bounds"]
        self.assertEqual(bounds["scope"],
                         "2d_source_footprints_no_text_arrow_or_rendered_bounds")
        self.assertEqual({key: float(number) for key, number in
                          bounds["architecture_bounds_m"].items()},
                         {"min_x": 0, "min_y": -0.1, "max_x": 4, "max_y": 0.1})
        self.assertEqual({key: float(number) for key, number in
                          bounds["annotation_reference_bounds_m"].items()},
                         {"min_x": 2, "min_y": -0.1, "max_x": 4.5, "max_y": 0.1})
        self.assertEqual(bounds["unresolved"], [])
        changed = deepcopy(value)
        changed["dimension_placements"][0]["offset_m"] = 0
        with self.assertRaises(module.PlanError):
            module.validate(changed)

    def test_v7_vertical_face_thickness_compiles_outside_wall(self):
        fixture = Path(__file__).with_name("fixtures") / \
            "synthetic-wall-face-dimension-vertical-v7.planspec.json"
        value = json.loads(fixture.read_text(encoding="utf-8"))
        result = module.dry_run(value)
        self.assertTrue(result["executable"])
        self.assertEqual(result["dimension_compilation"],
                         {"status": "compiled_single_vertical_face_thickness",
                          "generated_parts": 1})
        self.assertEqual(result["commands"][-1]["command"],
                         "DIMLINEAR -0.1,2 0.1,2 0,4.5")
        self.assertEqual(result["dimension_placement_qa"],
                         {"status": "outside_wall_bounds", "wall_id": "wall-1",
                          "dimension_id": "wall-thickness", "wall_end_y_m": "4",
                          "dimension_line_y_m": "4.5",
                          "scope": "2d_dimension_line_position_only_no_text_extents"})
        self.assertEqual(result["source_bounds"]["annotation_reference_bounds_m"],
                         {"min_x": "-0.1", "min_y": "2", "max_x": "0.1", "max_y": "4.5"})
        self.assertEqual(result["source_bounds"]["unresolved"], [])
        inside = deepcopy(value)
        inside["dimension_placements"][0]["offset_m"] = 0.5
        self.assertEqual(module.dry_run(inside)["quality_blockers"],
                         ["dimension_line_inside_wall_bounds"])
        wrong_axis = deepcopy(value)
        wrong_axis["dimensions"][0]["axis"] = "y"
        with self.assertRaises(module.PlanError):
            module.validate(wrong_axis)

    def test_source_bounds_do_not_merge_uncompiled_annotation_into_architecture(self):
        value = plan()
        value["dimensions"] = [{"id": "length", "start": "a", "end": "c",
                                "axis": "x", "reference_type": "axis", "value": 5,
                                "text": "5.00 m", "source": SOURCE}]
        result = module.dry_run(value)
        self.assertEqual(result["source_bounds"]["unresolved"],
                         ["dimension_placement_or_rendered_extents"])
        self.assertEqual(float(result["source_bounds"]["architecture_bounds_m"]["max_x"]), 5)
        self.assertEqual(float(result["source_bounds"]["annotation_reference_bounds_m"]["max_x"]), 5)
        fixture = Path(__file__).with_name("fixtures") / "synthetic-door-swing.planspec.json"
        door = module.dry_run(json.loads(fixture.read_text(encoding="utf-8")))
        self.assertNotIn("door_swing_extrema", door["source_bounds"]["unresolved"])

    def test_rotated_door_bounds_include_cardinal_arc_extremum(self):
        fixture = Path(__file__).with_name("fixtures") / "synthetic-door-swing.planspec.json"
        value = json.loads(fixture.read_text(encoding="utf-8"))
        value["lines"] = []
        value["topology"]["contours"] = []
        value["nodes"][1].update(x=2, y=2)
        value["openings"][0].update(offset_m=0.1, width_m=2.4)
        result = module.dry_run(value)
        bounds = result["source_bounds"]["architecture_bounds_m"]
        expected_cardinal_y = (0.1 + 0.1) / (2 ** 0.5) + 2.4
        self.assertAlmostEqual(float(bounds["max_y"]), expected_cardinal_y, places=9)
        self.assertLess(float(bounds["min_x"]), -1.5)
        self.assertEqual(result["source_bounds"]["unresolved"], [])

    def test_v7_readable_style_changes_steps_without_moving_dimension(self):
        fixtures = Path(__file__).with_name("fixtures")
        compact = module.dry_run(json.loads((fixtures /
            "synthetic-wall-face-dimension-exterior-v7.planspec.json").read_text(encoding="utf-8")))
        readable = module.dry_run(json.loads((fixtures /
            "synthetic-wall-face-dimension-readable-v7.planspec.json").read_text(encoding="utf-8")))
        self.assertTrue(readable["executable"])
        self.assertEqual(compact["commands"], readable["commands"])
        self.assertEqual(compact["source_bounds"], readable["source_bounds"])
        self.assertNotEqual(compact["commands_sha256"], readable["commands_sha256"])
        self.assertIn("DIMSTYLE SET OCS_WALL_READABLE dimtxt 0.07",
                      [step["command"] for step in readable["execution_steps"]])


if __name__ == "__main__":
    unittest.main()
