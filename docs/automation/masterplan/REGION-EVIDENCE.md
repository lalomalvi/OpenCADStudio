# Recortes de captura sintética con procedencia

`region_evidence.py` deriva recortes de un reporte L2 `passed` que contiene `capture_artifact` y `capture_overlay_policy=drawing_only`. Exige Pillow. No solicita otra captura al servidor; valida el PNG padre y sus revisiones antes de escribir. Rectángulos `[left, top, right, bottom]` usan píxeles de la captura, con borde derecho/inferior excluido. Los labels deben ser slugs únicos y el límite es 12 regiones por manifiesto.

Ejemplo desde la raíz del worktree:

```powershell
python docs/automation/masterplan/region_evidence.py target/mcp-isolated/20260924-025336-21aa919f/report.json docs/automation/masterplan/fixtures/synthetic-door-region-crops.json
```

El resultado se añade bajo `target/mcp-isolated/20260924-025336-21aa919f/regions/`, sin cambiar `report.json` ni `capture.png`. `manifest.json` enlaza hash del reporte, ArtifactRef original, rectángulos, ArtifactRef de cada recorte y estado `human_review_status=pending`. Si `regions/` ya existe, se detiene sin sobrescribir; para otra selección use `--output-name` distinto. `verify_regions(report_path, manifest_path)` comprueba los hashes/revisiones y que cada píxel del recorte coincide con el rectángulo declarado del PNG padre.

Estos recortes sirven para revisión visual localizada. No prueban que un área en píxeles corresponda a una región CAD semántica, ni miden tipografía impresa, colisiones u opinión humana. La aceptación L5 requiere un oráculo y revisión separados.
