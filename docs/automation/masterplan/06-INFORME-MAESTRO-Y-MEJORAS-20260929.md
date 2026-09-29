# Informe maestro MCP: evidencia, eficiencia y mejoras pendientes

Corte: 2026-09-29 UTC. **Producto parcial: capacidades útiles demostradas; fidelidad integral y eficiencia sostenida sin aceptación global.** Este informe reúne M0–M8 y las evaluaciones recientes, conserva los fallos y sirve como entrada para cualquier agente.

> **Versión redactada para publicación (2026-10-01).** Se retiraron las rutas personales del equipo, un identificador de proceso, el programa y las dimensiones de los casos de evaluación E1–E3 y los nombres, rutas y hashes de sus entregables. Las métricas agregadas no cambian; el índice completo de evidencia queda solo en la copia local privada. La instrucción «NO PUSH» de abajo es la del 29-sep; publicar esta versión exige el protocolo vigente de `AGENTS.md`.

**Instrucción vigente de Luis: documentar y guardar; commit local permitido; NO PUSH.** Las autorizaciones históricas de publicación no autorizan publicar este trabajo. Este cierre no modifica el servidor ni ejecuta evaluaciones nuevas. No necesita merge: se incorpora en la rama operativa existente.

## 1. Estado y autoridad

- Fork `lalomalvi/OpenCADStudio`; upstream `HakanSeven12/OpenCADStudio`, fuente de lectura.
- Operativo: worktree local `desktop-distribution`, rama `codex/windows-web-dxf`; HEAD previo `26bce00ab883b86c6f0e3b0edb3075d65b9062aa`.
- Windows instalado v2026.40.1, productor `196b1b7c554a17299fd546850614db4bfc77de7a`; SHA256 EXE `59F3E4305A594CE6F2BEE6031478BB65719450296943D1EB9EF1906E90D7CB56`. El commit documental no cambia su procedencia.
- Original: checkout local del escritorio, rama `feat/audited-mcp-save`, HEAD `0fa6f0083bc14aa5d2efe9790597b17d9e49f87f`. Tiene cambios históricos y CAD privado: no resetear, limpiar, abrir ni incorporar esos archivos.
- Git local/documentos revisados; sin actualización remota por red en este cierre. La publicación se cita desde recibos históricos.
- V2 dejó GUI propia abierta para revisión. Verificar inicio/binario/propiedad actuales antes de cualquier control; un PID antiguo nunca autoriza cerrar un proceso.

La autoridad geométrica es el CAD consultado en documento/revisión actuales. Contexto semántico, captura y memoria ayudan, pero no sustituyen esa lectura. Un archivo existente tampoco equivale a gate aprobado.

Fuentes: [evaluación conversacional](../evaluations/20260929-CAD-CONTEXTO-Y-SEGUNDA-ITERACION.md), [backlog M0–M8](03-FASES-Y-BACKLOG.md), [checkpoint](05-CHECKPOINT-Y-CONTINUACION.md), [cierre anterior](../CIERRE-SESION-20260928.md), [distribución](../../install/public-distribution-audit-20260928.md), [API](../API-SPEC.md), [cliente](../mcp_client.md).

## 2. Áreas que ya funcionan

| Área | Evidencia positiva | Límite |
|---|---|---|
| Transporte | Cliente persistente, handshake/readiness, correlación, plazos, journal y consulta de operación; M1 L1/L2 | Recuperación de GUI nueva/resultado multiproceso parcial |
| Sesiones | Discovery, identidad/ACL, aislamiento y cierre con propiedad comprobada | No cubre todos los modales/caídas |
| Construcción MCP | Muros, vanos, hatches, cotas, bloques originales y persistencia en los casos E2/E3 | Diseño conceptual, sin aceptación normativa ni de imagen |
| Edición localizada | V2 preserva 184 geometrías/capas y transforma cinco entidades originales; seis cambios comprobados | Contexto/selectores siguen como prototipo local |
| Reutilización | V1 trece bloques y 25 referencias; V2 transforma y reutiliza referencias existentes | Bounds/capa de INSERT pendientes; biblioteca externa no probada |
| Persistencia | Auditoría, save_verified, reapertura y capturas nativas en V1/V2 | No equivale a interoperabilidad externa |
| Contratos/QA | PlanSpec, grafo de cotas, puertas/ventanas tipadas, captura por revisión, negativos | Casos acotados, no semántica/topología universal |
| Distribución | v2026.40.1 publicada; Windows probado, Mac ARM/Intel en CI; checks por delta | Mac físico, mínimos SO y firma confiable separados de M7 |

