# Auditoría independiente: OpenCADStudio, su MCP y la evaluación con agentes

**Fecha:** 2026-09-30 · **Auditor:** Claude (Opus 5.5) en Claude Code · **Modo:** solo lectura
**Código auditado:** `origin/main` (`26bce00a`) + 1 commit documental, entonces local y sin publicar; su versión redactada para publicación es `d0d88409`, sin cambios de código

> El informe maestro 06 se usó como índice, no como verdad. Cada veredicto enlaza código o documento versionado; lo no verificado se declara como tal. Todas las rutas `archivo:línea` refieren a ese árbol; el código es el de `26bce00a`.
>
> **Nota de redacción (2026-10-01):** las menciones del commit documental apuntan a su versión redactada para publicación. Esa versión del 06 omite rutas personales, datos de los casos privados y el índice de entregables; este informe no los cita.

---

## 0. Alcance, método y estado del checkout

### 0.1 Estado verificado

| Elemento | Verificado | Consecuencia |
|---|---|---|
| Checkout de la sesión | `feat/audited-mcp-save` @ `0fa6f008` (igual a su remoto). 33 archivos rastreados modificados. Sin rastrear: `AGENTS.md`, un `.dwg` privado en la raíz, documentos y scripts de distribución. | **No** es el código que describen los informes: le faltan 535 commits del código auditado y no contiene `docs/automation/masterplan/`. No se usó para conclusiones de código. |
| Código auditado | Rama local `codex/windows-web-dxf`, en el worktree `desktop-distribution`, limpia: `26bce00a` + el commit «consolidate MCP evidence metrics…». | Ese commit **no estaba publicado**: `git ls-remote` mostraba la rama remota en `26bce00a`. Su versión redactada para publicación es `d0d88409`, sin cambios de código. |
| Binario instalado (según 06) | El productor `196b1b7c` es padre directo de `26bce00a`. No hay diferencias en `src/`, `Cargo.*` ni `crates/`. | A nivel de fuente, el binario declarado corresponde al código auditado. El EXE (hash y perfil) **no** se verificó. |
| Upstream | Remoto `HakanSeven12/main` = `ab068215`, no descargado. Ref local `upstream/main` = `60f35e2b` (2026-09-29). | La atribución fork/upstream se hizo contra `60f35e2b`. El upstream actual no se comparó. |
| Dependencias CAD | `Cargo.lock` fija `opencadcodec cdf2277`, `opencadkernel 8fe5928` y `opencadgraph fc936b6`. | Esas revisiones no están en la caché local de Cargo (†). La cita del codec se leyó en la revisión cercana `42b44d2`. |
| `AGENTS.md` auditado | Afirma «Existing user authorization for merging/pushing the fork remains valid» y también «The report's current cycle is local-only: do not push». | Instrucción contradictoria para agentes (H5). El `AGENTS.md` sin rastrear del checkout de la sesión es otro, más corto. |
| Evidencia local | 22/22 recibos no-dibujo del índice 06 existen en el worktree con **tamaño** coincidente; 0/22 en el checkout de la sesión. Las 7 entradas DWG/PNG no se tocaron. | Que la evidencia exista no significa que la prueba esté aprobada. No se leyó su contenido ni se verificaron hashes: son evidencia no versionada. |

### 0.2 Mapa de capas

| Capa | Dónde | Tamaño | Origen |
|---|---|---|---|
| Kernel/codec CAD | crates externos `opencadkernel`, `opencadcodec`, `opencadgraph` | — | upstream |
| Programa (GUI iced/wgpu, escena, E/S) | `src/`, salvo lo que sigue | ~478 k líneas de Rust en `src/` | compartido |
| Puente de control GUI | `src/app/control/*.rs` (transporte TCP, cola, caché de idempotencia), `src/app/automation.rs` (query, audit, save_verified), `src/automation_security.rs` | ~7.5 k + 3.4 k líneas | compartido + fork |
| Servidor MCP | `src/mcp.rs`: stdio JSON-RPC, 4 herramientas, lotes con journal, cierre con propiedad, cerco de captura | 2 883 líneas (upstream: 1 796) | compartido + fork |
| Otros transportes | `src/rest.rs`, `src/app/control/http_bridge.rs`, `--serve` | — | compartido |
| Cliente/harness | `docs/automation/mcp_client.py` y sus pruebas con par falso (`tests/fixtures/mcp_stdio_fake.py`); humos `docs/automation/mcp_*_smoke.py`, `mcp_eval.py`, `mcp_latency_series.py`, `mcp_budgeted_run.py` | — | fork |
| Evaluación | `docs/automation/masterplan/*.py`: PlanSpec, carril reservado, adaptadores de modelo, sellos, veredictos L4, M7/M8 | 261 pruebas unitarias en 50 archivos (†) | fork |
| Publicación | `.github/workflows/`, `packaging/`, `scripts/release.py`, `scripts/desktop*`, `docs/install/`, `fork_sync*.py` | — | fork |

### 0.3 Método

- **Lectura directa:**
  - `src/mcp.rs` completo;
  - el ciclo de solicitud en `src/app/control/mod.rs` y `transport.rs`;
  - `save_verified`, `document_manifest` y `query` en `src/app/automation.rs`;
  - `wall_edit.rs`;
  - los documentos 06, API-SPEC, el README de automatización, `mcp_client.md`, 03 y 04.
- **Barridos delegados:** tres, de solo lectura, con modelo Sonnet: bounds y capas, rendimiento, harness. Toda afirmación suya que sostenga un hallazgo de severidad Media o superior la verifiqué línea a línea. Las citas que no releí van marcadas con **(†)**.
- **Lo que no se hizo:**
  - no se ejecutaron builds, pruebas, GUI, CAD ni modelos;
  - no se abrió, copió ni hasheó ningún dibujo;
  - no se escribió en el repositorio.
- **Incidente único:** el escudo frenó, con razón, un borrado de archivo temporal cuya ruta estaba en una variable. No se ejecutó nada. Por decisión de Luis, la comparación se rehízo sin temporales.

### 0.4 Convenciones

**Veredictos**

- **Confirmada:** código o documento la sostienen en el alcance indicado.
- **Parcial:** es cierta, pero con salvedades materiales.
- **Contradicha:** el código dice otra cosa.
- **Desconocida:** no hay evidencia accesible con las reglas de esta auditoría.

**Severidad**

- **Alta:** puede duplicar o perder una mutación, o llevar a una conclusión o decisión equivocada.
- **Media:** degrada exactitud, recuperación o medición, y existe mitigación.
- **Baja:** fricción, deuda técnica o documentación.

---

## 1. Resumen ejecutivo

**Estado.** El producto es útil y su custodia es seria:

- token por sesión y descriptor con ACL privada;
- identidad de proceso por PID y hora de creación;
- cerco de captura por revisión;
- `run_script` estricto y journal que falla cerrado;
- cierre de sesión con propiedad comprobada.

Tiene tres puntos débiles:

- la semántica de recuperación **para un cliente MCP genérico** es inmadura;
- la «verificación» de persistencia es más débil de lo que su nombre sugiere;
- la evaluación todavía no tiene poder comparativo.

**Conclusión 1. Recuperar sin duplicar depende hoy del cliente, no del servidor.** El harness propio (`mcp_client.py`) mitiga el riesgo: siempre envía `revision` y consulta `operation` en vez de reenviar. Un cliente genérico no tiene esa protección, por cuatro defectos de contrato verificados en código:

- **Revisión implícita.** `revision` es opcional y el servidor la rellena con la última que vio *él*, no el agente (`src/mcp.rs:758`).
- **Errores mal etiquetados.** Todo error que el servidor propaga como `Err` sale como `invalid_arguments, retryable:false` (`src/mcp.rs:1993-2000`), también después de enviar la mutación: E/S, sondeo, consulta posterior, journal. Las respuestas de la GUI que llegan como valor (p. ej. `response_timeout`) sí conservan su código.
- **Lectura que ejecuta.** `ocs_read op:"operation"` se anuncia `readOnlyHint:true`, pero sobre un lote inconcluso ejecuta los pasos que faltan (`src/mcp.rs:1627-1633` → `708-724`).
- **Idempotencia acotada.** Solo cubre las últimas **128** operaciones en memoria de la GUI (`src/app/control/mod.rs:1287-1292`) y compara la solicitud entera, incluidos los campos que inyecta el servidor.

**Conclusión 2. D01 y D02 son del programa, no del harness.**

- **D01.** Ninguna ruta de consulta de la aplicación trata el INSERT: delega en el codec. En una revisión cercana del codec (`42b44d2`; la fijada, `cdf2277`, no estaba disponible) ese cálculo es un marcador provisional («*For now, return a bounding box at the insertion point*»). La propia aplicación asume ese colapso (`src/scene/mod.rs:1550-1552`).
  - `contains_point` y `near` ni siquiera consideran INSERT.
  - `query` mezcla hijos de definiciones de bloque en coordenadas locales.
- **D02.** `block_define` nunca asigna capa a la referencia; comparte función con el comando BLOCK de la GUI.
- **Además,** la comparación semántica de `save_verified` es de **conteos por tipo y por capa** (`src/app/automation.rs:366-378`). La operación sí comprueba reapertura y versión, pero «verificado» no significa geometría ni handles preservados.

**Conclusión 3. No hay base para declarar ganador entre modelos o harnesses.**

