# Censo M5 de capacidades CAD

Corte sintético L2 del 2026-09-23. Binario debug SHA-256 `0F9F4E42870D4AC5EDBD497986AD56DC1A21E779ADE98E3373B4021AB6597410`. `ocs_read commands` devolvió 634 nombres sin truncamiento; SHA-256 de nombres ordenados `19a7dd4115908496fe8d2d2f56859fadb7ddd3128de79cfa4be6cb20e4940243`. Reporte local: `target/mcp-isolated/20260923-212518-owned-3061d305/owned-report.json`. Solo contiene un perfil y documentos sintéticos; no se abrió el DWG del usuario.

| Necesidad M5 | Comando registrado | Generación mediante PlanSpec | Ejecución MCP L2 | Persistencia/semántica |
|---|---|---|---|---|
| Capas | `LAYER`, `CLAYER` | `LAYER NEW` y `CLAYER` con manifiesto de build probado | passed scoped L2 | A-WALL asignada por handle y conservada en manifest tras reapertura interna; estilos/anchos pending |
| Polilínea cerrada | `PLINE` | no implementada | passed scoped L2 | `is_closed=true`, vértices, ancho/grosor y handle comparados pre/post reapertura interna; uniones/escala pending |
| Arco nativo | `ARC` | no implementada | passed scoped L2 | centro/radio/ángulos/handle comparados pre/post reapertura interna; edición y motor externo pending |
| Cota lineal/alineada | `DIMLINEAR`, `DIMALIGNED` | validación de longitud; compilación unsupported | no probada | asociatividad pending |
| Bloque/instancia | `BLOCK`, `INSERT` | no implementada | no probada | unidades/rotación pending |
| Relleno | `HATCH` | no implementada | no probada | contorno/guardado pending |
| Plantilla de página | `PSETUPIN` | no implementada | no probada | es importación de page setup, no sustituye perfil métrico |
| Línea/círculo | `LINE`, `CIRCLE` | implementada, capa `0` | tres entidades L2 | audit/save_verified interno passed scoped |

La presencia en el catálogo acredita registro del nombre en ese build. ARC y PLINE tienen fixture L2 (`mcp_native_primitives_smoke.py`): crearon entidades con handles únicos, consulta de geometría, auditoría y guardado verificado con reapertura interna de tipos. Capas tienen fixture L2 nativo y PlanSpec (`mcp_layer_planspec_smoke.py`) con manifiesto de binario/catálogo exactos. Eso no acredita motor externo, asociatividad ni semántica de los demás comandos. El siguiente gate es un fixture pequeño por capacidad con comando, cambio de handle, auditoría y comparación geométrica pre/post guardado; las cotas requieren mover referencia y observar actualización antes de afirmar asociatividad. No crear funciones duplicadas hasta completar ese gate.
