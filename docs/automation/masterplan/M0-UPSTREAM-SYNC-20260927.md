# Integración del original en el fork — 2026-09-27

Estado: regresión local aprobada; publicación y CI del commit de integración pendientes en este corte. Alcance autorizado: actualizar el fork lalomalvi/OpenCADStudio conservando el masterplan y ensayos. No hay autorización de publicación al autor ni aceptación global M7/M8.

## Procedencia

- Base del masterplan: `7e61e98c0bf377eb4bf2d96e086f83e0d32e02ff`.
- Original a integrar: `315df5cd4749cc2f8234d4959942895c747d3f8a`.
- Main del fork previo: `f785e15600bbedfc06f255aa1f40dc603820e1ed`.
- Ancestro común: `133bfddba9dc994b1b5fadfe581c8ce0ebcd3e2d`.
- Rama aislada: `codex/mcp-upstream-sync-20260927`.
- Worktree: `C:/Users/Luis Martinez/.codex/worktrees/mcp-upstream-integration/OPEN CAD`.

La primera preparación falló por permisos de solo lectura. Luis habilitó solicitudes de aprobación y se preparó la rama/fusión mediante ejecución aprobada. No se modificaron ACL, safe.directory, configuración global ni protecciones. No se abrió/modificó el DWG privado. Las evidencias ignoradas permanecen en el worktree histórico, no se copian a Git.

## Cambios del original

112 commits exclusivos del original y 182 exclusivos de la rama masterplan desde el ancestro; no equivalen a cantidades de funciones. Cambio upstream: 511 archivos. Codec se renombra a `codec`/opencadcodec rev `4f7bd51`, kernel rev `8186605`, graph rev `048c9c5`; command_driver se divide en módulos. Se conservan graph, nuevas operaciones de entidades/bloques/REST, PDF/XREF y mejoras de dimensiones, render e interfaz. Parches previos de save, fuentes y tests ya tienen aportaciones upstream; se fusionan por función, sin reintroducir versiones antiguas de archivos completos.

## Resolución de los 12 archivos

| Archivo | Decisión |
|---|---|
| docs/automation/README.md | Conservar las dos vías de verificación externa, vendor-neutral y AutoCAD histórico |
| docs/automation/mcp_acceptance.py | Usar Client persistente, handshake y readiness; conservar aceptación versionada |
| docs/automation/mcp_eval.py | Conservar readiness y selección explícita del cliente persistente |
| docs/automation/mcp_smoke.py | Verificar correspondencia única de operaciones anunciadas/esquema y operaciones nuevas de ambos lados; no fijar el antiguo conteo 19/38 |
| src/mcp.rs | Unir operaciones, validaciones y parámetros; mantener run_script, journal, propiedad/cierre y captura fenced |
| src/app/control/mod.rs | Unir query/capabilities e interacción upstream; conservar exigencia de document_id en mutaciones y shutdown propio |
| src/app/automation.rs | Migrar a codec, conservar operaciones nuevas; usar stack 8 MiB upstream en PLINE; integrar guardado DWT con controles del fork |
| src/app/update/file.rs | Preservar color ACI upstream y texto semántico PDF del fork; versión de guardado codec |
| src/app/update/mod.rs | Mantener mensajes Graph y ambas fases de captura del fork |
| src/io/mod.rs | Migrar parse_target_version a codec y soportar DWT en guardado atómico protegido |
| src/scene/dimension_assoc.rs | Preservar test de referencias de caras paralelas con imports codec |
| src/ui/window/missing_fonts.rs | Adoptar builders de diálogo upstream conservando bloqueo de botones durante descarga |

Además, los módulos propios metric_plot/wall_edit y los tests agregados usan el namespace codec. Dos fixtures PDF upstream recibieron el nuevo campo opcional semantic_text.

## Incompatibilidades adicionales corregidas

El esquema compartía center entre un booleano de plot y un punto de transformación, plot_style entre CTB arbitrario y los dos estilos métricos, y name entre acciones y nombres libres. La resolución conserva la unión tipada y restricciones por operación; evita claves duplicadas y el rechazo accidental de nombres de bloque/grupo/layout. El backend conserva sus validadores.

El shortcut DWT upstream escribía scratch/rename antes del guardado protegido del fork. Se eliminó ese bypass y DWT se trata como familia DWG mediante la ruta atómica con versión, lease y detección de cambios externos. La prueba existente de template comprueba DWT 2013, reapertura y rechazo de save con edit_lock_conflict, sin reemplazar la salida. No se implementó una garantía nueva para save_verified de DWT: su alcance sigue DWG/DXF.

## Verificaciones al redactar