- E1, E2 y E3 son tareas distintas, con configuraciones distintas y n=1.
- La identidad efectiva del modelo no es verificable en ningún carril real.
- ~95 % del tiempo de pared cae fuera del MCP y no está atribuido.
- Las series de latencia probablemente se midieron con binario de depuración: 29 scripts lo usan por defecto (hipótesis).

Lo que sí existe es buena infraestructura de custodia —reserva con hash, cadena y ranuras de un solo uso— sobre la que se puede montar el protocolo de la §6.

**Orden recomendado**

1. Contrato: revisión obligatoria, taxonomía de errores, observar ≠ reanudar, ventana de idempotencia explícita.
2. R01/R02 con fixture sintético propio, y `save_verified` por propiedades.
3. Instrumentación por fase.
4. Solo entonces, optimizar y comparar modelos.

---

## 2. Matriz de afirmaciones

| ID | Afirmación (fuente) | Evidencia | Veredicto | Alcance |
|---|---|---|---|---|
| A01 | Rama operativa `codex/windows-web-dxf`; HEAD previo `26bce00a` (06 §1) | `26bce00a` + 1 commit documental; worktree limpio | Confirmada | El commit documental no estaba publicado; versión redactada para publicación: `d0d88409` |
| A02 | Binario instalado v2026.40.1 con productor `196b1b7c` (06 §1) | `196b1b7c` es padre de `26bce00a`; sin cambios en `src/`, `Cargo.*` ni `crates/` | Parcial | Fuente confirmada; EXE, hash y perfil sin verificar |
| A03 | El checkout original tiene cambios históricos y CAD privado (06 §1) | `git status` del checkout de la sesión | Confirmada | — |
| A04 | Los bounds de INSERT colapsan en el punto de inserción; una ventana dentro del símbolo devuelve cero (D01) | `src/scene/convert/tess.rs:1761-1793`: sin rama INSERT, cae en `bounding_box()` del codec. Codec `insert.rs:695-699` (†, rev. `42b44d2`). `src/scene/mod.rs:1550-1552`. Bucle en `src/app/automation.rs:1006` y filtro en `1049-1058` | Confirmada en la app; el colapso del codec, en revisión cercana | La app no trata INSERT (confirmado). El colapso al punto se leyó en el codec `42b44d2`, no en el fijado `cdf2277`. Las 25 referencias de E2 no se verificaron |
| A05 | Las primeras referencias de `block_define` quedaron en capa 0 (D02) | `src/scene/entity.rs:1080-1083` crea `DxfInsert::new(name, ZERO)` sin asignar capa; `src/app/control/entities.rs:173-198` hace lo mismo en `entities_create` | Confirmada y ampliada | Afecta a **todas** las referencias de `block_define` y a todo INSERT creado sin `layer`. Si es defecto o diseño lo fija el contrato R02 |
| A06 | Con MCP se pudo crear, modificar, conservar, guardar, reabrir y auditar (E2/E3) | Las operaciones existen (`src/mcp.rs:51-97`); `save_verified` en `src/app/automation.rs:1281-1412` | Parcial | Capacidad confirmada. Resultados de corrida sin verificar. «Verificado» = conteos |
| A07 | V2 conserva 184 entidades sin cambio geométrico y transforma 5 (E3) | Recibo local no versionado | Desconocida | No leído por regla. La comparación la hizo el harness, no el producto |
| A08 | El contexto de dibujo de V2 es un prototipo local (06 R04) | `git grep`: ni esquema ni código de `owned-cad-context-1` o `CHANGE-PLAN` | Confirmada | — |
| A09 | Imagen de baja resolución: persistencia acotada aprobada, comparación externa parcial, fidelidad no aceptada (E1) | L4 compara contra el PlanSpec y los handles del propio harness (†, `external_l4_verdict.py`, `cli_development_l4.py`) | Confirmada como límite | L4 prueba interoperabilidad, no fidelidad a la imagen. Cifras de E1 sin verificar |
| A10 | Crear y modificar son cargas distintas; no hay benchmark causal (06 §4) | Sin intercalado, n=1 por condición, identidad sin verificar | Confirmada | — |
| A11 | La identidad efectiva y el uso directo del modelo no están comprobados (06 D13) | `docs/automation/masterplan/cli_development_trial.py:370,402` fija `"unverified_by_cli_jsonl"`. `reserved_evaluator.py` exige `provider_response_verified`, que ningún código produce (†) | Confirmada | Vale para todos los carriles reales |
| A12 | Los recibos bajo `target` son locales (06 §8) | 22/22 presentes por tamaño en el worktree; 0/22 en el checkout de la sesión | Confirmada | Tamaño ≠ hash. DWG/PNG no tocados |
| A13 | Aritmética de 06 §4: 4.53 % y 3.24 %; caché 95.45 % y 94.27 %; 9.18 y 8.83 comandos/s | Recalculada: 4.528 %, 3.240 %, 95.45 %, 94.27 %, 9.175 y 8.828 | Confirmada | Solo la aritmética; los datos de origen no se verificaron |
| A14 | «Reenviar una mutación con el mismo `request_id` devuelve el resultado en caché» (API-SPEC §1) | `src/app/control/mod.rs:616-626` compara la solicitud entera. Caché de 128 en memoria (`:1287-1292`). `client_id` aleatorio por conexión MCP (`src/mcp.rs:731`) | Parcial | Solo en la misma GUI, dentro de las últimas 128 operaciones y con carga idéntica, incluidos los campos inyectados |
| A15 | «Cada operación es todo o nada; las transacciones de varios pasos son `batch`» (API-SPEC §1) | `batch` y `run_script` se detienen en el primer fallo sin revertir (`src/mcp.rs:972-985`; el README lo admite). `failed` se deduce de los errores de la línea de comandos, sin revertir (`control/mod.rs:1254`) | Contradicha para lotes | Parcial para operaciones sueltas |
| A16 | «`ocs_execute` acepta las 36 operaciones de mutación» (API-SPEC §3.5) | `EXECUTE_OPS` tiene 45; 36 es la lista de pasos de lote | Contradicha | Deriva documental |
| A17 | La spec aplica a builds 2026.41+ (y a 2026.40 salvo §3.5 y §6.12) | `Cargo.toml`: 2026.40.1 | Contradicha | El propio texto deja el MCP fuera de la build en uso |
| A18 | Filtro `bounds`: «entidades que intersecan la caja» (API-SPEC §6.4) | Ver A04. Además `document.entities()` incluye hijos de definición (`src/app/automation.rs:2541-2543`) | Contradicha para INSERT | Correcta para curvas simples |
| A19 | INSERT: «`block` must exist» (API-SPEC §6.2) | La creación no lo comprueba; `block_missing` solo existe en `block_delete` (`src/app/control/entities.rs:610`) | Contradicha | Se detecta tarde, en `audit` |
| A20 | `changes[]` lista los handles afectados, hasta 1000 (API-SPEC §5.1) | `control/mod.rs:1271-1272`. `replay_since` devuelve `None` tras un delta completo (`src/scene/mod.rs:2969-2981`, `3599-3600`) | Parcial | Puede ser `null` (p. ej. `block_define`) o truncarse sin aviso |
| A21 | `save_verified` compara el «semantic entity manifest» (README) | `document_manifest` = total, por tipo y por capa (`src/app/automation.rs:366-378`) | Parcial | Sin geometría ni handles. En DWG no se audita el grafo de handles |
| A22 | «Si se pierde una respuesta se consulta `operation`; jamás se reenvía» (`mcp_client.md`) | Cliente: sí (†, prueba `lost_mutation`). Servidor: `operation` sobre un lote no terminal ejecuta pasos | Parcial | Observar un lote equivale a hacerlo avanzar |
| A23 | Journal con reemplazo atómico y `sync_all` antes de cada paso (`mcp_client.md`) | `src/mcp.rs:249-271`; llamadas en `:838`, `883`, `1000` y en los terminales | Confirmada | También después de cada paso: 2N+2 reescrituras completas, sin retención |
| A24 | Captura con cerco de revisiones y temporizador de 8 s (`mcp_client.md`) | `src/mcp.rs:1704-1716`; `control/mod.rs:1364` y `1385-1396` | Confirmada | El hash lo calcula el cliente, no el servidor |
| A25 | `shutdown_owned_session` solo si este MCP lanzó la GUI; exige PID, hora de creación, ejecutable y `owned_root` | `src/mcp.rs:1092-1200` | Confirmada | La propiedad vive en memoria y no sobrevive a un reinicio del proceso MCP |
| A26 | Descubrimiento con 100 descriptores muertos: p50 ≈ 1.9 s (`mcp_client.md`) | 100 descriptores entre 16 hilos = 7 rondas × 250 ms ≈ 1.75 s, más gastos (`src/mcp.rs:530`, `556`) | Coherente con el diseño | No se volvió a medir |
| A27 | Las 4 herramientas y muchas operaciones son del proyecto compartido (06 §2) | Upstream `60f35e2b` tiene 38 operaciones de ejecución; el fork añade 7 más 1 de lectura y no quita ninguna | Confirmada | Contra la ref local, no contra `ab068215` |
| A28 | Los handles son estables tras guardar y abrir (API-SPEC §1) | `save_verified` no compara handles; el lector/escritor DWG no se auditó | Desconocida | — |
| A29 | `AGENTS.md` da instrucciones de publicación coherentes | Una línea autoriza push y otra lo prohíbe en el ciclo actual | Contradicha | — |
| A30 | Serie L2: RPC `run_script` p50 de 2608 ms a 492 ms, con ~6 ms de GUI (05, cortes 42 y 44) | Solo el documento; recibos no leídos | Desconocida (causa) | Hipótesis: orquestación MCP y/o binario de depuración (§3.5) |