Las cuatro herramientas MCP y muchas operaciones CAD pertenecen al proyecto compartido; no atribuir todo el catálogo al fork. Este aporta endurecimiento, custodia/recuperación, contratos, evaluación y automatización documentados. Una comparación exhaustiva actualizada con upstream requiere otro corte Git; aquí no se inventan exclusividades.

## 3. Evaluaciones conservadas

### E0 — Baseline histórico, septiembre 23

[Baseline](01-BASELINE-Y-CORRECCIONES.md): 84 respuestas, 9,797,952 tokens, 280 comandos exitosos, 273 entidades en capa 0. Tiempo activo aproximado 31 min 22 s, pared 32 min 25 s. Capturas: aproximadamente 86% de bytes del log, no de tokens. Persistencia interna aprobada; semántica/fidelidad parcial. No es comparable directamente con una sola llamada Luna ni con una modificación localizada.

### E1 — Imagen difícil, todo lo visible

Una llamada solicitada a Luna medium; fuente 168×300 px y solo cotas exteriores. 86 primitivas: 38 LINE, 26 POLYLINE, cinco ARC, cinco CIRCLE, dos DIMENSION, diez TEXT. Calibración y algunos límites ambiguos; no hay medidas interiores exactas.

**Fidelidad no aceptada:** particiones y recintos interiores, espesores, escaleras, radios de puertas y mobiliario deficientes. Inventario declarado no equivale a geometría correcta. No asignar porcentaje global sin oráculo independiente.

JSON estricto falló por `closed` duplicada en `stair_tread_5`. Recuperación explícita solo de representación idéntica; no corrección geométrica ni nueva llamada. Presentación v2 aplicó un perfil métrico existente omitido por el helper; no es otra generación aceptada. Persisten limitaciones de composición de rótulos/cotas.

Guardado/reapertura/auditoría internos y apertura/censo/AUDIT originales AutoCAD pasaron en su alcance. Comparación 83/86 a 1e-6: tres radios limitados por seis cifras significativas; compatibles con redondeo, pero sin aprobar tolerancia ni relajarla. Negativo de LINE desplazada rechazado.

Sonda adicional de precisión reescribió su entrada al salir: **invalidada**. Archivo modificado conservado; original restaurado de `.bak` con hash idéntico. No invalida la sonda externa original independiente. Futura sonda: copia desechable y hashes pre/post obligatorios.

### E2 — Diseño propio SOL V1

Sin imagen, biblioteca externa ni delegación: geometría exclusivamente por MCP. Programa arquitectónico omitido en la versión redactada para publicación. 303 entidades Model; 435 serializadas incluyendo definiciones/cotas: denominadores diferentes.

Verificados nueve bisagras/radios/barridos de 90°, doce medidas de cota, trece símbolos, cuadro de áreas, save_verified, reapertura y auditoría sin incidencias. Captura nativa permitió detectar/corregir rótulos seleccionados incorrectamente; fallos anteriores conservados.

Defectos observados: 25 referencias con bounds colapsados en inserción y consulta dentro de un símbolo de mueble devuelve cero; primeras trece referencias block_define en capa 0. Causa interna y contrato de capa por investigar. No aceptar QA espacial de muebles usando esta consulta.

### E3 — Modificación SOL V2, con ampliación

Se verificaron seis cambios localizados; el detalle del programa se omite en la versión redactada para publicación:

1. Acceso nuevo, cierre del anterior y ajuste de una ventana.
2. Redistribución de un recinto mediante cinco transformaciones que conservan handles.
3. Una puerta eliminada y su vano cerrado.
4. Una ventana eliminada y su vano cerrado.
5. Un recinto sustituido por otro de distinto uso.
6. Ampliación exterior con elementos nuevos; el cuadro de áreas no cuenta dos veces las superficies anidadas.

