# M5.7 — TEXT sencillo buscable en PDF métrico v1

## Alcance

El PDF conserva los glifos vectoriales visibles. Para una entidad CAD `TEXT` con glifos SDF y handle resuelto, añade una sola capa PDF invisible con su valor original, origen y altura. El modo de renderizado PDF 3 permite búsqueda y extracción sin pintar un segundo rótulo. El arnés `mcp_metric_content_smoke.py` exige exactamente una ocurrencia de `TEST123` en cada PDF sintético.

La capa semántica se limita a `TEXT` de una línea, ASCII imprimible, alineación izquierda/baseline, ancho unitario, sin rotación, oblicuidad, espejo, normal inclinada ni secuencias CAD `%%`. Una geometría fuera de este subconjunto conserva el render vectorial anterior sin promesa de búsqueda. MTEXT, cifras generadas por DIMLINEAR, Unicode, bloques/atributos y posicionamiento exacto de selección no están acreditados. El PDF puede ser buscable para ese subconjunto sin ser accesible en sentido amplio.

## Oráculo y reproducción

1. `cargo check --bin OpenCADStudio` y `cargo test --lib semantic_text_uses_invisible_pdf_render_mode`.
2. `cargo build --bin OpenCADStudio` y `python docs/automation/mcp_metric_content_smoke.py` con GUI/perfil aislados. El fixture crea LINE, TEXT y DIMLINEAR sintéticos, guarda/reabre el DWG y exporta A4 a 1:100 y 1:50.
3. Exigir `pypdf.extract_text().count('TEST123') == 1` en ambas páginas. Inspeccionar PNG de Poppler y comparar píxel por píxel con el ensayo sin capa semántica `target/mcp-isolated/20260924-061533-metric-content-51d148bf`.

El ensayo final `target/mcp-isolated/20260924-074815-metric-content-bc8b01da/report.json` mostró `TEST123` exactamente una vez a ambas escalas, dimensiones y componentes previos conservados y PNG idénticos. AutoCAD Core Console volvió a cotejar las cuatro entidades del DWG sintético con `AUDIT` 0/0 y hash intacto en `target/mcp-external/20260924-074854-autocad-30071870/report.json`. El estado final y hashes se sellan en [05-CHECKPOINT-Y-CONTINUACION.md](05-CHECKPOINT-Y-CONTINUACION.md). El histórico que documentó `extract_text()` vacío permanece intacto.
