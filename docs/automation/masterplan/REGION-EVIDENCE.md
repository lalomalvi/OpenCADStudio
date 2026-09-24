# Recortes de captura sintética con procedencia

`region_evidence.py` deriva recortes de un reporte L2 `passed` que contiene `capture_artifact` y `capture_overlay_policy=drawing_only`. Exige Pillow. No solicita otra captura al servidor; valida el PNG padre y sus revisiones antes de escribir. Rectángulos `[left, top, right, bottom]` usan píxeles de la captura, con borde derecho/inferior excluido. Los labels deben ser slugs únicos y el límite es 12 regiones por manifiesto.

Ejemplo desde la raíz del worktree:

```powershell
python docs/automation/masterplan/region_evidence.py target/mcp-isolated/20260924-025336-21aa919f/report.json docs/automation/masterplan/fixtures/synthetic-door-region-crops.json
```

El resultado se añade bajo `target/mcp-isolated/20260924-025336-21aa919f/regions/`, sin cambiar `report.json` ni `capture.png`. `manifest.json` enlaza hash del reporte, ArtifactRef original, rectángulos, ArtifactRef de cada recorte y estado `human_review_status=pending`. Si `regions/` ya existe, se detiene sin sobrescribir; para otra selección use `--output-name` distinto. `verify_regions(report_path, manifest_path)` comprueba los hashes/revisiones y que cada píxel del recorte coincide con el rectángulo declarado del PNG padre.

Estos recortes sirven para revisión visual localizada. No prueban que un área en píxeles corresponda a una región CAD semántica, ni miden tipografía impresa, colisiones u opinión humana. La aceptación L5 requiere un oráculo y revisión separados.

## Mapeo CAD a píxel, fixture de dos puertas v8

`ocs_capture` admite hasta 32 anclas `{id,point:[x,y,z]}` en `scope=viewport`. El backend proyecta con la cámara del frame codificado, aplica exactamente el recorte y redimensionamiento del PNG, y devuelve `projection_contract=viewport-rte-pixels-1` y `landmarks_px`. El cliente exige IDs, valores finitos, ámbito `drawing_only` y revisiones de documento/geometría/cámara coincidentes antes de escribir el PNG. En el L2 de `synthetic-two-door-wall-v8`, ocho anclas CAD fijas cubren bisagra, hoja cerrada, punto medio de arco y hoja abierta de cada puerta; un oráculo de píxel exige trazo visible a radio 3 px y umbral de canal RGB 80. El resultado queda en `capture_projection` del reporte, vinculado al ArtifactRef de la misma captura.

```powershell
python docs/automation/masterplan/region_evidence.py target/mcp-isolated/20260924-042327-357da0b0/report.json --from-projection --output-name projected-doors
```

`projected_door_regions` deriva los rectángulos con margen 12 px de esas anclas y comprueba la identidad del frame. El manifiesto de recortes conserva el contrato anterior de píxeles; la relación CAD→píxel está en el reporte padre, cuyo hash figura en el manifiesto. La prueba verifica que los recortes son subconjuntos exactos del PNG. Alcance: fixture sintético, vista actual y ocho puntos; no constituye calibración general de imágenes de entrada, inspección de texto/impresión ni revisión humana L5.