303→384 entidades Model; 189 handles conservados = 184 sin cambio geométrico/de capa a 1e-6 + cinco transformados. 114 eliminadas y 195 nuevas incluyen lámina/anotaciones. 521 serializadas; 26 referencias, siete arcos y doce cotas.

V1 intacta; auditoría/guardado/reapertura internos aprobados; capturas general y de detalle revisadas. V2 sin rechazo de mutación, reintento oculto ni corrección geométrica tras primer plan ejecutado. Persisten bounds/capa, colisiones completas y prueba externa. No acredita normativa, estructura, instalaciones ni diseño técnico de los elementos añadidos.

## 4. Tiempos, tokens y eficiencia

[Datos sanitizados y conteos de evidencia](06-METRICAS-Y-EVIDENCIAS-20260929.json). V1/V2 usan deltas `token_count` del hilo; `turn_context` registra `gpt-6-sol`. No se atribuye recibo directo del proveedor más allá de esa observación.

| Indicador | E2 crear V1 | E3 modificar V2 |
|---|---:|---:|
| Entrada | 4,070,859 | 2,761,216 |
| Cache incluida en entrada | 3,885,824 | 2,603,008 |
| Entrada no cacheada | 185,035 | 158,208 |
| Salida | 32,006 | 26,443 |
| Razonamiento incluido en salida | 10,891 | 10,495 |
| Total entrada + salida | 4,102,865 | 2,787,659 |
| Cache / entrada | 95.45% | 94.27% |
| Pared hasta corte | 1,230.681 s (20 min 31 s) | 921.624 s (15 min 22 s) |
| Suma serial llamadas herramientas MCP | 55.726305 s | 29.860522 s |
| RPC incluyendo negociación | 150 | 58 |
| Llamadas herramientas MCP | 142 | 55 |
| Mutaciones completadas | 59 | 26 |
| Tiempo cliente mutaciones | 48.474996 s | 25.758028 s |
| Comandos strict | 430 | 218 |
| Tiempo cliente scripts strict | 46.865433 s | 24.694737 s |
| Comandos strict / s | 9.18 | 8.83 |
| Ventana primera–última RPC, con intervalos | 820.432994 s | 430.250908 s |

V1 inicio `2026-09-29T06:44:49.350Z`, corte `07:05:20.031Z`; V2 inicio `07:13:47.587Z`, corte `07:29:09.211Z`. V2 excluye cierre posterior/respuesta final. Este informe no se suma a V2.

E1: recibo `model-result.json` **135.83 s**; 16,629 entrada (11,008 cache), 7,352 salida, 23,981 total. Resumen anterior dice 135.84 s: discrepancia de 0.01 s conservada, prevalece dato estructurado. Excluye evaluador/herramientas. Luna solicitado; efectivo `unverified_by_cli`; costo facturado desconocido.

- Entrada repetida se cuenta por respuesta; no son millones de palabras nuevas. Cache y razonamiento son subconjuntos, no sumandos adicionales.
- RPC incluye transporte/GUI, no CPU pura. Pared menos MCP incluye preparación, helpers, archivos, revisión y esperas; no mide por sí solo razonamiento o desperdicio.
- Suma MCP/pared: aproximadamente 4.53% V1 y 3.24% V2. Orienta investigación; no demuestra ahorro posible. Falta atribuir tiempo por fase.
- Crear y modificar son cargas distintas. Menos tiempo/tokens/llamadas en V2 no prueba aceleración causal. Nueve comandos/s no es un límite universal.
- Uso local no equivale a factura, tarifa ni saldo del plan. No inventar costo monetario.

## 5. Incidentes: separar causa y estado

