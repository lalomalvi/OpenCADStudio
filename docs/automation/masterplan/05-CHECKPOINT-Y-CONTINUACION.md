# Checkpoint y continuación
Corte inicial: 2026-09-23. Este documento describe el estado antes del commit documental; consultar historial Git y remotos para el SHA final de publicación.

## Estado conservado
- Raíz del usuario: C:/Users/Luis Martinez/Desktop/PROYECTOS DE CODIGO/02. EN DESARROLLO/OPEN CAD.
- Rama raíz: feat/audited-mcp-save, 0fa6f008; original FIBRA OPITA PLANETARIO.dwg sin seguimiento. No añadirlo a Git.
- Worktree del plan: C:/Users/Luis Martinez/.codex/worktrees/mcp-robustness-masterplan/OPEN CAD.
- Rama del plan: codex/mcp-robustness-masterplan, base origin/main 133bfddb.
- Endurecimiento: C:/Users/Luis Martinez/.codex/worktrees/image-to-cad-hardening/OPEN CAD, rama codex/image-to-cad-hardening, HEAD d002b08a4c70a88de5af5df103b4ecbfb6890b26.
- Worktree Luna: C:/Users/Luis Martinez/.codex/worktrees/a4be/OPEN CAD, detached d002b08a.
- Binario: C:/Users/Luis Martinez/.codex/worktrees/image-to-cad-hardening/OPEN CAD/target/release/OpenCADStudio.exe.
- Evidencia privada: C:/Users/Luis Martinez/.codex/acceptance/open-cad/2026-09-23-luna-floorplan-01.
- Tarea Luna: 01a0cef6-c939-7d30-929b-5c649b33449e.

La raíz no está en main y no recibe automáticamente los documentos de la otra rama; abrir este worktree o fetch/checkout controlado. El ensayo permanece partial. No hay revisión externa ni visual del usuario aceptada. La próxima sesión no necesita abrir el DWG para M0/M1.

## Publicación verificada de esta sesión
- Documentación: commit 9814cd17a1ad95b0565cd1454da82d695a62b111 (incluye normalización de finales de archivo).
- Merge documental publicado en origin/main: ed8dbaf2a87494f23d3960232fda4a212fc05a01.
- Rama experimental respaldada en origin/codex/image-to-cad-hardening: d002b08a4c70a88de5af5df103b4ecbfb6890b26; no integrada a main.
- El worktree del plan quedó en codex/mcp-masterplan-integration siguiendo origin/main.
- Se comprobaron enlaces Markdown locales y git diff --check del diff integrado. No se ejecutó suite CAD porque este cambio solo contiene documentación.
- El cierre se integra con commit posterior al merge indicado; obtener su SHA con git log y contrastar git ls-remote origin refs/heads/main.
- No se publicaron PNG, DWG, JSONL privados ni cambios en upstream. No se creó PR: merge local documental y push directo autorizado al fork.

## Primera entrega siguiente
M0 completo y un cambio acotado M1 con pruebas de protocolo. No prometer completar todos los hitos en un turno. Antes de editar comprobar AGENTS.md en rutas aplicables, HEAD/remotos, manifest del binario y cambios ajenos.
Revisar especialmente la diferencia entre capacidades del programa ya disponibles y capacidades no usadas por Luna. Revisar asistencia supervisora y telemetría para no declarar ejecución autónoma total.
Mantener todos los ensayos nuevos en directorios nuevos; no reescribir el corte 2026-09-23.

## Prompt listo para pegar
Continúa el masterplan de robustecimiento de OpenCADStudio MCP. Empieza leyendo por completo docs/automation/masterplan/00-INDICE.md y sus cinco documentos vinculados en el worktree C:/Users/Luis Martinez/.codex/worktrees/mcp-robustness-masterplan/OPEN CAD. Verifica Git/remotos/AGENTS.md y el estado real antes de confiar en este checkpoint.

Ejecuta M0 y después el primer alcance verificable de M1: base de integración revisada, cliente MCP persistente reutilizando los harnesses existentes, handshake, readiness, correlación, timeouts y recuperación sin duplicar mutaciones. Implementa y prueba ese alcance; actualiza backlog y checkpoint. El código previo está en codex/image-to-cad-hardening (d002b08a) y todavía requiere revisión para integrarlo a main. No supongas que la publicación documental lo integró.

