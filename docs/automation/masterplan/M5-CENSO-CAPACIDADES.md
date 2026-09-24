# Censo M5 de capacidades CAD

Corte sintético L2 del 2026-09-23. Binario debug SHA-256 `0F9F4E42870D4AC5EDBD497986AD56DC1A21E779ADE98E3373B4021AB6597410`. `ocs_read commands` devolvió 634 nombres sin truncamiento; SHA-256 de nombres ordenados `19a7dd4115908496fe8d2d2f56859fadb7ddd3128de79cfa4be6cb20e4940243`. Reporte local: `target/mcp-isolated/20260923-212518-owned-3061d305/owned-report.json`. Solo contiene un perfil y documentos sintéticos; no se abrió el DWG del usuario.

| Necesidad M5 | Comando registrado | Generación mediante PlanSpec | Ejecución MCP L2 | Persistencia/semántica |
|---|---|---|---|---|
| Capas | `LAYER`, `CLAYER` | unsupported para capa distinta de `0` | no probada | pending |
| Polilínea cerrada | `PLINE` | no implementada | no probada | pending |
| Arco nativo | `ARC` | no implementada | no probada | pending |
| Cota lineal/alineada | `DIMLINEAR`, `DIMALIGNED` | validación de longitud; compilación unsupported | no probada | asociatividad pending |
| Bloque/instancia | `BLOCK`, `INSERT` | no implementada | no probada | unidades/rotación pending |
| Relleno | `HATCH` | no implementada | no probada | contorno/guardado pending |
| Plantilla de página | `PSETUPIN` | no implementada | no probada | es importación de page setup, no sustituye perfil métrico |
| Línea/círculo | `LINE`, `CIRCLE` | implementada, capa `0` | tres entidades L2 | audit/save_verified interno passed scoped |

La presencia en el catálogo acredita registro del nombre en ese build. El manifiesto de comandos ofrece categoría, selección y orientación de sintaxis, pero no demuestra que `run_script` pueda completar todas las variantes ni que el DWG guardado preserve asociatividad, propiedades o interoperabilidad. El siguiente gate es un fixture pequeño por capacidad con comando, cambio de handle, auditoría y comparación pre/post guardado; las cotas requieren mover referencia y observar actualización antes de afirmar asociatividad. No crear funciones duplicadas hasta completar ese gate.