| ID | Observación y capa | Estado / siguiente acción |
|---|---|---|
| D01 | Producto: bounds INSERT degenerados/falso negativo | Confirmado E2, causa interna por investigar; R01 |
| D02 | Producto/contrato: primera referencia en capa 0 | Observado E2/E3; R02 antes de cambiar API |
| D03 | Helper: op summary inexistente | Llamada corregida; falta prevención reutilizable R03 |
| D04 | Helper Windows: nombres distintos solo por mayúsculas | Colisión acciones/metadatos corregida localmente; R03 |
| D05 | Helper: selección solo por texto editó fila de áreas | Corregido con posición/rol; prevención general R03/R04 |
| D06 | Helper: espacios TEXT normalizados | Precondición corregida; conservar identidad/posición R03 |
| D07 | Modelo: JSON con clave duplicada | Estricto fallido, salvage explícito solo representación; R08 |
| D08 | Interpretación imagen/topología deficiente | Confirmada; causas no aisladas, oráculo incompleto; R08/R09/R15 |
| D09 | Presentación: perfil métrico omitido | Helper corregido en v2, no nuevo arreglo del motor; R10 |
| D10 | Censo externo: precisión de tres radios insuficiente | Parcial, no prueba desviación ni aprueba; R11 |
| D11 | Sonda externa reescribió entrada | Ensayo invalidado/original recuperado, custodia R11 |
| D12 | Orquestación: helpers extensos y lecturas reiteradas | Oportunidad observada, ahorro sin demostrar; R04–R07/R14 |
| D13 | Identidad/uso directo CLI incompleto | Metadatos locales disponibles, recibo directo pendiente; R13 |
| D14 | Histórico: runner debug sin locales | Corregido con recursos incrustados, fallo preservado en corte 159 |
| D15 | Histórico: crash git-remote-https | Causa desconocida; HTTPS posterior no prueba reparación; R19 |
| D16 | Distribución: primer deploy tag rechazado | Corregido habilitando solo v2026.40.1 y repitiendo deploy; R18 |
| D17 | Este informe: comando de escritura excedió límite Windows (error 206) | No se creó proceso ni escribió archivo; guardar en partes, evitar payload gigante |

Fallos del helper corregidos en un ensayo no equivalen a defensa reutilizable. Negativos deliberados no son fallos de usuario. Defectos históricos resueltos no se reclasifican como vigentes sin evidencia de regresión.

## 6. Backlog ejecutable unificado

P0 protege identidad/custodia; P1 corrige exactitud y trabajo manual; P2 optimiza/generaliza con medición. Responsable: agente ejecutor; Luis define alcance/aceptación humana. Cada cierre registra commit, entorno/binario, positivos/negativos, evidencia y límites. Documentación sola no cambia a aprobado.

### R01 — Bounds y consultas de bloques [P1, abierto, M5/M6]

Investigar cálculo desde definición/transformación, índice espacial y caché, sin asumir causa. Casos: rotación, escala no uniforme, traslación, anidación, definición vacía/cíclica y recarga. **Aceptación:** ventana dentro del símbolo devuelve su handle; fuera no; límites correctos tras transformar y guardar/reabrir. Negativo lejano no colisiona. Depende de reproducción mínima propia E2; no convertir todo el caso en test unitario.

### R02 — Capa de referencia/contenido [P1, abierto, M5]

Precisar contrato block_define frente a INSERT, capa activa/0, ByLayer/ByBlock y contenido heterogéneo. Separar comportamiento intencional y defecto. **Aceptación:** primera y siguientes referencias respetan contrato explícito, por handle y tras reapertura; visibilidad de capa coherente sin mover contenido ajeno. No normalizar automáticamente destruyendo semántica de biblioteca.

### R03 — Adaptador y selectores seguros [P1, parcial local, M1/M4]

Funciones tipadas sobre capabilities del build; selector por rol+tipo+Model+geometría y cardinalidad exacta. Separar archivos de acciones/metadatos y detectar equivalencias de ruta Windows. Normalizar TEXT según contrato. **Aceptación:** rótulo duplicado, selector ambiguo, operación inexistente, ruta equivalente y revisión obsoleta fallan antes de mutar, con diagnóstico concreto. Reutilizar mcp_client.py; no otro transporte ad hoc.

### R04 — Contexto persistente y patch semántico [P1, prototipo, M4/M8]

Convertir owned-cad-context-1/CHANGE-PLAN locales en esquema versionado/validado: hash, unidades, documento/revisión, recintos/grupos, dependencias, ID semántico→handles, fingerprints y procedencia. Compilar pedidos como trasladar acceso o mover mueble a un diff previo. **Aceptación:** nueva sesión recupera contexto, detecta edición manual/archivo viejo y resuelve handles tras copia/reapertura; cambio en un recinto preserva otras zonas y actualiza cotas/áreas/rótulos dependientes. Handle no es global ni eterno. Depende R03; R01 para selección espacial confiable.