Preserva originales y evidencia del ensayo 2026-09-23-luna-floorplan-01. Usa fixtures sintéticos para pruebas técnicas. El ensayo de imagen permanece parcial: 273 entidades todas en capa 0, cotas como texto, sin aceptación de fidelidad externa. No atribuyas las diferencias de cadenas al plano original sin verificar extremos/caras/ejes. No abras ni modifiques el DWG del usuario para este hito.

Mantén controles críticos en backend y contratos. Guarda evidencia automática y sanitizada. No transcribas hashes manualmente ni deduzcas modelo efectivo de config.toml. Respeta negativas de política sin eludirlas. No publiques planos, logs crudos ni credenciales. La reconstrucción visual de futuros benchmarks usa exclusivamente GPT-6 Luna medium salvo protocolo nuevo; el desarrollo del software no tiene esa restricción. No lances evaluaciones de modelos adicionales por iniciativa propia.

La autorización vigente permite implementar el alcance, pruebas, documentación, commits, merge y push al fork lalomalvi/OpenCADStudio cuando el diff y los checks estén conformes. Inspecciona siempre origin/upstream; no publiques al repositorio del autor. Si es apropiado crear PR en el fork, adjúntalo a la tarea. No uses force push ni incluyas archivos ajenos. Cierra con resultados passed/failed/partial/pending, SHAs local/remoto, pruebas ejecutadas, riesgos reales y el siguiente prompt.

## Corte M0/M1 — 2026-09-23 (vigente)

Worktree: `C:/Users/Luis Martinez/.codex/worktrees/mcp-robustness-masterplan/OPEN CAD`. Rama: `codex/mcp-persistent-client`. `origin` es `lalomalvi/OpenCADStudio`; `upstream` es `HakanSeven12/OpenCADStudio`. Base comprobada `origin/main` = `a069d7f146c27a18255f2a47d733bf678385feae`. El commit `55fc9948` documentó la decisión de integración antes del merge `c449853c` de la rama experimental `d002b08a`. Véanse `M0-INTEGRACION.md` y `BASELINE.json`; el generador no leyó el DWG original. El hash del Release previo coincide con el documentado. No se han modificado el original ni el ensayo histórico.

El primer corte M1 está en `docs/automation/mcp_client.py`: proceso stdio persistente, negociación moderna, correlación, cola limitada, drenado de stderr, timeout/deadline monotónico, sondeo de arranque sin doble launch, selección explícita y consulta de operación tras respuesta de mutación perdida. Los tres harnesses de evaluación importan el cliente compartido. `docs/automation/test_mcp_client.py` y `tests/fixtures/mcp_stdio_fake.py` dan ocho pruebas L1. `mcp_client.md` describe el contrato y sus límites.

Verificaciones observadas: ocho pruebas L1 pasaron; `py_compile` pasó; `git diff --check` pasó; `mcp_smoke.py` contra el Release anterior y contra el binario debug de este worktree pasó; el cliente nuevo negoció `2026-07-28` y enumeró cuatro herramientas reales. `cargo test --lib mcp::tests` pasó 13/13, y `cargo test --lib` pasó 1665 con 24 ignored y cero fallos; hubo cuatro warnings preexistentes. `cargo build --bin OpenCADStudio` pasó. El hash del binario debug lo genera `BASELINE.json`. No se lanzó la evaluación GUI sobre una sesión de usuario ni se abrió el DWG. L2 CAD sintético y L3–L5 siguen pending. El formato formal de readiness del servidor, precondiciones cliente obligatorias de documento/revisión, recuperación de lotes `run_script` tras pérdida de transporte, journal durable, propiedad/cierre y telemetría quedan pendientes.

### Publicación verificada del corte

