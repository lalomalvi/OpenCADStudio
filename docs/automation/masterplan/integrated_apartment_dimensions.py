"""Place an existing Luna axis-chain observation below the apartment geometry.

The seven native dimensions refer to a dimension-only support wall. They are
source aligned to printed axes but are not associative to exterior wall parts.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

from measurement_axis_chain import compile_bottom_chain
from planspec import dry_run


class IntegratedDimensionError(ValueError):
    pass


def compile_integrated_apartment(base_plan: dict, observation: dict, *,
                                 image_width: int, image_height: int,
                                 frozen: dict) -> tuple[dict, dict]:
    if not isinstance(base_plan, dict) or \
            base_plan.get("schema_version") != "planspec-1" or \
            base_plan.get("units") != "m" or \
            len(base_plan.get("nodes", [])) != 29 or \
            len(base_plan.get("lines", [])) != 21 or \
            not isinstance(frozen, dict) or \
            frozen.get("axis_pixels_x") != [392, 558, 741, 907, 1090, 1155, 1285] or \
            frozen.get("pixel_calibration") != {
                "left_px": 392, "right_px": 1285,
                "top_px": 365, "bottom_px": 869,
                "width_m": 13.86, "height_m": 8.0} or \
            frozen.get("axis_alignment_tolerance_m") != 0.05 or \
            frozen.get("chain_baseline_y_m") != -3.0:
        raise IntegratedDimensionError("Frozen integration scope differs")
    chain = compile_bottom_chain(
        observation,
        frozen={"expected_widths_m": [2.58, 2.85, 2.58, 2.85, 1.0, 2.0],
                "style_variant": "legible_fixed_25cm_v2"},
        image_width=image_width, image_height=image_height)
    chain = deepcopy(chain)
    for node in chain["nodes"]:
        node["x"] = float(Decimal(str(node["x"])) - Decimal("0.5"))
        node["y"] = -3.0
    axis_nodes = {node["id"]: node for node in chain["nodes"]
                  if node["id"].startswith("axis-")}
    calibration = frozen["pixel_calibration"]
    for index, x_px in enumerate(frozen["axis_pixels_x"]):
        expected_x = ((x_px - calibration["left_px"]) *
                      calibration["width_m"] /
                      (calibration["right_px"] - calibration["left_px"]))
        if abs(float(axis_nodes[f"axis-{index}"]["x"]) - expected_x) > \
                frozen["axis_alignment_tolerance_m"]:
            raise IntegratedDimensionError(f"Axis {index} differs from source scale")
    if set(node["id"] for node in chain["nodes"]) & \
            set(node["id"] for node in base_plan["nodes"]):
        raise IntegratedDimensionError("Axis IDs collide with apartment nodes")
    if set(line["id"] for line in base_plan["lines"]) & \
            set(item["id"] for item in [*chain["dimensions"], *chain["walls"]]):
        raise IntegratedDimensionError("Dimension IDs collide with apartment lines")
    plan = {"schema_version": "planspec-8", "units": "m",
            "origin": {"x": 0, "y": 0},
            "nodes": [*deepcopy(base_plan["nodes"]), *chain["nodes"]],
            "lines": deepcopy(base_plan["lines"]), "circles": [],
            "dimensions": chain["dimensions"],
            "topology": {"contours": [{
                "id": "apartment-visible-outline",
                "line_ids": [f"edge{index}" for index in range(13)],
                "role": "exterior", "source": base_plan["nodes"][0]["source"]}]},
            "walls": chain["walls"], "openings": [], "joins": [],
            "dimension_bindings": chain["dimension_bindings"],
            "dimension_style": chain["dimension_style"],
            "dimension_placements": chain["dimension_placements"],
            "obstacles": []}
    compiled = dry_run(plan)
    if not compiled["executable"] or compiled["unsupported"] or \
            compiled["quality_blockers"] or len(compiled["commands"]) != 32 or \
            compiled["dimension_compilation"] != {
                "status": "compiled_multi_axis_spans", "generated_parts": 7}:
        raise IntegratedDimensionError("Integrated PlanSpec cannot compile safely")
    return plan, compiled
