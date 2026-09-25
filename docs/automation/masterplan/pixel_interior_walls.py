"""Compile a bounded, source-bound interior-wall trace onto a frozen perimeter.

This produces centerline references only. Openings, wall thickness, rooms, and
door semantics are outside this narrow development fixture.
"""

from __future__ import annotations

import math


class PixelInteriorError(ValueError):
    pass


def compile_interior_walls(observation: dict, *, perimeter: dict, frozen: dict,
                           image_width: int, image_height: int) -> dict:
    expected = frozen.get("expected_walls_px")
    tolerance = frozen.get("wall_tolerance_px")
    calibration = frozen.get("pixel_calibration")
    if not isinstance(observation, dict) or set(observation) != {
            "schema_version", "status", "segments", "confidence"} or \
            observation["schema_version"] != "ocs-interior-wall-segments-1" or \
            observation["status"] != "observed" or \
            not isinstance(expected, list) or len(expected) != 3 or \
            type(tolerance) is not int or not 1 <= tolerance <= 12 or \
            not isinstance(calibration, dict) or \
            set(calibration) != {"left_px", "right_px", "top_px", "bottom_px",
                                 "width_m", "height_m"} or \
            not isinstance(perimeter, dict) or \
            perimeter.get("schema_version") != "planspec-1" or \
            perimeter.get("units") != "m" or \
            len(perimeter.get("lines", [])) != 13 or \
            len(perimeter.get("nodes", [])) != 13 or \
            not isinstance(observation["segments"], list) or \
            len(observation["segments"]) != 3:
        raise PixelInteriorError("Interior trace envelope differs")
    if type(image_width) is not int or type(image_height) is not int or \
            image_width < 64 or image_height < 64:
        raise PixelInteriorError("Image dimensions differ")
    left, right, top, bottom = (calibration[key] for key in
                                ("left_px", "right_px", "top_px", "bottom_px"))
    width_m, height_m = calibration["width_m"], calibration["height_m"]
    if any(type(value) is not int for value in (left, right, top, bottom)) or \
            not 0 <= left < right < image_width or \
            not 0 <= top < bottom < image_height or \
            any(type(value) not in {int, float} or not math.isfinite(value) or
                value <= 0 for value in (width_m, height_m)):
        raise PixelInteriorError("Calibration differs")
    def confidence(value):
        return type(value) in {int, float} and math.isfinite(value) and 0 <= value <= 1
    if not confidence(observation["confidence"]):
        raise PixelInteriorError("Global confidence differs")
    nodes = list(perimeter["nodes"])
    lines = list(perimeter["lines"])
    for index, (item, oracle) in enumerate(zip(observation["segments"], expected), 1):
        if not isinstance(item, dict) or set(item) != {
                "id", "start_px", "end_px", "orientation", "confidence"} or \
                item["id"] != f"s{index}" or not confidence(item["confidence"]) or \
                not isinstance(oracle, list) or len(oracle) != 2:
            raise PixelInteriorError(f"Wall {index} envelope differs")
        points = []
        for key, reference in zip(("start_px", "end_px"), oracle):
            point = item[key]
            if not isinstance(point, list) or len(point) != 2 or \
                    any(type(value) is not int for value in point) or \
                    not 0 <= point[0] < image_width or \
                    not 0 <= point[1] < image_height or \
                    not isinstance(reference, list) or len(reference) != 2 or \
                    any(type(value) is not int for value in reference) or \
                    max(abs(point[axis] - reference[axis]) for axis in (0, 1)) > tolerance:
                raise PixelInteriorError(f"Wall {index} differs from frozen visual oracle")
            points.append(point)
        a, b = points
        if item["orientation"] != "vertical" or \
                abs(a[0] - b[0]) > tolerance or b[1] - a[1] < 60 or \
                max(a[1], b[1]) >= bottom - 140:
            raise PixelInteriorError(f"Wall {index} crosses the allowed interior band")
        ids = []
        for suffix, point in zip(("a", "b"), points):
            node_id = f"wall{index}{suffix}"
            ids.append(node_id)
            nodes.append({"id": node_id,
                          "x": round((point[0] - left) * width_m / (right - left), 6),
                          "y": round((bottom - point[1]) * height_m / (bottom - top), 6),
                          "source": {"region_px": [max(0, point[0]-12),
                                                    max(0, point[1]-12),
                                                    min(image_width, point[0]+13),
                                                    min(image_height, point[1]+13)],
                                     "confidence": float(item["confidence"]),
                                     "classification": "inferred"}})
        lines.append({"id": f"wall{index}", "start": ids[0], "end": ids[1],
                      "layer": "0", "source": nodes[-2]["source"]})
    return {"schema_version": "planspec-1", "units": "m",
            "origin": {"x": 0, "y": 0}, "nodes": nodes, "lines": lines,
            "circles": [], "dimensions": []}