- Código y evidencia M0/M1: `6db1b790eeb0609f5efdf46d7e20d6f4a09a4322`.
- `origin/codex/mcp-persistent-client` y `origin/main` devolvieron ese SHA en `git ls-remote` después de sendos push no forzados. `main` avanzó desde `a069d7f1`; incluye el merge explícito `c449853c` de la rama experimental y el commit de implementación.
- Destino exclusivo: `https://github.com/lalomalvi/OpenCADStudio.git`. No hubo push a `upstream` ni PR al repositorio del autor. No se creó PR en el fork: el usuario autorizó merge/push y ambos refs se publicaron directamente.
- El commit de este último registro documental tendrá un SHA posterior al de código. Verificarlo en la próxima sesión mediante `git log -1` y `git ls-remote origin`; el propio archivo no puede contener su SHA final sin crear otro commit.
- Revisión de publicación: 13 archivos de implementación/checkpoint, cero DWG/PNG/JPG/JSONL añadidos, cero coincidencias de patrones de secretos en el diff staged, enlaces Markdown locales completos, `git diff --check` aprobado. El caso histórico y el DWG del usuario permanecen intactos.

### Prompt de continuación tras este corte

Lee `docs/automation/masterplan/00-INDICE.md`, los cinco documentos vinculados y este corte vigente. Empieza con `git status --short --branch`, `git remote -v`, `git log -3 --oneline` y `git ls-remote origin refs/heads/main refs/heads/codex/mcp-persistent-client`; contrasta los SHAs publicados con el checkpoint. Reproduce `python -m unittest discover -s docs/automation -p test_mcp_client.py -v` y los tests Rust focalizados. Continúa M1: añade el contrato formal `starting/ready`, selecciona sesión por identidad y documento, exige revisión antes de mutaciones, y resuelve recuperación de `run_script` por request_id sin repetir efectos. Implementa pruebas de fallos y un L2 sintético aislado antes de afirmar aceptación CAD. Preserva el DWG y el ensayo privado; no publiques secretos ni envíes nada a `upstream`.

## Corte en progreso M1/M2 — 2026-09-23

La sesión siguiente al corte publicado trabaja en `codex/mcp-lifecycle-and-recovery`, basada en `f785e15600bbedfc06f255aa1f40dc603820e1ed`. Al iniciar este corte, `origin/main` y `origin/codex/mcp-persistent-client` devolvieron ese mismo SHA. `origin` sigue siendo el fork `lalomalvi/OpenCADStudio`; `upstream` sigue siendo el repositorio del autor. Verificar de nuevo antes de publicar: este apartado se redactó antes del commit y push del corte.

Cambios: `ocs_sessions` expone estados `absent/starting/ready/failed` y arranque sin doble lanzamiento; descriptor con PID, ejecutable e instante de inicio; descubrimiento paralelo acotado y conexión directa al descriptor elegido; precondición de documento/revisión; progreso de `run_script` consultable por `request_id` dentro del mismo proceso MCP; cliente que no reenvía mutaciones inciertas y bloquea al perder la prueba de resultado. El journal entre reinicios, ACL de descriptor en Windows, heartbeat, cuarentena y cierre formal de sesión propia siguen pendientes. `mcp_client.md` delimita el contrato.

Ensayos L2 bajo `target/mcp-isolated`:

- `20260923-184721-770a24ab`: **failed** por modales de inicio; `report.json` original preservado.
- `20260923-185016-a0cf7e3e`: **failed** por sondeo transitorio de sesión; `report.json` original preservado.
- `20260923-185109-3e55f0f9`: **passed** con binario anterior a la última corrección; 3 entidades sintéticas, audit/save_verified/hash y salida.
- `20260923-185832-eab9a934`: **failed** porque `close_modal` reveló otro modal y el cliente trató `waiting_input` como fallo incierto; `report.json` preservado.
- `20260923-190435-10a7ca1c`: **passed**; `report.json` generado contiene hashes del binario y DWG sintético, tamaño, PID y sesión. Tres entidades, `save_verified` y salida del PID propio. Los PID de los tres ensayos fallidos también salieron tras cierre de ventana con ruta de ejecutable comprobada; no se forzó terminación.
- `20260923-191629-18cb7573`: **passed** con el binario reconstruido tras el límite de descriptor y la marca de inicio obtenida del SO; `report.json` local contiene hashes y `gui_exited: true`. Es el L2 final del corte.

Los artefactos L2 no se añaden a Git. No se abrió ni modificó el DWG del usuario, y no se cambió el ensayo histórico. El L2 no acredita L3 (interpretación de imagen), L4 (motor externo) ni L5 (revisión humana). Las pruebas L1 Python más recientes dieron 15/15; Rust focalizado dio 15/15. `cargo test --lib` dio 1667 passed, 24 ignored y cero fallos. La medición directa del binario de test en diez repeticiones con 100 descriptores sintéticos muertos dio 1851.7–1909.1 ms, p50 1869.7 ms y p95 conservador 1909.1 ms. La revisión final del diff estaba pendiente al redactar.

