# M5.4 — contenido de bloque en motor independiente

Fecha: 2026-09-24. Alcance: un fixture sintético `MCP-SYMBOL`; no se abrió el DWG privado. Los runs anteriores se conservan. El primer intento de ampliar la sonda, `target/mcp-external/20260924-135841-autocad-cf89bc05`, leyó correctamente el contenido pero falló el gate de unidades: el fixture histórico tenía `INSUNITS=4`. Se generó un nuevo documento aislado con `SETVAR INSUNITS 6` antes del símbolo.

| Evidencia | Resultado |
|---|---|
| L2 | `target/mcp-isolated/20260924-140039-f3e83f1a/report.json`, passed, GUI cerrada; SHA `1BF897BE70EF72E1E0DC4066359D8FB083C4463E7615D9AC0AC18C0580016403` |
| DWG | `synthetic-verified.dwg`, SHA `10422B5A76EE72C5BF60A91A55AD255F677FC9F51BF645CB1AF25F5C97AE6893`; AutoCAD no modificó los bytes |
| L4 | `target/mcp-external/20260924-140100-autocad-2aaea73c/report.json`, SHA `F9C6C5CDFD8A23916BCA30645656F89D6E12679810ED0DDA99DE902C2576F78B`; `audit_and_census_passed`, AUDIT 0/0, unidades 6, salida limpia, 23/23 propiedades |
| Censo AutoCAD | SHA `C82F292D500A9DA3BCE07FD9EAC9AE8F096467915F1B6B3C2DBF5208E0FF6804`; definición `MCP-SYMBOL`, base `(0,0,0)`, un hijo LINE en `A-DIMS` desde `(0,0,0)` hasta `(2,0,0)` |
| Verificador | `block-definition-verdict.json` en el run externo: 10/10 checks; adulterar el extremo local de 2 a 3 produce `failed` |

Los INSERT por handle `74` y `75` conservaron escala/rotación/posición. Aplicando las transformaciones leídas por AutoCAD al hijo local, los extremos efectivos son `(62,0)`→`(63.732050807569,1)` y `(66,0)`→`(70,0)` metros. Esto demuestra la definición y las transformaciones para una línea sintética, sin probar cómo se ve el bloque explotado, atributos, anidamiento, dinámica, edición paramétrica, otras unidades o compatibilidad general. La sonda agrega `block_definitions` al reporte L4 existente; el campo es opcional para dibujos sin ese símbolo.

Reproducción: `python docs/automation/mcp_native_primitives_smoke.py`; después ejecutar `pwsh -NoProfile -File docs/automation/mcp_autocad_probe.ps1 -SyntheticDwg <nuevo-run>/synthetic-verified.dwg -ExpectedInsunits 6 -ExpectedSourceReportSha256 <SHA-del-report-L2> -TimeoutSeconds 120`; finalmente `python docs/automation/masterplan/verify_block_definition_l4.py <nuevo-run>/report.json <run-externo>/report.json`. El verificador ata hashes de fuente, DWG y censo, y comprueba contenido, propiedades y extremos derivados. Los directorios bajo `target` son evidencia local ignorada por Git.
