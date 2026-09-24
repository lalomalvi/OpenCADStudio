# Matriz de gates para el pase exploratorio de cinco casos

`cli_sample_gates.py` revalida el resumen desde las fuentes, prompts, protocolo congelado, eventos CLI, evidencias CAD y reportes AutoCAD locales antes de producir una matriz. El reporte local `target/mcp-cli-development/five-sample-gates-v1.json` tiene SHA-256 `04095ECD70C2CB3035EBABBB61F3F15F9EE5E1F7CDD00B0F7AD80CC4F59D85F7`.

Tres casos tienen evidencia **acotada** de medida/topología rectangular, LINE/capa/unidades, guardado, auditoría, hashes, salida de GUI propia y motor externo identificado. Un caso falló su métrica previamente fijada y otro se abstuvo; no se dibujó CAD para ellos. G0 permanece pendiente por falta de identidad efectiva directa; G1 solo tiene evidencia de intento local único, no trazabilidad proveedor completa; G6 espera revisión visual humana; G10 espera uso directo comparable y baseline/candidato. En los tres positivos, el oráculo métrico provino de revisión previa del asistente, no de humano ni herramienta independiente. Ningún caso recibe aceptación M7, aunque haya pasado su contraste geométrico L4.

La matriz no convierte resultados de rectángulos en fidelidad de lámina completa. Las diferencias entre lo observado y lo solicitado permanecen en los reportes privados de `target/`, sin publicar planos ni prompts de las fuentes del usuario.
