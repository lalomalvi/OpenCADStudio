# Masterplan de robustecimiento MCP y reconstrucción CAD
Versión 1.0 · 2026-09-23 · Estado: planificación; implementación futura pendiente.

Actualización M0/M1: ver [M0-INTEGRACION.md](M0-INTEGRACION.md), [BASELINE.json](BASELINE.json), [mcp_client.md](../mcp_client.md) y el corte vigente en [05-CHECKPOINT-Y-CONTINUACION.md](05-CHECKPOINT-Y-CONTINUACION.md). Los contratos acotados de obstáculos M6.3 y cotas de eje M4/M5 están en [OBSTACLE-QA-V8.md](OBSTACLE-QA-V8.md), [AXIS-SPAN-DIMENSION-V8.md](AXIS-SPAN-DIMENSION-V8.md), [AXIS-ENDPOINT-ALIGNED-V9.md](AXIS-ENDPOINT-ALIGNED-V9.md), [ASSOCIATIVE-AXIS-LENGTH-EDIT.md](ASSOCIATIVE-AXIS-LENGTH-EDIT.md), [JOINED-WALL-SINGLE-DOOR-V1.md](JOINED-WALL-SINGLE-DOOR-V1.md), [THREE-WALL-UNION-V1.md](THREE-WALL-UNION-V1.md), [THREE-WALL-SINGLE-DOOR-V1.md](THREE-WALL-SINGLE-DOOR-V1.md), [METRIC-PLOT-PDF-V1.md](METRIC-PLOT-PDF-V1.md), [METRIC-PAGE-SETUP-DWG-V1.md](METRIC-PAGE-SETUP-DWG-V1.md), [METRIC-CONTENT-PRINT-QA-V1.md](METRIC-CONTENT-PRINT-QA-V1.md), [METRIC-PEN-WIDTH-QA-V1.md](METRIC-PEN-WIDTH-QA-V1.md), [METRIC-BYLAYER-PRINT-QA-V1.md](METRIC-BYLAYER-PRINT-QA-V1.md), [METRIC-MONOCHROME-CTB-V1.md](METRIC-MONOCHROME-CTB-V1.md), [METRIC-SEARCHABLE-TEXT-V1.md](METRIC-SEARCHABLE-TEXT-V1.md), [M7-ORACLE-FREEZE-V1.md](M7-ORACLE-FREEZE-V1.md), [M7-TRIAL-JOURNAL-V1.md](M7-TRIAL-JOURNAL-V1.md), [M7-INVOCATION-GATE-V1.md](M7-INVOCATION-GATE-V1.md) y [M7-EVIDENCE-BINDING-V1.md](M7-EVIDENCE-BINDING-V1.md). La tabla siguiente conserva el estado inicial histórico.

## Propósito

