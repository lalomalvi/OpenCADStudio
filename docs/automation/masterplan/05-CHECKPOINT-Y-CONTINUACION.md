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

La publicación, SHAs definitivos y verificación remota se añadirán al terminar los gates; no interpretar este párrafo como evidencia de push.

### Prompt de continuación tras este corte

Lee `docs/automation/masterplan/00-INDICE.md`, los cinco documentos vinculados y este corte vigente. Empieza con `git status --short --branch`, `git remote -v`, `git log -3 --oneline` y `git ls-remote origin refs/heads/main refs/heads/codex/mcp-persistent-client`; contrasta los SHAs publicados con el checkpoint. Reproduce `python -m unittest discover -s docs/automation -p test_mcp_client.py -v` y los tests Rust focalizados. Continúa M1: añade el contrato formal `starting/ready`, selecciona sesión por identidad y documento, exige revisión antes de mutaciones, y resuelve recuperación de `run_script` por request_id sin repetir efectos. Implementa pruebas de fallos y un L2 sintético aislado antes de afirmar aceptación CAD. Preserva el DWG y el ensayo privado; no publiques secretos ni envíes nada a `upstream`.