- Masterplan Python: 202/202, 20.512 s.
- Automatización Python: 45/45, 4.899 s; cliente 26 incluido, no sumarlo otra vez.
- Sin marcadores de conflicto en Rust/Python y git diff --check sin errores.
- `cargo test --workspace --locked --no-run -j 2`: compilación en curso en esta nota inicial; no declarar éxito antes de estado terminal.
- Smoke GUI sintético, pruebas Rust y CI de la integración: pendientes.

## Hallazgos de compilación de la integración

El primer build falló al expandir el esquema JSON combinado (recursion_limit 256); se aumentó a 512. El siguiente detectó duplicados de document_audit/save_verified_request: upstream ya absorbió implementaciones relacionadas. Se conserva una sola implementación con snapshot document_for_save del original (excluye overrides visuales/XREF resueltos), materialización de bloques de dimensiones y timings del fork. Se consolidaron también seis tests duplicados, preservando las aserciones adicionales del fork. Se conservaron los errores como fallos de integración; ningún build fallido se declara aprobado.

El esquema de batch tenía una segunda lista de parámetros que rechazaba operaciones nuevas anunciadas. Ahora deriva sus parámetros y restricciones condicionales del esquema de requests individuales, quitando solo campos del ejecutor/envolvente; no permite batches anidados. La prueba existente comprueba parámetros de entidades, center, name y las restricciones CTB en su ubicación condicional. Cuatro líneas vacías finales de archivos upstream se retiraron para diff-check.

## Evidencia nueva conservada (antes del commit)

El ejecutable se construyó desde el árbol de fusión aún sin commit; SHA256 `08BB0ACA0798A2BA58E10F2D93C604F0B43B8746A663FD0DE03DEB081FF9F882`. No es paquete de release ni binario atribuido a un SHA limpio. Las correcciones posteriores a estas sondas afectan fixtures de tests, no las operaciones medidas.

| Verificación | Resultado | Evidencia local bajo target |
|---|---|---|
| L2 sintético | 3 entidades, save_verified/reapertura/captura fenced, AUDIT 0/0, GUI salida | mcp-isolated/20260927-023300-3fe67255/report.json |
| Dos clientes | Una sola LINE; segundo request_id_reused; GUI salida | mcp-isolated/20260927-023453-cross-client-db9488da/report.json |
| MCP stdio | Legacy/modern handshake, discovery, esquema y rechazo de entradas pasan | upstream-sync/20260927-023758-discovery-83fa1957/report.json |
| AutoCAD 2025 | 3/3 geometrías/handles, INSUNITS 6, AUDIT sin errores/arreglos y DWG intacto | mcp-external/20260927-023653-autocad-35fef6f2/report.json |
| Rust focalizado | 24/24 MCP; DWT falló por usar loader general en vez de lector de template | upstream-sync/20260927-023854-focused-d322e95d/report.json |
| Primera suite Rust | 1776 passed, 4 failed, 24 ignored; no es aceptación | upstream-sync/20260927-023159-fe504b12/rust-tests.log |

Hashes SHA256 de reportes, en el mismo orden de las primeras cuatro filas: `5B17A5DBBD02A4A07C1DBAAF8670EDEDB846EBF86E25228CEE5814B560CDF801`, `FCCDF33CA55B34386129A172540F12FCE4B3BEC615321A2CD63EE54CB2C91176`, `6F2DE415104940BA416D39F5F0AC9BDC367CC56C16BFE6BCC7CBBAF01EED3ED8`, `07796DCE8457E8A95F889B2CEF3B5B83C4C9EC654854BCB26077BBB412A87924`. DWG sintético: `59BEACB7E287DC2CEB62C5CAE9374E8FD7497A4677433441A7D803FC968B23E9`. Log de suite fallida: `98DA28B746BB6F35ED5D5E0D3FB5713A219807565ABF09800DE269F2B61CCB9A`.

La suite señaló dos fixtures de owned_root incorrectos bajo el aislamiento local: TEMP estaba dentro del repo y sus archivos supuestamente extranjeros también quedaban dentro de current_dir. Se usan ahora directorios owned_root sintéticos separados y sus archivos extranjeros quedan como hermanos, manteniendo el guard real. La prueba DWT lee sus bytes como DWG, igual que apply_template upstream, y comprueba versión/bloqueo antes del template-based new. El cuarto fallo fue ReplaceFileW, error Windows 1175 al guardar por segunda vez. El caso pasó en un perfil focalizado nuevo; esto no borra el fallo ni demuestra ausencia de intermitencia. Si reaparece, investigar sin reejecutar mutaciones inciertas ni degradar el reemplazo a delete+write.

La segunda suite está en `upstream-sync/20260927-024431-77a29979`; resultado pendiente al añadir esta nota. Los smokes positivos no aceptan GUI recovery ni resultado común entre procesos; AutoCAD valida solo las tres primitivas del fixture.

