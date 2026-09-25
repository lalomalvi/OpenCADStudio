# M8: segundo candidato local Windows x64, fuente b79e1b9b

Fecha: 2026-09-25. Estado: `partial_scoped_l4`. El paquete es un artefacto local de prueba, sin firma, sin llamada al modelo y sin aceptación M7/M8. No se publicó como release. El paquete histórico `rc-c875-v1` y sus ensayos permanecen intactos.

## Fuente, guard y bundle

- Git limpio al construir y empaquetar: `b79e1b9bc70b9d7b9c2be93d6d2e7eee040692b1`, rama `codex/mcp-m8-release-candidate`, `origin` fork `lalomalvi/OpenCADStudio`.
- `cargo build --release --locked --bin OpenCADStudio --target-dir target/mcp-release-build -j 1` pasó en 17m53s. `OpenCADStudio.exe --version` informó revisión `b79e1b9bc70b`, perfil `release` y sin features. EXE 106249728 bytes, SHA-256 `EC80DD5DB3609F0CA1E161127669DFCCDB7C5E23A8B83F322083F5EDDE65EAA4`.
- Antes de reconstruir, `stage` con el EXE anterior `c875d652` y raíz nueva `target/mcp-release-bundles/stale-reject-b79e-v1` falló con `Release binary revision differs from source Git SHA`; la raíz de salida no se creó. Esta es la prueba real del nuevo guard.
- `stage` creó `target/mcp-release-bundles/rc-b79e-v1` desde lista explícita de 20 miembros. ZIP SHA-256 `F1E417CA237B130B6076CDDEE7E9C713A275D639A9F5A2CD58B712B332D2EBC8`; manifiesto SHA-256 `C2D767BA9E6AAB685E6BD2D261095B5FEE3E597209D62AE950E135D8425F888F`. Registra `binary_source_revision=b79e1b9bc70b`. `verify` pasó tanto en staging como tras `Expand-Archive` en `extracted`. La lista excluye imágenes de desarrollo, DWG privado, perfiles, tokens y evidencias históricas.

## Smoke ejecutado desde la copia extraída

Desde `target/mcp-release-bundles/rc-b79e-v1/extracted`, `m8_case_cli.py prepare` congeló contrato SHA `35110A6B03BB9E063E4F93B4DF7551D93D445AB387BA43898E89F732F8C21207` para el fixture **sintético** `synthetic-wall.planspec.json`. `run` se invocó una sola vez en `target/mcp-release/synthetic-01` y devolvió `passed_scoped_l2`: cuatro LINE, DWG SHA `174CBBAA892F641309F846BCB33B46C079DA9079EA23519D38F1F7273C07A940`, captura SHA `08D45D440725BCDF4BD1FB0D3C194324012E525C8C702359694CF619AD0E603A`, GUI cerrada. `verify` releyó contrato y artefactos sin ejecutar CAD; reporte SHA `FA6F7E0D11B1224D1DB1A3A93B4F5ED1E982D66135A3DD18D4D27BF24F2D148C`.

Se copió **solo** el DWG sintético verificado a `extracted/target/mcp-isolated/rc-b79e-synthetic-01/release-smoke.dwg`, con SHA idéntico. AutoCAD Core Console 2025 `25.0.162.0.0` reabrió esa copia en el run `target/mcp-external/20260925-024009-autocad-33d11c1e`: AUDIT 0 errores/0 correcciones, `INSUNITS=6`, cuatro LINE, SHA de entrada intacto, salida 0. Reporte externo SHA `F87E574693BFA6BAE741FA24EBACD67C03E47D0D1E395BF7EC3B94E42A9360D2`. `m8_case_l4_mixed.py` cotejó el PlanSpec, contrato, DWG y censo independiente: `passed_scoped_l4 4 4`; veredicto SHA `5491431F724D67EF9615B2D0C5C908F54A1D2D82EB356A8534F5575F69488840`.

La [ejecución CI 36112961441](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36112961441) terminó `completed/success` sobre la fuente `b79e1b9b`, con Rust workspace y suites Python de masterplan/automatización en Ubuntu. Se despachó manualmente; `statusCheckRollup` del PR draft debe verificarse por separado. Localmente las suites 202/202 y 42/42 pasaron antes del build. El [host Linux/Windows 36111979583](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36111979583) pasó sobre el commit anterior `a04657a1`, cuyo cambio posterior fue solo el empaquetador/documentación; no se presenta como check del HEAD actual.

El candidato satisface build, integridad del bundle, repetición de un caso sintético L2 y cotejo AutoCAD L4. Falta llamada real de modelo desde el paquete, revisión visual humana L5, reconstrucción integral y evaluación controlada M7, identidad/uso directo M3, checks automáticos del PR y aceptación M8. No hacer merge ni publicar un release aceptado basándose en este smoke.