### Prompt de continuidad desde este corte

En el worktree `C:/Users/Luis Martinez/.codex/worktrees/mcp-robustness-masterplan/OPEN CAD`, lee el índice y los cinco documentos. Verifica `AGENTS.md`, Git/remotos, estado local, SHA remoto y pruebas: no des por publicado este corte sin `git ls-remote`. Conserva los fallos L2 originales. Completa M1.6 con recuperación durable o declara claramente la brecha; después M2 con identidad de proceso, política de documentos sucios y cierre de sesión propia, midiendo p50/p95 de descubrimiento. Prosigue M3–M8 por gates y fixtures sintéticos sin abrir el DWG del usuario ni publicar artefactos privados. Si un gate exige oracle, motor externo o revisión del usuario, registra exactamente qué evidencia falta. Mantén `upstream` intacto.

## Segundo corte M2 — 2026-09-23, en progreso

La rama `codex/mcp-lifecycle-and-recovery` publicó el primer corte en `origin/codex/mcp-lifecycle-and-recovery` con SHA `94967c302711a427d759c1ebe6784f1228cb95a9`; `origin/main` permaneció en `f785e15600bbedfc06f255aa1f40dc603820e1ed`. Se comprobó con `git ls-remote`. No hubo push a `upstream`. El segundo corte sigue sin commit al redactar; verificar SHA después de publicarlo.

M2 añadió `shutdown_owned_session` en el backend. Requiere que la GUI sea hija lanzada por ese mismo proceso MCP, compara PID, creación del proceso y ejecutable, canonicaliza `owned_root` y rechaza modal, comando activo, documento sucio o documento fuera de la raíz. Tras pedir salida espera el `Child` y guarda el resultado para la misma `request_id`. El primer L2 de este control quedó interrumpido con una pestaña sintética sucia; el cliente bloqueó al cerrar streams y ese hallazgo se corrigió con join acotado. El segundo L2 `20260923-193344-owned-8032995c` falló por comparar una ruta canonicalizada con otra sin canonicalizar; el documento sintético se guardó en `recovered-synthetic.dwg` dentro de ese run y su GUI salió. No se alteró ningún ensayo anterior.

El L2 `target/mcp-isolated/20260923-194235-owned-f6c67219/owned-report.json` pasó: rechazo `dirty_document`, rechazo `foreign_document`, cierre del PID propio, repetición del mismo ID con idéntico resultado y descubrimiento posterior `absent`. Después se duplicó el control en la cola de la GUI para cerrar la carrera entre lectura y salida. El L2 final `target/mcp-isolated/20260923-195314-owned-53014dbb/owned-report.json` repitió todos esos resultados. Ambos artefactos son locales, sintéticos y fuera de Git. `cargo test --lib mcp::tests` pasó 16/16 después de la corrección de identidad; la prueba GUI nueva también pasó. Las pruebas Python pasaron 15/15 sin ResourceWarning tras el cierre acotado. El binario Rust de ese build ejecutó la suite completa: 1669 passed, 24 ignored, cero fallos. La revisión y publicación de este segundo corte siguen pendientes al redactar.

Al segundo corte, M1.6 seguía parcial: el lote conservaba progreso solo dentro del proceso MCP. M2.2 y cierre explícito de pestañas seguían pendientes. M3–M8 no se promovieron por aquel L2.

## Tercer corte M1.6 — 2026-09-23, en progreso

Desde `41350691202f8326f8963e5333e967effdcb2217`, publicado y verificado en `origin/codex/mcp-lifecycle-and-recovery`, se abrió la rama `codex/mcp-durable-journal`. El servidor escribe un journal local por sesión y lote con archivo temporal, `sync_all` y reemplazo atómico antes de despachar un paso. La ruta se deriva de SHA-256 de IDs; el contenido conserva solicitud/progreso/estado pero ningún token. Al consultar la operación desde un nuevo proceso MCP, carga exactamente ese journal y consulta el ID de paso activo de la GUI. Precondiciones de documento y revisión se envían explícitamente en cada paso. Un journal corrupto falla cerrado. Los archivos están en el perfil local y no se publican.

