# Plan de estabilización: modelo, MCP + harness y programa

**Fecha:** 2026-09-30 · **Autor:** Claude (Opus 5.5) con Luis
**Base:** auditoría independiente [07-AUDITORIA-INDEPENDIENTE-MCP-20260930.md](07-AUDITORIA-INDEPENDIENTE-MCP-20260930.md) sobre `d0d88409`, cuyo código es el de `26bce00a`

**Estado (2026-10-01): en ejecución.** Fase 4a cumplida en su alcance; fase 0 a medias; el resto pendiente.

- **Estado vigente:** en la [§11](#11-estado-vigente-2026-10-01). Esa sección, este encabezado y la columna «Estado» de la §7 **se reescriben**, no se apilan.
- Los hechos que sustentan el plan están en la auditoría 07; los identificadores B01–B22 y A01–A30 remiten a ella.
- R01–R19 remiten al [informe maestro 06](06-INFORME-MAESTRO-Y-MEJORAS-20260929.md).
- Las sesiones son estimados, no compromisos.
- **Publicación:** historial redactado en una rama candidata; el push espera la reauditoría de Codex y el visto bueno de Luis (§11).

---

## 1. Qué significa «estable» aquí

«Estable» en el sentido de **dúctil**:

- si algo falla, el sistema avisa y se detiene sin dañar el dibujo;
- nunca duplica ni esconde nada;
- el modelo se puede cambiar sin rehacer lo demás.

No significa que el modelo acierte siempre, porque eso no está en nuestras manos. Significa que su error no se propague.

«Arquitectura formal» se lee en dos sentidos, y el plan cubre ambos:

- **La del software:** capas con contrato, en las que el MCP es una pieza formal y no un añadido.
- **La del edificio:** muros, vanos y recintos con identidad propia, no líneas sueltas.

**Idea rectora: la trayectoria de cargas.** Una intención recorre modelo → harness → MCP → programa → DWG. Ese camino tiene que ser continuo, con cada conexión diseñada para lo que transmite.

- Las conexiones débiles están hoy en el MCP (recuperación) y en el programa (consultas de bloques, verificación del guardado).
- El modelo es la carga variable.

## 2. Arquitectura objetivo

```
Modelo (reemplazable)   → entrega PlanSpec / patch semántico en JSON estricto, o se abstiene
Harness (código propio) → valida, compila determinista, traza por fase, recibo de identidad
MCP (adaptador delgado) → sin semántica propia; contrato estricto; errores honestos
Despachador de control  → revisión obligatoria, idempotencia persistente, lotes y journal
Dominio CAD             → bounds correctos, capas por contrato, identidad ARQ en XDATA, verificación por propiedades
DWG                     → única fuente de verdad: geometría + identidad semántica
```

**Hoy el estado está repartido en tres sitios:**

- el journal de lotes, en el proceso MCP;
- la caché de idempotencia, en la memoria de la GUI (128 operaciones);
- el contexto semántico, en un archivo aparte que envejece.

**Meta:** todo lo que importa vive en el despachador o dentro del propio DWG.

## 3. Principio rector: contrato antes de trazar

**Sin contrato:** el agente recibe un objetivo y dispara los comandos que cree entender. Es una cuadrilla sin planos.

**Con contrato:** el agente primero entrega su intención como PlanSpec —estructurado, verificable y legible—. Se acuerda antes de trazar una sola línea, y después la obra se ejecuta y se supervisa contra ese proyecto. Los fallos dejan de ser sorpresas y pasan a ser **desviaciones respecto del contrato**, medibles una por una.

### Lo que ya existe (verificado en `d0d88409`)

- **PlanSpec v1–v11** con esquemas versionados (`planspec.py`, `planspec-*.schema.json`).
- **`dry_run`** (`planspec.py:1564`): devuelve `execution_steps`, `commands_sha256`, `unsupported`, `quality_blockers` y `executable` sin tocar el CAD (`:1938-1959`).
- **Contrato determinista en `m8_case_cli.py`** (`:52-81`): hashes del plan, el binario, los comandos y el código del compilador, el ejecutor y el CLI. Según el 03, rechaza contratos alterados y reejecuciones antes de abrir la GUI.

### Lo que falta

1. **Vista legible del contrato.** Una página en términos de despacho, no JSON:
   - encargo, versión y hash del plan, unidades, escala y origen;
   - elementos por tipo: muros y espesores; vanos; puertas con ancho y sentido de giro; ventanas; recintos con área; bloques;
   - medidas clave que vienen del encargo;
   - **supuestos**: lo que el agente decidió sin dato (p. ej. «muro interior 0.15 m, no indicado»);
   - **dudas y abstenciones**: lo que no pudo decidir. Si son críticas, bloquean la aprobación;
   - controles automáticos que se van a correr y, de forma explícita, lo que **no** se verifica;
   - en ediciones, el diff contra la versión anterior: qué cambia y qué queda intacto.
2. **Registro de aprobación.** JSONL de solo-anexar con `plan_sha256`, quién aprobó, cuándo y el alcance.
3. **Ejecutor que exige un hash aprobado.** Amplía el contrato de `m8_case_cli.py`: sin aprobación, no hay GUI.
4. **Verificación contra el plan.** Cada elemento del plan se liga a sus comandos, a sus handles y a su XDATA con `plan_sha256` (Pilar 3). El resultado se compara contra el plan, no contra lo que el agente dice haber hecho.
5. **Cambios como versiones.** Toda modificación es un patch sobre el plan, que produce una versión nueva con su diff y su nueva aprobación.

### Criterios de diseño del contrato

- **Legible:** revisarlo toma 1–2 minutos, no 20.
- **Completo o explícitamente incompleto:** los supuestos y las dudas son parte del contrato.
- **Verificable:** cada cláusula relevante tiene un control automático, por ejemplo: la cota coincide con la distancia medida; la puerta no invade el barrido.
- **Inmutable una vez aprobado:** el hash lo garantiza.
- **Trazable** hasta el DWG.

### Límite honesto

El contrato adelanta los errores; no los elimina. Un PlanSpec equivocado que se aprueba produce un dibujo equivocado bien construido. Por eso la vista debe resaltar supuestos y dudas por encima de todo, y los niveles de aprobación son una decisión de Luis (§9).

## 4. Pilar 1 — Modelo: hacerlo reemplazable, no confiable

**Lo que no se controla:** actualizaciones silenciosas del proveedor, variación entre corridas, latencia y precio.

**Lo que sí se controla:**

1. **Estrechar su trabajo.**
   - El modelo entrega un PlanSpec o un patch validado por esquema estricto (§3); nunca comandos CAD crudos para trabajo que importe.
   - La geometría y las medidas las calcula siempre el motor.
   - Es lo que más estabiliza y lo que abarata cambiar de modelo.
2. **Abstención válida.** El esquema y el prompt admiten «ambiguo / no soportado», y el harness pregunta en vez de inventar.
3. **Fijar y registrar.**
   - Snapshot con fecha cuando el proveedor lo ofrezca.
   - Recibo con modelo solicitado y efectivo, esfuerzo y uso (B05).
   - Prompts e instrucciones con hash.
4. **Suite canaria.**
   - Entre 10 y 15 tareas sintéticas pequeñas —creación, edición localizada, consulta y recuperación— con oráculo congelado.
   - Se corre cada vez que cambia el modelo, el CLI o el harness, y decide si el cambio se acepta.
   - Minutos de ejecución y tokens acotados.
5. **Presupuestos.** Tope de tokens, tiempo y llamadas por tarea; al excederlo, se detiene e informa.

## 5. Pilar 2 — MCP + harness: que ningún fallo duplique ni esconda

1. **Contrato P0** (B01–B04 y B14):
   - revisión obligatoria, sin relleno implícito del servidor;
   - errores posteriores al envío como `outcome_unknown`, con la instrucción de recuperación;
   - plazos coherentes: el del MCP mayor que el de la GUI;
   - `operation` de solo lectura, y `batch_abort`;
   - ventana de idempotencia persistente;
   - el descubrimiento no lanza una segunda GUI.

   **Sin retrocompatibilidad:** el único cliente es Luis, a través de sus harnesses.
2. **Suite de fallos inyectados (T4) como prueba de regresión:**
   - respuesta perdida;
   - reinicio del MCP a mitad de lote;
   - un modal abierto;
   - edición humana entre lectura y escritura.

   Se aprueba con 0 duplicados y 0 pérdidas.
3. **Harness como paquete único.** `mcp_client.py`, más:
   - selectores tipados (R03);
   - un compilador PlanSpec único (R08) que sustituya los 30 scripts `apartment_*.py` atados a coordenadas de un caso observado (p. ej. `apartment_northeast_door_compiler.py:54-58`);
   - trazas por defecto;
   - recibos.

   Se cumple cuando otro agente retoma una tarea con el índice y el contrato, sin conversación previa (R16).
4. **Medir antes de optimizar:** instrumentación por fase (B12, B05) y binario release con su perfil registrado (B19).

## 6. Pilar 3 — Programa: recibir la arquitectura como objetos, no como líneas

1. **Corrección de lo que usan los agentes:**
   - bounds de INSERT y alcance de `query` (B06);
   - contrato de capa (B07, decisión de Luis);
   - `save_verified` por propiedades (B08);
   - `changes` fiable (B09);
   - validación en el servidor, unidades incluidas (B10);
   - prueba de que los handles se conservan al reabrir.
2. **Identidad semántica persistente en el DWG.**
   - Cada muro, vano, puerta, ventana, recinto y mueble lleva XDATA registrada: id del elemento, tipo, versión de esquema y `plan_sha256`. Es el mismo mecanismo que ya usa `file_identity`.
   - El contexto (R04) deja de ser un archivo que envejece: se reconstruye leyendo el dibujo.
   - Las ediciones se piden por id y se resuelven a handles en el momento.
   - Cambio pequeño en el producto: que `entities_create` acepte `xdata` por entidad, para que geometría e identidad nazcan en el mismo paso de deshacer.
   - Hay que verificar en L4 que AutoCAD conserva esa XDATA.
3. **Patch semántico v1 con tres operaciones reales de despacho:**
   - mover una puerta a lo largo de su muro;
   - cambiar el espesor de un muro;
   - mover o rotar un mueble.

   Cada una se compila de forma determinista y se verifica que el resto quede intacto por handle a 1e-6.
4. **Un anfitrión que no se congela:** trabajo pesado fuera del hilo de la GUI (guardado verificado, codificación de captura) y arranque medido.

## 7. Secuencia

| Fase | Qué | Sesiones | Modelo | Sale cuando | Estado (2026-10-01) |
|---|---|---|---|---|---|
| 0 | Higiene: commit local de 07 y 08 (si se aprueba), `AGENTS.md` sin contradicción, release por defecto y perfil en recibos, spec = código, revisión de publicabilidad antes de cualquier push | 1 | Sonnet (Haiku para el barrido de docs) | Una prueba confirma que spec y listas de operaciones coinciden; las series rechazan binarios de depuración; el historial a publicar no contiene rutas locales ni datos de proyectos privados | **A medias.** Hecho: 07 y 08 commiteados; `AGENTS.md` aclarado; historial redactado en la rama candidata. Falta: reauditoría de publicabilidad, release por defecto y spec = código |
| 1 | Contrato MCP P0 + suite T4 mínima | 2–3 | Sonnet; Opus revisa la taxonomía | T4 con 0 duplicados en 50 corridas sintéticas | Pendiente |
| 2 | Corrección del dominio (B06–B10) | 2–3 | Sonnet | Fixtures en verde: bounds, capas, guardado por propiedades y handles | Pendiente |
| 3 | Instrumentación y recibos | 1–2 | Sonnet | ≥ 95 % del tiempo de pared atribuido o marcado; lo ausente queda `null` | Pendiente |
| 4a | Contrato humano–agente (§3): vista legible, registro de aprobación, ejecutor que exige hash aprobado | 1–2 | Sonnet con esta receta | Un plan no aprobado no abre la GUI; uno aprobado se ejecuta y se verifica contra su contrato | **Cumplida en su alcance:** L2 acotado con binario de depuración |
| 4b | Identidad ARQ en el DWG + patch v1 + compilador único | 1 de diseño + 2–4 | Opus diseña, Sonnet ejecuta | Una sesión nueva reconstruye el contexto desde el DWG y aplica los 3 patches sin tocar nada más | Pendiente |
| 5 | Suite canaria + línea base del modelo actual | 1–2 | Sonnet; requiere cuota | Línea base con intervalos y regla escrita para aceptar un cambio de modelo | Pendiente |
| 6 | Rendimiento medido, orquestación en el despachador (decisión), comparación de modelos (§6 de la auditoría 07), L5, imagen→CAD | abierto | según tarea | Cada mejora con su antes y después en release | Abierto |

**Adelantar la 4a.** No depende de las fases 1–3: usa `dry_run`, el contrato SHA y el cliente del proyecto, que ya compensa los defectos del contrato MCP.

## 8. Definición de «estable» medible

| Pilar | Criterio |
|---|---|
| MCP + harness | Suite T4 con 0 duplicados y 0 pérdidas en ≥ 50 corridas. Cada rama de error con su prueba. Ningún truncado silencioso |
| Programa | Fixtures de dominio en verde en CI. Guardar y reabrir sin diferencias de propiedades a 1e-6. Handles conservados |
| Modelo | Suite canaria con línea base. Un cambio de modelo se acepta solo si no empeora más allá del umbral fijado tras el piloto |
| Contrato | Toda ejecución referida a un plan aprobado por hash. Toda desviación reportada contra el contrato |
| Trazabilidad | Toda corrida con recibo: modelo efectivo, build, perfil y hashes. Tiempos por fase ≥ 95 % atribuidos |

## 9. Decisiones de Luis

1. **Capa de las referencias de bloque:** la capa actual, la de los objetos de origen o «0».
2. **Batería de encargos típicos:** qué encargos la forman. Define qué significa «sale solo».
3. **Umbral de aceptación** de un cambio de modelo, fijado tras el piloto de la fase 5.
4. **Cuota** para la línea base y los canarios.
5. **Mover lotes y journal al despachador.**
   - A favor: una sola semántica para todo transporte y todo reinicio.
   - En contra: toca código compartido con el upstream y encarece cada sincronización. Proponer al upstream las correcciones compartidas (M1, M2, M5) lo aliviaría.
   - Recomendación: decidirlo con los datos de la fase 3.
6. **Tolerancias:** 1e-6 para identidad geométrica y 0.001 m para medidas vinculadas.
7. **Niveles de aprobación del contrato:** qué cambios se aprueban solos —menores y dentro de umbral— y cuáles exigen la firma de Luis.

## 10. Qué no hacer todavía

- **Comparar modelos antes de la fase 3:** sin identidad ni tiempos por fase, cualquier resultado es anécdota.
- **Optimizar latencia antes de medir en release.**
- **Usar imagen→CAD como vara de estabilidad:** es la pista más difícil y va aparte.
- **Añadir capacidades al MCP mientras la fase 1 siga abierta.**

## 11. Estado vigente (2026-10-01)

**Se reescribe, no se apila.** Lo histórico vive en Git y en las notas M*.

### Dónde está el trabajo

- **Ubicación:** worktree `desktop-distribution`, rama `claude/mcp-stabilization-candidate`, candidata a publicar. El checkout del escritorio no sirve de base.
- **Commits sobre `26bce00a`, en orden:**
  1. documental de Codex del 29-sep, redactado para publicación (`d0d88409`);
  2. auditoría 07 y plan 08 (`186772d0`);
  3. fase 4a (`fb0bdd25`);
  4. registro del L2 (`6f488405`);
  5. correcciones de la primera doble auditoría (`9db0ce37`);
  6. hoja de revisión con referencias de cotas y líneas de ventanas (`faff5d88`);
  7. este estado.
- **Ramas locales que no se publican:**
  - `codex/windows-web-dxf`, con la versión sin redactar;
  - `claude/mcp-stabilization-candidate-r1`, la primera candidata, que bloqueó la segunda auditoría. Se conserva para comparar.
- **Remoto:** `origin/main` sigue en `26bce00a`; la candidata no está publicada.

### Hecho y verificado (2026-10-01, Windows, Python 3.13.7)

- **Documentos.** Auditoría independiente [07](07-AUDITORIA-INDEPENDIENTE-MCP-20260930.md), con adenda A02 y tres erratas tras Codex. Este plan.
- **Fase 4a**, en `plan_contract.py` y la puerta de `m8_case_cli.py`:
  - hoja de revisión con una tabla por grupo del PlanSpec, que incluye extremos, vínculos y `offset_m` de las cotas y las líneas de los símbolos; hasta 60 filas por grupo, y la cabecera dice «PARCIALES» si alguno no cabe; no lista `topology` ni `dimension_style`;
  - aprobación solo en terminal interactiva, con registro encadenado;
  - `status` con `usable_by_run`.
  - Detalle y límites: [M4-CONTRATO-HUMANO-AGENTE-V1](M4-CONTRATO-HUMANO-AGENTE-V1.md).
- **Pruebas** con Python 3.13.7 y Pillow en un entorno aislado, sobre el código del commit 6: masterplan **230/230**, automatización **59/59**. Las de la candidata congelada van en la solicitud de reauditoría.
- **Historial redactado:** el documental del 29-sep se rehízo sin rutas personales, PID, programa ni dimensiones de los casos privados, ni nombres, rutas o hashes de sus entregables; las métricas agregadas se conservan. Los demás commits se reaplicaron con sus referencias de SHA resueltas y sin afirmar una publicación que no ha ocurrido. Hasta el commit 5, frente a la rama anterior cambian ocho documentos y ningún `.py`.
- **Segunda auditoría de Codex:** bloqueó la primera candidata por la hoja incompleta, afirmaciones prematuras de «publicado» y un PID histórico. Los tres motivos están corregidos (commits 1, 2, 5 y 6); detalle en M4.
- **L2 acotado con la firma de Luis** (registro `9B8AADB7…`, único del registro, utilizable por `run`):
  - sin aprobación, `run` no abrió la GUI;
  - con aprobación, `passed_scoped_l2` y `verify` con `human_approval: rechecked`.

### Roto o a medias

- **Publicación pendiente.** La candidata tiene el SHA congelado mientras Codex la reaudita. Faltan, en orden:
  1. veredicto favorable de Codex sobre el rango completo, de `26bce00a` a la punta de la candidata;
  2. visto bueno explícito de Luis;
  3. push sin forzar, solo de esta rama, a `lalomalvi/OpenCADStudio`;
  4. CI mediante PR o despacho manual: el nombre de la rama no activa el workflow por push.

  Merge y publicación de release son decisiones aparte.
- **Una hoja parcial no bloquea.** Con más de 60 elementos en un grupo, aprobar exige leer el PlanSpec íntegro, y la puerta no lo comprueba.
- **El L2 no se reverifica con el HEAD actual:** responde «Frozen contract differs». Es por diseño: el contrato ata el hash de `plan_contract.py`, que cambió después del L2. Hay dos caminos:
  - reverificar con el árbol del commit «record L2» (`6f488405`);
  - repetir el L2: la firma sigue siendo utilizable.
- **El L2 usó un binario de depuración** (`09794ab6`, artefacto de CI), que no es el código vigente.
  - No hay localmente un binario release del código vigente.
  - La v2026.40.1 que el 06 da por instalada no está: lo instalado es v2026.38.
- **Entorno de Codex:** en su primera auditoría no tuvo Pillow (24 errores de importación) y su sandbox le bloqueó `target/ci-flow-tests` y `target/fork-sync-tests`. Para correr las suites hace falta Pillow o permiso para esos temporales.

### Qué sigue (más caro primero)

1. **Fase 1, contrato MCP P0** (B01–B04, B14). Es lo que más riesgo de duplicar geometría quita.
2. **Publicación:** reauditoría de Codex, visto bueno de Luis, push de la candidata y CI. Bloquea el respaldo remoto y la CI.
3. **B19:** build release del código vigente y repetir el L2. Ocupa la máquina; decide Luis.
4. **Fases 2 y 3**, después **4b** y **5**.

### Decisiones pendientes de Luis

- Visto bueno de publicación del rango congelado, después del veredicto de Codex.
- Qué hacer con datos de la máquina que ya están en el historial publicado; el detalle queda fuera de Git.
- Si una hoja con tablas parciales debe bloquear la aprobación.
- Hacer o no la build release.
- Capa de las referencias de bloque (§9.1).
- Aprobación de un solo uso o reutilizable.
- Niveles de aprobación (§9.7).
- El resto de la §9.

### Qué está corriendo

Nada:

- sin agentes ni tareas en segundo plano;
- sin GUI propia viva.

Una GUI abierta en la máquina es de Luis, salvo prueba de propiedad; esta sesión no la toca.

### Cómo se comprueba (no se cita de memoria)

Desde el worktree:

- `git log --oneline 26bce00a..HEAD` → 7 commits
- `git ls-remote origin refs/heads/claude/mcp-stabilization-candidate` → vacío mientras no se publique
- `git diff --stat codex/windows-web-dxf~1 9db0ce37` → ocho documentos, ningún `.py` (solo en esta máquina: la rama anterior es local)
- `git diff --stat claude/mcp-stabilization-candidate-r1 HEAD` → lo que cambió desde la primera candidata (solo en esta máquina)
- Con Python 3.13 y Pillow: `python -m unittest discover -s docs/automation/masterplan -p "test_*.py"` → 230
- Con Python 3.13 y Pillow: `python -m unittest discover -s docs/automation -p "test_*.py"` → 59
- `python docs/automation/masterplan/plan_contract.py verify-registry --registry target/mcp-release/plan-approvals.jsonl` → 1 registro
- `python docs/automation/masterplan/plan_contract.py status --plan docs/automation/masterplan/fixtures/synthetic-wall.planspec.json --registry target/mcp-release/plan-approvals.jsonl` → `usable_by_run: true`

### Dónde vive el detalle

- **Auditoría 07:** hallazgos, protocolo de comparación (§6), instrumentación (§7) y lo no verificado (§8).
- **M4:** contrato, L2, las dos auditorías de Codex y límites.
- **`AGENTS.md`:** reglas para agentes, incluidas la de no aprobar y el protocolo de push.
- **Evidencia local, fuera de Git:**
  - `target/mcp-release/plan-approvals.jsonl`;
  - `target/mcp-release/l2-contrato-aprobado-20260930/`;
  - `target/mcp-release/contrato-demo-20260930/`;
  - `target/mcp-release/candidata-20261001/` (primera candidata) y `target/mcp-release/candidata-20261001-r2/` (esta): pruebas y barrido de privacidad.
- **Canal con Codex:** no hay CLI en el PATH. Luis pasa un prompt autocontenido y trae el veredicto.