---

## 3. Hallazgos

Cada hallazgo indica: severidad, impacto, causa (confirmada o hipótesis), reproducción disponible, datos faltantes y recomendación enlazada al backlog (§5). **Ninguna prueba se ejecutó.** La reproducción es por lectura de código, y se propone la prueba sintética mínima.

### 3.1 Programa

**P1 · Bounds de INSERT degenerados en todas las rutas de consulta — Alta**

- **Impacto:**
  - Cualquier control espacial de mobiliario o símbolos da falsos negativos: colisiones, ventanas de selección, «qué hay en este recinto».
  - `measure` y `audit.bounds` subestiman las extensiones.
  - La API lo anuncia como correcto.
- **Causa confirmada:**
  - `entity_bounds` no tiene rama para INSERT y cae en `bounding_box()` del codec (`src/scene/convert/tess.rs:1761-1793`). El codec devuelve el punto de inserción (†).
  - La propia aplicación ya asume ese comportamiento (`src/scene/mod.rs:1550-1552`; `tess.rs:1853-1863`).
  - `contains_point` exige una curva cerrada y `near` exige una curva, así que un INSERT nunca aparece (`src/app/automation.rs:1059-1082`).
  - `query` recorre `document.entities()`, que incluye los hijos de las definiciones de bloque (`:1006`; el test `:2541-2543` lo reconoce).
- **Lo aprovechable:** ya existen cálculos correctos, pero no conectados a `query`:
  - `defn_metrics_recursive` del caché de render (†);
  - `model_space_extents` (†);
  - `insert_extents` de XCLIP (`src/app/commands/xclip.rs:10-32`, †), la plantilla más cercana.
- **Prueba mínima:**
  1. Definir un bloque rectangular de 1×1 con base (0,0).
  2. Insertarlo en (10,10) con rotación de 30° y escala (2,1).
  3. Consultar `query bounds` con una ventana interior que no contenga el punto de inserción.

  Hoy devuelve 0 resultados y `measure` da min == max.
- **Dato faltante:** la revisión fijada del codec no está disponible localmente.
- **Recomendación:** B06.

**P2 · Toda referencia creada por `block_define` o por `entities_create` sin capa va a «0» — Media**

- **Impacto:** los símbolos no obedecen las capas de mobiliario (apagar o congelar). El contrato E3 obliga a «normalizar explícitamente» a mano, que es un trabajo del harness evitable.
- **Causa confirmada:**
  - `src/scene/entity.rs:1080-1083` crea el INSERT sin asignar `clayer` ni la capa activa.
  - Los hijos conservan su capa.
  - `entities_create` sin `layer` usa el valor por defecto del codec, «0» (†).
  - Existen dos «capas actuales»: `sysvar clayer` escribe solo la cabecera, mientras la GUI sella `active_layer` (†, `control/sheets.rs:611-624`).
- **¿Defecto o diseño?** El comando BLOCK de la GUI usa la misma función, así que es un comportamiento del producto sin contrato escrito, no un desliz del MCP. Hay tres opciones: capa actual, capa de origen o «0» (la convención CAD habitual es la capa actual, pero es inferencia y no se verificó aquí). **Es criterio de dibujo: decide Luis (R02).**
- **Prueba mínima:** `sysvar set clayer=MUEBLES`, luego `block_define`, luego leer la capa del INSERT.
- **Recomendación:** B07.

**P3 · `save_verified` verifica conteos, no propiedades — Media**

- **Impacto:** `verified:true` es compatible con coordenadas desplazadas, radios alterados, handles cambiados o referencias de bloque rotas, siempre que se conserven los conteos por tipo y capa. En DWG no se audita el grafo de handles; solo en DXF ASCII (`src/app/automation.rs:1346-1353`).
- **Causa confirmada:** `src/app/automation.rs:366-378` y `1379-1389`. El propio backlog (M6.4) y el 04 (§Pruebas) ya piden comparar propiedades.
- **A favor:**
  - auditoría previa y reconocimiento explícito de pérdidas;
  - rechazo de sobrescritura;
  - reapertura con control de versión;
  - tiempos por fase (`:1401-1410`).
- **Recomendación:** B08.

**P4 · `changes` puede ser `null` o truncarse sin aviso — Media**

- **Impacto:** el agente no puede deducir con fiabilidad los efectos de una operación a partir de `changes`. El `added_entities` de `run_script` cuenta de menos cuando un paso provocó una reconstrucción completa, como BLOCK.
- **Causa confirmada:**
  - Corte a 1000 sin bandera (`control/mod.rs:1271-1272`).
  - `bump_geometry()` registra un delta completo, y `replay_since` devuelve `None` (`src/scene/mod.rs:3599-3600`, `2969-2981`).
  - `src/mcp.rs:952-961` ignora los `changes` que no son lista.
- **Recomendación:** B09.

**P5 · Las ediciones de muro asumen metros sin consultar INSUNITS — Baja**

- **Causa:** `wall_edit.rs:27-34` y `70-73`.
- **Impacto:** en un plano en mm la operación falla cerrada, pero con un diagnóstico falso (`wall_thickness_stale` o `invalid_thickness`).
- **Recomendación:** B10.

**P6 · INSERT a un bloque inexistente se crea sin error — Baja**

- **Causa:** `entities.rs:173-198`; solo `audit` y `save_verified` lo detectan después.
- **Recomendación:** B10.

**P7 · Trabajo pesado en el hilo de la GUI — Media (impacto por medir)**

- **Confirmado en código:**
  - `save_verified` se ejecuta de principio a fin en el hilo UI: auditoría, 3 manifiestos, al menos 3 clones del documento (†), escritura, hash del archivo entero y reapertura completa.
  - `audit` serializa entidad por entidad.
  - La captura copia, recorta, redimensiona y codifica el PNG en el hilo UI (†).
  - `query` y `records` serializan todas las entidades que coinciden antes de paginar (†, `automation.rs:1082`).
  - `control_state` busca fuentes SHX faltantes en disco en cada respuesta (`control/mod.rs:435`).
- **Consecuencias:**
  - la GUI se congela;
  - pasados 15 s, el transporte responde `response_timeout` en dibujos grandes;
  - mientras dura, `hello` supera los 250 ms del descubrimiento (M9).
- **Recomendación:** B17 y B18, midiendo antes.

**P8 · Arranque frío sin medir — Baja/Media (hipótesis)**

- **Posibles costes:**
  - sondeo de GPU por subproceso, hasta 10 s por backend y sin caché (†, `gpu_backend.rs:389-428`);
  - carga de plugins, con 30 s de tiempo de espera de arranque (†);
  - llamadas de red en segundo plano (†).
- **Efecto confirmado:** los modales de inicio hacen que `control_settle` informe `waiting_input` (`control/mod.rs:1255-1258`), así que un `run_script` estricto falla en un perfil nuevo.
- **Recomendación:** B22.

### 3.2 MCP

**Fortalezas verificadas**

- Descriptor con token de 32 bytes y ACL privada.
- Identidad de proceso por PID y hora de creación, con cuarentena de descriptores muertos (`src/mcp.rs:405-474`).
- Cola acotada (32) y límite de 8 conexiones (`transport.rs:60`, `98`).
- Verificación de sesión (`session_changed`) y de revisión (`stale_state`) **antes** de ejecutar (`control/mod.rs:494-505`, `690-704`).
- Pasos de lote con ID determinista y sin reenvío.
- Journal que falla cerrado ante corrupción o identidad distinta (`src/mcp.rs:273-292`).
- `run_script` estricto: comandos incompletos o tokens sin consumir (`:1015-1029`).
- Cerco de captura (`:1704-1716`).
- Cierre con propiedad comprobada (`:1092-1200`).
- Mensajes de error con ejemplo de solicitud (`:1247-1490`).

**Respuesta directa: ¿puede un agente saber qué pasó tras perder una respuesta, sin repetir ni duplicar?** Sí con el cliente del proyecto, dentro de ciertos límites; no en general.

| Escenario | ¿Se sabe sin duplicar? | Cómo | Condición o riesgo |
|---|---|---|---|
| Respuesta perdida entre MCP y agente, operación suelta | Sí | `ocs_read operation` con el mismo ID | Solo dentro de las últimas 128 operaciones y en la misma GUI |
| Tiempo de espera de 15 s con la operación en cola o en curso | Sí | `operation` responde `running` o `completed` (la cola es FIFO) | Si llega un error de E/S etiquetado `invalid_arguments`, el agente debe ignorar la etiqueta (M2) |
| Reintento con el mismo ID tras un cambio de estado | Parcial | `operation` sí responde | Sin `revision` explícita el reintento recibe `request_id_reused` (M1) |
| Lote o `run_script` con respuesta perdida | Solo el progreso, y **no sin hacerlo avanzar** | `operation` carga el journal y continúa | Exige la misma GUI (M3) |
| Proceso MCP reiniciado, operación suelta | Sí | `operation`: la caché vive en la GUI | Reenviar el mismo ID devuelve `request_id_reused`, porque el `client_id` es nuevo |
| Más de 128 operaciones después | No con certeza | `unknown_operation` es ambiguo | Hay que conciliar por censo (M4) |
| GUI reiniciada o caída | No por protocolo | Sesión nueva; se pierden la caché y los cambios sin guardar | Conciliar contra el último archivo guardado; no reproducir en la sesión nueva |
| Falla la consulta posterior de `changed_entities` | Sí, si el agente ignora la etiqueta | `operation` | Hoy llega como `invalid_arguments` (M2) |

