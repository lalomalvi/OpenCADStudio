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