## Regresión Windows reproducida y corrección de persistencia

La segunda suite (`20260927-024431-77a29979`) terminó con 1779 passed, 1 failed, 24 ignored: los fixtures owned_root quedaron corregidos y el guardado repetido pasó; DWT falló al leer mediante otro handle mientras la propia aplicación tenía lease exclusiva. La prueba usa ahora `read_drawing`, que ya ofrece lectura mediante la lease de la sesión, igual que apply_template; no se quitó la protección.

La tercera suite (`20260927-025659-b23f1a19`) volvió a terminar 1779 passed, 1 failed, 24 ignored. DWT, su versión 2013, rechazo con edit_lock_conflict y creación posterior desde template pasaron. Reapareció el fallo de reemplazo Windows 1175. Los tres runs y sus perfiles/logs se preservan.

[Microsoft ReplaceFileW](https://learn.microsoft.com/windows/win32/api/winbase/nf-winbase-replacefilew) especifica que 1175 conserva los nombres originales del destino y del reemplazo; 1176/1177 pueden tener resultados distintos y no se reintentan. Se implementa un máximo de cinco intentos del mismo archivo ya serializado, con esperas de 25/50/100/200 ms (375 ms total), solo en guardados protegidos de Windows con huella esperada. Identidad de archivo y huella se revalidan después de cada espera y antes del reemplazo. Se mantiene la lease y su reader; no se reejecuta el comando CAD, no se repite serialización/backup, no se borra el destino, no se reenvía ocs_execute. Cualquier cambio externo o error distinto de 1175 aborta. El fallo terminal sigue siendo fallo.

Tres tests de seguridad comprueban revalidación por intento, abortar antes del siguiente commit ante cambio externo, límite de cinco intentos y ausencia de retry para errores inciertos o guardados sin protección. No atribuir todavía causa específica al 1175 (no está demostrada una causa como antivirus). La cuarta suite `20260927-031227-71b1a6bb` está en curso al añadir esta nota. Las sondas previas al cambio de persistencia siguen siendo históricas positivas, no son atribución binaria del código posterior: se requiere un smoke nuevo del ejecutable resultante.

## Resultado visual y evaluación

Luis abrió el DWG parcial de 60 entidades y comentó que inicialmente quedó bien parcialmente. Es una observación humana positiva sobre ese alcance, sin aprobación de lámina completa, cotas, topología o M7 global. Consultar `../RESULTADOS-MCP-20260927.md` para tablas de los seis casos y comparación de prompts. La puerta sigue 0/3 vs 1/3; no ocultar fallos ni repetir slots para mejorar la cifra.

## Publicación y continuación

Publicar solamente la rama verificada al fork. Antes de actualizar main, confirmar pruebas/CI, ascendencia de upstream y del masterplan, diff sanitizado y SHAs remotos. Esta integración no constituye release ni aceptación global M7/M8. Los reportes de cada nuevo run deben tener perfil, ID y salida propios; preservar los históricos. Nunca publicar a upstream, usar force push o tocar el DWG privado.

## Cierre de regresión local

La cuarta suite terminó con **1996 passed, 0 failed, 27 ignored** en 31 grupos, exit 0, incluidos doctests; núcleo de OpenCADStudio 1783 passed/24 ignored y todas las suites de integración ejecutadas. Comando: `cargo test --workspace --locked -j 1 -- --test-threads=1`, con APPDATA/LOCALAPPDATA/TEMP/TMP solo del proceso bajo un perfil sintético nuevo. Tiempo total con recompilación: 960.567 s. Log `target/upstream-sync/20260927-031227-71b1a6bb/rust-tests.log`, SHA256 `365BB611DE89ADC8D772465F29699444758A1E31D1EE29BFD41B1D0B91D36ECA`. No sumar los 24 tests MCP focalizados otra vez. Las 27 ignoradas, incluidas pruebas GPU y doctests, no son pruebas aprobadas.

El guardado repetido, DWT 2013 y su rechazo por edit lock, propiedad/cierre, las tres pruebas de commit acotado y el resto del workspace pasaron. Se requiere huella esperada y reader de la lease para habilitar el retry Windows. Esta aprobación no afirma que 1175 nunca pueda ocurrir: agotado el límite, el guardado sigue fallando y preserva el destino. Los tres runs anteriores fallidos permanecen intactos.

Python permanece 202 masterplan/45 automatización aprobadas. Se revisó la captura L2 anterior: dos líneas y círculo visibles, sin overlays. El binario anterior a este cambio de persistencia sigue identificado por su hash histórico; para el SHA publicado se generará un build nuevo y una sonda nueva, sin reusar IDs/perfiles. La publicación queda limitada al fork y a sincronización de código, sin release ni aceptación global del masterplan.
