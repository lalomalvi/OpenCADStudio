# Sello de evidencia M3 para run CAD sintético

`seal_cad_run.py` toma un run L2 terminado de `mcp_isolated_smoke.py` o `mcp_native_primitives_smoke.py` y el binario exacto usado. Comprueba SHA-256 del binario, fixture PlanSpec, comandos, DWG, tamaño, auditoría sin errores/advertencias, manifest antes/después de reapertura interna, captura PNG/revisiones si existe y salida de GUI. La versión 2 escribe una sola vez `AUDIT.json`, `SAVE.json`, `VERDICT.json`, `ARTIFACTS.json` y `SEAL.json` dentro del run local. `--verify` recalcula hashes y compara los documentos generados con el reporte original. La versión 1 anterior permanece legible. Para corregir un run se crea otro directorio; no se sobreescribe el corte anterior.

Ejemplo desde este worktree, con un run **sintético** propio:

```powershell
python docs/automation/mcp_native_primitives_smoke.py
python docs/automation/masterplan/seal_cad_run.py target/mcp-isolated/<run> target/debug/OpenCADStudio.exe
python docs/automation/masterplan/seal_cad_run.py target/mcp-isolated/<run> target/debug/OpenCADStudio.exe --verify
```

El run `20260923-213433-3a2932b3` pasó el L2 y conserva el sello v1. El run `20260923-214352-af7e4c77` añadió captura local ligada a documento/revisión y sello v2. Ambos veredictos son `partial` por gates de interpretación de imagen, render-fence, motor externo y revisión humana. El sello contiene hashes y resúmenes sanitizados, no binarios, rutas de perfil, tokens ni transcript. El PNG local puede mostrar texto de la interfaz y nunca se añade a Git. No es firma criptográfica ni prueba independiente de interoperabilidad. El coste facturado permanece `null` y la identidad del modelo `unknown` cuando el run CAD no incluye telemetría confiable de un LLM. La herramienta de uso histórico `usage_evidence.py` es independiente y deduplica por respuesta sin copiar el rollout privado. La verificación de un run requiere el binario exacto; si el debug se recompila, conservar otra copia identificada antes de intentar verificar un sello anterior.
