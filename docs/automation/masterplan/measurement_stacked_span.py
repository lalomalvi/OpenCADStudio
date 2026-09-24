"""Compile source-bound stacked dimensions into a reference rectangle."""

from __future__ import annotations

import math


class StackedSpanError(ValueError):
    pass


def _number(value, name: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        raise StackedSpanError(f"{name} must be finite numeric data")
    return float(value)


def compile_lower_span_rectangle(measurement: dict, *, frozen: dict,
                                 image_width: int, image_height: int) -> dict:
    """Use the lower of two horizontal dimension lines as the width."""
    if not isinstance(measurement, dict) or set(measurement) != {
            "schema_version", "status", "units", "upper_span_m",
            "lower_span_m", "level_delta_m", "source_regions", "confidence"} or \
            measurement["schema_version"] != "ocs-stacked-spans-1" or \
            measurement["status"] != "measured" or measurement["units"] != "m" or \
            type(image_width) is not int or type(image_height) is not int or \
            image_width < 64 or image_height < 64:
        raise StackedSpanError("Stacked span envelope differs")
    regions = measurement["source_regions"]
    if not isinstance(regions, dict) or set(regions) != {
            "upper_span_px", "lower_span_px", "level_delta_px"}:
        raise StackedSpanError("Stacked span regions differ")
    for key, region in regions.items():
        if not isinstance(region, list) or len(region) != 4 or \
                any(type(value) is not int for value in region) or \
                not (0 <= region[0] < region[2] <= image_width) or \
                not (0 <= region[1] < region[3] <= image_height):
            raise StackedSpanError(f"{key} escapes the image")
    upper = regions["upper_span_px"]
    lower = regions["lower_span_px"]
    if not (upper[3] <= lower[1]):
        raise StackedSpanError("Lower dimension line is not below upper line")
    confidence = _number(measurement["confidence"], "confidence")
    if not 0 <= confidence <= 1:
        raise StackedSpanError("Confidence outside 0..1")
    values = {}
    for key in ("upper_span_m", "lower_span_m", "level_delta_m"):
        actual = _number(measurement[key], key)
        expected = _number(frozen.get("expected_" + key), "frozen " + key)
        if actual <= 0 or expected <= 0 or abs(actual - expected) > 0.001:
            raise StackedSpanError(f"{key} differs from frozen criterion")
        values[key] = actual
    width, height = values["lower_span_m"], values["level_delta_m"]
    union = [min(r[0] for r in regions.values()),
             min(r[1] for r in regions.values()),
             max(r[2] for r in regions.values()),
             max(r[3] for r in regions.values())]

    def source(region):
        return {"region_px": region, "confidence": confidence,
                "classification": "inferred"}

    coords = ((0, 0), (width, 0), (width, height), (0, height))
    nodes = [{"id": f"n{i}", "x": x, "y": y, "source": source(union)}
             for i, (x, y) in enumerate(coords)]
    edges = ((0, 1, lower), (1, 2, regions["level_delta_px"]),
             (2, 3, lower), (3, 0, regions["level_delta_px"]))
    lines = [{"id": f"l{i}", "start": f"n{a}", "end": f"n{b}",
              "layer": "0", "source": source(region)}
             for i, (a, b, region) in enumerate(edges)]
    return {"schema_version": "planspec-1", "units": "m",
            "origin": {"x": 0, "y": 0}, "nodes": nodes, "lines": lines,
            "circles": [], "dimensions": []}
