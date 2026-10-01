"""Human-agent plan contract: review sheet, human approval registry, execution gate.

Phase 4a of 08-PLAN-DE-ESTABILIZACION-20260930.md. An agent proposes a PlanSpec;
nothing is drawn until a human approves the exact plan hash after reading a
deterministic review sheet. Agents must never run `approve` or `revoke`:
those commands require an interactive terminal and record the human channel.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys

from planspec import PlanError, dry_run


REVIEW_SCHEMA = "m4-plan-contract-review-2"
APPROVAL_SCHEMA = "m4-plan-contract-approval-1"
HUMAN_CHANNEL = "interactive_tty"
DOUBTS_ACK = "ACEPTO DUDAS"
PREFIX_LENGTH = 12
DETAIL_ROWS = 60
DEFAULT_CAPABILITIES = frozenset({"layer_assignment"})
REVIEW_MD = "contract-review.md"
REVIEW_JSON = "contract-review.json"
ELEMENT_GROUPS = (
    ("nodes", "nodo"), ("walls", "muro"), ("openings", "vano"), ("joins", "unión"),
    ("lines", "línea"), ("circles", "círculo"), ("dimensions", "cota"),
    ("dimension_bindings", "vínculo de cota"), ("dimension_placements", "colocación de cota"),
    ("door_symbols", "símbolo de puerta"), ("window_symbols", "símbolo de ventana"),
    ("obstacles", "obstáculo"),
)
CLASSIFICATION_LABELS = {"measured": "medido", "inferred": "inferido", "unknown": "desconocido"}
REFERENCE_SIDES = {"left": "cara izquierda", "right": "cara derecha", "axis": "eje"}


class ContractError(ValueError):
    pass


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _load_plan(path: Path) -> tuple[dict, str]:
    data = path.read_bytes()
    try:
        plan = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError(f"PlanSpec is not valid UTF-8 JSON: {error}") from error
    if not isinstance(plan, dict):
        raise ContractError("PlanSpec must be a JSON object")
    return plan, digest_bytes(data)


def _elements(plan: dict, key: str) -> list[dict]:
    value = plan.get(key)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _identity(element: dict) -> str:
    return str(element.get("id", element.get("dimension_id", "?")))


def _source_label(element: dict) -> str:
    source = element.get("source") if isinstance(element.get("source"), dict) else {}
    label = CLASSIFICATION_LABELS.get(source.get("classification"), "sin origen")
    confidence = source.get("confidence")
    return f"{label} {confidence:.2f}" if isinstance(confidence, (int, float)) else label


def _classified(plan: dict, classification: str) -> list[dict]:
    found = []
    for key, noun in ELEMENT_GROUPS:
        for element in _elements(plan, key):
            source = element.get("source") if isinstance(element.get("source"), dict) else {}
            if source.get("classification") == classification:
                found.append({"group": key, "noun": noun, "id": _identity(element),
                              "confidence": source.get("confidence")})
    return found


def _meters(value) -> str:
    return f"{value:.3f}" if isinstance(value, (int, float)) else "?"


def _length(nodes: dict, element: dict):
    start, end = nodes.get(str(element.get("start"))), nodes.get(str(element.get("end")))
    if not start or not end or not all(isinstance(point.get(axis), (int, float))
                                       for point in (start, end) for axis in ("x", "y")):
        return None
    return math.hypot(end["x"] - start["x"], end["y"] - start["y"])


def _node_label(nodes: dict, identifier) -> str:
    node = nodes.get(str(identifier))
    if not node:
        return f"{identifier} (?)"
    return f"{identifier} ({_meters(node.get('x'))}, {_meters(node.get('y'))})"


def _reference_label(reference) -> str:
    if not isinstance(reference, dict):
        return "?"
    side = REFERENCE_SIDES.get(reference.get("side"), reference.get("side", "?"))
    return (f"{reference.get('wall_id', '?')} · {side} · "
            f"estación {_meters(reference.get('station_m'))} m")


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_cell(value) for value in row) + " |" for row in rows]
    return lines


def _opening_detail(opening: dict) -> str:
    swing = opening.get("swing") if isinstance(opening.get("swing"), dict) else None
    elevation = opening.get("elevation") if isinstance(opening.get("elevation"), dict) else None
    parts = []
    if swing:
        side = {"left": "izquierda", "right": "derecha"}.get(swing.get("side"), swing.get("side"))
        hinge = {"start": "el inicio", "end": "el fin"}.get(swing.get("hinge"), swing.get("hinge"))
        parts.append(f"bisagra en {hinge}, abre a la {side}, {swing.get('angle_deg', '?')}°")
    if elevation:
        parts.append(f"antepecho {_meters(elevation.get('sill_m'))} m, "
                     f"dintel {_meters(elevation.get('head_m'))} m")
    return "; ".join(parts) or "—"


def _group_diff(previous: dict, current: dict) -> list[str]:
    lines = []
    for key, noun in ELEMENT_GROUPS:
        before = {_identity(item): item for item in _elements(previous, key)}
        after = {_identity(item): item for item in _elements(current, key)}
        for identifier in sorted(after.keys() - before.keys()):
            lines.append(f"- Nuevo {noun} `{identifier}`")
        for identifier in sorted(before.keys() - after.keys()):
            lines.append(f"- Eliminado {noun} `{identifier}`")
        for identifier in sorted(before.keys() & after.keys()):
            changed = sorted(field for field in before[identifier].keys() | after[identifier].keys()
                             if before[identifier].get(field) != after[identifier].get(field))
            if changed:
                lines.append(f"- Modificado {noun} `{identifier}`: {', '.join(changed)}")
    for field in ("schema_version", "units", "origin", "dimension_style", "topology"):
        if previous.get(field) != current.get(field):
            lines.append(f"- Cambia `{field}`")
    return lines or ["- Sin diferencias de contenido."]


def build_review(plan_path: Path, previous_path: Path | None = None,
                 capabilities=DEFAULT_CAPABILITIES) -> tuple[str, dict]:
    """Return the deterministic review sheet and its machine summary."""
    plan, plan_sha = _load_plan(plan_path)
    try:
        compiled = dry_run(plan, capabilities=set(capabilities))
    except PlanError as error:
        raise ContractError(f"PlanSpec is invalid: {error}") from error
    commands_sha = str(compiled.get("commands_sha256", "")).upper()
    unsupported = list(compiled.get("unsupported") or [])
    blockers = list(compiled.get("quality_blockers") or [])
    commands = compiled.get("commands") or []
    executable = bool(compiled.get("executable")) and bool(commands)
    assumptions = _classified(plan, "inferred")
    doubts = _classified(plan, "unknown")
    nodes = {str(node.get("id")): node for node in _elements(plan, "nodes")}
    origin = plan.get("origin") if isinstance(plan.get("origin"), dict) else {}

    kinds = {"door": "puerta", "window": "ventana", "clear": "vano libre"}
    sections = [
        ("nodes", "Nodos", "nodos", ["id", "x (m)", "y (m)", "origen"],
         lambda item: [f"`{item.get('id')}`", _meters(item.get("x")), _meters(item.get("y")),
                       _source_label(item)]),
        ("walls", "Muros", "muros", ["id", "de → a", "longitud (m)", "espesor (m)", "capa", "origen"],
         lambda item: [f"`{item.get('id')}`", f"{item.get('start')} → {item.get('end')}",
                       _meters(_length(nodes, item)), _meters(item.get("thickness_m")),
                       item.get("layer", "?"), _source_label(item)]),
        ("openings", "Vanos", "vanos",
         ["id", "muro", "desde inicio (m)", "ancho (m)", "tipo", "detalle", "origen"],
         lambda item: [f"`{item.get('id')}`", item.get("wall_id", "?"),
                       _meters(item.get("offset_m")), _meters(item.get("width_m")),
                       kinds.get(item.get("kind"), item.get("kind", "?")),
                       _opening_detail(item), _source_label(item)]),
        ("joins", "Uniones", "uniones", ["id", "muro A (extremo)", "muro B (extremo)", "estilo", "origen"],
         lambda item: [f"`{item.get('id')}`", f"{item.get('wall_a_id')} ({item.get('wall_a_end')})",
                       f"{item.get('wall_b_id')} ({item.get('wall_b_end')})",
                       item.get("style", "?"), _source_label(item)]),
        ("lines", "Líneas", "líneas", ["id", "de → a", "longitud (m)", "capa", "origen"],
         lambda item: [f"`{item.get('id')}`", f"{item.get('start')} → {item.get('end')}",
                       _meters(_length(nodes, item)), item.get("layer", "?"), _source_label(item)]),
        ("circles", "Círculos", "círculos", ["id", "centro", "radio (m)", "capa", "origen"],
         lambda item: [f"`{item.get('id')}`", _node_label(nodes, item.get("center")),
                       _meters(item.get("radius")), item.get("layer", "?"), _source_label(item)]),
        ("dimensions", "Cotas", "cotas",
         ["id", "de → a", "eje", "referencia", "valor (m)", "texto", "origen"],
         lambda item: [f"`{item.get('id')}`", f"{_node_label(nodes, item.get('start'))} → "
                       f"{_node_label(nodes, item.get('end'))}", item.get("axis", "?"),
                       item.get("reference_type", "?"), _meters(item.get("value")),
                       item.get("text", ""), _source_label(item)]),
        ("dimension_bindings", "Vínculos de cota", "vínculos", ["cota", "inicio", "fin", "origen"],
         lambda item: [f"`{item.get('dimension_id')}`", _reference_label(item.get("start_ref")),
                       _reference_label(item.get("end_ref")), _source_label(item)]),
        ("dimension_placements", "Colocación de cotas", "colocaciones",
         ["cota", "offset_m (m)", "capa", "origen"],
         lambda item: [f"`{item.get('dimension_id')}`", _meters(item.get("offset_m")),
                       item.get("layer", "?"), _source_label(item)]),
        ("door_symbols", "Símbolos de puerta", "símbolos",
         ["id", "líneas opuesta / bisagra / hoja", "capa", "origen"],
         lambda item: [f"`{item.get('id')}`", f"{item.get('opposite_line_id')} / "
                       f"{item.get('hinge_line_id')} / {item.get('leaf_line_id')}",
                       item.get("layer", "?"), _source_label(item)]),
        ("window_symbols", "Símbolos de ventana", "símbolos",
         ["id", "líneas muro izq. / der.", "riel ext. / int.", "jamba izq. / der.", "capa",
          "elevación", "perfil", "origen"],
         lambda item: [f"`{item.get('id')}`",
                       f"{item.get('left_wall_line_id')} / {item.get('right_wall_line_id')}",
                       f"{item.get('outer_rail_line_id')} / {item.get('inner_rail_line_id')}",
                       f"{item.get('left_jamb_line_id')} / {item.get('right_jamb_line_id')}",
                       item.get("layer", "?"), item.get("elevation_status", "?"),
                       item.get("frame_profile_status", "?"), _source_label(item)]),
        ("obstacles", "Obstáculos", "obstáculos",
         ["id", "tipo", "caja mín → máx (m)", "base z (m)", "altura (m)", "origen"],
         lambda item: [f"`{item.get('id')}`", item.get("kind", "?"),
                       f"({_meters(item.get('min_x_m'))}, {_meters(item.get('min_y_m'))}) → "
                       f"({_meters(item.get('max_x_m'))}, {_meters(item.get('max_y_m'))})",
                       _meters(item.get("base_z_m")), _meters(item.get("height_m")),
                       _source_label(item)]),
    ]
    hidden = {key: len(_elements(plan, key)) - DETAIL_ROWS for key, *_ in sections
              if len(_elements(plan, key)) > DETAIL_ROWS}

    lines = ["# Contrato de plan · hoja de revisión", "",
             "> Nada se dibuja hasta que un humano apruebe **este** hash. "
             "Un agente no debe aprobar.", ""]
    lines += _table(["Campo", "Valor"], [
        ["Plan", f"`{plan_path.name}`"],
        ["Esquema", f"`{plan.get('schema_version', '?')}` · unidades "
                    f"`{plan.get('units', '?')}` · origen ({_meters(origin.get('x'))}, "
                    f"{_meters(origin.get('y'))})"],
        ["Hash del plan", f"`{plan_sha[:PREFIX_LENGTH]}…` (completo al final)"],
        ["Compilación", f"{len(commands)} comandos · `commands_sha256` "
                        f"`{commands_sha[:PREFIX_LENGTH]}…`"],
        ["¿Ejecutable?", "**Sí**" if executable else
            f"**NO** — {len(blockers)} bloqueos, {len(unsupported)} no soportados"],
        ["Tablas de la §1", "completas" if not hidden else
            f"**PARCIALES** — filas sin mostrar: {sum(hidden.values())} (máximo "
            f"{DETAIL_ROWS} por grupo); revisa el PlanSpec íntegro"],
    ])

    lines += ["", "## 1. Qué se va a dibujar", ""]
    drawn = False
    for key, title, plural, headers, row in sections:
        items = _elements(plan, key)
        if not items:
            continue
        drawn = True
        shown = items[:DETAIL_ROWS]
        lines += [f"**{title} ({len(items)})**", ""]
        lines += _table(headers, [row(item) for item in shown])
        if len(items) > len(shown):
            lines.append(f"… y {len(items) - len(shown)} {plural} más: revisa el PlanSpec íntegro.")
        lines.append("")
    if not drawn:
        lines += ["Ningún elemento dibujable.", ""]
    lines += ["La hoja no lista los contornos de `topology` ni el `dimension_style`: "
              "revísalos en el PlanSpec.", ""]

    lines += ["## 2. Supuestos del agente (inferidos, sin dato medido)", ""]
    lines += [f"- {item['noun']} `{item['id']}` · confianza "
              f"{_meters(item['confidence']) if item['confidence'] is not None else '?'}"
              for item in assumptions] or ["Ninguno."]
    lines += ["", "## 3. Dudas (origen «unknown»)", ""]
    if doubts:
        lines += [f"- {item['noun']} `{item['id']}`" for item in doubts]
        lines += ["", f"Aprobar exige teclear `{DOUBTS_ACK}`: se aprueba sabiendo que "
                      "estos elementos no tienen origen conocido."]
    else:
        lines.append("Ninguna.")
    lines += ["", "## 4. Bloqueos y capacidades no soportadas", ""]
    lines += [f"- Bloqueo: {item}" for item in blockers] + \
             [f"- No soportado: {item}" for item in unsupported] or ["Ninguno."]
    lines += ["", "## 5. Qué se verificará al ejecutar, y qué no", "",
              "Se verifica (L2 interno, GUI propia):",
              "- que los comandos compilados coincidan con el `commands_sha256` aprobado;",
              "- que se añadan exactamente las entidades compiladas, con mapa id del plan → handle;",
              "- guardado verificado y reapertura (hoy compara conteos por tipo y capa, "
              "no geometría fina; ver B08) y DWG sin cambios después;",
              "- captura cercada a la revisión dibujada.",
              "",
              "No se verifica:",
              "- fidelidad respecto del encargo o de una imagen fuente: solo contra este plan;",
              "- criterio estructural, normativo o de obra;",
              "- interoperabilidad con otro CAD (L4 va aparte);",
              "- elevaciones y perfiles de ventana marcados como no verificados o esquemáticos;",
              "- extensiones de bloques INSERT (defecto R01 pendiente).", ""]

    previous = None
    if previous_path is not None:
        previous_plan, previous_sha = _load_plan(previous_path)
        previous = {"path": str(previous_path.resolve()), "sha256": previous_sha}
        lines += ["## 6. Cambios respecto de la versión anterior", "",
                  f"Versión anterior: `{previous_path.name}` · `{previous_sha[:PREFIX_LENGTH]}…`", ""]
        lines += _group_diff(previous_plan, plan) + [""]

    lines += ["## Aprobación", "",
              f"Hash completo del plan: `{plan_sha}`", "",
              "Solo el humano responsable, en su propia terminal interactiva:", "",
              "```powershell",
              "python docs/automation/masterplan/plan_contract.py approve --plan <plan> "
              "--review <carpeta de esta hoja> --registry <registro.jsonl> "
              "--approver \"<nombre>\" --scope \"<alcance>\"",
              "```", ""]
    markdown = "\n".join(lines)
    data = {
        "schema_version": REVIEW_SCHEMA,
        "plan_path": str(plan_path.resolve()),
        "plan_sha256": plan_sha,
        "plan_schema": plan.get("schema_version"),
        "units": plan.get("units"),
        "commands_sha256": commands_sha,
        "entity_count": len(commands),
        "executable": executable,
        "unsupported": unsupported,
        "quality_blockers": blockers,
        "assumptions": [item["id"] for item in assumptions],
        "doubts": [item["id"] for item in doubts],
        "detail_rows_hidden": dict(sorted(hidden.items())),
        "previous": previous,
        "planspec_code_sha256": digest(Path(__file__).with_name("planspec.py")),
        "review_code_sha256": digest(Path(__file__)),
        "review_md_sha256": digest_bytes(markdown.encode("utf-8")),
    }
    return markdown, data


def write_review(plan_path: Path, out_dir: Path, previous_path: Path | None = None) -> dict:
    """Write the review sheet into a new directory; never overwrite a reviewed sheet."""
    markdown, data = build_review(plan_path, previous_path)
    out_dir.mkdir(parents=True, exist_ok=False)
    with (out_dir / REVIEW_MD).open("xb") as stream:
        stream.write(markdown.encode("utf-8"))
    with (out_dir / REVIEW_JSON).open("xb") as stream:
        stream.write(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8") + b"\n")
    return {"review_dir": str(out_dir), "plan_sha256": data["plan_sha256"],
            "commands_sha256": data["commands_sha256"], "executable": data["executable"],
            "doubts": data["doubts"], "review_md_sha256": data["review_md_sha256"],
            "review_json_sha256": digest(out_dir / REVIEW_JSON)}


def load_review(plan_path: Path, review_dir: Path) -> tuple[str, dict]:
    """Load a stored review and prove it still matches the current plan and code."""
    markdown_path, json_path = review_dir / REVIEW_MD, review_dir / REVIEW_JSON
    if not markdown_path.is_file() or not json_path.is_file():
        raise ContractError("Review sheet is absent; run review first")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_bytes().decode("utf-8")
    if data.get("schema_version") != REVIEW_SCHEMA or \
            data.get("review_md_sha256") != digest_bytes(markdown.encode("utf-8")):
        raise ContractError("Review sheet was modified after it was written")
    previous = data.get("previous")
    previous_path = Path(previous["path"]) if previous else None
    if previous_path is not None and (not previous_path.is_file() or
                                      digest(previous_path) != previous["sha256"]):
        raise ContractError("Previous plan of the review is absent or changed")
    current, current_data = build_review(plan_path, previous_path)
    if current != markdown or current_data != data:
        raise ContractError("Review no longer matches the plan or compiler; write a new review")
    return markdown, current_data


def _record_hash(record: dict) -> str:
    return digest_bytes(canonical({key: value for key, value in record.items()
                                   if key != "record_sha256"}))


def read_registry(registry: Path) -> list[dict]:
    """Read the approval registry and verify its hash chain."""
    if not registry.is_file():
        raise ContractError("Approval registry is absent")
    records, previous = [], None
    for number, raw in enumerate(registry.read_bytes().split(b"\n"), start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ContractError(f"Approval registry line {number} is not JSON") from error
        if not isinstance(record, dict) or record.get("schema_version") != APPROVAL_SCHEMA or \
                record.get("sequence") != len(records) + 1 or \
                record.get("previous_record_sha256") != previous or \
                record.get("record_sha256") != _record_hash(record) or \
                record.get("decision") not in {"approved", "revoked"}:
            raise ContractError(f"Approval registry is corrupt or tampered at line {number}")
        records.append(record)
        previous = record["record_sha256"]
    return records


def _append(registry: Path, fields: dict) -> dict:
    records = read_registry(registry) if registry.exists() else []
    record = {"schema_version": APPROVAL_SCHEMA, "sequence": len(records) + 1,
              "previous_record_sha256": records[-1]["record_sha256"] if records else None,
              **fields}
    record["record_sha256"] = _record_hash(record)
    registry.parent.mkdir(parents=True, exist_ok=True)
    with registry.open("ab") as stream:
        stream.write(canonical(record) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return record


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def approve(plan_path: Path, review_dir: Path, registry: Path, approver: str, scope: str,
            *, channel: str, ask) -> dict:
    """Record a human approval; `ask(prompt) -> str` reads the human's typed answer."""
    if not approver.strip() or not scope.strip():
        raise ContractError("Approver and scope are required")
    _, data = load_review(plan_path, review_dir)
    if not data["executable"]:
        raise ContractError("Plan has blockers or unsupported parts; it cannot be approved")
    typed = ask(f"Teclea los primeros {PREFIX_LENGTH} caracteres del hash del plan: ")
    if typed.strip().upper() != data["plan_sha256"][:PREFIX_LENGTH]:
        raise ContractError("Typed hash prefix differs; nothing was approved")
    if data["doubts"] and ask(f"Hay dudas sin origen. Teclea «{DOUBTS_ACK}» para aceptarlas: "
                              ).strip() != DOUBTS_ACK:
        raise ContractError("Doubts were not acknowledged; nothing was approved")
    return _append(registry, {
        "decision": "approved", "plan_sha256": data["plan_sha256"],
        "commands_sha256": data["commands_sha256"], "entity_count": data["entity_count"],
        "review_md_sha256": data["review_md_sha256"],
        "review_json_sha256": digest(review_dir / REVIEW_JSON),
        "planspec_code_sha256": data["planspec_code_sha256"],
        "doubts": data["doubts"], "doubts_acknowledged": bool(data["doubts"]),
        "approver": approver.strip(), "scope": scope.strip(), "channel": channel,
        "recorded_at_utc": _now()})


