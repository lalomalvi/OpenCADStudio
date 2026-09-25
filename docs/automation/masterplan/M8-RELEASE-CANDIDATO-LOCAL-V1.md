# M8: candidato local Windows x64, corte 138

Fecha: 2026-09-25. Alcance: paquete reproducible de prueba para un caso sintético. Estado: `partial_scoped_l4`; M8 y M7 no aceptados.

## Fuente y compilación

- Fuente Git limpia al empaquetar: `c875d652ac60bd3b2ef1ab885cbdf795e3e1b5e3` en `codex/mcp-m8-release-candidate`.
- `cargo build --release --locked --bin OpenCADStudio --target-dir target/mcp-release-build` pasó desde ese SHA. La segunda compilación tras incorporar el guard de PE AMD64 pasó también.
- `OpenCADStudio.exe --version`: `OpenCADStudio 2026.38+201.gc875d652`, revisión `c875d652ac60`, perfil `release`, sin features.
- `Cargo.lock` SHA-256 `8A5C4B498C2352D4DDC62673EF730B99F9EAAB4AA0904953D5AEAF1E9881C4C5`.
- EXE AMD64 de 106249728 bytes, SHA-256 `17B3DCA8B0AD5E204D033440AB0E25CF3A3E3DDEECDC0607BAE1EC8622023EAC`.

## Paquete y controles

`python docs/automation/masterplan/m8_release_package.py stage --root target/mcp-release-bundles/rc-c875-v1 --binary target/mcp-release-build/release/OpenCADStudio.exe` construyó el ZIP desde lista explícita de 20 miembros públicos. Incluye ejecutable, CLI, cierre de imports Python, fixture sintético, sonda externa, guía, licencia y requisitos; no incluye imagen de desarrollo, DWG privado, perfil ni evidencia histórica. El empaquetador exige árbol Git limpio, binario de `target/mcp-release-build`, cabecera PE AMD64, verifica hashes y rechaza miembros extra o alterados.

- ZIP: `target/mcp-release-bundles/rc-c875-v1/OpenCADStudio-mcp-rc-windows-x64.zip`, SHA-256 `0D81353A5632F104BA78BBF5927EEF4F496BD4E3706F5E5924DBEB6B252E74E5`.
- Manifiesto: SHA-256 `C0BBB61495A5D3E1C571530928A3E8DF0F323EE8ACF7EAFC59841C5569A9D026`.
- `verify` pasó en el staging y de nuevo tras `Expand-Archive` en `target/mcp-release-bundles/rc-c875-v1/extracted`.
- Manifiesto declara `candidate_partial_m7_gates_open`, `acceptance_m8=false`, `model_call=false`; paquete sin firma. No publicar el ZIP como release aceptado.

## Smoke desde el paquete extraído

Con CWD `target/mcp-release-bundles/rc-c875-v1/extracted`, se ejecutó `m8_case_cli.py prepare`, `run` una sola vez y `verify` sobre `docs/automation/masterplan/fixtures/synthetic-wall.planspec.json`, con `--binary OpenCADStudio.exe` y raíz nueva `target/mcp-release/synthetic-01`. Contrato SHA `9F2E5854FE621BA943366281A12DF837E22C775F7CFA5D1B9302BD57739074B0`. Resultado `passed_scoped_l2`: cuatro entidades, DWG SHA `174CBBAA892F641309F846BCB33B46C079DA9079EA23519D38F1F7273C07A940`, captura SHA `08D45D440725BCDF4BD1FB0D3C194324012E525C8C702359694CF619AD0E603A`, GUI salida normal.

Se copió **solo** ese DWG sintético a `extracted/target/mcp-isolated/synthetic-01/release-smoke.dwg`. `pwsh -NoProfile -File docs/automation/mcp_autocad_probe.ps1 -SyntheticDwg target/mcp-isolated/synthetic-01/release-smoke.dwg -ExpectedInsunits 6 -TimeoutSeconds 90` produjo `target/mcp-external/20260925-003530-autocad-8b6d9596/report.json`: AutoCAD Core Console `25.0.162.0.0`, AUDIT 0 errores/0 reparaciones, INSUNITS 6, SHA de entrada sin cambio, cuatro LINE, salida 0. `m8_case_l4_mixed.py` cotejó PlanSpec, contrato, DWG y censo externo: `passed_scoped_l4 4 4`, veredicto en `target/mcp-release/synthetic-01/l4-verdict.json`.

Pruebas: `python -m unittest discover -s docs/automation/masterplan -p test_*.py -q` 193/193; `python -m unittest discover -s docs/automation -p test_*.py -q` 40/40. Los checks del PR se registran por separado.

La primera invocación `cargo test --workspace --locked` no pasó: varias compilaciones simultáneas agotaron el archivo de paginación Windows (OS 1455), y `tests/annotative_context_roundtrip.rs` tenía una llamada `hex(raw)` incompatible con la firma `hex(&[u8])`. El test se corrigió a `hex(&raw)`. La repetición secuencial `-j 1` descubrió inicializaciones de test desactualizadas en `tests/pdf_export_text_check.rs` y `tests/pdf_export_images_check.rs`: faltaba `semantic_text: None` en `PlotWire`; se corrigieron. `cargo test --no-run -j 1` continuó enlazando binarios de integración grandes sin completar en tiempo razonable; se canceló para ejecutar `cargo check --workspace --tests --locked -j 1`, que **pasó** en 3m43s y verifica todos los tests sin enlace. La ejecución completa Rust queda como gate separado. Estos fallos iniciales permanecen registrados y no invalidan el smoke del ejecutable release anterior.

## Límite y siguiente gate

El paquete permite reproducir un PlanSpec **ya preparado** y un fixture sintético; no invoca Luna ni transforma imagen en PlanSpec. La comparación L4 es de cuatro LINE, no de fidelidad de planta. Siguen pendientes M3 identidad/uso directo, M7 plano integral, cohorte independiente y L5 humana, compatibilidad adicional, revisión de diff/checks y merge de M8. Las cinco imágenes autorizadas permanecen material de desarrollo. No se tocó el DWG privado ni el remoto del autor.
