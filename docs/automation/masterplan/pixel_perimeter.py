"""Compile a source-bound visible exterior outline into a CAD reference contour.

The calibration and visual oracle are frozen before the model call. This is
an exterior reference trace, not a wall footprint or full room plan.
"""

from __future__ import annotations

import math


class PixelPerimeterError(ValueError):
    pass


def _segment_crosses(a, b, c, d) -> bool:
    def turn(p, q, r):
        value = ((q[0] - p[0]) * (r[1] - p[1]) -
                 (q[1] - p[1]) * (r[0] - p[0]))
        return (value > 0) - (value < 0)

    return turn(a, b, c) * turn(a, b, d) < 0 and \
        turn(c, d, a) * turn(c, d, b) < 0


def compile_visible_perimeter(observation: dict, *, frozen: dict,
                              image_width: int, image_height: int) -> dict:
    if not isinstance(observation, dict) or set(observation) != {
            "schema_version", "status", "vertices_px", "confidence"} or \
            observation["schema_version"] != "ocs-visible-perimeter-pixels-1" or \
            observation["status"] != "traced" or \
            type(image_width) is not int or type(image_height) is not int or \
            image_width < 64 or image_height < 64 or not isinstance(frozen, dict):
        raise PixelPerimeterError("Visible perimeter envelope differs")
    vertices = observation["vertices_px"]
    oracle = frozen.get("expected_vertices_px")
    tolerance = frozen.get("vertex_tolerance_px")
    calibration = frozen.get("pixel_calibration")
    if not isinstance(vertices, list) or not isinstance(oracle, list) or \
            len(vertices) != len(oracle) or not 4 <= len(vertices) <= 32 or \
            type(tolerance) is not int or not 1 <= tolerance <= 20 or \
            not isinstance(calibration, dict) or set(calibration) != {
                "left_px", "right_px", "top_px", "bottom_px",
                "width_m", "height_m"}:
        raise PixelPerimeterError("Frozen perimeter or calibration differs")
    measured = []
    for index, (point, expected) in enumerate(zip(vertices, oracle)):
        if not isinstance(point, list) or len(point) != 2 or \
                any(type(value) is not int for value in point) or \
                not (0 <= point[0] < image_width and
                     0 <= point[1] < image_height) or \
                not isinstance(expected, list) or len(expected) != 2 or \
                any(type(value) is not int for value in expected):
            raise PixelPerimeterError(f"Vertex {index} is invalid")
        if max(abs(a - b) for a, b in zip(point, expected)) > tolerance:
            raise PixelPerimeterError(f"Vertex {index} differs from frozen visual oracle")
        measured.append(tuple(point))
    if len(set(measured)) != len(measured):
        raise PixelPerimeterError("Perimeter has duplicate vertices")
    for index in range(len(measured)):
        a, b = measured[index], measured[(index + 1) % len(measured)]
        if math.dist(a, b) <= 10:
            raise PixelPerimeterError("Perimeter has a degenerate edge")
        for other in range(index + 2, len(measured)):
            if index == 0 and other == len(measured) - 1:
                continue
            c, d = measured[other], measured[(other + 1) % len(measured)]
            if _segment_crosses(a, b, c, d):
                raise PixelPerimeterError("Perimeter self-intersects")
    confidence = observation["confidence"]
    if type(confidence) not in {int, float} or not math.isfinite(confidence) or \
            not 0 <= confidence <= 1:
        raise PixelPerimeterError("Confidence differs")
    left, right, top, bottom = (calibration[key] for key in
                                ("left_px", "right_px", "top_px", "bottom_px"))
    width_m, height_m = calibration["width_m"], calibration["height_m"]
    if any(type(value) is not int for value in (left, right, top, bottom)) or \
            not (0 <= left < right < image_width and
                 0 <= top < bottom < image_height) or \
            any(type(value) not in {int, float} or not math.isfinite(value) or
                value <= 0 for value in (width_m, height_m)):
        raise PixelPerimeterError("Calibration differs")
    scale_x = width_m / (right - left)
    scale_y = height_m / (bottom - top)
    source = lambda point: {"region_px": [max(0, point[0] - 12),
                                          max(0, point[1] - 12),
                                          min(image_width, point[0] + 13),
                                          min(image_height, point[1] + 13)],
                            "confidence": float(confidence),
                            "classification": "inferred"}
    nodes = [{"id": f"p{index}",
              "x": round((point[0] - left) * scale_x, 6),
              "y": round((bottom - point[1]) * scale_y, 6),
              "source": source(point)}
             for index, point in enumerate(measured)]
    lines = [{"id": f"edge{index}", "start": f"p{index}",
              "end": f"p{(index + 1) % len(measured)}", "layer": "0",
              "source": source(measured[index])}
             for index in range(len(measured))]
    return {"schema_version": "planspec-1", "units": "m",
            "origin": {"x": 0, "y": 0}, "nodes": nodes, "lines": lines,
            "circles": [], "dimensions": []}
