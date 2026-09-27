# OpenCADStudio: avance MCP y actualización del original

Fecha: 2026-09-27. Informe de continuidad solicitado por Luis. La auditoría inicial se conserva abajo. Actualización vigente: permisos resueltos, integración realizada en `codex/mcp-upstream-sync-20260927` y regresión local aprobada (1996 Rust, 202 masterplan Python y 45 automatización; 27 Rust ignoradas). El estado de publicación, CI, hallazgos de guardado y hashes está en [M0-UPSTREAM-SYNC-20260927.md](masterplan/M0-UPSTREAM-SYNC-20260927.md). El masterplan global sigue incompleto.

## 1. Ubicación y preservación

Trabajo autorizado del masterplan: `C:/Users/Luis Martinez/.codex/worktrees/mcp-robustness-masterplan/OPEN CAD`, rama `codex/mcp-m8-release-candidate`. El checkpoint histórico autoritativo es `docs/automation/masterplan/05-CHECKPOINT-Y-CONTINUACION.md`, corte 155. Se leyeron el índice y los cinco documentos base, además del cierre vigente. No se sobrescribió ese historial.

Este informe se guarda en la carpeta actual del proyecto, donde la sesión tiene escritura. El worktree histórico está fuera de las raíces de escritura de esta sesión. La carpeta actual está en `feat/audited-mcp-save`, HEAD `0fa6f008`; contiene un DWG privado sin seguimiento. Se identificó únicamente por el estado de Git: no se abrió, leyó, calculó su hash, movió ni modificó. No usar `git add .`.

No se borraron ensayos, perfiles, paquetes ni worktrees. No se ejecutó CAD ni Luna en esta revisión. La pausa por el límite del 25 de septiembre terminó la implementación anterior; esta nueva instrucción autoriza documentación y revisión de actualización, sin dar por aceptados los gates pendientes.

## 2. SHAs verificados ahora

| Referencia | SHA completo | Estado |
|---|---|---|
| Masterplan local y remoto del fork | `7e61e98c0bf377eb4bf2d96e086f83e0d32e02ff` | Árbol local limpio; último cambio documental |
| Último checkpoint con CI | `113537c2a529d9d8e61dbd39a07cbb12d5a098a7` | Checks REST vigentes aprobados |
| Último código del masterplan | `e86d6a92398427c4601c5a11c54f96f9efd242b6` | Pruebas registradas en checkpoint; sin nueva ejecución local hoy |
| `main` del fork lalomalvi | `f785e15600bbedfc06f255aa1f40dc603820e1ed` | Consulta remota y copia aislada coinciden |
| `main` original HakanSeven12 | `315df5cd4749cc2f8234d4959942895c747d3f8a` | Consulta remota y copia aislada coinciden |
| Ancestro común original/fork/masterplan | `133bfddba9dc994b1b5fadfe581c8ce0ebcd3e2d` | `git merge-base` |

Remotos históricos: `origin=https://github.com/lalomalvi/OpenCADStudio.git`; `upstream=https://github.com/HakanSeven12/OpenCADStudio.git`. No se hizo push a ninguno durante esta revisión.