El recibo L0 de identidad/uso tomado de objetos Responses API se documenta en [M3-DIRECT-RESPONSE-RECEIPT-V1.md](M3-DIRECT-RESPONSE-RECEIPT-V1.md), la creación única de Luna en [M3-LUNA-ONCE-ADAPTER-V1.md](M3-LUNA-ONCE-ADAPTER-V1.md), el gate de salida PlanSpec en [M3-LUNA-PLANSPEC-GATE-V1.md](M3-LUNA-PLANSPEC-GATE-V1.md), el callback reservado en [M3-LUNA-PIPELINE-CALLBACK-V1.md](M3-LUNA-PIPELINE-CALLBACK-V1.md), el ejecutor de GUI aislada en [M3-OWNED-CAD-EXECUTOR-V1.md](M3-OWNED-CAD-EXECUTOR-V1.md), la integración sintética L2 en [M3-RESERVED-PIPELINE-L2-V1.md](M3-RESERVED-PIPELINE-L2-V1.md), la captura cercada en [M3-FENCED-CAD-CAPTURE-V1.md](M3-FENCED-CAD-CAPTURE-V1.md), el supervisor de una solicitud en [M3-SUPERVISOR-ONCE-ADAPTER-V1.md](M3-SUPERVISOR-ONCE-ADAPTER-V1.md) y la trazabilidad externa en [M4-HANDLE-MAP-L4-V1.md](M4-HANDLE-MAP-L4-V1.md). Ninguno acredita aún una invocación Luna real.
La prueba Luna real vía plan de Codex CLI y sus límites de procedencia están en [M7-CODEX-CLI-EXPLORATORY-V1.md](M7-CODEX-CLI-EXPLORATORY-V1.md); el pase de cinco imágenes autorizado por el usuario y su balance 3/1/1 en [M7-CINCO-MUESTRAS-V1.md](M7-CINCO-MUESTRAS-V1.md); el vínculo de verdicts AutoCAD positivos/negativos en [M7-EXTERNAL-VERDICT-BINDING-V1.md](M7-EXTERNAL-VERDICT-BINDING-V1.md). Estas pruebas de desarrollo no equivalen al experimento reservado de 36 casillas ni a un recibo directo Responses API.
La separación de evidencia por gate para los cinco casos se documenta en [M7-CINCO-CASOS-GATES-V1.md](M7-CINCO-CASOS-GATES-V1.md); ningún caso obtiene aceptación M7 por el contraste geométrico acotado.
El ensayo de mediciones tipadas y compilación determinista de una retícula de dos recintos está en [M7-MEDICIONES-TIPADAS-RETICULA-V1.md](M7-MEDICIONES-TIPADAS-RETICULA-V1.md); tampoco concede aceptación M7.
Las abstenciones al distinguir cotas horizontales apiladas y el contrato tipado correspondiente están en [M7-COTAS-APILADAS-DESARROLLO-V1.md](M7-COTAS-APILADAS-DESARROLLO-V1.md).
La selección trazable de recortes visuales por grupos de anclas CAD ya proyectadas está en [M6-RECORTES-POR-ANCLAS-V1.md](M6-RECORTES-POR-ANCLAS-V1.md).
La conciliación versionada de cadenas de cotas alineadas en 2D está en [M4-GRAFO-COTAS-ALINEADAS-V2.md](M4-GRAFO-COTAS-ALINEADAS-V2.md).
La identidad de vértices mediante referencias de muro/cara/estación vinculadas para PlanSpec v6–v9 está en [M4-GRAFO-REFERENCIAS-VINCULADAS-V3.md](M4-GRAFO-REFERENCIAS-VINCULADAS-V3.md).
La primera cadena de tres cotas nativas sobre un muro sintético, con reapertura y contraste AutoCAD por handle, está en [M4-CADENA-COTAS-NATIVAS-V1.md](M4-CADENA-COTAS-NATIVAS-V1.md).
El segundo pase Luna sobre las cinco imágenes disponibles, con retícula de cinco franjas y seis cotas nativas de ejes en alcances de referencia, está en [M7-CINCO-IMAGENES-SEGUNDO-PASE-V1.md](M7-CINCO-IMAGENES-SEGUNDO-PASE-V1.md).
La revisión de píxeles de las cajas de cota declaradas por Luna y sus fallas verificadas está en [M6-CAJAS-DE-TEXTO-FUENTE-V1.md](M6-CAJAS-DE-TEXTO-FUENTE-V1.md).
La expansión derivada de 25 píxeles, con 6/6 textos completos por caso en dos hojas revisadas, está en [M6-CAJAS-DERIVADAS-PAD25-V1.md](M6-CAJAS-DERIVADAS-PAD25-V1.md).
La variante de texto 0.25 m para la cadena de cotas nativas, reutilizando la misma salida Luna, está en [M5-LEGIBILIDAD-COTAS-REFERENCIA-V1.md](M5-LEGIBILIDAD-COTAS-REFERENCIA-V1.md).
La retícula de tres regiones de recámaras, con fallo métrico v1, L2/L4 v2 y procedencia de caja 3/4 fallida, está en [M7-RECÁMARAS-TRES-REGIONES-V1.md](M7-RECÁMARAS-TRES-REGIONES-V1.md).
El rechazo L2 de seis valores inválidos en `DIMSTYLE SET` y el límite de la prueba de asociación están en [M5-RECHAZO-DIMSTYLE-Y-ASOCIACION-V1.md](M5-RECHAZO-DIMSTYLE-Y-ASOCIACION-V1.md).
La prueba conjunta de cota nativa asociada con estilo `fixed_2`, edición, reapertura y AutoCAD está en [M5-COTA-FIXED2-ASOCIADA-V1.md](M5-COTA-FIXED2-ASOCIADA-V1.md).
El contorno exterior visible del departamento leído por Luna, con dos fallos conservados, superposición de fuente y AutoCAD 13/13, está en [M7-APARTAMENTO-CONTORNO-VISIBLE-V1.md](M7-APARTAMENTO-CONTORNO-VISIBLE-V1.md).
La selección posterior de tres tabiques visibles, dos nuevos fallos Luna y el cotejo AutoCAD 16/16 del esqueleto parcial están en [M7-APARTAMENTO-TABIQUES-VISIBLES-V1.md](M7-APARTAMENTO-TABIQUES-VISIBLES-V1.md).
Cinco tramos horizontales detectados por Luna en recortes 8× y el esqueleto de 21 LINE cotejado en AutoCAD están en [M7-APARTAMENTO-RECORTES-HORIZONTALES-V1.md](M7-APARTAMENTO-RECORTES-HORIZONTALES-V1.md).
La integración de siete cotas nativas en el DWG parcial de la misma planta, con AutoCAD 32/32 y soporte técnico visible pendiente de corregir, está en [M7-APARTAMENTO-COTAS-INTEGRADAS-V1.md](M7-APARTAMENTO-COTAS-INTEGRADAS-V1.md).
La corrección posterior de la visibilidad del soporte técnico, con el fallo v2 conservado y el run v3 cotejado en AutoCAD, está en [M7-APARTAMENTO-SOPORTE-COTAS-OCULTO-V1.md](M7-APARTAMENTO-SOPORTE-COTAS-OCULTO-V1.md).
Los cuatro intentos Luna sobre una puerta de la planta, con dos abstenciones, un fallo geométrico y una observación válida sin CAD, están en [M7-APARTAMENTO-PUERTA-OBSERVACION-V1.md](M7-APARTAMENTO-PUERTA-OBSERVACION-V1.md).
La integración posterior de una puerta y su tramo vertical faltante en el DWG parcial, con AutoCAD 35/35 y negativo de arco 34/35, está en [M7-APARTAMENTO-UNA-PUERTA-CAD-V1.md](M7-APARTAMENTO-UNA-PUERTA-CAD-V1.md).
El contrato PlanSpec v10 para arco de puerta ligado al hueco, con QA de barrido y run nuevo 35/35 en AutoCAD, está en [M4-PLANSPEC-V10-SIMBOLO-PUERTA.md](M4-PLANSPEC-V10-SIMBOLO-PUERTA.md).
El formato nativo de dos decimales con ceros finales, cotejado en AutoCAD por estilo y handle, está en [M5-COTAS-DECIMALES-FIJOS-V1.md](M5-COTAS-DECIMALES-FIJOS-V1.md).
El rechazo adversarial de cajas derivadas que mezclan regiones vecinas está en [M6-CAJAS-DERIVADAS-SIN-SOLAPE-V1.md](M6-CAJAS-DERIVADAS-SIN-SOLAPE-V1.md).
Convertir el ensayo Luna → MCP → OpenCADStudio en un flujo reproducible, medible y recuperable que genere CAD editable con precisión declarada. Este plan abarca arranque, transporte, ejecución, evidencia, consumo, semántica CAD, evaluación e integración. El programa probado fue OpenCADStudio; LibreCAD no participó.