### R05 — Recuperación GUI y resultado multiproceso [P0, parcial, M1/M2]

Completar journal/resultado durable compartido y conciliación de GUI nueva. Partir de [dos clientes](M1-DOS-CLIENTES-MISMO-ID-V1.md) y [pérdida GUI](M1-PERDIDA-GUI-SINTETICA-V1.md), respetando límites de sus pruebas. **Aceptación:** dos clientes/mismo ID producen un efecto; caída antes/durante/después de respuesta devuelve estado verificable o incertidumbre que bloquea writes, nunca replay automático. Definir retención/expiración por documento. Journal local no es lock distribuido.

### R06 — Lecturas compactas y conexión persistente [P2, propuesto, M1/M3]

Reutilizar conexión/capabilities con caché ligado a build/version/configuración; consultas proyectadas por handles/campos y deltas/paginación cuando proceda. **Aceptación:** mismo cambio/gates con menos bytes/tokens medidos, sin perder elementos entre páginas ni usar caché obsoleta. Medir frío/caliente separados. Depende R03/R04; no omitir identidad para ahorrar una llamada.

### R07 — Lotes y overhead de ejecución [P2, propuesto, M1/M4/M5]

Agrupar transformaciones compatibles y medir refresco/render/overhead por comando antes de optimizar. Script strict secuencial no equivale a transacción atómica: conservar índice/progreso y ejecución parcial. **Aceptación:** orden, handles, errores intermedios y reapertura equivalentes al control; timeout se consulta con ID original. Depende R05/R13; lote mayor no debe perder recuperabilidad.

### R08 — PlanSpec e interpretación integral [P1, parcial, M4/M7]

Inventario fuente→elemento→geometría, incertidumbre de escala/cotas, abstenciones y JSON estricto. Extender puertas v10, ventanas v11 y grafo dimensional existentes a uniones/espesores/vanos/recintos y orientaciones. **Aceptación:** claves duplicadas/referencias incoherentes rechazadas; cada elemento visible representado o ausencia justificada; inventario/topología contra oráculo congelado. El generador no certifica fidelidad de su propia salida. E1 sigue fallido aunque su DWG sea válido.

### R09 — Biblioteca CAD paramétrica [P2, pendiente, M5.6]

Camas/autos/sanitarios/mobiliario exterior reutilizables sí reducirían variabilidad y generación repetida. Antes de importar: licencia/procedencia, unidades, base/origen, orientación, dimensiones, capas/atributos, versión/hash y tipos admitidos; distinguir símbolo esquemático y fiel. **Aceptación:** fixture autorizado importado a copia conserva transformaciones/capas/escala/footprint al guardar, sin publicar geometría privada. Depende R01/R02. Biblioteca no resuelve reconocimiento, distribución, circulación ni fidelidad integral. Ninguna biblioteca externa proporcionada/evaluada en estos ensayos.

### R10 — Perfil métrico y presentación [P1, parcial, M5/M6]

Aplicar perfil existente desde contrato: unidades, estilos, alturas, grosor/escala, cotas y bounds de anotación separados de arquitectura. Ampliar legibilidad/solape existente. **Aceptación:** fixtures m/mm con conversión explícita mantienen medidas y rótulos/cotas legibles, sin invadir título/tabla/planta, tras reapertura y a escala de salida. Medida correcta de DIMENSION no acredita su presentación.

### R11 — Sondas externas: custodia y precisión [P0 custodia/P1 precisión, parcial, M6]

Usar copia desechable, manifiesto pre/post, hash original, propiedad del proceso y salida verificada. Extraer precisión suficiente manteniendo tolerancia congelada. **Aceptación:** ARC conocido pasa y negativo alterado falla a 1e-6; modificación de copia se reporta y original queda intacto incluso al fallar; cierre incompleto no se etiqueta aprobado. Sonda suplementaria E1 permanece invalidada; no reemplazarla silenciosamente.