Ensayos L2 aislados, todos en directorios nuevos:

- `20260923-200635-journal-5b09fc82`: **failed**, el reemplazo nativo no aceptó la ruta larga; quedó un `.tmp` sin `.json`. GUI cerrada limpiamente.
- `20260923-201129-journal-e5f259f0`: **failed de harness**, `wait_seconds:0` devolvió `running` con cero comandos completados, estado válido. La pestaña sintética se guardó en el mismo run y la GUI salió; el reporte original no se alteró.
- `20260923-201223-journal-ba19ea11`: **passed**; el primer MCP se cerró con el paso activo, el segundo recuperó por el ID original, terminó tres comandos con tres entidades, verificó el DWG sintético por hash y cerró la GUI. `journal-report.json` generado contiene identidad y hashes; no transcribirlos a mano.

La prueba Rust de journal en ruta Windows deliberadamente larga y de corrupción pasó. Pruebas focalizadas M1/MCP: 17/17 antes del ajuste de ruta larga; la prueba específica del ajuste pasó. Pruebas Python: 16/16. El binario Rust de ese corte ejecutó la suite completa: 1670 passed, 24 ignored, cero fallos. Revisión y publicación aún pendientes al redactar. M1.6 puede marcarse passed **solo para reinicio de MCP con la misma GUI**; reinicio de GUI, ACL Windows, retención de journal y conciliación externa continúan pendientes.

## Cuarto corte M2.3 — 2026-09-23, en progreso

El tercer corte se publicó en `origin/codex/mcp-durable-journal` con SHA `739f14cef397b58cd821f4873821e9cb1c0b207e`, verificado con `git ls-remote`; `origin/main` seguía en `f785e156`. La rama actual `codex/mcp-owned-document-lifecycle` deriva de ese SHA. No hubo push al repositorio del autor. Verificar remoto después de publicar este cuarto corte.

Se añadió `close_document` con política `require_saved` al servidor MCP y a la cola de la GUI. Exige que el mismo proceso MCP haya lanzado la GUI, identifica PID/inicio/binario, exige `document_id`/`revision`, rechaza pestaña sucia, modal, comando activo y ruta no guardada o fuera de `owned_root`. No habilita descarte automático. El L2 final `target/mcp-isolated/20260923-202242-owned-e9de5b27/owned-report.json` reportó rechazo de cierre sucio y externo, cierre del documento sintético ID 2, cierre del proceso propio y descubrimiento posterior `absent`. El reporte fue generado por el harness; no se añade a Git. Dos pruebas Rust focalizadas pasaron y el binario de test ejecutó la suite completa: 1672 passed, 24 ignored, cero fallos. M2.2 heartbeat/descriptor obsoleto/cuarentena y escenarios adicionales de M2.4 siguen pendientes; M3–M8 también.

## Quinto corte M2.2 — 2026-09-23, en progreso

El cuarto corte se publicó en `origin/codex/mcp-owned-document-lifecycle` con SHA `3b90ef81288deaa773df89e940e8b5f8f3d2473f`; `origin/main` permanecía en `f785e156`. La rama de este quinto corte es `codex/mcp-descriptor-liveness`. Verificar su SHA remoto después del commit y push; no enviar nada a `upstream`.

La GUI escribe un heartbeat local cada dos segundos sin token. Descubrimiento contrasta PID y creación del proceso con Win32 antes del handshake; un proceso terminado o PID reutilizado provoca cuarentena del descriptor en el mismo perfil, tras validar nombre, archivo regular y contención de rutas. Un proceso inaccesible o un timeout no autoriza cuarentena. El primer L2 `target/mcp-isolated/20260923-203703-owned-9a8cb961/owned-report.json` confirmó heartbeat e identidad, pero dejó el descriptor activo: faltaba `SYNCHRONIZE` para distinguir un proceso terminado con handle retenido. La prueba Win32 reprodujo `WAIT_FAILED` y el permiso denegado; se corrigió la máscara de `OpenProcess`. El L2 final `target/mcp-isolated/20260923-204627-owned-2626c01d/owned-report.json` pasó con heartbeat de 1345 ms, identidad `matched`, rechazo de pestañas sucias/ajenas, cierre del PID propio, descubrimiento `absent` y un descriptor en cuarentena. Ambos reportes originales se conservan. El heartbeat residual queda local en el perfil del ensayo. `cargo build --bin OpenCADStudio`, 16 pruebas Python y `cargo test --lib` (1674 passed, 24 ignored, 0 failed) pasaron. Cuatro warnings Rust preexistentes no son gates de este cambio. La protección ACL del descriptor en Windows todavía no está demostrada; M2.2 queda **partial**. M2.4 también permanece partial, al igual que M3–M8.