**M1 · `revision` opcional y rellenada por el servidor — Alta**

- **Impacto:**
  1. El control optimista protege contra el estado que vio el *servidor*, no el que vio el agente.
  2. La GUI compara la solicitud entera, incluidos `revision`, `selection` y `client_id` inyectados. Un reintento legítimo con el mismo ID tras un cambio de estado recibe `request_id_reused` («Request payload changed»), no el resultado en caché.
  3. La reacción natural pero equivocada —reenviar con otro ID— pasa el control, porque el servidor inyecta la revisión *actual*: geometría duplicada.
- **Escenario derivado del código (no reproducido):**
  1. Mutación sin `revision`: el servidor inyecta R.
  2. Se pierde la respuesta.
  3. La GUI completa: la revisión pasa a R+1.
  4. El agente lee `state`.
  5. Reintenta con el mismo ID: recibe `request_id_reused`.
  6. Reenvía con un ID nuevo: el servidor inyecta R+1 y la mutación se ejecuta **dos veces**.
- **Mismo mecanismo en Tasks:** `poll_task` reenvía los argumentos y `request()` vuelve a inyectar valores desde el estado actual (`src/mcp.rs:2048-2050`, `746-763`). Si otra lectura actualizó el estado entretanto, el sondeo puede terminar la tarea con `busy` o `request_id_reused` mientras la operación sigue viva. Es hipótesis.
- **Causa confirmada:**
  - `src/mcp.rs:746-763`;
  - el esquema exige `revision` solo para `batch`, `run_script` y las operaciones de muro, impresión métrica y cierre (`:1857-1910`);
  - comparación en la GUI: `control/mod.rs:616-633`.
- **Origen:** heredado del upstream.
- **Mitigación actual:** el cliente del proyecto.
- **Recomendación:** B01.

**M2 · Errores propagados después del envío etiquetados `invalid_arguments, retryable:false`, con carrera de 15 s contra 15 s — Alta**

- **Causa confirmada:** todo `Err` de `call_tool` pasa por `error_result` (`src/mcp.rs:1993-2000`, `2202`). Estos `Err` pueden ocurrir **después** de enviar la mutación:
  - lectura de E/S en `exchange` (`:501-507`);
  - fallo de un sondeo (`:780-784`);
  - la consulta de `changed_entities` (`:1586-1589`);
  - el journal tras un paso (`:1000`).
- **Carrera:** el MCP corta la lectura a los 15 s (`:769`) y la GUI responde `response_timeout` también a los 15 s (`transport.rs:106-107`, `130`). Lo que llegue primero decide si el agente recibe un error estructurado y recuperable, o un error de E/S crudo presentado como «argumentos inválidos».
- **Impacto:** empuja al agente a creer que «no pasó nada», que es justo la condición para duplicar.
- **Origen:** heredado del upstream.
- **Recomendación:** B02.

**M3 · `ocs_read operation` reanuda lotes; no hay consulta pura ni aborto — Media/Alta**

- **Causa confirmada:**
  - `ocs_read` se anuncia `readOnlyHint:true` (`src/mcp.rs:1958`).
  - Pero `op:"operation"` sobre un lote no terminal llama a `execute_batch` (`:1627-1633`, `708-724`), que envía mutaciones nuevas (`:893-914`).
  - `tasks/get` avanza un paso por sondeo (`:2048-2050`, `870-875`).
- **Impacto:**
  - no se puede observar un lote sin avanzarlo;
  - no se le puede ordenar que pare;
  - un cliente que aprueba automáticamente las herramientas de solo lectura deja pasar mutaciones.
- **Origen:** propio del fork (`resume_batch_operation` no existe en el upstream).
- **Recomendación:** B03.

**M4 · Ventana de idempotencia real: 128 operaciones en memoria — Media**

- **Causa confirmada:**
  - FIFO de 128 entradas en la GUI (`control/mod.rs:1287-1292`).
  - Cada paso de lote cuenta, así que un solo `run_script` de 256 órdenes la vacía.
  - Se pierde al reiniciar la GUI.
- **Riesgos:**
  - Un ID expulsado ya no se reconoce. Si se reenvía con su `revision` original, `stale_state` lo detiene. Si se reenvía **sin** `revision` —el servidor inyecta la actual (M1)— o con la actual, **se vuelve a ejecutar**.
  - `unknown_operation` no distingue «nunca llegó» de «expiró» ni de «la GUI se reinició». El mensaje («do not automatically replay») es buen consejo, pero ambiguo.
- **Anotación `idempotentHint:true` de `ocs_execute` (`src/mcp.rs:1965`):** vale solo dentro de esa ventana.
- **Recomendación:** B04.

**M5 · Bucle MCP monohilo y bloqueante, sin cancelación real — Media**

- **Causa confirmada:**
  - `run()` procesa las líneas de stdin en serie (`src/mcp.rs:2237-2264`).
  - Una llamada puede bloquear hasta 60 s de espera más 15 s de E/S.
  - Se ignoran los mensajes sin `id`, así que `notifications/cancelled` no hace nada (`:2108-2110`).
  - `tasks/cancel` responde éxito sin cancelar (`:2223-2231`).
  - `TaskStore` nunca expulsa entradas, aunque anuncia un ttl de 1 h.
- **Impacto:**
  - bloqueo en cabeza de cola: las lecturas concurrentes del cliente se serializan y `ping` queda bloqueado;
  - un «cancelado» que es falso.
- **Origen:** heredado del upstream.
- **Recomendación:** B20.

**M6 · Esquema anunciado pero no aplicado en el servidor — Media**

- **Causa confirmada:** no hay validación JSON Schema en el servidor; `additionalProperties:false` solo se declara.
- **Impacto:** un campo mal escrito (p. ej. `revison`) se ignora en silencio. Sumado a M1, el control optimista desaparece sin que nadie lo note.
- **Recomendación:** B10.

**M7 · Journal: 2N+2 reescrituras completas con sincronización y sin retención — Media (rendimiento y privacidad)**

- **Causa confirmada:**
  - Cada paso hace `write_all` + `sync_all` + `MoveFileExW(…WRITE_THROUGH)` (`src/mcp.rs:233`, `249-271`).
  - Se llama al inicio, antes y después de cada paso, y al terminar (`:838`, `883`, `1000`, terminales).
  - Cada reescritura incluye la solicitud (con los comandos por duplicado: `commands` y `steps`), todos los resultados, todos los `changes` y el estado. En bytes, el coste crece como O(N²).
- **Consecuencias:**
  - Con el tope de 16 MiB, un script largo puede fallar a mitad de ejecución.
  - Nunca se borra: los comandos de dibujos privados se acumulan en el perfil.
- **Recomendación:** B15.

**M8 · Respuestas duplicadas y capturas en base64 — Baja/Media**

- **Causa confirmada:**
  - `tool_result` pone el JSON completo en `content[0].text` y en `structuredContent` (`src/mcp.rs:1986-1990`): ≈2× bytes. En clientes que pasan el texto al modelo, todo entra en contexto.
  - La captura viaja en base64 dentro del contenido (`:1719`) y el servidor no calcula su hash.
- **Recomendación:** B12, B18.

**M9 · El descubrimiento puede lanzar una segunda GUI cuando la primera está ocupada — Media (hipótesis derivada del código)**

- **Causa:**
  - Un descriptor cuyo `hello` no responde en 250 ms se descarta (`src/mcp.rs:556`).
  - Si ninguno responde, `sessions()` lanza otra GUI; `launch_if_none` vale `true` por defecto (`:644-692`).
  - La GUI contesta `hello` desde su hilo UI, que puede estar ocupado varios segundos (P7).
- **Mitigación actual:** el harness del proyecto usa una sesión explícita y `wait_for_existing`.
- **Recomendación:** B14.

**M10 · Otros — Baja**

- La propiedad de la sesión no sobrevive a un reinicio del MCP: `LAUNCH` vive en memoria (`src/mcp.rs:170`, `1119-1130`).
- `changed_entities` pide 25 600 entidades, pero `query` recorta a 10 000 sin avisar (`:1587`; `src/app/automation.rs:983`).
- `gui.log` crece sin rotación (`src/mcp.rs:619-629`).
- La carpeta de cuarentena se acumula.

### 3.3 Harness y modelo

**Atribución causal de incidentes.** Las categorías son las pedidas: modelo, harness, MCP, programa o desconocida.

