"""Freeze and score one development window observation before CAD."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

CROP = (360, 535, 430, 685)
SCALE = 8
EXPECTED = ((393, 564), (393, 654))
TOLERANCE = 5
PROMPT = (
    "Observa este recorte 8x de una ventana vertical en el muro exterior izquierdo. "
    "Marca los dos remates superior e inferior donde la banda gris sólida del muro se "
    "interrumpe por el marco oscuro de la ventana. Da el centro horizontal del marco "
    "en ambos remates. Usa coordenadas enteras [x,y] del recorte de 560x1200 píxeles, "
    "de arriba hacia abajo. No sigas el eje punteado, el texto ni el patrón "
    "del piso. Responde SOLO JSON estricto con schema_version='ocs-window-endpoints-1', "
    "status='observed', top_px, bottom_px, confidence. Si no ves claramente ambos "
    "remates, responde status='unsupported' sin coordenadas. No uses herramientas."
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def prepare(source, root):
    if root.exists():
        raise FileExistsError(root)
    root.mkdir(parents=True)
    with Image.open(source) as image:
        if image.size != (1650, 1275):
            raise ValueError("Unexpected source dimensions")
        image.crop(CROP).resize(((CROP[2]-CROP[0])*SCALE,
                                 (CROP[3]-CROP[1])*SCALE)).save(root / "crop.png")
    (root / "prompt.txt").write_text(PROMPT + "\n", encoding="utf-8")
    freeze = {"schema_version": "m7-west-window-observation-freeze-1",
              "source_sha256": digest(source), "crop_sha256": digest(root / "crop.png"),
              "prompt_sha256": digest(root / "prompt.txt"),
              "crop_original_xyxy": CROP, "scale": SCALE,
              "expected_original_px": EXPECTED, "tolerance_original_px": TOLERANCE,
              "requested_model": "gpt-6-luna", "effort": "medium",
              "cohort": "development_seen", "cad_permitted": False,
              "oracle_provenance": "assistant_visual_before_model"}
    (root / "freeze.json").write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    return freeze


def score(source, root, *, persist=True):
    freeze = json.loads((root / "freeze.json").read_text(encoding="utf-8"))
    checks = {"source_hash": digest(source) == freeze["source_sha256"],
              "crop_hash": digest(root / "crop.png") == freeze["crop_sha256"],
              "prompt_hash": digest(root / "prompt.txt") == freeze["prompt_sha256"]}
    events = [json.loads(line) for line in (root / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    finals = [event["item"]["text"] for event in events
              if event.get("type") == "item.completed"
              and event.get("item", {}).get("type") == "agent_message"]
    outcome = {"schema_version": "m7-west-window-observation-verdict-1",
               "freeze_sha256": digest(root / "freeze.json"),
               "events_sha256": digest(root / "events.jsonl"), "checks": checks,
               "status": "failed", "cad_permitted": False,
               "effective_model": "unverified_by_cli_jsonl"}
    if len(finals) != 1 or not any(event.get("type") == "turn.completed" for event in events):
        outcome["reason"] = "no_single_completed_model_message"
    else:
        try:
            observation = json.loads(finals[0])
            outcome["observation"] = observation
            if observation.get("status") == "unsupported":
                outcome["status"] = "abstained"
            else:
                points = [observation.get("top_px"), observation.get("bottom_px")]
                valid = (observation.get("schema_version") == "ocs-window-endpoints-1"
                         and observation.get("status") == "observed"
                         and all(isinstance(p, list) and len(p) == 2 and
                                 all(type(v) is int for v in p) for p in points)
                         and isinstance(observation.get("confidence"), (int, float)))
                if valid:
                    actual = [[CROP[0] + p[0]/SCALE, CROP[1] + p[1]/SCALE]
                              for p in points]
                    outcome["observed_original_px"] = actual
                    checks["source_oracle"] = all(
                        abs(p[axis] - expected[axis]) <= TOLERANCE
                        for p, expected in zip(actual, EXPECTED) for axis in range(2))
                    if all(checks.values()):
                        outcome["status"] = "passed_observation_only"
                else:
                    outcome["reason"] = "invalid_observation_shape"
        except ValueError:
            outcome["reason"] = "invalid_json"
    if persist:
        (root / "verdict.json").write_text(json.dumps(outcome, indent=2) + "\n", encoding="utf-8")
    return outcome


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "score"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.root) if args.mode == "prepare"
                     else score(args.source, args.root), indent=2))