### Prompt de continuidad desde el quinto corte

Desde el worktree del masterplan, verifica Git, `AGENTS.md`, remotos y SHA remoto de `codex/mcp-descriptor-liveness` antes de asumir su publicación. Lee los seis documentos del masterplan y conserva todos los ensayos anteriores. Completa M2.2 verificando ACL de descriptores y cuarentena en Windows y midiendo p50/p95 tras el cambio; amplía M2.4 en modalidades/`waiting_user` con fixtures. Continúa M3–M8 por gates, con datos y planos sintéticos: telemetría y sellos, PlanSpec, semántica CAD, QA, evaluación controlada y entrega reproducible. No abras ni modifiques el DWG del usuario; no publiques archivos privados ni envíes nada a `upstream`. Si una aceptación requiere caso reservado, motor externo o revisión humana, registra el gate pendiente sin promoverlo a passed.

## Sexto corte M3 inicial — 2026-09-23, en progreso

`codex/mcp-descriptor-liveness` fue publicado en `origin` con commit `67231fc8` (verificar SHA completo remoto al retomar). Se añadió `usage_evidence.py`: recorre el rollout local sin exportar mensajes, IDs de respuesta ni rutas y deduplica por `response_id`. El ensayo histórico privado contenía 84 registros y 84 respuestas únicas; la salida sanitizada reprodujo entrada 9,727,404, entrada cacheada 9,513,472, salida 70,548 y total 9,797,952. El coste facturado queda `null`, la identidad efectiva del modelo y el uso del supervisor quedan `unknown`: el resumen numérico por sí solo no los acredita. Los cuatro tests sintéticos prueban duplicado idéntico, duplicado contradictorio, suma incorrecta e identidad ausente.

`artifact_evidence.py` introduce referencias locales PNG con hash, tamaño, dimensiones, documento y revisiones de geometría/cámara. Un hash cambiado o revisión obsoleta falla; el sello determinista excluye binario y restringe campos para evitar exportar el rollout o credenciales. Tres tests usan solo bytes sintéticos. Esto cubre el primer alcance verificable de M3.1, M3.3 y M3.5; **M3 sigue partial**: faltan instrumentación de tiempos por fase en el cliente/CAD, render-fence real, captura negociada, bitácora append-only, AUDIT/SAVE/VERDICT desde ejecución y presupuestos con reanudación. El PNG de fixture solo comprueba encabezado y hash, no decodificación completa. El caso histórico no se reescribe ni se promueve.

### Prompt de continuidad desde el sexto corte

Verifica Git y remoto del fork, ejecuta las pruebas M3 con `python -m unittest discover -s docs/automation/masterplan -p 'test_*.py'` y reproduce el agregado privado local mediante `python docs/automation/masterplan/usage_evidence.py <rollout-local> --expected-total 9797952` sin publicar la ruta ni contenido del rollout. Completa M2.2 ACL/latencia y M2.4; luego instrumenta M3 en el flujo real con timestamps, artefactos, sellos y presupuesto. Prosigue M4–M8 en fixtures sintéticos. Mantén intactos el DWG y el caso histórico; nada a `upstream`.

## Séptimo corte M4 inicial — 2026-09-23, en progreso