[PR #1 del fork](https://github.com/lalomalvi/OpenCADStudio/pull/1): REST confirma abierto, draft, mergeable, base `f785e156`, HEAD `7e61e98c`, merge sintético `e9488af3c76f25d4c8400d398b28d732a34e0e67`. Esa base sigue siendo la antigua del fork. Ser mergeable contra ella no acredita compatibilidad con el original nuevo. La consulta GraphQL mediante `gh pr view` falló con HTTP 401; REST permitió leer metadata pública, sin modificar autenticación.

## 3. Avance y pendientes por fase

| Fase | Resultado verificable histórico | Falta |
|---|---|---|
| M0 | Integración experimental revisada y publicada; baseline preservado; censo y builds | Mantener procedencia al integrar upstream nuevo |
| M1 | Cliente stdio persistente, handshake/discovery, readiness, correlación, plazos, journal, recuperación sin reenvío; evidencia L1/L2 | Conciliar GUI nueva tras caída; contrato de resultado común entre procesos; recuperación durable ampliada |
| M2 | Descubrimiento concurrente, identidad/ACL, aislamiento, cierre de sesión propia y cuarentena con evidencia acotada | Generalizar modalidades y fallos de ciclo de vida |
| M3 | Contratos, trazas sanitizadas, artefactos/hash, capture fence, presupuestos y adaptadores; pruebas sintéticas y CLI | Identidad efectiva y uso directo del proveedor; cobertura completa supervisor/generador; eficiencia controlada |
| M4 | PlanSpec tipado y compilación determinista; referencias/cadenas de cotas, puertas v10 y ventanas v11; validaciones adversariales | Generalizar referencias, geometría y resolución dimensional a planos completos |
| M5 | Capas, unidades, cotas nativas/asociación y estilos, bloques/INSERT, impresión métrica y alcances AutoCAD | Semántica integral, edición y fidelidad completa; revalidar con nuevo codec/kernel |
| M6 | QA geométrica, persistencia, capturas por revisión y regiones; comparadores externos con negativos | Cobertura integral topológica/visual y casos distintos |
| M7 | Cinco imágenes de desarrollo, observaciones Luna CLI, planta parcial de 60 entidades cotejada 60/60 en AutoCAD y negativo 59/60 | Plano integral, comparación controlada, independencia de evaluación y L5 humana; no aceptar globalmente |
| M8 | CLI determinista, paquetes sanitizados verificables, smoke L2/L4 4/4 y CI del fork; PR draft | Rebuild del código vigente, integración original, regresión/CI nuevo, aceptación y publicación final |

No pedir otra imagen ni API key: Luis decidió trabajar con las cinco disponibles mediante su plan. Haber usado imágenes de desarrollo no las convierte en una cohorte independiente. No cambiar los criterios después de ver resultados.

## 4. Hallazgos que gobiernan la continuación

1. Una respuesta perdida exige consultar la operación y conciliar efectos. Reenviar una mutación incierta puede duplicar CAD. El bloqueo local de mutaciones serializa reserva, ejecución y recuperación dentro de un `Client`.
2. Dos hilos con el mismo ID y respuesta perdida obtuvieron un efecto con una sola ejecución y una lectura. Dos procesos MCP en GUI real produjeron una sola LINE; uno completó y otro recibió `request_id_reused`. Esto prueba no duplicación en ese alcance, sin demostrar que ambos reciben el mismo resultado.
3. Si una sesión seleccionada desaparece temporalmente de un barrido, el cliente reintenta descubrimiento de solo lectura hasta el plazo, sin lanzar otra GUI. Ambigüedad sigue bloqueando.
4. Escritura al pipe y correlación usan candados distintos. IDs `true`, `1.0` y `"1"` se rechazan; un entero positivo exacto identifica la respuesta.
5. Al perder la GUI propia durante un script, la recuperación falló cerrado y bloqueó nuevas mutaciones. No se aceptó recuperación automática en una GUI nueva.
6. Audit/save/reopen y coincidencia en AutoCAD prueban el artefacto de su alcance. No demuestran que Luna interpretó toda la fuente ni sustituyen revisión humana.
7. La puerta noreste mostró repetibilidad insuficiente: baseline 0/3 y prompt corregido 1/3. Cinco observaciones confundieron trazos; se conservaron sin promover a CAD. Una ventana tuvo 1/3 frente a 3/3 en desarrollo, sin generalización estadística.
8. Recibos CLI/configuración no son un recibo directo Responses API de identidad efectiva y uso. El costo equivalente API histórico no es un cobro de suscripción.
9. El paquete release `rc-b79e-v1` antecede a las últimas correcciones Python. Su éxito no acredita un paquete del HEAD vigente.
10. Checks de HEAD, igualdad de árboles y checks del ref de merge son evidencias distintas. El último HEAD documental no tuvo una ronda separada de CI. No declarar M8 terminado por `mergeable=true`.

## 5. Evidencia reproducible preservada

Rutas de esta sección relativas al worktree histórico, no a la carpeta actual. Reportes no reejecutados hoy; hashes y resultados provienen de los documentos sellados, salvo CI consultado nuevamente abajo.

| Evidencia | Ruta | SHA256 / resultado |
|---|---|---|
| Pérdida GUI propia | `target/mcp-isolated/20260925-030448-gui-loss-a7cbcbcd/gui-loss-report.json` | `08D64FE569A5AE7331C912951079255BCB127A6C22A58F843293A3C83A71A103`; passed_fail_closed |
| Smoke tres entidades tras concurrencia | `target/mcp-isolated/20260925-030802-27b4f9a7/report.json` | `9CA20725D02F02B6DB8231DDF3995D408C2E4FDF55DAA22C5B6D92875DA81628`; saved/reopened |
| Dos procesos mismo ID | `target/mcp-isolated/20260925-035332-cross-client-404bc190/report.json` | `B8706B390E13C2B673772D6A699FDD69750E3803AD4047EFDFB2B5060A6687A5`; una LINE, AUDIT 0/0, GUI cerrada |
| Paquete anterior | `target/mcp-release-bundles/rc-b79e-v1/OpenCADStudio-mcp-rc-windows-x64.zip` | `F1E417CA237B130B6076CDDEE7E9C713A275D639A9F5A2CD58B712B332D2EBC8`; 20 miembros |
| Manifiesto bundle/extraído | `target/mcp-release-bundles/rc-b79e-v1/bundle/manifest.json` | `C2D767BA9E6AAB685E6BD2D261095B5FEE3E597209D62AE950E135D8425F888F` |
| EXE anterior | Bundle desde `b79e1b9bc70b9d7b9c2be93d6d2e7eee040692b1` | `EC80DD5DB3609F0CA1E161127669DFCCDB7C5E23A8B83F322083F5EDDE65EAA4` |
| L5 preparada | `target/mcp-review/apartment-east-divider-northeast-door-v2/review-side-by-side.png` | 60 entidades; revisión humana pendiente |

Últimas suites locales registradas: cliente 26/26, masterplan 202/202, automatización 45/45, py_compile y diff check. No se vuelven a atribuir como ejecutadas el 27 de septiembre.

CI consultado hoy por REST: [36122640507](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36122640507) y [36122643188](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36122643188), ambos `completed/success` en `113537c2`. Cuatro checks `test`, `masterplan-python`, `linux`, `windows` aprobados. Los runs son manuales. El CI histórico `36116579611` permanece documentado como cancelado, sin convertirlo en éxito. Ninguno prueba la integración nueva con `315df5cd`.

## 6. Avance del repositorio original

Copia Git bare aislada: `target/upstream-audit-20260927.git`, creada dentro de la carpeta actual. Se trajeron las ramas del fork como `fork-main` y `masterplan`; se conservaron refs existentes de los worktrees originales.

`git rev-list --left-right --count fork-main...main`: **18 / 112**. Para `masterplan...main`: **182 / 112**. Son commits exclusivos por ascendencia, incluyen merges y posibles cambios equivalentes; no contar como 112 funcionalidades distintas. Diff de upstream desde ancestro: **511 archivos, 51,321 inserciones y 22,166 eliminaciones**.

Cambios relevantes observados en el historial y manifests:

- `f537aff7`: migración a opencadcodec/opencadkernel/opencadgraph y graph overlay; panel y guardado `.ocg` posteriores.
- Cargo vigente: codec rev `4f7bd51`, kernel y constraints rev `8186605`, graph rev `048c9c5`. El HEAD `315df5cd` actualiza codec con fixes #56–#61.
- `e4fa5232`: división de `src/app/command_driver.rs` en módulos de dominio. Reubicar cualquier parche local por función, sin restaurar el archivo monolítico.
- `279a8741` y API-SPEC: ampliaciones de entidades, bloques, publicación y REST; revisar solapamientos con los contratos MCP del fork.
- PDF/XREF: attach, clipping, importación, snapping, ajustes, capas, UI y comandos de automatización. Nuevas rutas de render y persistencia necesitan regresión proporcional.
- `83e1ebd4`: texto automático de cotas vuelve a colocarse desde el estilo; `6d363565`: conversión de cotas asociativas a restricciones. Afecta M4/M5.
- Nuevos dibujos métricos, aislamiento de tests, rendering de texto y cambios de plugins (preview interactivo, repetición y finish_dispatch).
- Aportaciones previas de lalomalvi aparecen integradas: PR #1454 PSETUPIN, #1455 plot isolation y #1460 missing-font hardening. `dddf60d7` incorpora save auditado (#1452). Verificar equivalencia funcional antes de conservar parches duplicados: ascendencia y títulos no bastan.

Archivos generados de auditoría bajo `target`, sin secretos ni planos:
`upstream-commits-20260927.txt`, `upstream-paths-20260927.txt`, `fork-main-merge-conflicts-20260927.txt`, `masterplan-merge-conflicts-20260927.txt`.

## 7. Ensayo de fusión sin tocar ramas de trabajo

`git merge-tree --write-tree --name-only` devolvió exit 1 por conflictos en ambas comparaciones. Es una simulación en la copia Git aislada, sin checkout ni merge publicado.

Conflictos comunes (10):
`docs/automation/README.md`, `docs/automation/mcp_acceptance.py` (add/add), `docs/automation/mcp_eval.py`, `docs/automation/mcp_smoke.py`, `src/app/automation.rs`, `src/app/control/mod.rs`, `src/app/update/file.rs`, `src/io/mod.rs`, `src/mcp.rs`, `src/ui/window/missing_fonts.rs`.

La rama masterplan añade conflictos en `src/app/update/mod.rs` y `src/scene/dimension_assoc.rs`: **12 archivos en total**. Los árboles emitidos con marcadores no son builds aceptables.

## 8. Orden concreto para ponernos al corriente y resubir

1. Conservar los SHAs anteriores y ensayos; trabajar sobre una rama `codex/*` aislada con escritura Git autorizada. Esta sesión puede escribir el informe y la copia bajo target, pero no el worktree histórico ni el `.git` compartido protegido.
2. Integrar `315df5cd` con `7e61e98c` en la rama de integración para resolver una sola vez el conjunto completo de conflictos. Mantener `main` del fork hasta que pase la verificación. No seleccionar globalmente ours/theirs.
3. Auditar paridad de save auditado, fuentes y tests ya incorporados; resolver `src/mcp.rs`, control y automatización preservando journal, request IDs, revisiones, permisos, captures, shutdown y rechazo de replay. Portar cambios de dimensiones a la arquitectura actual.
4. Incorporar upstream de los harnesses conservando el cliente persistente del fork y todas las pruebas negativas. Revisar Cargo.lock y las dependencias nuevas; compilar desde fuente limpia con `--locked`.
5. Ejecutar suites focalizadas MCP/PlanSpec/dimensiones/codec/impresión y las suites relevantes del workspace; registrar fallos nuevos con SHA. GUI aislada y fixtures nuevos únicamente. Revalidar save/reopen y AutoCAD de un sintético. No reutilizar IDs o perfiles ya consumidos.
6. Revisar diff, sanitización y contratos, construir paquete nuevo desde SHA limpio y probar extracción/smoke. Publicar la rama verificada al fork; consultar CI de HEAD y merge/base actualizados por separado.
7. Actualizar main del fork mediante integración revisada cuando sus gates de compatibilidad pasen; mantener visible la falta de aceptación global M7/M8. Sin push ni PR al autor. Sin force push ni cambios a protecciones.

Esta revisión dejó preparada la información para integrar. **No se efectuó todavía merge, commit o push nuevo**, ni se sincronizó main del fork: los conflictos y el build nuevo siguen pendientes. Las evidencias locales generadas y este documento son el resultado nuevo de esta sesión.

Verificación documental: `git diff --no-index --check -- NUL docs/automation/MASTERPLAN-ESTADO-Y-UPSTREAM-20260927.md` no emitió errores de espacios. El documento está sin seguimiento en la carpeta actual; se conserva para revisión/publicación posterior. La primera lectura de Git ejecutada desde el worktree histórico confirmó HEAD y árbol limpio; una comprobación final con `git -C` fue rechazada por `dubious ownership` (propietario Luis frente al usuario sandbox). No se cambió `safe.directory` ni configuración global, ni se eludió el bloqueo. Antes de integrar desde ese worktree se necesita un entorno con propiedad/permisos Git adecuados. La comparación aislada y las consultas remotas anteriores sí terminaron.

## 9. Prompt de continuidad

> Continúa OpenCADStudio desde este informe del 2026-09-27 y el corte 155 del checkpoint histórico. Revisa AGENTS, permisos, los seis documentos base, estado de Git y remotos. Preserva el DWG privado y todos los ensayos. Verifica remotos otra vez: masterplan 7e61e98c, fork-main f785e156 y upstream-main 315df5cd eran los SHAs al corte. Utiliza la copia target/upstream-audit-20260927.git para reproducir divergencia 18/112 y 182/112 y los 10/12 conflictos, sin asumir que refs siguen iguales. Prepara una rama codex de integración aislada con permisos de escritura; integra el original en el masterplan preservando controles persistentes y revisando parches ya absorbidos por upstream. Resuelve por función, revisa nuevos codec/kernel/graph y command_driver modular. Ejecuta tests, build locked y GUI/AutoCAD sintéticos nuevos; reconstruye el paquete desde código limpio vigente. Publica solo cambios verificados al fork lalomalvi/OpenCADStudio, sin force push ni envío al autor. No pidas sexta imagen ni API ni repitas slots consumidos. Mantén M1 recuperación GUI, M3 identidad/uso directo y M7 integral/L5/evaluación sin aceptación mientras falte evidencia. Documenta SHAs, CI, diferencias, fallos, pendientes y continuación antes de cerrar.