| Incidente | Causa | Base |
|---|---|---|
| D01 bounds de INSERT | **Programa**, y el contrato MCP promete más de lo que hay | Código (P1) |
| D02 capa 0 | **Programa**, sin contrato | Código (P2) |
| D03 operación `summary` inexistente | **Harness**. El MCP la rechazó explícitamente, que es lo correcto | Documento 06 |
| D04 colisión de nombres por mayúsculas en Windows | **Harness** | Documento |
| D05 selección solo por texto | **Harness** (selector) | Documento |
| D06 TEXT normaliza espacios | **Desconocida**. Probablemente la sintaxis de `run` separa por espacios; no verificado | — |
| D07 JSON con clave duplicada | **Modelo**. El control estricto del harness lo atrapó, correctamente | Documento |
| D08 interpretación de imagen deficiente | **Desconocida**: no hay ablación que separe modelo, prompt, resolución (168×300) y cobertura de PlanSpec | Documento |
| D09 perfil métrico omitido | **Harness** | Documento |
| D10 precisión de radios en el censo externo | **Harness** (herramienta L4) | Documento |
| D11 la sonda reescribió su entrada | **Harness** (custodia) | Documento |
| D12 helpers extensos y relecturas | **Harness**; el ahorro no está demostrado | Documento |
| D13 identidad | **Harness / interfaz del proveedor** | Código (H1) |
| Nuevo: `changes:null` | **Programa/MCP**: informa de forma incompleta | Código (P4) |
| Nuevo: `invalid_arguments` tras enviar | **MCP**: informa mal | Código (M2) |

**H1 · La identidad efectiva del modelo no es verificable — Alta**

- **Causa confirmada:**
  - El carril CLI escribe la constante `unverified_by_cli_jsonl` (`cli_development_trial.py:370`, `402`).
  - El adaptador directo por API nunca se ejecutó de verdad (†, `M3-DIRECT-RESPONSE-RECEIPT-V1.md:7`).
  - `provider_response_verified` es inalcanzable (†).
- **Riesgo (inferencia):** la completitud exige igualdad exacta de cadena con el modelo solicitado (†, `luna_pipeline.py:47`, `reserved_trial.py:231-232`). Un ID con fecha de snapshot nunca «completaría».
- **Recomendación:** B05.

**H2 · Contabilidad de tokens: ceros que pueden ser ausencias, y uso perdido en fallos — Media**

- **Posibles ausencias escritas como 0:** en E1, `reasoning_output_tokens` y `cache_write_input_tokens` valen 0 (`06-METRICAS…json:14-18`), pero el parser del CLI no exige esos campos (†, `cli_development_trial.py:82-86`). Choca con la regla del 06: «medición ausente es desconocida, no cero».
- **Uso perdido en fallos:** el carril reservado pierde el uso de las ranuras `uncertain` (`reserved_runner.py:175-180`, verificado).
- **Sin deduplicación:** no se deduplican `response_id` entre ranuras (†).
- **Origen no versionado:** las cifras de E2 y E3 vienen de contadores del hilo, calculados por scripts no versionados.
- **Recomendación:** B05, B12.

**H3 · Binario de depuración por defecto — Media**

- **Causa confirmada:**
  - 29 scripts usan `target/debug` por defecto; solo 1 usa release (p. ej. `mcp_latency_series.py:71`).
  - `Cargo.toml:155-156` no define optimización para `dev`.
- **Impacto:** las series de latencia no son comparables con el binario instalado. El recibo no registra el perfil; `--version` sí lo imprime (†, `cli.rs:24-34`).
- **Recomendación:** B19.

**H4 · ~95 % del tiempo de pared sin atribuir; el contexto domina — Media**

- **Evidencia:** MCP/pared = 4.5 % y 3.2 % (06, aritmética verificada). La línea base E0 promedia ~117 k tokens por respuesta (9 797 952 / 84).
- **Inferencia:** el tamaño de contexto × el número de turnos pesa más que el servidor. La palanca principal es el harness: contexto compacto, menos turnos, sin helpers ad hoc, no la latencia del MCP.
- **Recomendación:** B12 y R06/R16.

**H5 · Instrucciones de agente contradictorias y distintas entre checkouts — Media**

- **Causa confirmada:** el `AGENTS.md` auditado se contradice sobre push, y el del checkout de la sesión es otro archivo.
- **Impacto:** el comportamiento del agente depende de dónde arranque.
- **Recomendación:** B11.

**H6 · Selectores y helpers improvisados — Media**

- **Evidencia:** D03–D06 y D09. El R03 del 06 ya apunta a la solución: adaptador tipado sobre `capabilities`, cardinalidad exacta, rol + tipo + geometría.
- **Recomendación:** R03/R16 (B10 cubre el lado servidor).

**H7 · En E1 no se aislaron causas — Media**

- **Causa:** sin ablación de modelo, prompt, resolución ni cobertura de PlanSpec. El L4 compara contra la salida del propio generador (A09).
- **Recomendación:** §6 (tareas T5 separadas); R08/R15.

### 3.4 Evaluación

**E1 · No existe comparación controlada modelo × harness — Alta**

- **Evidencia:** las únicas «comparaciones» son los pilotos M7.3, con n=3 sobre recortes ya vistos: ventana 1/3 contra 3/3; puerta 0/3 contra 1/3.
- **Intervalos:** con Wilson al 95 %, 1/3 → [0.06, 0.79] y 3/3 → [0.44, 1.00]. Se solapan casi por completo.
- **Nota:** los documentos ya lo advierten, y lo hacen bien.
- **Recomendación:** §6, B21.

**E2 · Conjunto reservado bien custodiado pero sin estrenar — Media**

- **Controles existentes (†):**
  - 6 imágenes con hash único, 2 de cada dificultad;
  - 36 ranuras (2 × 6 × 3) en JSONL encadenado con sincronización y candado;
  - el oráculo debe congelarse antes de reservar ranura.
- **Carencias (†):**
  - ninguna imagen real congelada (`M7-ORACLE-FREEZE-V1.md:31`);
  - tolerancias como texto libre;
  - aislamiento del oráculo solo por convención;
  - L5 sin código de ingestión.
- **Recomendación:** §6.3.

**E3 · Los niveles de evidencia mezclan ejes — Media**

- **Causa confirmada:** en el 04, L3 («imagen interpretada por Luna») es un *tipo de tarea*; L0–L2, L4 y L5 son *verificadores*.
- **Recomendación:** §6.7.

**E4 · Herramientas de piloto de un solo uso — Baja**

- **Causa confirmada:** `summarize_cli_samples.py:80-82` exige los conteos congelados (3/1/1) y falla si difieren. Es una salvaguarda de regresión, **no una fabricación**, pero no sirve como agregador general.
- **Estadística:** con n ≤ 10, el «p95» es el máximo; el 05 lo reconoce.

**E5 · Faltan tiempos por fase, bytes y capturas — Media**

- **Carril reservado:** sin tiempos, RPC ni bytes (†).
- **Traza del cliente:** apagada por defecto, con la fase fija en `"rpc"` (†).
- **Índice 06 de E2/E3:** sin bytes ni número de capturas (verificado en el JSON).
- **Recomendación:** §7.

### 3.5 Rendimiento por capa

| Capa | Qué se sabe | ¿Cuello demostrado? | Hipótesis a medir | Dato faltante |
|---|---|---|---|---|
| Modelo | Contadores locales de tokens por corte (06) | No | Tamaño de contexto × turnos domina la pared | Latencia y uso por `response_id` |
| Harness | ~95 % del tiempo de pared fuera del MCP (06) | No: nada atribuido | Helpers, relecturas, escritura de archivos | Intervalos por fase |
| Transporte MCP↔GUI | Una conexión TCP nueva por solicitud; sondeo cada 50 ms; sin `TCP_NODELAY` ni búfer; respuesta escrita con `writeln!` sobre el socket (`transport.rs:134`) | No | Esperas por ACK retardado (Nagle + escrituras pequeñas); número de sondeos | Histograma de RTT de `state`; sondeos por operación |
| Orquestación de lotes | 2N+2 sincronizaciones con renombrado. RPC de script 0.5–2.6 s contra ~6 ms de GUI (05) | Parcial: se midió la brecha, no su causa | El journal y la E/S síncrona dominan | Tiempo de `persist_batch` por llamada |
| GUI | `timings.total_ms` por operación. Captura 1.05–1.24 s, de los cuales 0.92–1.09 s son PNG (05, sin recibos) | Sí para la captura, en el binario medido | PNG en binario de depuración y en el hilo UI | Perfil del binario; release frente a depuración |
| Kernel/codec | Sin medición separada | No | Menor en operaciones sintéticas | Benchmarks por operación MCP (los existentes no las cubren, †) |
| E/S | `save_verified` con tiempos por fase; RPC de guardado 60–66 ms en sintético (05) | No en dibujos reales | Los clones y la reapertura escalan con N | Serie por tamaño de dibujo |
| Arranque | Sondeo de GPU por subproceso, plugins, modales (†) | No | El arranque frío lo dominan GPU y plugins | Marcas inicio→descriptor→`hello` |

**Qué no se puede afirmar:** que el cuello de botella esté en el kernel CAD, ni que V2 fuera más rápido *por método*. Las cargas son distintas (A10).

---

## 4. Relación con R01–R19

- **Tabla de fases 06 (§7):** la uso tal cual.
- **Correcciones a sus supuestos:**
  - **R01:** la causa ya no está «por investigar» (P1).
  - **R05:** su criterio «nunca replay automático» no lo cumple `tasks/get`, que reenvía la mutación con el mismo ID y se apoya en la caché de 128. Es seguro solo dentro de esa ventana (M4).
  - **R06/R07:** medir con binario release antes de optimizar (H3).
- **Ítems nuevos que propongo:** R20 «contrato publicado = código» y R21 «semántica de error y recuperación para clientes genéricos». Integro R21 en R05 donde encaja.

---

## 5. Backlog priorizado

**Prioridades:** P0 protege el estado y la no duplicación; P1, exactitud y contrato; P2, rendimiento medido y comparación.
**Criterio de aceptación:** observable en un fixture sintético propio; nunca en el dibujo privado.