### R12 — QA espacial/topológica completa [P1, parcial, M6]

Conectividad de recintos, acceso exterior, continuidad muro/hatch, vanos, barrido de puertas, circulación, duplicados/degenerados y solapes por categoría. Depende R01 para muebles. Distinguir superposición decorativa y colisión funcional. **Aceptación:** negativos de puerta bloqueada, muro en vano, hatch desactualizado y mueble sobre paso fallan; falsos positivos documentados. Captura bonita/AUDIT limpio no certifican estos controles.

### R13 — Identidad, tokens y fases temporales [P1, parcial, M3]

Recibo de modelo solicitado/efectivo, effort, uso/cache, supervisor/generador; unknown si no existe. Fases monotónicas preparación/modelo/transporte/GUI/render/save/reopen/QA, espera del usuario y cobertura de corte, sin sumar solapamientos. **Aceptación:** deduplicación por respuesta, factura ausente null, recibo preservado aun si falla validación; reconciliación con fuente. [Recibo sintético](M3-DIRECT-RESPONSE-RECEIPT-V1.md) no prueba enlace real con todo proveedor.

### R14 — Benchmark de eficiencia [P2, pendiente, M7]

Congelar workload/modelo/effort/hardware/build/plan/gates; separar crear/modificar/extender, frío/caliente y casos inéditos. Intercalar control/tratamiento con repeticiones; incluir correcciones/fallos hasta aceptación. **Aceptación:** ahorro reproducible sin degradar gates; pared/tokens/cache/RPC/bytes/capturas/éxitos, mediana/p95 con muestra y límites. Depende exactitud/R13. V1/V2 y pilotos históricos 1/3→3/3 no prueban mejora general.

### R15 — Fidelidad integral y revisión humana [P1, pendiente, M7]

Oráculo independiente/tolerancias por región y separación desarrollo/reserva; imágenes ya usadas permanecen desarrollo. Validar inventario, cotas, colocación, topología y presentación además de persistencia. **Aceptación:** L5 humana con quién/qué/revisión/fecha, sin sustituir por autoevaluación del generador. Aprovechar material autorizado; no pedir otra imagen automáticamente ni reusar slots agotados sin nueva decisión de alcance.

### R16 — Flujo repetible por cualquier agente [P1, parcial, M8]

Consolidar CLI/manifiesto/paquete existentes: entrada pequeña+contrato+patch, salidas compactas y artefactos verificables; evitar cientos de líneas nuevas de Python por petición. **Aceptación:** otro agente retoma con este índice, valida contexto y ejecuta fixture autorizado sin conversación previa; incluye negativos/recuperación. Depende R03/R04/R05. Copiar helpers privados al repo sin abstraer/probar no cierra esto.

### R17 — Modales, captura y ciclo de vida [P1, parcial, M2/M3/M6]

Ampliar waiting_user, arranque/cierre con ownership, captura por revisión/fence y recortes con cuotas. No volver a Base64 repetido en prompts. **Aceptación:** frame viejo/revisión incorrecta rechazados; modal diagnosticado; sesión ajena/dirty no cerrada; artefacto verificable sin volcar binarios. Omitir captura exige cobertura justificada.

### R18 — Distribución/plataformas/upstream [P2 separado, parcial, M0/M8]

v2026.40.1 ya cerró paquete/publicación de su corte: no repetir pendiente histórico de rebuild como si nunca ocurrió. Faltan Mac físico, mínimos macOS 11/Windows 10 y firma confiable Windows/Developer ID/notarización cuando haya credenciales. Usuario aceptó firma actual y dejó Mac para después. Nuevos tags requieren política Pages revisada. Nueva integración upstream congela otro SHA/gates por delta; no se hace durante este informe ni habilita push.

### R19 — CI, operación y conservación [P2, continuo, M0/M3/M8]

Reutilizar recibos solo por equivalencia fuente/entorno/cobertura; un productor Cargo por target y --locked. No repetir CI por timeout/prosa. Medir caché/features en delta real. Si reaparece crash git-remote-https, registrar hora/evento/comando sin secretos; causa aún desconocida. Inventariar artefactos expirables/copia privada recuperable: target ignorado no es backup ni viaja con el clon. No limpiar worktrees en uso. Transferencia/custodia privada de evidencia aún necesita procedimiento reproducible.