`codex/mcp-evidence-contract` publicó el sexto corte con commit `66a895f0` en el fork; obtener SHA completo remoto al retomar. En este corte se añadió `planspec.schema.json` y validador/compilador puro `planspec.py`. El contrato exige unidad `m`, origen, nodos con IDs únicos y procedencia, referencias existentes, cifras finitas y región/confianza. Comprueba texto y valor de cota contra la geometría referenciada con tolerancia de 0.001 m. Dos cotas de referencias distintas no producen falso conflicto; el fixture 2.50 sobre distancia 2.54 falla antes de emitir comandos. El dry-run ordena líneas/círculos por ID, da SHA-256 estable y mapa ID→comando. Cotas nativas y capas distintas de 0 se declaran `unsupported` y `executable=false`; no se ha conectado a GUI ni abierto un DWG. Cinco pruebas sintéticas de PlanSpec y siete de evidencia pasaron. M4 permanece **partial**: faltan grafo general de cotas, compilación de muros/aperturas/símbolos, manifest de capacidades por build, ejecución con trazabilidad de handles y L2 sintético de esa ejecución. El JSON Schema describe el subconjunto actual, no el contrato arquitectónico completo de `02-ARQUITECTURA-Y-CONTRATOS.md`.

### Prompt de continuidad desde el séptimo corte

Reverifica `git status`, `git remote -v`, SHA local/remoto y AGENTS. Mantén los cortes anteriores intactos. Mide M2 discovery con 100 entradas tras el heartbeat y resuelve ACL; completa trazas M3 y evidencia real. Extiende M4 por manifiesto/compilador/handles y prueba L2 usando únicamente un plano sintético. Después censa M5, valida M6 y prepara M7/M8 según sus gates. El DWG y evidencias privadas históricos no se abren ni se reescriben; no publiques en `upstream`.

## Octavo corte ACL Windows M2 — 2026-09-23, en progreso

El séptimo corte se publicó en `origin/codex/mcp-planspec-contract` con commit `5ff1af94` (verificar SHA completo remoto). La rama actual `codex/mcp-windows-descriptor-acl` añade `automation_security.rs`. En Windows el descriptor con token se crea directamente con `CreateFileW` y DACL protegido `owner rights + SYSTEM`, sin ventana de ACL heredado entre creación y escritura. El lector consulta el DACL y rechaza uno ampliado. Los journals nuevos también se escriben primero a un archivo privado y luego se reemplazan atómicamente. Esto mantiene la recuperación de lotes bajo el perfil sintético. Un journal antiguo con ACL heredado amplio, como el ensayo anterior que incluía otro SID con lectura, falla cerrado; no se migra automáticamente ni se reenvía el comando. Ese cambio de compatibilidad está identificado.

El L2 `target/mcp-isolated/20260923-210821-owned-f10b9292/owned-report.json` pasó: identidad/heartbeat, rechazo dirty/foreign, cierre propio, un descriptor en cuarentena. `Get-Acl` sobre ese descriptor mostró DACL protegido de propietario y SYSTEM sin ACE heredada. Una prueba Rust cambia deliberadamente el DACL de un archivo de fixture a Everyone y confirma rechazo. El L2 `target/mcp-isolated/20260923-211201-journal-d93ec728/journal-report.json` recuperó el lote tras reinicio de MCP, verificó tres entidades y cerró GUI. Diez ejecuciones de descubrimiento con 100 descriptores privados dieron 1874.5–1904.3 ms, p50 1890.85 ms y p95 conservador 1904.3 ms. `cargo build --bin OpenCADStudio`, 16 pruebas Python de cliente, 12 pruebas Python de masterplan y `cargo test --lib` (1675 passed, 24 ignored, 0 failed) pasaron. Los artefactos permanecen en `target` sin añadir a Git. M2.1 y M2.2 pasan **solo para este alcance Windows/sintético**; M2.4 y M3–M8 aún no están aceptados globalmente.

Una revisión final corrigió el caso de un descriptor legado con nombre de sesión válido y ACL amplio: ahora `descriptors_in` devuelve error en vez de ignorarlo y presentar `absent`, lo que podría haber lanzado una segunda GUI. El test focalizado de 100 descriptores privados pasó tras ese cambio. Se remidió el binario final en 10 ejecuciones: 1890.6–1907.2 ms, p50 1900.45 ms y p95 conservador 1907.2 ms. La medición anterior se conserva como corte previo.

### Prompt de continuidad desde el octavo corte