| ID | Prio | Qué | Rxx | Depende de | Aceptación observable |
|---|---|---|---|---|---|
| B01 | P0 | `revision` obligatoria en toda mutación; sin relleno implícito de `revision`, `selection` ni `document_id`. Guardar la forma canónica en el primer envío y reutilizarla en reintentos y tareas | R05, R03 | — | (i) sin `revision` → `revision_required`, sin tocar la GUI; (ii) mismo ID tras cambio de estado → resultado en caché; (iii) ID nuevo con revisión vieja → `stale_state`; censo L2 sin duplicados |
| B02 | P0 | Taxonomía de errores: `invalid_arguments` solo antes del envío; después, `outcome_unknown` con `recover:{op:"operation",request_id}`. Plazo MCP mayor que el de la GUI (p. ej. 20 s frente a 15 s) | R05/R21 | — | Con retraso inyectado de 16 s, 20/20 intentos reciben `response_timeout` estructurado; una prueba unitaria por rama de error, incluidas `changed_entities` y el journal |
| B03 | P0 | Separar observar de reanudar: `operation` de solo lectura; `batch_resume` y `batch_abort` explícitos en `ocs_execute`; `tasks/get` no avanza pasos | R05, R07 | B02 | Con un par falso que cuenta mutaciones: `operation` sobre un lote no terminal → 0 mutaciones; abortar deja `terminal:"aborted"` |
| B04 | P0 | Ventana de idempotencia explícita: registro persistente de IDs vistos por sesión (solo IDs, p. ej. 10 000); anunciarla en `capabilities` | R05 | B01 | Tras 300 operaciones, reenviar el primer ID → `result_expired`, sin geometría nueva |
| B05 | P0 | Recibo de identidad y uso por `response_id`: modelo efectivo tal como lo devuelve el proveedor, esfuerzo solicitado y eco, subconjuntos de tokens; ausente = `null`, nunca 0. Regla de completitud declarada, no igualdad exacta de cadena | R13 | — | Con respuestas sintéticas: campo ausente → `null`; snapshot con fecha → aceptado según la regla; recibo conservado aunque falle la validación |
| B06 | P1 | Bounds de INSERT transformados: base, escala, rotación, OCS y anidación con guardia de ciclos, en `query`, `measure`, `audit` y `get_selection`. `query` limitado por defecto a espacio Model/Paper | R01, R12 | fixture | Criterios de R01, más: sin hijos de definición en `query` por defecto; comportamiento de `contains_point` sobre INSERT documentado |
| B07 | P1 | Contrato de capa de las referencias, **decidido por Luis**, aplicado en `block_define` y `entities_create`; unificar `clayer` de la cabecera con la capa activa de la GUI | R02 | decisión | Primera referencia y siguientes cumplen el contrato por handle y tras reapertura |
| B08 | P1 | `save_verified` por propiedades: huella por handle (tipo, capa, geometría clave a tolerancia congelada, referencias de bloque); auditoría de referencias también en DWG | M6.4, R11 | — | Defectos sembrados → `semantic_mismatch`: desplazamiento de 1e-3, radio alterado, capa cambiada. Sobrecoste medido |
| B09 | P1 | `changes` fiable: `changes_complete:false` en lugar de `null`; `truncated:true`; `added_entities` marcado como cota inferior | R12, R07 | — | `block_define` devuelve la referencia y los hijos creados; `run_script` con BLOCK no cuenta de menos en silencio |
| B10 | P1 | Validación en servidor: esquema aplicado, bloque existente al crear INSERT, opción `allow_new_layers:false`, unidades en ediciones de muro | R03, R10 | B01 | Campo desconocido → rechazo antes de la GUI; INSERT a bloque inexistente → `block_missing`; plano en mm → `units_mismatch` |
| B11 | P1 | Contrato publicado = código: API-SPEC y README con 45 operaciones, versión, límites (Anexo A), `changes:null`, bounds de INSERT, alcance de `save_verified`, lotes no atómicos; `AGENTS.md` sin contradicción | R20 (nuevo) | B01–B04 | Prueba documental que compara las listas de operaciones del código con la spec y falla si divergen |
| B12 | P1 | Instrumentación por fase (§7) | R13, R14 | B05 | Una corrida sintética con ≥ 95 % del tiempo de pared atribuido o marcado «sin atribuir»; telemetría fuera del texto que ve el modelo |
| B13 | P1 | Contexto versionado (`owned-cad-context`) | R04, R16 | B01, B06 | Criterios de R04 |
| B14 | P1 | El descubrimiento no lanza una segunda GUI si la identidad de proceso coincide y solo está lenta | R17 | — | Con la GUI ocupada 5 s, `ocs_sessions` devuelve la sesión existente como `busy`; 0 procesos nuevos |
| B15 | P2 | Journal incremental (anexar un registro por paso con una sincronización) y retención aplicada | R07, R19 | B03 | Coste por paso constante con N = 8, 64 y 256 en release; política de borrado documentada y probada |
| B16 | P2 | Transporte: medir el RTT de `state`; si hay esperas por ACK, escritura en un solo búfer y/o `TCP_NODELAY`, o conexión persistente | R06 | B12, B19 | p50 y p95 de `state` y de un paso de script, antes y después, con binario release e intercalado |
| B17 | P2 | Consultas proporcionales a la página: filtrar antes de serializar; índice por handle | R06 | B06 | Coste de `query handles=[h]` y `records limit=1` independiente de N (1 k, 10 k, 100 k) |
| B18 | P2 | Captura fuera del hilo UI, con tiempos separados (copia, recorte, escala, codificación); referencia de artefacto con hash del servidor | R17 | B12 | Tiempos por subfase; release frente a depuración; captura sin congelar la GUI |
| B19 | P2 | El perfil del binario (`--version`) y su hash en todo recibo de tiempo; series en release por defecto | R19, R14 | — | Una serie con binario de depuración se rechaza sin bandera explícita |
| B20 | P2 | Concurrencia y cancelación MCP: `ping` y lecturas durante esperas; `tasks/cancel` real o que declare que no puede; caducidad de tareas | R17 | B02, B03 | Durante una espera de 30 s, `ping` responde en < 100 ms; `tasks/cancel` no devuelve éxito falso |
| B21 | P2 | Protocolo de comparación (§6) | R14, R15 | B05, B12 | Piloto con varianza estimada antes de fijar n |
| B22 | P2 | Arranque medido, frío y caliente; modales de inicio sin bloquear `run_script` en perfil aislado | R17, R19 | B12 | Marcas inicio→descriptor→`hello` para 3 condiciones intercaladas |

**Resto de los R.** R08–R10, R15, R16 y R18 siguen como en el 06. Ninguno debe medirse por eficiencia antes de cerrar B01–B05 y B12.

---

## 6. Protocolo para comparar modelos y harnesses

### 6.1 Unidad experimental

Una **combinación** C es:

- el modelo solicitado **y** el efectivo, según el recibo (B05);
- el esfuerzo o razonamiento;
- el harness y su versión, con hash de instrucciones, `AGENTS.md`, esquemas de herramientas y helpers;
- la build de OCS, con hash y perfil;
- el perfil de hardware.

Se registra antes de cada corrida. Cambiar un solo hash define una combinación nueva.

Para **separar causas**, conviene un diseño factorial mínimo 2×2: dos modelos × dos harnesses, con el mismo MCP y la misma build. Así se estima el efecto de cada factor y su interacción.

### 6.2 Batería de tareas fija

| Familia | Ejemplo sintético | Éxito |
|---|---|---|
| T1 Creación | Brief textual, sin imagen: recinto con muros de espesor dado, una puerta, una ventana, dos cotas, un bloque repetido 3 veces con capa especificada | Todas las entidades del oráculo, dentro de tolerancia congelada; capas y tipos nativos |
| T2 Edición localizada | Fixture DWG con hash fijo: mover una puerta 0.50 m, cambiar un espesor, rotar un mueble | Cambio correcto **y** todo lo demás intacto por handle a 1e-6 |
| T3 Consulta espacial | Preguntas que solo `query` responde: qué cruza una ventana, qué curva cerrada contiene un punto, la más cercana; incluye casos INSERT | Respuesta exacta, **o abstención correcta** mientras R01 no esté corregido |
| T4 Recuperación | Fallos inyectados: respuesta perdida (proxy que la descarta), reinicio del MCP a mitad de `run_script`, modal, edición humana entre lectura y escritura (`stale_state`) | Estado final igual al oráculo, 0 duplicados, 0 ediciones perdidas y un informe del agente correcto. Detenerse y declarar incertidumbre es un resultado válido |
| T5 Imagen→CAD (pista aparte) | Solo imágenes con derechos y oráculo congelado | Fidelidad por región en cuatro dimensiones, sin un porcentaje global |

Las tareas se generan con un script paramétrico y semilla. Cada familia debe tener 3 niveles de dificultad.

### 6.3 Conjunto reservado y anticontaminación

- **Dos generadores.** Uno de desarrollo, con semillas públicas: se usa para ajustar prompts. Otro reservado, con semilla y parámetros que guarda Luis. Solo se versionan los hashes.
- **Congelar antes de correr.** Instancias reservadas, oráculo y tolerancias —como datos, no como texto libre— se congelan y encadenan antes de la primera corrida (ya existe: `reserved_trial.py`, †).
- **Oráculo fuera del alcance del agente.**
  - Lo guarda el evaluador en otro directorio y otro proceso.
  - El agente trabaja en un directorio de corrida sin acceso de lectura a oráculos ni a corridas previas.
  - Sin memoria persistente del cliente, sin reanudar conversaciones y sin red a ubicaciones del oráculo.
