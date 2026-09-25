"""Add the observed west window to the three-window apartment development plan."""

from window_extension import WindowExtensionError, extend


def compose(base, observation):
    if observation.get("status") != "passed_observation_only":
        raise WindowExtensionError("West window observation did not pass")
    pixels = observation.get("observed_original_px")
    if not isinstance(pixels, list) or len(pixels) != 2 or \
            not all(388 <= item[0] <= 398 for item in pixels) or \
            not 559 <= pixels[0][1] < pixels[1][1] <= 659:
        raise WindowExtensionError("West window source endpoints differ")
    nodes = {item["id"]: item for item in base["nodes"]}
    p12, p0 = nodes["p12"], nodes["p0"]
    if (abs(p12["x"] + 0.062083) > 1e-6 or
            abs(p0["x"] + 0.062083) > 1e-6 or
            abs(p12["y"] - 2.349206) > 1e-6 or
            abs(p0["y"] - 8.095238) > 1e-6):
        raise WindowExtensionError("West host calibration differs")
    def y_from_pixel(py):
        return round(p12["y"] + (709 - py) * (p0["y"] - p12["y"]) / (709 - 365), 6)
    first_y = y_from_pixel(pixels[1][1])
    second_y = y_from_pixel(pixels[0][1])
    source = {"classification": "inferred", "confidence": 0.7,
              "region_px": [388, 559, 398, 659]}
    plan, compiled = extend(
        base, host_id="edge12", window_id="west-window",
        first=(p12["x"], first_y), second=(p12["x"], second_y),
        inward=(0.15, 0), source=source)
    if (len(base.get("window_symbols", [])) != 3 or
            {item["id"] for item in base["window_symbols"]} !=
            {"north-window", "east-north-window", "south-window"} or
            len(compiled["commands"]) != 55 or
            compiled["door_symbol_qa"]["status"] != "clear"):
        raise WindowExtensionError("Four-window apartment preflight differs")
    return plan, compiled, {
        "schema_version": "m7-apartment-four-windows-composite-1",
        "status": "four_schematic_windows",
        "west_window_height_plan_m": round(second_y - first_y, 6),
        "west_frame_offset_m": 0.15,
        "source_observed_px": pixels,
        "window_symbol_qa": compiled["window_symbol_qa"],
        "limitation": "elevations and frame profiles unverified",
    }