def revoke(plan_path: Path, registry: Path, approver: str, reason: str,
           *, channel: str, ask) -> dict:
    """Record a human revocation of the latest approval of a plan."""
    if not approver.strip() or not reason.strip():
        raise ContractError("Approver and reason are required")
    _, plan_sha = _load_plan(plan_path)
    latest = _latest(read_registry(registry), plan_sha)
    if latest is None or latest["decision"] != "approved":
        raise ContractError("Plan has no active approval to revoke")
    typed = ask(f"Teclea los primeros {PREFIX_LENGTH} caracteres del hash del plan: ")
    if typed.strip().upper() != plan_sha[:PREFIX_LENGTH]:
        raise ContractError("Typed hash prefix differs; nothing was revoked")
    return _append(registry, {
        "decision": "revoked", "plan_sha256": plan_sha,
        "commands_sha256": latest["commands_sha256"], "entity_count": latest["entity_count"],
        "review_md_sha256": latest["review_md_sha256"],
        "review_json_sha256": latest["review_json_sha256"],
        "planspec_code_sha256": latest["planspec_code_sha256"],
        "doubts": latest["doubts"], "doubts_acknowledged": latest["doubts_acknowledged"],
        "approver": approver.strip(), "scope": "revocation: " + reason.strip(),
        "channel": channel, "recorded_at_utc": _now()})