- **Canarios.** Cada instancia reservada lleva una cadena canario. Antes de cada lote se buscan en prompts, `AGENTS.md`, memorias y helpers; si aparece alguna, se invalida el protocolo.
- **Un solo uso por versión de protocolo.** El conjunto se renueva generando instancias nuevas de la misma distribución, en vez de reutilizar las gastadas. No se mezclan resultados de versiones de protocolo distintas.
- **Revisión L5 ciega:** el revisor no sabe qué combinación produjo cada salida.

### 6.4 Condiciones iguales para toda combinación

- Mismos bytes de entrada.
- Unidades explícitas (INSUNITS) y hash de `capabilities`.
- Mismos límites: `wait_seconds`, pasos, presupuesto de tokens y de pared, número de capturas.
- Mismos gates, fijados antes: 1e-6 para identidad geométrica y 0.001 m para medidas vinculadas.
- Mismo procedimiento de revisión.
- Estado de arranque declarado:
  - siempre frío, **o**
  - siempre caliente, con una corrida de calentamiento descartada **y registrada**.

### 6.5 Diseño intercalado

- **Bloques aleatorizados.** Cada bloque es una instancia de tarea ejecutada por todas las combinaciones, en orden aleatorio.
- **Reparto en el tiempo.** Los bloques se reparten en días y franjas horarias distintas, en la misma máquina, para absorber la variación de carga del proveedor.
- **Reglas fijadas antes de empezar:** parada y criterios de corrida inválida (solo fallos de infraestructura). Las inválidas también se reportan.

### 6.6 Registro por corrida

- **Resultado:** `éxito | fallo | abstención | inválida`.
- **Correcciones:** autocorrecciones del agente.
- **Reintentos:** de herramienta y de modelo.
- **Intervenciones humanas:** tipo y duración.
- **Coste hasta la aceptación:** incluye los intentos fallidos.
- **Clasificación de causa de cada fallo**, con árbol decidido de antemano:
  1. ¿El programa soporta la operación? (capacidad y prueba unitaria)
  2. ¿El MCP informó bien? (respuesta contra censo)
  3. ¿El harness eligió bien con la información que tenía? (traza)
  4. ¿El modelo interpretó bien? (plan contra oráculo)

  Si los registros no permiten decidir, la causa es **desconocida**. Una muestra se codifica por dos revisores y se reporta su concordancia (kappa de Cohen).

### 6.7 Niveles de evidencia en ejes separados

**Eje «verificador»:**

- **P:** protocolo (L0/L1, par falso);
- **I:** persistencia interna (L2: el mismo motor reabre y compara **propiedades**);
- **X:** CAD externo (L4, con motor, versión y hash);
- **H:** revisión humana (L5 ciega: quién, qué, revisión, fecha).

**Eje «tarea»:** T1–T5.

Cada gate reporta el nivel más alto alcanzado. Nunca se promueve un nivel: un P no sustituye a un I.

### 6.8 Tamaño de muestra y análisis

**Variable primaria:** éxito de la tarea con los gates congelados (binaria).
**Secundarias:** coste hasta la aceptación, pared, tokens, llamadas, bytes y capturas.

**Intervalos de Wilson (95 %)**

| Observado | Intervalo |
|---|---|
| 3/3 | [0.44, 1.00] |
| 1/3 | [0.06, 0.79] |
| 10/10 | [0.72, 1.00] |
| 27/30 | [0.74, 0.97] |
| 15/30 | [0.33, 0.67] |
| 90/100 | [0.83, 0.94] |

**Descriptivo por combinación:** ≥ 30 corridas (p. ej. 10 tareas × 3 repeticiones) dan ±11–17 puntos. Por debajo de eso, solo se describe.

**Comparación pareada por instancia**, con McNemar o regresión logística con efecto aleatorio por tarea (α = 0.05 bilateral, potencia 0.80):

- Para detectar 20 puntos (p. ej. 70 % frente a 90 %): **≈ 45–65 pares**, según cuán correlacionadas estén las combinaciones.
- Para detectar 10 puntos: **≈ 140–200 pares**.

**Tiempo y tokens:** en escala logarítmica, con diferencias pareadas. Con una desviación de la diferencia de ~0.35:

- un cambio del 20 % necesita **≈ 19 pares**;
- uno del 10 %, **≈ 87**.

Se reporta la mediana y un bootstrap al 95 % **por tareas**, no por corridas.

**Procedimiento:**

1. Piloto de 3 repeticiones por tarea para estimar la varianza y la discordancia.
2. Cálculo de n.
3. Corrida confirmatoria.

**Reglas:**

- Comparación primaria prerregistrada; Holm para las secundarias.
- Nunca se declara ganador con 1–2 corridas, ni sin intervalo que excluya la diferencia nula **y** supere un umbral práctico acordado.
- Siempre se muestra el resultado por tarea, además del agregado.

### 6.9 Límites del protocolo

- **Coste:** a la escala de E2 (~4 M tokens de entrada por corrida), 60 corridas por brazo son caras. La suite comparativa debe usar tareas sintéticas de 5–10 min; las «casas completas» quedan como estudios de caso descriptivos.
- **Identidad:** sin recibo del proveedor (B05), el eje «modelo» sigue siendo «modelo solicitado».
- **Validez externa:** los resultados valen para esta build, estos harnesses y esta máquina.
- **Oráculos:** los generados por el asistente no sirven para la reserva.

---

## 7. Plan de instrumentación

### 7.1 Relojes y fases

Todo con reloj monotónico, más un UTC de anclaje por corrida.

| Capa | Dónde | Qué registrar |
|---|---|---|
| Modelo | Harness | Por respuesta: `response_id`, inicio y fin, modelo efectivo, uso con subconjuntos, motivo de parada; fase activa del harness al pedirla |
| Harness | Harness | Intervalos por fase: plan, lectura, compilación, ejecución, QA, guardado, captura, informe. Subprocesos y helpers con su tiempo. Espera humana (`waiting_user`) como intervalo aparte |
| Transporte (cliente) | `mcp_client.py`, con la traza encendida por defecto en corridas de evaluación | Por RPC: método, herramienta, operación, hash de `request_id`, bytes de ida y vuelta, inicio y fin, estado, número de sondeos |
| Servidor MCP (nuevo) | `src/mcp.rs` | Por llamada: recepción, número de intercambios con la GUI y su conexión, escritura, primer byte y EOF; sondeos y sueño acumulado; persistencias del journal (número, bytes, tiempo). Se devuelve en `result._meta["io.opencadstudio/timings"]` y opcionalmente en una traza JSONL con `run_id` recibido por `_meta` |
| Transporte GUI (nuevo) | `transport.rs` | `accepted_at`, `enqueued_at`, `dequeued_at` → `queue_ms`; tiempo de escritura de la respuesta |
| GUI | `control/mod.rs` | El `timings.total_ms` existente, más `settle_ms`, `state_build_ms` y `serialize_ms` |
| Operaciones | `automation.rs` | `query`: recorrido, filtro, serialización. `save_verified`: ya lo tiene. Captura: espera de fotograma, lectura, recorte, escala, codificación, escritura |
| Arranque | `main.rs`, `app` | Inicio, GPU, plugins, descriptor escrito, primer `hello` |

**Reconciliación:** unión de intervalos, no suma. Se reporta «sin atribuir» explícitamente; nunca se reparte a ojo.

### 7.2 Tokens y coste

- Uso por `response_id`, deduplicado. Ausente = `null`, con fracción de cobertura.
- Los tokens de imagen se reportan aparte (medidos o estimados con la fórmula documentada del proveedor, marcados «estimado»).
- Coste monetario solo con una tabla de precios fechada; sin factura, `null`.

### 7.3 Sin inflar tokens

- La telemetría nunca va en el texto que ve el modelo: va en `_meta` o en archivos de traza. El harness resume al cierre, fuera del contexto de trabajo.
- Corregir la duplicación de `tool_result`: texto compacto más `structuredContent` completo (M8).
- Capturas por referencia (ruta, hash y dimensiones) cuando el cliente lo admita; base64 solo cuando haga falta verla.

### 7.4 Sin omitir fallos

- **Intención antes, resultado después.** Registro de intención antes de cada llamada y de resultado después, en un JSONL solo-anexar con sincronización. Una intención sin resultado es un fallo o una incertidumbre, nunca un hueco.
- **Resumen derivado de la traza, no de la narración.** Conteos de éxito, fallo, abstención, reintento y corrección; las ranuras `uncertain` conservan el uso que haya.
- **Consistencia de totales.** Toda corrida cierra con una suma que cuadre contra los totales del proveedor o del hilo. La discrepancia se reporta, no se corrige.

---

## 8. No verificado y pruebas mínimas que lo cerrarían

