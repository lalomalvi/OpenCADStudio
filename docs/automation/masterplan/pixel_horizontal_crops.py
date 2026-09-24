"""Compile five bounded single-wall crop observations onto a frozen plan.

These are centerline references. Crop and source hashes are checked by the
caller; visual tolerances were frozen before each model invocation.
"""

from __future__ import annotations

import math


class HorizontalCropError(ValueError):
    pass


def compile_horizontal_crops(observations: list[tuple[dict, dict]], *,
                             base_plan: dict, image_width: int,
                             image_height: int) -> dict:
    if not isinstance(observations, list) or len(observations) != 5 or \
            not isinstance(base_plan, dict) or \
            base_plan.get("schema_version") != "planspec-1" or \
            base_plan.get("units") != "m" or \
            len(base_plan.get("nodes", [])) != 19 or \
            len(base_plan.get("lines", [])) != 16 or \
            type(image_width) is not int or type(image_height) is not int or \
            image_width < 64 or image_height < 64:
        raise HorizontalCropError("Horizontal bundle envelope differs")
    calibration = {"left_px": 392, "right_px": 1285,
                   "top_px": 365, "bottom_px": 869,
                   "width_m": 13.86, "height_m": 8.0}
    nodes = list(base_plan["nodes"])
    lines = list(base_plan["lines"])
    mapped = []
    for index, (observation, frozen) in enumerate(observations, 1):
        if not isinstance(observation, dict) or set(observation) != {
                "schema_version", "status", "start_px", "end_px", "confidence"} or \
                observation["schema_version"] != "ocs-single-wall-crop-1" or \
                observation["status"] != "observed" or \
                not isinstance(frozen, dict) or \
                frozen.get("case_id") != f"apartment-horizontal-h{index}-v1" or \
                frozen.get("schema_version") != "m7-single-wall-crop-freeze-1" or \
                frozen.get("acceptance_m7") is not False or \
                frozen.get("scale") != 8 or \
                frozen.get("tolerance_original_px") != 10 or \
                type(observation["confidence"]) not in {int, float} or \
                not math.isfinite(observation["confidence"]) or \
                not 0 <= observation["confidence"] <= 1:
            raise HorizontalCropError(f"Crop h{index} envelope differs")
        box = frozen.get("crop_original_xyxy")
        if not isinstance(box, list) or len(box) != 4 or \
                any(type(value) is not int for value in box) or \
                not 0 <= box[0] < box[2] <= image_width or \
                not 0 <= box[1] < box[3] <= image_height:
            raise HorizontalCropError(f"Crop h{index} bounds differ")
        endpoints = []
        for key, oracle_key in (("start_px", "expected_original_start"),
                                ("end_px", "expected_original_end")):
            point = observation[key]
            expected = frozen.get(oracle_key)
            if not isinstance(point, list) or len(point) != 2 or \
                    any(type(value) is not int for value in point) or \
                    not 0 <= point[0] < (box[2] - box[0]) * 8 or \
                    not 0 <= point[1] < (box[3] - box[1]) * 8 or \
                    not isinstance(expected, list) or len(expected) != 2 or \
                    any(type(value) is not int for value in expected):
                raise HorizontalCropError(f"Crop h{index} endpoint differs")
            original = (box[0] + point[0] / 8, box[1] + point[1] / 8)
            if max(abs(original[axis] - expected[axis]) for axis in (0, 1)) > 10:
                raise HorizontalCropError(f"Crop h{index} differs from frozen oracle")
            endpoints.append(original)
        a, b = endpoints
        if b[0] - a[0] < 20 or abs(a[1] - b[1]) > 5:
            raise HorizontalCropError(f"Crop h{index} is not a horizontal wall")
        mapped.append(endpoints)
        ids = []
        for suffix, point in zip(("a", "b"), endpoints):
            node_id = f"horizontal{index}{suffix}"
            ids.append(node_id)
            nodes.append({"id": node_id,
                          "x": round((point[0] - calibration["left_px"]) *
                                     calibration["width_m"] /
                                     (calibration["right_px"] - calibration["left_px"]), 6),
                          "y": round((calibration["bottom_px"] - point[1]) *
                                     calibration["height_m"] /
                                     (calibration["bottom_px"] - calibration["top_px"]), 6),
                          "source": {"region_px": [max(0, int(point[0])-12),
                                                    max(0, int(point[1])-12),
                                                    min(image_width, int(point[0])+13),
                                                    min(image_height, int(point[1])+13)],
                                     "confidence": float(observation["confidence"]),
                                     "classification": "inferred"}})
        lines.append({"id": f"horizontal{index}", "start": ids[0],
                      "end": ids[1], "layer": "0",
                      "source": nodes[-2]["source"]})
    for left, right in zip(mapped, mapped[1:]):
        if abs(left[0][1] - right[0][1]) <= 5 and \
                right[0][0] - left[1][0] < 10:
            raise HorizontalCropError("Adjacent wall segments cover an opening")
    return {"schema_version": "planspec-1", "units": "m",
            "origin": {"x": 0, "y": 0}, "nodes": nodes, "lines": lines,
            "circles": [], "dimensions": []}
