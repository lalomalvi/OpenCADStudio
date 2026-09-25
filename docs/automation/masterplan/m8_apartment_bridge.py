"""Bind an M8 CLI replay to independently audited, byte-identical M7 CAD."""

import argparse
import json
from pathlib import Path

from apartment_four_window_l4 import assess as assess_apartment
from m8_case_cli import digest, validate, verify
from owned_cad_executor import verify_owned_cad_evidence


class ApartmentBridgeError(ValueError):
    pass


def bind(m8_root: Path, m7_root: Path, image: Path, binary: Path,
         external: Path) -> dict:
    plan = m7_root / "model-plan.json"
    release, compiled = validate(m8_root, plan, binary)
    local = verify(m8_root, plan, binary)
    source_l4 = assess_apartment(m7_root, image, binary, external)
    m7_cad_paths = list((m7_root / "cad").glob("*.json"))
    m8_cad_paths = list((m8_root / "cad").glob("*.json"))
    if len(m7_cad_paths) != 1 or len(m8_cad_paths) != 1:
        raise ApartmentBridgeError("CAD evidence count differs")
    earlier = verify_owned_cad_evidence(m7_cad_paths[0])
    current = verify_owned_cad_evidence(m8_cad_paths[0])
    if (source_l4["status"] != "passed_scoped_l4"
            or source_l4["geometry_matches"] != 55
            or source_l4["geometry_total"] != 55
            or release["entity_count"] != 55
            or local["entity_count"] != 55
            or local["dwg_sha256"] != earlier["dwg"]["sha256"]
            or current["dwg"]["sha256"] != earlier["dwg"]["sha256"]
            or local["capture_sha256"] != earlier["capture"]["sha256"]
            or current["capture"]["sha256"] != earlier["capture"]["sha256"]
            or compiled["commands_sha256"] != earlier["commands_sha256"]
            or current["commands_sha256"] != earlier["commands_sha256"]
            or source_l4["dwg_sha256"] != local["dwg_sha256"]):
        raise ApartmentBridgeError("M8 replay and audited M7 geometry differ")
    return {
        "schema_version": "m8-apartment-four-window-bridge-1",
        "status": "passed_scoped_l2_l4_byte_identical",
        "model_call": False,
        "acceptance_m7_m8": False,
        "plan_sha256": digest(plan),
        "m8_contract_sha256": local["contract_sha256"],
        "m8_report_sha256": local["report_sha256"],
        "m7_l4_external_report_sha256": source_l4["external_report_sha256"],
        "m7_l4_census_sha256": source_l4["census_sha256"],
        "m7_l4_matches": source_l4["geometry_matches"],
        "commands_sha256": compiled["commands_sha256"],
        "dwg_sha256": local["dwg_sha256"],
        "capture_sha256": local["capture_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--m8-run", type=Path, required=True)
    parser.add_argument("--m7-run", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--external", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = bind(args.m8_run.resolve(strict=True), args.m7_run.resolve(strict=True),
                  args.image.resolve(strict=True), args.binary.resolve(strict=True),
                  args.external.resolve(strict=True))
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(result["status"], result["m7_l4_matches"])


if __name__ == "__main__":
    main()