| Incertidumbre | Por qué no se verificó | Prueba mínima | Requiere |
|---|---|---|---|
| Cifras de E1–E3 (184/5, 25 INSERT, tokens, tiempos) | Recibos no versionados; regla de usar solo evidencia del repo | Rehacer hashes de los 22 recibos no-dibujo contra el índice y derivar agregados saneados | Autorización para leer esos recibos |
| Revisión fijada del codec (`cdf2277`) | No está en la caché local | Leer `insert.rs` en esa revisión (fuente en GitHub o `cargo fetch --locked` en un `CARGO_HOME` desechable) | Lectura de red |
| Hash y perfil del EXE instalado | Fuera de lo autorizado | `Get-FileHash` y `OpenCADStudio --version` (imprime el perfil) | Autorización para leer la ruta de instalación |
| Binario usado en las series y en E2/E3 | En recibos no leídos | Leer el campo binario de `series.json` y `RUN-CONTRACT.json` | Idem a la primera fila |
| Duplicación por revisión implícita (M1) | Sin ejecución | L2 sintético con proxy que pierde la respuesta; seguir los pasos 1–6; contar entidades | GUI aislada |
| Carrera de 15 s contra 15 s (M2) | Sin ejecución | Operación retrasada 16 s por gancho de prueba; 20 intentos; distribución del tipo de error | Build de prueba |
| `operation` que muta lotes (M3) | Sin ejecución | L1 con par falso que cuenta mutaciones durante `ocs_read operation` | Ninguno (sin CAD) |
| Segunda GUI en descubrimiento (M9) | Sin ejecución | `save_verified` de un dibujo sintético grande y `ocs_sessions` simultáneo; contar procesos | GUI aislada |
| `changes:null` tras `block_define` (P4) | Sin ejecución | L2 sintético | GUI aislada |
| Bounds de INSERT con rotación, escala y anidación (P1) | Sin ejecución | L2 sintético (§3.1) | GUI aislada |
| Depuración frente a release (H3) | Sin ejecución | 10 corridas intercaladas de cada perfil con `synthetic-room` | Dos builds |
| Coste del journal (M7) | Sin ejecución | Micro-benchmark de `persist_batch` con N = 8…256 en release, con y sin exclusión del antivirus | Build release |
| Nagle y ACK retardado | Sin ejecución | Histograma de RTT de `state`; A/B escribiendo con búfer | Build de prueba |
| Upstream actual (`ab068215`) | No descargado | `fetch` autorizado y diff de `src/mcp.rs` y `src/app/control/` | Autorización de red |
| Identidad efectiva del modelo | Sin llamadas a modelos | Primera corrida autorizada por API directa, con recibo | Autorización y cuota |
| Coste en tokens de la respuesta duplicada (M8) | Sin tokenizador del cliente | Contar tokens de respuestas de muestra con el contador del proveedor | Posible llamada a API |
| Handles estables tras guardar y abrir (A28) | `save_verified` no lo compara | L2: huella por handle antes y después de reabrir, en DWG 2000/2013/2018 | GUI aislada |

---

## 9. Dictamen

**Se puede estandarizar ya**, porque es neutral respecto al proveedor:

- **Contrato de mutación:** `request_id` y `revision` obligatorios; recuperación solo por `operation`; nunca reenviar con otro ID.
- **Estados:** `accepted`, `running`, `waiting_input`, `waiting_user`, `completed`, `failed`, `cancelled`.
- **Fallos:** `unknown_operation` como incertidumbre que bloquea escrituras.
- **Captura:** cercada por revisión.
- **Sesiones:** cierre con propiedad.
- **`run_script`:** estricto.
- **Fixtures:** sintéticos, con el conjunto reservado ya custodiado.
- **Niveles de evidencia:** en dos ejes.
- **Formato de traza por fase y reglas de conteo:** subconjuntos; ausente ≠ 0.
- **Diseño intercalado de comparación.**

Primero hay que corregir B01–B04 para que el contrato valga igual para cualquier cliente.

**Debe seguir siendo específico de cada proveedor o cliente:**

- el adaptador de identidad y uso (forma de la respuesta, campos de caché y razonamiento, IDs con fecha);
- la contabilidad de tokens de imagen y los precios;
- la configuración de esfuerzo y razonamiento;
- lo que admita cada cliente MCP: Tasks, `structuredContent` frente a `content`, enlaces a recursos, cancelación, tratamiento de `readOnlyHint` en permisos;
- los límites de contexto y la caché de prompts;
- las opciones de cada CLI.

**Afirmaciones que aún no están respaldadas:**

- que un modelo o harness sea mejor o más rápido que otro;
- que V2 fuera más eficiente que V1 *por método*;
- que el MCP sea «atómico» o «idempotente» sin calificativos;
- que `save_verified` pruebe preservación geométrica;
- que la QA espacial de mobiliario funcione;
- que el cuello de botella esté en el kernel CAD;
- que el flujo imagen→CAD alcance fidelidad;
- que «correr como mantequilla» se logre optimizando el servidor, cuando ~95 % del tiempo está fuera de él.

---

## Anexo A · Constantes que conviene conocer

| Constante | Valor | Dónde |
|---|---|---|
| Solicitud máxima MCP→GUI | 1 MiB | `src/mcp.rs:25`; `transport.rs:113-114` |
| Respuesta máxima | 16 MiB | `src/mcp.rs:26` |
| E/S por intercambio en el MCP | 15 s | `src/mcp.rs:769` |
| Respuesta de la GUI | 15 s → `response_timeout` | `transport.rs:130` |
| Sondeo de `operation` | 50 ms | `src/mcp.rs:779` |
| Espera por llamada | por defecto 30 s, máximo 60 s | `src/mcp.rs:771`, `1662` |
| Descubrimiento | 16 hilos, 250 ms por descriptor | `src/mcp.rs:530`, `556` |
| Handshake de la sesión elegida | 2 s | `src/mcp.rs:610` |
| Arranque de la GUI | plazo 90 s, reintento cada 200 ms | `src/mcp.rs:665-685` |
| Conexiones simultáneas a la GUI | 8 (las demás se cierran) | `transport.rs:98` |
| Cola de la GUI | 32 | `transport.rs:60` |
| Latido | 2 s | `transport.rs:34` |
| Caché de resultados | 128 operaciones | `control/mod.rs:1290` |
| Anillo de eventos | 128 | `control/mod.rs:1284` |
| `changes` | 1000 | `control/mod.rs:1272` |
| Anillo de deltas geométricos | 256 | `src/scene/mod.rs:1000` |
| Lote | 64 pasos | `src/mcp.rs:136` |
| `run_script` | 256 órdenes × 4096 B; 256 KiB en total | `src/mcp.rs:137-139` |
| Journal | 16 MiB | `src/mcp.rs:199` |
| `query limit` | por defecto 1000, máximo 10 000 | `src/app/automation.rs:983` |
| Captura | 256–4096 px (por defecto 1600); cerco 8 s; 2 fotogramas limpios | `src/mcp.rs:1676`; `control/mod.rs:1364`, `1394` |
| Tareas MCP | ttl anunciado de 1 h, sin caducidad aplicada | `src/mcp.rs:2028`, `327-339` |

## Anexo B · Atribución fork/upstream (contra `60f35e2b`)

- **Heredado (igual en ambos):**
  - relleno de `revision` (M1);
  - etiqueta `invalid_arguments` (M2);
  - bucle monohilo y `tasks/cancel` vacío (M5);
  - 15 s a ambos lados;
  - caché de 128;
  - heurística de `failed`;
  - corte de `changes` en 1000;
  - manifiesto por conteos (P3).
- **Propio del fork:**
  - journal (M7);
  - `ocs_read operation` que reanuda (M3);
  - cierre y cierre de documento con propiedad;
  - cerco de captura;
  - ediciones de muro;
  - impresión métrica;
  - `run_script`.
- **Operaciones:** el fork no pierde ninguna del upstream; añade 7 de ejecución y 1 de lectura.

(†) Localizado por barrido delegado y verificado solo de forma puntual. Todo hallazgo de severidad Media o superior se verificó línea a línea.

## Adenda 2026-09-30 (posterior a la auditoría)

**A02 (binario instalado)** sigue parcial, con dato nuevo:

- La v2026.40.1 no está en la ruta de instalación del fork (`%LOCALAPPDATA%\Programs\OpenCADStudio Fork`).
- La aplicación instalada en `%LOCALAPPDATA%\Programs\Open CAD Studio` es v2026.38: release, revisión `0d023d26`.
- En los worktrees solo hay binarios de depuración o anteriores al código auditado. El más cercano es un artefacto de CI en depuración (`09794ab6`).

No hay evidencia local de un binario compilado del código auditado, así que B19 gana prioridad. Detalle en [M4-CONTRATO-HUMANO-AGENTE-V1](M4-CONTRATO-HUMANO-AGENTE-V1.md).

## Erratas 2026-09-30 (tras la auditoría de Codex)

Codex contrastó cinco hallazgos de esta auditoría con el código. Confirmó la revisión implícita (M1) y la lectura que reanuda lotes (M3), y señaló tres exageraciones de redacción, corregidas en el texto:

1. **M2 y resumen.** Decía «todo error posterior al envío». Correcto: todo error que el servidor **propaga como `Err`**; las respuestas de la GUI que llegan como valor conservan su código.
2. **A04 y resumen (D01).** Decía «confirmada» sin salvedad. Correcto: la ausencia de tratamiento de INSERT en la aplicación está confirmada; el colapso al punto se leyó en una revisión cercana del codec, no en la fijada.
3. **Resumen (`save_verified`).** Decía que «compara solo conteos». Correcto: su comparación semántica es de conteos, y además comprueba reapertura y versión.

Los hallazgos, sus severidades y el backlog no cambian.