## 7. Cobertura M0–M8 y secuencia

| Fase | Estado consolidado | Continuidad |
|---|---|---|
| M0 | Integración/baseline aprobados en cortes concretos; mantenimiento continuo | R18/R19 |
| M1 | Cliente y recuperación L1/L2 acotados; recuperación completa parcial | R03/R05/R06/R07 |
| M2 | Discovery/propiedad/cierre acotados; modalidades pendientes | R05/R17 |
| M3 | Contratos/medidas locales útiles; procedencia directa/atribución parcial | R06/R13/R17/R19 |
| M4 | Compilador/grafo/símbolos tipados parciales; contexto prototipo | R03/R04/R07/R08 |
| M5 | Semántica nativa demostrada en alcances; exactitud integral pendiente | R01/R02/R09/R10 |
| M6 | Persistencia/comparadores acotados; no QA universal | R01/R10/R11/R12/R17 |
| M7 | Casos de desarrollo/pilotos; sin aceptación global nueva | R08/R14/R15 |
| M8 | CLI/paquetes y release vigente; flujo conversacional incompleto | R04/R16/R18/R19 |

El [backlog anterior](03-FASES-Y-BACKLOG.md) y checkpoint conservan subhitos y contratos íntegros. Tablas iniciales «todo pendiente» son históricas; no sustituyen cortes posteriores. No promover pruebas sintéticas a GUI/imagen/humano.

| Paso | Alcance | Gate |
|---|---|---|
| A | Reproducción mínima R01/R02, contrato R03 | Fallo actual demostrado en fixture propio; custodia/no replay R05/R11 desde el inicio |
| B | Bounds y contrato de capa | Positivos/negativos focalizados, GUI propia, save/reopen mismo binario |
| C | Adaptador/contexto/patch R03/R04/R16 | Ambigüedad bloqueada antes de mutar; nueva sesión recupera invariantes |
| D | Recuperación R05, telemetría R13, captura R17 | Fallos inyectados/un solo efecto/recibos durables; incertidumbre bloquea optimización dependiente |
| E | PlanSpec/biblioteca/QA/presentación R08–R12 | Inventario, topología, colisiones y sondas seguras; biblioteca autorizada |
| F | Reducir contexto/RPC/overhead R06/R07 y medir R14 | Comparación pareada con gates iguales y costo hasta aceptación |
| G | Fidelidad/entrega R15/R16/R18 | L5 independiente, límites claros, Mac/credenciales cuando disponibles; publicar solo con instrucción vigente |

No prometer segundos ni ahorro antes de medir. «Correr como mantequilla» requiere petición→contexto validado→diff semántico→ejecución recuperable→verificación compacta→entrega, sin reconstruir todo el historial ni improvisar scripts, con diagnóstico comprensible si falta información.

## 8. Evidencia y custodia

[Índice estructurado](06-METRICAS-Y-EVIDENCIAS-20260929.json): en la versión redactada para publicación, conteos de recibos, capturas y CAD por caso; rutas, nombres, tamaños y hashes de cada archivo quedan solo en la copia local privada. **target no está versionado**: otro clon tendrá informe/índice, no dibujos/capturas/logs. Si faltan: `evidence_unavailable`, recuperar paquete privado autorizado cuando sea necesario; nunca fabricar passed o regenerar una corrida para sustituirla silenciosamente.

| ID | Evidencia privada bajo target/mcp-isolated, fuera de Git |
|---|---|
| E1a | RESULTADO, VERDICT, model-result, generator-summary, strict-gate-failure, representation-salvage |
| E1b | presentation-change, precision-limitation, INCIDENT de la sonda y un DWG |
| E2 | RESULTADO, VERDICT, GEOMETRY-CHECKS, RUN-CONTRACT, COMMANDS, una captura y un DWG |
| E3 | RESULTADO, VERDICT, GEOMETRY-CHECKS, RUN-CONTRACT, METRICS-CIERRE, DRAWING-CONTEXT, CHANGE-PLAN, COMMANDS, tres capturas y un DWG |

