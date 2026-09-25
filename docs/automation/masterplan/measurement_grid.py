"""Compile three measured spans into a reference grid, never into walls.

The model supplies only source-bound metric observations. This module checks
them against a frozen private development oracle and constructs PlanSpec-1
deterministically. Doors, wall thickness and room semantics are out of scope.
"""

from __future__ import annotations

import math


class MeasurementGridError(ValueError):
    pass


def _finite(value, where: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        raise MeasurementGridError(f"{where} is not finite numeric data")
    return float(value)


def compile_two_bay(measurement: dict, *, frozen: dict,
                    image_width: int, image_height: int) -> dict:
    """Build seven connected LINE entities from three independently read spans."""
    if not isinstance(measurement, dict) or set(measurement) != {
            "schema_version", "status", "units", "left_width_m",
            "right_width_m", "height_m", "source_regions", "confidence"} or \
            measurement["schema_version"] != "ocs-measurements-two-bay-1" or \
            measurement["status"] != "measured" or measurement["units"] != "m" or \
            not isinstance(frozen, dict) or \
            type(image_width) is not int or type(image_height) is not int or \
            image_width < 64 or image_height < 64:
        raise MeasurementGridError("Two-bay measurement envelope differs")
    regions = measurement["source_regions"]
    if not isinstance(regions, dict) or set(regions) != {
            "left_width_px", "right_width_px", "height_px"}:
        raise MeasurementGridError("Measurement source regions differ")
    for key, region in regions.items():
        if not isinstance(region, list) or len(region) != 4 or \
                any(type(value) is not int for value in region) or \
                not (0 <= region[0] < region[2] <= image_width) or \
                not (0 <= region[1] < region[3] <= image_height):
            raise MeasurementGridError(f"{key} escapes the source image")
    confidence = _finite(measurement["confidence"], "confidence")
    if not 0 <= confidence <= 1:
        raise MeasurementGridError("Confidence lies outside 0..1")
    values = {}
    for key in ("left_width_m", "right_width_m", "height_m"):
        value = _finite(measurement[key], key)
        expected = _finite(frozen.get("expected_" + key), "frozen " + key)
        if value <= 0 or expected <= 0 or abs(value - expected) > 0.001:
            raise MeasurementGridError(f"{key} differs from frozen criterion")
        values[key] = value
    left, right, height = (values[key] for key in
                           ("left_width_m", "right_width_m", "height_m"))
    coordinates = ((0, 0), (left, 0), (left + right, 0),
                   (left + right, height), (left, height), (0, height))
    union = [min(region[0] for region in regions.values()),
             min(region[1] for region in regions.values()),
             max(region[2] for region in regions.values()),
             max(region[3] for region in regions.values())]

    def source(region):
        return {"region_px": region, "confidence": confidence,
                "classification": "inferred"}

    nodes = [{"id": f"n{i}", "x": x, "y": y, "source": source(union)}
             for i, (x, y) in enumerate(coordinates)]
    edge_data = ((0, 1, "left_width_px"), (1, 2, "right_width_px"),
                 (2, 3, "height_px"), (3, 4, "right_width_px"),
                 (4, 5, "left_width_px"), (5, 0, "height_px"),
                 (1, 4, "height_px"))
    lines = [{"id": f"l{i}", "start": f"n{a}", "end": f"n{b}",
              "layer": "0", "source": source(regions[region_key])}
             for i, (a, b, region_key) in enumerate(edge_data)]
    return {"schema_version": "planspec-1", "units": "m",
            "origin": {"x": 0, "y": 0}, "nodes": nodes, "lines": lines,
            "circles": [], "dimensions": []}


def compile_five_bay(measurement: dict, *, frozen: dict,
                     image_width: int, image_height: int) -> dict:
    """Build a five-cell reference grid from six printed metric dimensions."""
    required = {"schema_version", "status", "units", "bay_widths_m", "depth_m",
                "source_regions", "confidence"}
    if not isinstance(measurement, dict) or set(measurement) != required or \
            measurement["schema_version"] != "ocs-measurements-five-bay-1" or \
            measurement["status"] != "measured" or measurement["units"] != "m" or \
            not isinstance(frozen, dict) or type(image_width) is not int or \
            type(image_height) is not int or image_width < 64 or image_height < 64:
        raise MeasurementGridError("Five-bay measurement envelope differs")
    widths = measurement["bay_widths_m"]
    expected = frozen.get("expected_widths_m")
    if not isinstance(widths, list) or len(widths) != 5 or \
            not isinstance(expected, list) or len(expected) != 5:
        raise MeasurementGridError("Five-bay width count differs")
    for index, (value, oracle) in enumerate(zip(widths, expected)):
        value = _finite(value, f"width {index}")
        oracle = _finite(oracle, f"oracle width {index}")
        if value <= 0 or oracle <= 0 or abs(value - oracle) > 0.001:
            raise MeasurementGridError(f"width {index} differs from frozen criterion")
    depth = _finite(measurement["depth_m"], "depth")
    expected_depth = _finite(frozen.get("expected_depth_m"), "oracle depth")
    if depth <= 0 or expected_depth <= 0 or abs(depth - expected_depth) > 0.001:
        raise MeasurementGridError("depth differs from frozen criterion")
    confidence = _finite(measurement["confidence"], "confidence")
    if not 0 <= confidence <= 1:
        raise MeasurementGridError("Confidence lies outside 0..1")
    regions = measurement["source_regions"]
    keys = {f"width_{index}_px" for index in range(1, 6)} | {"depth_px"}
    if not isinstance(regions, dict) or set(regions) != keys:
        raise MeasurementGridError("Five-bay source regions differ")
    for key, region in regions.items():
        if not isinstance(region, list) or len(region) != 4 or \
                any(type(value) is not int for value in region) or \
                not (0 <= region[0] < region[2] <= image_width) or \
                not (0 <= region[1] < region[3] <= image_height):
            raise MeasurementGridError(f"{key} escapes source image")
    stations = [0.0]
    for width in widths:
        stations.append(stations[-1] + float(width))
    union = [min(region[0] for region in regions.values()),
             min(region[1] for region in regions.values()),
             max(region[2] for region in regions.values()),
             max(region[3] for region in regions.values())]

    def source(region):
        return {"region_px": region, "confidence": confidence,
                "classification": "inferred"}

    nodes = [{"id": f"n{row}_{column}", "x": x, "y": row * depth,
              "source": source(union)}
             for row in (0, 1) for column, x in enumerate(stations)]
    lines = []
    for row in (0, 1):
        for column in range(5):
            lines.append({"id": f"h{row}_{column}",
                          "start": f"n{row}_{column}",
                          "end": f"n{row}_{column + 1}", "layer": "0",
                          "source": source(regions[f"width_{column + 1}_px"])})
    for column in range(6):
        lines.append({"id": f"v{column}", "start": f"n0_{column}",
                      "end": f"n1_{column}", "layer": "0",
                      "source": source(regions["depth_px"])})
    return {"schema_version": "planspec-1", "units": "m",
            "origin": {"x": 0, "y": 0}, "nodes": nodes, "lines": lines,
            "circles": [], "dimensions": []}


def compile_three_region(measurement: dict, *, frozen: dict,
                         image_width: int, image_height: int) -> dict:
    """Build two lower bays and one upper region from four printed spans."""
    fields = {"schema_version", "status", "units", "lower_widths_m",
              "lower_height_m", "upper_height_m", "source_regions", "confidence"}
    if not isinstance(measurement, dict) or set(measurement) != fields or \
            measurement["schema_version"] != "ocs-bedroom-three-region-measurements-1" or \
            measurement["status"] != "measured" or measurement["units"] != "m" or \
            not isinstance(frozen, dict) or type(image_width) is not int or \
            type(image_height) is not int or image_width < 64 or image_height < 64:
        raise MeasurementGridError("Three-region measurement envelope differs")
    widths = measurement["lower_widths_m"]
    expected_widths = frozen.get("expected_lower_widths_m")
    if not isinstance(widths, list) or len(widths) != 2 or \
            not isinstance(expected_widths, list) or len(expected_widths) != 2:
        raise MeasurementGridError("Three-region widths differ")
    for index, (actual, expected) in enumerate(zip(widths, expected_widths)):
        actual = _finite(actual, f"width {index}")
        expected = _finite(expected, f"expected width {index}")
        if actual <= 0 or expected <= 0 or abs(actual - expected) > 0.001:
            raise MeasurementGridError(f"width {index} differs from frozen criterion")
    for key in ("lower_height_m", "upper_height_m"):
        actual = _finite(measurement[key], key)
        expected = _finite(frozen.get("expected_" + key), "expected " + key)
        if actual <= 0 or expected <= 0 or abs(actual - expected) > 0.001:
            raise MeasurementGridError(f"{key} differs from frozen criterion")
    confidence = _finite(measurement["confidence"], "confidence")
    if not 0 <= confidence <= 1:
        raise MeasurementGridError("Confidence lies outside 0..1")
    regions = measurement["source_regions"]
    keys = {"left_width_px", "right_width_px", "lower_height_px",
            "upper_height_px"}
    if not isinstance(regions, dict) or set(regions) != keys:
        raise MeasurementGridError("Three-region source fields differ")
    for key, box in regions.items():
        if not isinstance(box, list) or len(box) != 4 or \
                any(type(value) is not int for value in box) or \
                not (0 <= box[0] < box[2] <= image_width) or \
                not (0 <= box[1] < box[3] <= image_height):
            raise MeasurementGridError(f"{key} escapes image")
    left, right = (float(item) for item in widths)
    lower = float(measurement["lower_height_m"])
    upper = float(measurement["upper_height_m"])
    points = ((0, 0), (left, 0), (left + right, 0),
              (left + right, lower), (left, lower), (0, lower),
              (left + right, lower + upper), (0, lower + upper))
    union = [min(box[0] for box in regions.values()),
             min(box[1] for box in regions.values()),
             max(box[2] for box in regions.values()),
             max(box[3] for box in regions.values())]

    def source(box):
        return {"region_px": box, "confidence": confidence,
                "classification": "inferred"}

    nodes = [{"id": f"n{index}", "x": x, "y": y,
              "source": source(union)}
             for index, (x, y) in enumerate(points)]
    edges = ((0, 1, "left_width_px"), (1, 2, "right_width_px"),
             (2, 3, "lower_height_px"), (3, 4, "right_width_px"),
             (4, 5, "left_width_px"), (5, 0, "lower_height_px"),
             (1, 4, "lower_height_px"), (5, 7, "upper_height_px"),
             (7, 6, "upper_height_px"), (6, 3, "upper_height_px"))
    lines = [{"id": f"l{index}", "start": f"n{a}", "end": f"n{b}",
              "layer": "0", "source": source(regions[key])}
             for index, (a, b, key) in enumerate(edges)]
    return {"schema_version": "planspec-1", "units": "m",
            "origin": {"x": 0, "y": 0}, "nodes": nodes, "lines": lines,
            "circles": [], "dimensions": []}
