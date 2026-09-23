# Arquitectura propuesta y contratos
Estado: diseño, nombres ilustrativos; no API disponible todavía.

## Flujo
Imagen congelada → interpretación visual Luna → PlanSpec → validación dimensional/topológica → compilador de comandos → cliente MCP persistente → OpenCADStudio → QA numérica y visual → guardado/reapertura → informe generado por código.

## Responsabilidades
| Componente | Responsabilidad | No debe asumir |
|---|---|---|
| Orquestador | Identidad efectiva, presupuesto, aislamiento, secuencia | Autocertificación del modelo |
| Luna | Inventario visual, referencias de cotas, hipótesis y revisión | Hashes escritos a mano o geometría oculta |
| Validador | Unidades, restricciones, tolerancias, topología | Resolver silenciosamente ambigüedades |
| Compilador | PlanSpec a comandos soportados y trazabilidad | Inyección directa de registros CAD |
| Cliente MCP | Transporte, plazos, correlación, bitácora y recuperación | Repetir mutaciones inciertas |
| Servidor MCP | Contratos, idempotencia y estado real | Leer globalmente cualquier ruta |
| Motor CAD | Geometría y persistencia | Medir identidad/costo del LLM |
| Verificador | Métricas y evidencia reproducibles | Confundir autocrítica con oracle externo |

## RunContract v2
Campos: schema_version, run_id, created_at_utc, source(path/hash/bytes/pixel_size), runtime(executable/hash/revision), model(requested/effective/provider/effort/identity_evidence), units, coordinate_system, dimension_reference_policy, tolerances, allowed_operations, output_root, budgets, benchmark_split, lifecycle_ownership y acceptance_version.
Identidad efectiva desconocida produce unknown; no rellenar con el nombre esperado. Fijar versiones antes de consumir la imagen. Las rutas se canonicalizan y se restringen al directorio del run; rechazar traversal, escapes por enlaces y sobreescritura accidental.
Budgets incluyen respuestas, tokens nuevos/cache/salida, tiempo, capturas, reintentos y bytes; sobrepasar termina con checkpoint recuperable, no abandono silencioso.

## PlanSpec v1
Unidades explícitas, origen y ejes. Colecciones con IDs estables: walls, openings, rooms, fixtures, annotations, dimensions, constraints y unresolved.
Cada elemento conserva source_region_px, confidence y classification (measured/inferred/unknown). Cada dimensión conserva texto observado, unidad, valor numérico, extremos/entidades de referencia y tipo de referencia (cara/eje/exterior/interior).
Puertas: wall_id, offset, width, hinge, swing. Muros: línea/eje o contorno, espesor y uniones. Símbolos: tipo y parámetros con procedencia; no presentar una biblioteca genérica como réplica exacta de símbolos.
Campos desconocidos se rechazan o migran mediante versión; NaN, infinito, unidades mezcladas, IDs duplicados y referencias colgantes se rechazan antes de mutar CAD.

## Resolución dimensional
Construir grafo de restricciones por referencias comunes. Comparar solo cadenas con mismos extremos. No ajustar automáticamente medidas certificadas; si referencias no resuelven el sistema, emitir conflicto localizado y pedir decisión puntual cuando sea imprescindible.
El solver devuelve satisfechas, incompatibles, indeterminadas y residuales por restricción. Las hipótesis quedan visibles. Nunca usar text_override para ocultar una distancia diferente.
Tolerancia numérica de compilación separada de tolerancia de interpretación raster; propuestas iniciales: 1e-6 unidades CAD para identidad determinista y 0.001 m para longitudes explícitamente vinculadas. Congelar valores adecuados al caso antes de evaluar, no afirmar que la resolución raster permite esa precisión.

## Compilación y ejecución
Normalizar orden y redondeo para hash determinista del plan. Generar capas/estilos antes de geometría, luego aperturas/símbolos y cotas. Mapear PlanSpec ID → comandos → request_id → handles → revisión.
Consultar manifiestos por hash de build y cachearlos. Usar comandos nativos existentes: ARC, dimensiones, capas, BLOCK/INSERT, polilíneas y HATCH según censo. Si falta soporte real, señalar capacidad no soportada.
run_script sigue siendo no atómico. Marcar inicio/fin por lote y conservar resultados parciales. No prometer rollback completo sin evidencia. Una repetición del mismo request_id consulta/resume; un plan modificado requiere otro ID y referencia a la corrección.
Preservar document_id y revision; modificaciones externas invalidan precondiciones. Las respuestas incluyen conteos/resumen/bounds/IDs; geometría completa solo bajo petición.

## Ciclo de vida
Estados propuestos: absent → starting → ready → executing → verifying → closing → closed; estados laterales waiting_user, failed y recoverable.
readiness devuelve retry_after_ms, deadline y motivo estable. Identificar proceso por PID + inicio + ejecutable + session_id; PID aislado es insuficiente por reutilización.
Descubrimiento: validar propiedad y descriptor privado; sondear sesiones con presupuesto total y concurrencia limitada; cachear conexiones vivas. Evitar relanzamientos durante arranque. No borrar descriptores solo por TTL: confirmar proceso/identidad y estado.
Cierre: close_document con política explícita de guardar/descartar; shutdown solo para sesión propia, después de verificar salida durable. Negativas de herramientas se registran; no cambiar de mecanismo para eludirlas.
Descriptores muertos pueden ir a cuarentena local con metadata sanitizada. Nunca publicar su token. No cerrar sesiones de usuario ni desactivar protección de Windows.

## Capturas y artefactos
Mantener respuesta MCP image compatible con clientes remotos. Añadir transporte negociado: imagen nativa, recurso MCP o artefacto local autorizado. Una ruta Windows sola no funciona para clientes remotos.
ArtifactRef: id, mime, hash, bytes, width, height, document_id, geometry_revision, camera_revision, region y expires_at. Persistir PNG fuera del JSONL; registrar referencias.
Captura tras render-fence de la revisión objetivo; rechazar imágenes obsoletas. Recorte en coordenadas CAD y padding; captura final completa con escala/encuadre reproducible. Presupuesto adaptativo, no eliminar QA esencial para cumplir un número.

## Evidencia y telemetría
TraceEvent: run_id, model_response_id, request_id, phase, timestamps UTC, monotonic_start/end, queue_ms, discovery_ms, execution_ms, render_ms, bytes_in/out, status, error_code, retry_of y artifact_refs.
UsageRecord: input, cached_input, cache_write, output, reasoning_output, provider/model/effort, response_id, source y completeness. Deduplicar por response_id. Separar agregados acumulados de incrementales, supervisor de generador y coste estimado de factura.
Evidencia generada por código a partir de fuentes, validada contra esquema y sellada con hashes. Registrar correcciones como nuevo manifiesto que apunta al anterior. MODEL-SUMMARY no se llama transcript. Exportar transcript sanitizado de mensajes/herramientas visibles; no pretender exportar razonamiento privado.