No copiar CAD/capturas/logs/transcript a Git. Conservar fallos, recovery y METRICS.json temprano junto al corte final. El CAD privado del checkout original queda fuera incluso del hash del inventario. Los datos de este informe son agregados sanitizados y referencias a entregas propias autorizadas.

## 9. Registro exigido para cada mejora

Registrar por Rxx: hipótesis, antes/después, owner_role, dependencias, paths/commit, productor/binario/configuración, contrato/tolerancias, inicio/fin/fases, entrada/cache/salida/razonamiento/cobertura, RPC/bytes/capturas, comandos/mutaciones, correcciones/abstenciones/fallos, positivos/negativos y límites. Generar datos automáticamente y compartir solo resumen sanitizado.

Estados: propuesto, pendiente, en curso, aprobado acotado, parcial, fallido, bloqueado por dependencia, no ejecutado. Medición ausente es desconocida, no cero. Objetivo/presupuesto no es resultado. Nueva revisión exige checks por impacto, no repetición indiscriminada.

Este cierre documental registra aparte sus lecturas, consolidación, hashes, enlaces y diff; no nuevos modelos, imágenes, Cargo ni GUI. Recibo local de tiempo/tokens: target/distribution-port/master-report-20260929-close.json, con corte propio previo a respuesta final; no sumar a E3. El límite de comando Windows y la búsqueda inicial con glob literal no aceptado por rg quedaron diagnosticados: dividir escrituras y usar -g sobre directorio. Las salidas extensas truncadas motivaron lecturas acotadas; otra oportunidad de eficiencia documental es generar índices pequeños en vez de releer checkpoints completos.

## 10. Entrada rápida y continuación

1. Leer AGENTS.md, este informe, su JSON y contrato Rxx elegido; este ciclo **no autoriza push**.
2. Verificar worktree/rama/HEAD/cambios; no usar checkout privado sucio ni mezclar ramas por su nombre.
3. Comprobar evidencia/hash. Para CAD: binario, sesión propia, documento/revisión/unidades; no confiar en PID/contexto históricos.
4. Elegir defecto→fixture→gate→fix→verificación proporcional. No repetir casas/modelos/build por cerrar documentación.
5. Mutación incierta: consultar operación con request_id original, no reenviar con otro. starting significa disponibilidad pendiente.
6. Preservar originales/fallos/negativos y actualizar Rxx con estado real; commit con paths explícitos, sin push/release.

Prompt listo:

> Continúa OpenCADStudio en desktop-distribution, rama codex/windows-web-dxf. Lee AGENTS.md y docs/automation/masterplan/06-INFORME-MAESTRO-Y-MEJORAS-20260929.md, su JSON y contratos vinculados. Verifica Git/evidencia antes de mutar; no tocar checkout privado original. Comienza por reproducción sintética mínima R01/R02 y contrato R03; aplica custodia R05/R11 desde el inicio. No aceptar consulta espacial INSERT hasta corregir/probar bounds. No reejecutar casas/modelos para documentar. Cada mejora deja tiempos/tokens con corte, dificultades, negativos, productor/binario, resultado y siguiente paso. La propuesta E3 terminó en su alcance conceptual; contexto es prototipo, no aceptación global. No push/publicación ni merges de ramas experimentales sin necesidad revisada. Conserva sesiones ajenas. Cierra con commit local, verificación y pendiente concreto.

## 11. Medición separada de este informe

Inicio `2026-09-29T07:31:26.876Z`; corte `2026-09-29T07:47:11.884Z`. Modelo registrado `gpt-6-astra`. Excluye verificación/commit posteriores al corte y respuesta final; no es duración final completa.

| Medida documental | Valor al corte |
|---|---:|
| Entrada | 1,013,796 |
| Cache incluida | 745,472 |
| Entrada no cacheada | 268,324 |
| Salida | 22,346 |
| Razonamiento incluido | 863 |
| Total entrada + salida | 1,036,142 |
| Pared en segundos | 945.008 |

Contadores locales, no facturación. Conservan también el costo de incidentes y lecturas truncadas de este cierre. El anexo estructurado replica este corte; no se alteraron métricas de CAD V1/V2.
