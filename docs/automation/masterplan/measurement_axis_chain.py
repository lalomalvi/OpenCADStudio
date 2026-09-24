"""Compile six printed axis spans to a scoped native dimension reference drawing."""

from __future__ import annotations

from decimal import Decimal
import math


class AxisChainError(ValueError):
    pass


def compile_bottom_chain(value: dict, *, frozen: dict,
                         image_width: int, image_height: int) -> dict:
    required = {"schema_version", "status", "units", "widths_m",
                "source_regions", "confidence"}
    if not isinstance(value, dict) or set(value) != required or \
            value["schema_version"] != "ocs-bottom-chain-1" or \
            value["status"] != "measured" or value["units"] != "m" or \
            not isinstance(frozen, dict) or type(image_width) is not int or \
            type(image_height) is not int or image_width < 64 or image_height < 64:
        raise AxisChainError("Bottom chain envelope differs")
    widths = value["widths_m"]
    expected = frozen.get("expected_widths_m")
    regions = value["source_regions"]
    if not isinstance(widths, list) or len(widths) != 6 or \
            not isinstance(expected, list) or len(expected) != 6 or \
            not isinstance(regions, list) or len(regions) != 6:
        raise AxisChainError("Six widths and six source regions are required")
    confidence = value["confidence"]
    if type(confidence) not in {float, int} or not math.isfinite(confidence) or \
            not 0 <= confidence <= 1:
        raise AxisChainError("Confidence is invalid")
    for index, region in enumerate(regions):
        if not isinstance(region, list) or len(region) != 4 or \
                any(type(point) is not int for point in region) or \
                not (0 <= region[0] < region[2] <= image_width) or \
                not (0 <= region[1] < region[3] <= image_height):
            raise AxisChainError(f"Source region {index} escapes image")
    if any(regions[index][0] >= regions[index + 1][0] for index in range(5)):
        raise AxisChainError("Source regions are not ordered left to right")
    stations = [Decimal("0.5")]
    numeric_widths = []
    for index, (actual, oracle) in enumerate(zip(widths, expected)):
        if type(actual) not in {int, float} or type(oracle) not in {int, float} or \
                not math.isfinite(actual) or not math.isfinite(oracle):
            raise AxisChainError("Nonfinite width")
        if actual <= 0 or oracle <= 0 or abs(actual - oracle) > 0.001:
            raise AxisChainError(f"Width {index} differs from frozen criterion")
        width = Decimal(str(actual))
        numeric_widths.append(width)
        stations.append(stations[-1] + width)
    union = [min(region[0] for region in regions),
             min(region[1] for region in regions),
             max(region[2] for region in regions),
             max(region[3] for region in regions)]

    def source(region, classification="inferred"):
        return {"region_px": region, "confidence": confidence,
                "classification": classification}

    nodes = [{"id": "support-start", "x": 0, "y": 0, "source": source(union)},
             {"id": "support-end", "x": float(stations[-1] + Decimal("0.5")),
              "y": 0, "source": source(union)}]
    nodes.extend({"id": f"axis-{index}", "x": float(station), "y": 0,
                  "source": source(union)}
                 for index, station in enumerate(stations))
    dimensions = []
    bindings = []
    placements = []
    for index, width in enumerate(numeric_widths):
        dimension_id = f"span-{index + 1}"
        region = regions[index]
        dimensions.append({"id": dimension_id, "start": f"axis-{index}",
                           "end": f"axis-{index + 1}", "axis": "x",
                           "reference_type": "axis", "value": float(width),
                           "text": f"{width:.2f} m",
                           "source": source(region, "measured")})
        bindings.append({"dimension_id": dimension_id,
                         "start_ref": {"wall_id": "reference-support", "side": "axis",
                                       "station_m": float(stations[index])},
                         "end_ref": {"wall_id": "reference-support", "side": "axis",
                                     "station_m": float(stations[index + 1])},
                         "source": source(region)})
        placements.append({"dimension_id": dimension_id,
                           "offset_m": 0.5, "layer": "0",
                           "source": source(region)})
    total = stations[-1] - stations[0]
    dimensions.append({"id": "span-total", "start": "axis-0", "end": "axis-6",
                       "axis": "x", "reference_type": "axis", "value": float(total),
                       "text": f"{total:.2f} m", "source": source(union, "inferred")})
    bindings.append({"dimension_id": "span-total",
                     "start_ref": {"wall_id": "reference-support", "side": "axis",
                                   "station_m": float(stations[0])},
                     "end_ref": {"wall_id": "reference-support", "side": "axis",
                                 "station_m": float(stations[-1])},
                     "source": source(union)})
    placements.append({"dimension_id": "span-total", "offset_m": 0.9,
                       "layer": "0", "source": source(union)})
    return {"schema_version": "planspec-8", "units": "m",
            "origin": {"x": 0, "y": 0}, "nodes": nodes, "lines": [],
            "circles": [], "dimensions": dimensions, "topology": {"contours": []},
            "walls": [{"id": "reference-support", "start": "support-start",
                       "end": "support-end", "thickness_m": 0.2,
                       "layer": "0", "source": source(union)}],
            "openings": [], "joins": [], "dimension_bindings": bindings,
            "dimension_style": {"name": "OCS_AXIS_METRIC",
                                "text_height_m": 0.035, "arrow_size_m": 0.02,
                                "gap_m": 0.01, "scale": 1,
                                "measurement_factor": 1},
            "dimension_placements": placements, "obstacles": []}