def _latest(records: list[dict], plan_sha256: str) -> dict | None:
    matching = [record for record in records if record["plan_sha256"] == plan_sha256]
    return matching[-1] if matching else None


def require_approval(registry: Path, plan_sha256: str, commands_sha256: str,
                     *, accepted_channels=frozenset({HUMAN_CHANNEL})) -> dict:
    """Gate: return the active human approval of this plan and command set, or raise."""
    latest = _latest(read_registry(registry), plan_sha256)
    if latest is None:
        raise ContractError("Plan has not been approved by a human")
    if latest["decision"] != "approved":
        raise ContractError("Plan approval was revoked")
    if latest["channel"] not in accepted_channels:
        raise ContractError("Approval was not recorded through an interactive human channel")
    if latest["commands_sha256"] != commands_sha256.upper():
        raise ContractError("Compiled commands differ from the approved ones; review again")
    return latest


def find_record(registry: Path, record_sha256: str) -> dict:
    for record in read_registry(registry):
        if record["record_sha256"] == record_sha256:
            return record
    raise ContractError("Approval record is not in the registry")


def approval_status(registry: Path, plan_path: Path) -> dict:
    """Latest decision for a plan and whether the execution gate would accept it now."""
    _, data = build_review(plan_path)
    latest = _latest(read_registry(registry), data["plan_sha256"]) if registry.is_file() else None
    try:
        require_approval(registry, data["plan_sha256"], data["commands_sha256"])
        usable, reason = True, None
    except ContractError as error:
        usable, reason = False, str(error)
    return {"plan_sha256": data["plan_sha256"], "commands_sha256": data["commands_sha256"],
            "decision": latest["decision"] if latest else "none",
            "record_sha256": latest["record_sha256"] if latest else None,
            "usable_by_run": usable, "reason": reason}


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    review = commands.add_parser("review", help="write the one-page review sheet")
    review.add_argument("--plan", type=Path, required=True)
    review.add_argument("--out", type=Path, required=True)
    review.add_argument("--previous", type=Path)
    for name in ("approve", "revoke"):
        human = commands.add_parser(name, help=f"{name} a plan (human, interactive only)")
        human.add_argument("--plan", type=Path, required=True)
        human.add_argument("--registry", type=Path, required=True)
        human.add_argument("--approver", required=True)
        if name == "approve":
            human.add_argument("--review", type=Path, required=True)
            human.add_argument("--scope", required=True)
        else:
            human.add_argument("--reason", required=True)
    status = commands.add_parser("status", help="show the latest decision for a plan")
    status.add_argument("--plan", type=Path, required=True)
    status.add_argument("--registry", type=Path, required=True)
    check = commands.add_parser("verify-registry", help="verify the registry hash chain")
    check.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()

    try:
        if args.mode == "review":
            result = write_review(args.plan.resolve(strict=True), args.out.resolve(),
                                  args.previous.resolve(strict=True) if args.previous else None)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print(f"\nHoja de revisión: {Path(result['review_dir']) / REVIEW_MD}")
            return
        if args.mode == "verify-registry":
            records = read_registry(args.registry.resolve())
            print(json.dumps({"records": len(records),
                              "head_record_sha256": records[-1]["record_sha256"] if records else None},
                             indent=2))
            return
        plan = args.plan.resolve(strict=True)
        registry = args.registry.resolve()
        if args.mode == "status":
            status = approval_status(registry, plan)
            print(json.dumps(status, indent=2, ensure_ascii=False))
            sys.exit(0 if status["usable_by_run"] else 1)
        if not _interactive():
            raise ContractError("Human decision requires an interactive terminal; "
                                "agents must never approve or revoke plans")
        if args.mode == "approve":
            markdown, _ = load_review(plan, args.review.resolve(strict=True))
            print(markdown)
            record = approve(plan, args.review.resolve(), registry, args.approver, args.scope,
                             channel=HUMAN_CHANNEL, ask=input)
        else:
            record = revoke(plan, registry, args.approver, args.reason,
                            channel=HUMAN_CHANNEL, ask=input)
        print(json.dumps({"decision": record["decision"], "sequence": record["sequence"],
                          "record_sha256": record["record_sha256"]}, indent=2))
    except ContractError as error:
        print(f"Contrato: {error}", file=sys.stderr)
        sys.exit(2)
    except FileExistsError as error:
        print(f"Contrato: la carpeta de revisión ya existe; usa una nueva ({error.filename})",
              file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