Verifica commit y SHA remoto de `codex/mcp-windows-descriptor-acl` antes de afirmar publicación. Preserva todos los runs previos, incluidos los fallos. Completa M2.4 y M3 con trazas reales por fase, artefactos y sellos; integra PlanSpec en L2 sintético y después aborda M5–M8 según los gates. No reutilices automáticamente journals viejos de ACL heredado: concilia su estado antes de cualquier edición. Mantén el DWG y la evidencia histórica intactos, y publica exclusivamente en el fork.

## Noveno corte M3 transporte — 2026-09-23, en progreso

El octavo corte se publicó en `origin/codex/mcp-windows-descriptor-acl` con commit `2b8ff754` (verificar SHA completo remoto). La rama actual `codex/mcp-transport-trace` añade un `TraceSink` opcional al cliente persistente: un JSONL nuevo por run, append-only, con ID de run, secuencia, método MCP de lista blanca, estado, timestamps UTC y duración monotónica por RPC. Nunca serializa argumentos, resultados, tokens ni texto de error. Un fallo de escritura queda indicado por `trace.failed`, sin reinterpretar ni repetir una mutación. El test L1 envió valores privados de fixture en dos RPC y confirmó que no aparecen en el archivo. La suite Python de cliente pasó 17/17 tras la instrumentación.

El L2 `target/mcp-isolated/20260923-212002-owned-185c1b47/owned-report.json` pasó cierre/propiedad y registró 27 eventos RPC; `write_failed=false` y `contains_token_field=false`. El JSONL permanece en `target`, fuera de Git. Esto acredita tiempos de transporte del cliente, **no** separación de tiempo de modelo, cola GUI, ejecución CAD o render, ni cobertura de toda la ejecución del benchmark. M3.2 sigue partial. M3 requiere todavía bitácora integral, ArtifactRef conectado a captura real, render-fence, AUDIT/SAVE/VERDICT automáticos y presupuestos/reanudación. El DWG del usuario y el ensayo histórico siguen sin abrirse ni alterarse.

### Prompt de continuidad desde el noveno corte

Reverifica remotos/SHAs y pruebas. Completa trazas M3 desde GUI/CAD hasta evidencia final con cobertura; conecta capturas reales mediante referencias y revisiones sin Base64 en JSONL. Ejecuta PlanSpec sintético por el cliente persistente, manteniendo `unsupported` como fallo de gate. Después censa e implementa M5/M6, y evalúa M7/M8 solo con cohorte y revisiones autorizadas. No abra el DWG del usuario; preserve evidencia previa y no publique en upstream.

## Décimo corte PlanSpec L2 — 2026-09-23, en progreso

El noveno corte se publicó en `origin/codex/mcp-transport-trace` con commit `3ca13bd1` (verificar SHA completo remoto). En `codex/mcp-planspec-l2`, el fixture versionado `fixtures/synthetic-room.planspec.json` se valida y compila antes de lanzar GUI; si el dry-run declara `unsupported`, no hay ejecución CAD. `mcp_isolated_smoke.py` envía los tres comandos del compilador al cliente persistente, comprueba tres entidades y mapea cada ID PlanSpec al handle `Added` del paso correspondiente. El primer L2 `target/mcp-isolated/20260923-212219-f47e037a/report.json` pasó ejecución, auditoría, guardado verificado y salida; el segundo `target/mcp-isolated/20260923-212302-cda4b60e/report.json` repitió y añadió trazabilidad ID→handle (`line-1`→`64`, `line-2`→`65`, `circle-1`→`66`). Ambos DWG son sintéticos, en `target`, fuera de Git. El SHA del fixture y de los comandos se generó por código en los reportes.

El L2 confirma ese subconjunto geométrico en el mismo motor y formato DWG; no demuestra interpretación de imagen, arcos/cotas/bloques/HATCH, dimensiones asociativas, interoperabilidad externa ni QA visual. M4 permanece partial. El DWG del usuario y el ensayo histórico continúan intactos.

### Prompt de continuidad desde el décimo corte

Verifica SHA publicado del corte PlanSpec y árbol limpio. Continúa M3 con telemetría por fase y evidencia automática real, M4 con grafo de cotas y capacidades por build; censa M5 antes de implementar semántica. Luego M6 QA geométrica/persistencia y M7/M8 con gates de motor externo/casos reservados/revisión humana. Usa solo fixtures sintéticos hasta nueva autorización; no publiques datos privados ni envíes nada a `upstream`.
