# Plan de estabilización: modelo, MCP + harness y programa

**Fecha:** 2026-09-30 · **Autor:** Claude (Opus 5.5) con Luis
**Base:** auditoría independiente [07-AUDITORIA-INDEPENDIENTE-MCP-20260930.md](07-AUDITORIA-INDEPENDIENTE-MCP-20260930.md) sobre `d0d88409`, cuyo código es el de `26bce00a`

**Estado: propuesta (doctrina), no resultado verificado.**

- Los hechos que la sustentan están en la auditoría 07; los identificadores B01–B22 y A01–A30 remiten a ella.
- R01–R19 remiten al [informe maestro 06](06-INFORME-MAESTRO-Y-MEJORAS-20260929.md).
- Las sesiones son estimados, no compromisos.
- Sin push.

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

| Fase | Qué | Sesiones | Modelo | Sale cuando |
|---|---|---|---|---|
| 0 | Higiene: commit local de 07 y 08 (si se aprueba), `AGENTS.md` sin contradicción, release por defecto y perfil en recibos, spec = código | 1 | Sonnet (Haiku para el barrido de docs) | Una prueba confirma que spec y listas de operaciones coinciden; las series rechazan binarios de depuración |
| 1 | Contrato MCP P0 + suite T4 mínima | 2–3 | Sonnet; Opus revisa la taxonomía | T4 con 0 duplicados en 50 corridas sintéticas |
| 2 | Corrección del dominio (B06–B10) | 2–3 | Sonnet | Fixtures en verde: bounds, capas, guardado por propiedades y handles |
| 3 | Instrumentación y recibos | 1–2 | Sonnet | ≥ 95 % del tiempo de pared atribuido o marcado; lo ausente queda `null` |
| 4a | Contrato humano–agente (§3): vista legible, registro de aprobación, ejecutor que exige hash aprobado | 1–2 | Sonnet con esta receta | Un plan no aprobado no abre la GUI; uno aprobado se ejecuta y se verifica contra su contrato |
| 4b | Identidad ARQ en el DWG + patch v1 + compilador único | 1 de diseño + 2–4 | Opus diseña, Sonnet ejecuta | Una sesión nueva reconstruye el contexto desde el DWG y aplica los 3 patches sin tocar nada más |
| 5 | Suite canaria + línea base del modelo actual | 1–2 | Sonnet; requiere cuota | Línea base con intervalos y regla escrita para aceptar un cambio de modelo |
| 6 | Rendimiento medido, orquestación en el despachador (decisión), comparación de modelos (§6 de la auditoría 07), L5, imagen→CAD | abierto | según tarea | Cada mejora con su antes y después en release |

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

## 11. Avance

- **2026-09-30 · Fase 4a.** Implementados `plan_contract.py` y la puerta en `m8_case_cli.py`.
  - Verificado en L0/L1: masterplan 220/220, automatización 59/59.
  - Detalle: [M4-CONTRATO-HUMANO-AGENTE-V1](M4-CONTRATO-HUMANO-AGENTE-V1.md).
- **2026-09-30 · Fase 4a, L2 acotado.** Primera aprobación humana real (registro `9B8AADB7…`).
  - Un plan sin aprobar no abrió la GUI.
  - El aprobado se ejecutó y se verificó con `human_approval: rechecked`.
  - Binario: artefacto de CI en depuración `09794ab6`, que no es el código auditado. Repetirlo con release (B19).
  - **Criterio de salida de la 4a cumplido en su alcance.**
