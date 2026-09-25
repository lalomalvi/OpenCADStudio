"""Freeze and score one already authorized development image door observation."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from PIL import Image


SOURCE_SHA = "0CD0B310FC337C18704B658B41DF49ABB63E2F398893273BBFCFD503B2134057"
CROP = (1040, 475, 1170, 575)
SCALE = 8
EXPECTED = ((1090, 501), (1090, 550), (1145, 550))
TOLERANCE = 8
PROMPT = (
    "Observa este recorte 8x de una planta arquitectonica, 1040x800 px. "
    "Hay dos tramos grises de un mismo muro vertical, una abertura entre ellos, "
    "una hoja de puerta horizontal hacia la derecha desde la jamba inferior "
    "y un arco punteado de giro. Identifica tres puntos en coordenadas del "
    "recorte con origen arriba a la izquierda: upper_jamb_px es el centro del "
    "extremo inferior del tramo gris superior; lower_hinge_px es el centro del "
    "extremo superior del tramo gris inferior, donde inicia la hoja; "
    "leaf_tip_px es el extremo derecho de la hoja horizontal, no un punto del arco. "
    "Responde SOLO JSON estricto: schema_version='ocs-door-observation-1', "
    "status='observed', upper_jamb_px:[x,y], lower_hinge_px:[x,y], "
    "leaf_tip_px:[x,y], confidence: numero 0..1. Cada punto DEBE ser un "
    "arreglo de dos enteros, no objeto. Si no puedes distinguir uno de los "
    "tres puntos, status='unsupported' y omite las coordenadas. "
    "Ignora muebles, reticula de piso y cualquier texto. No uses herramientas."
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_new(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")


def prepare(root: Path, source: Path, cli: Path) -> dict:
    if root.exists() or digest(source) != SOURCE_SHA:
        raise ValueError("New run and authorized source required")
    with Image.open(source) as image:
        if image.size != (1650, 1275):
            raise ValueError("Source dimensions differ")
        crop = image.crop(CROP).resize(((CROP[2] - CROP[0]) * SCALE,
                                        (CROP[3] - CROP[1]) * SCALE),
                                       Image.Resampling.NEAREST)
        root.mkdir(parents=True)
        crop.save(root / "crop.png")
    (root / "prompt.txt").write_text(PROMPT + "\n", encoding="utf-8")
    freeze = {"schema_version": "m7-northeast-door-freeze-1",
              "cohort": "development_seen", "cad_permitted": False,
              "source_sha256": SOURCE_SHA, "crop_sha256": digest(root / "crop.png"),
              "prompt_sha256": digest(root / "prompt.txt"),
              "runner_sha256": digest(Path(__file__)), "cli_sha256": digest(cli),
              "requested_model": "gpt-6-luna", "effort": "medium",
              "crop_original_xyxy": CROP, "scale": SCALE,
              "expected_original_px": EXPECTED,
              "tolerance_original_px": TOLERANCE,
              "oracle_provenance": "assistant_visual_before_model"}
    write_new(root / "freeze.json", freeze)
    return freeze


def validate(root: Path, source: Path, cli: Path) -> dict:
    freeze = json.loads((root / "freeze.json").read_text(encoding="utf-8"))
    expected = {"source_sha256": digest(source),
                "crop_sha256": digest(root / "crop.png"),
                "prompt_sha256": digest(root / "prompt.txt"),
                "runner_sha256": digest(Path(__file__)),
                "cli_sha256": digest(cli)}
    if (freeze.get("schema_version") != "m7-northeast-door-freeze-1"
            or any(freeze.get(key) != value for key, value in expected.items())
            or freeze.get("source_sha256") != SOURCE_SHA
            or freeze.get("requested_model") != "gpt-6-luna"
            or freeze.get("effort") != "medium"
            or freeze.get("cohort") != "development_seen"
            or freeze.get("cad_permitted") is not False
            or freeze.get("crop_original_xyxy") != list(CROP)
            or freeze.get("scale") != SCALE
            or freeze.get("expected_original_px") != [list(point) for point in EXPECTED]
            or freeze.get("tolerance_original_px") != TOLERANCE):
        raise ValueError("Frozen northeast door input differs")
    return freeze


def invoke(root: Path, source: Path, cli: Path) -> dict:
    validate(root, source, cli)
    if (root / "intent.json").exists() or (root / "events.jsonl").exists():
        raise ValueError("Observation already started; never replay")
    intent = {"schema_version": "m7-northeast-door-intent-1",
              "freeze_sha256": digest(root / "freeze.json"),
              "prompt_sha256": digest(root / "prompt.txt"),
              "crop_sha256": digest(root / "crop.png")}
    write_new(root / "intent.json", intent)
    command = [str(cli), "exec", "-m", "gpt-6-luna",
               "-c", 'model_reasoning_effort="medium"',
               "-s", "read-only", "--skip-git-repo-check", "--json",
               "--image", str(root / "crop.png"), "-"]
    start = time.monotonic_ns()
    with (root / "events.jsonl").open("xb") as events, \
            (root / "stderr.txt").open("xb") as error:
        process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[3],
                                   stdin=subprocess.PIPE, stdout=events, stderr=error)
        process.communicate((root / "prompt.txt").read_bytes())
    result = {"schema_version": "m7-northeast-door-invocation-1",
              "exit_code": process.returncode,
              "elapsed_seconds": round((time.monotonic_ns() - start) / 1e9, 6),
              "intent_sha256": digest(root / "intent.json"),
              "events_sha256": digest(root / "events.jsonl"),
              "stderr_sha256": digest(root / "stderr.txt")}
    write_new(root / "result.json", result)
    return result


def score(root: Path, source: Path, cli: Path) -> dict:
    validate(root, source, cli)
    intent = json.loads((root / "intent.json").read_text(encoding="utf-8"))
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))
    if (intent.get("freeze_sha256") != digest(root / "freeze.json")
            or intent.get("prompt_sha256") != digest(root / "prompt.txt")
            or intent.get("crop_sha256") != digest(root / "crop.png")
            or result.get("intent_sha256") != digest(root / "intent.json")
            or result.get("events_sha256") != digest(root / "events.jsonl")
            or result.get("stderr_sha256") != digest(root / "stderr.txt")
            or result.get("exit_code") != 0):
        raise ValueError("Observation invocation integrity differs")
    events = [json.loads(line) for line in
              (root / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    answers = [event["item"]["text"] for event in events
               if event.get("type") == "item.completed"
               and event.get("item", {}).get("type") == "agent_message"]
    completed = [event for event in events if event.get("type") == "turn.completed"]
    if len(answers) != 1 or len(completed) != 1:
        raise ValueError("No single completed answer")
    observation = json.loads(answers[0])
    fields = ("upper_jamb_px", "lower_hinge_px", "leaf_tip_px")
    points = [observation.get(field) for field in fields]
    shape = (observation.get("schema_version") == "ocs-door-observation-1"
             and observation.get("status") == "observed"
             and all(isinstance(point, list) and len(point) == 2
                     and all(type(value) is int for value in point) for point in points))
    actual = ([[CROP[0] + point[0] / SCALE, CROP[1] + point[1] / SCALE]
               for point in points] if shape else None)
    inside = bool(actual and all(0 <= point[0] <= 1040 and 0 <= point[1] <= 800
                                 for point in points))
    oracle = bool(actual and all(abs(point[axis] - expected[axis]) <= TOLERANCE
                                 for point, expected in zip(actual, EXPECTED)
                                 for axis in range(2)))
    geometry = bool(actual and abs(actual[0][0] - actual[1][0]) <= 5
                    and abs(actual[1][1] - actual[2][1]) <= 5
                    and actual[0][1] < actual[1][1]
                    and actual[2][0] > actual[1][0]
                    and abs((actual[1][1] - actual[0][1])
                            - (actual[2][0] - actual[1][0])) <= 12)
    passed = inside and oracle and geometry
    verdict = {"schema_version": "m7-northeast-door-verdict-1",
               "status": "passed_observation_only" if passed else
                         ("abstained" if observation.get("status") == "unsupported"
                          else "failed_source_oracle"),
               "cad_permitted": passed,
               "effective_model": "unverified_by_cli_jsonl",
               "freeze_sha256": digest(root / "freeze.json"),
               "events_sha256": digest(root / "events.jsonl"),
               "observation": observation,
               "observed_original_px": actual,
               "usage_cli_aggregate": completed[0].get("usage")}
    write_new(root / "verdict.json", verdict)
    return verdict


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "invoke", "score"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    args = parser.parse_args()
    function = {"prepare": prepare, "invoke": invoke, "score": score}[args.mode]
    print(json.dumps(function(args.root.resolve(), args.source.resolve(strict=True),
                              args.cli.resolve(strict=True)), indent=2))


if __name__ == "__main__":
    main()