## Lectura y autoridad
1. [01-BASELINE-Y-CORRECCIONES.md](01-BASELINE-Y-CORRECCIONES.md): hechos, métricas y límites del ensayo.
2. [02-ARQUITECTURA-Y-CONTRATOS.md](02-ARQUITECTURA-Y-CONTRATOS.md): responsabilidades y contratos propuestos.
3. [03-FASES-Y-BACKLOG.md](03-FASES-Y-BACKLOG.md): ejecución, dependencias y aceptación.
4. [04-EVALUACION-Y-PUBLICACION.md](04-EVALUACION-Y-PUBLICACION.md): pruebas, métricas, integración y recuperación.
5. [05-CHECKPOINT-Y-CONTINUACION.md](05-CHECKPOINT-Y-CONTINUACION.md): rutas, estado y prompt para otra sesión.

Los contratos aceptados de cada evaluación prevalecen sobre objetivos orientativos. No cambiar umbrales después de observar resultados: emitir otra versión y otro run. La aprobación del plan no convierte las propuestas en funcionalidades implementadas.

## Estado inicial
| Hito | Estado |
|---|---|
| Ensayo original con Luna | Parcial; persistencia interna aprobada, fidelidad no aceptada |
| Auditoría previa sin abrir DWG | Realizada; observaciones corregidas en este plan |
| Masterplan | Documento inicial listo para revisión |
| M0 integración reproducible | Pendiente |
| M1–M8 | Pendientes |
| Verificación externa DWG | Pendiente |
| Revisión visual del usuario | Pendiente |

## Alcance y límites
La sesión de cierre publica documentación y respalda el código previamente desarrollado en una rama. No incorpora automáticamente las 28 modificaciones experimentales a main. El siguiente trabajo empieza por M0 y M1; mantiene el plano original y el ensayo histórico intactos. No requiere redibujar el caso para iniciar.

Unidades, permisos, validación, límites, identidad de sesión y recuperación deben residir en código verificable. El modelo propone interpretación y decisiones visuales; no certifica por sí mismo su identidad, integridad, costo o conformidad.

## Definición de terminado
Una versión candidata requiere todos los gates técnicos y de fidelidad de su alcance aprobados, costo y latencia medidos, limitaciones explícitas, evidencia reproducible, revisión del diff, publicación en el fork correcto y checkpoint suficiente para continuar sin esta conversación. Una única reconstrucción no permite declarar compatibilidad universal.

## Evidencia reciente
[M5-BLOCK-CONTENT-L4-V1.md](M5-BLOCK-CONTENT-L4-V1.md): definición interna de un bloque sintético, unidades métricas y dos INSERT cotejados con AutoCAD. El estado vigente y los pendientes están en el checkpoint 125.
[M7-APARTAMENTO-VENTANA-NORTE-V1.md](M7-APARTAMENTO-VENTANA-NORTE-V1.md): observación Luna de una ventana, primer intento visual insuficiente y segundo marco esquemático cotejado con AutoCAD. El checkpoint 126 conserva ambos runs.
[M4-PLANSPEC-V11-SIMBOLO-VENTANA.md](M4-PLANSPEC-V11-SIMBOLO-VENTANA.md): contrato tipado 2D de ventana, QA de hueco y run 40/40 en AutoCAD. El checkpoint 127 registra sus límites.
