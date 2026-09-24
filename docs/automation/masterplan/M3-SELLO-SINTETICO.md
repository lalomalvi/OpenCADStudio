# Sello de evidencia M3 para run CAD sintético

`seal_cad_run.py` toma un run L2 terminado de `mcp_isolated_smoke.py` o `mcp_native_primitives_smoke.py` y el binario exacto usado. Comprueba SHA-256 del binario, fixture PlanSpec, comandos, DWG, tamaño, auditoría sin errores/advertencias, manifest antes/después de reapertura interna y salida de GUI. Escribe una sola vez `AUDIT.json`, `SAVE.json`, `VERDICT.json` y `SEAL.json` dentro del run local. `--verify` recalcula hashes y compara los documentos generados con el reporte original. Para corregir un run se crea otro directorio; no se sobreescribe el corte anterior.

Ejemplo desde este worktree, con un run **sintético** propio:

```powershell
python docs/automation/mcp_native_primitives_smoke.py
python docs/automation/masterplan/seal_cad_run.py target/mcp-isolated/<run> target/debug/OpenCADStudio.exe
python docs/automation/masterplan/seal_cad_run.py target/mcp-isolated/<run> target/debug/OpenCADStudio.exe --verify
```

El run `20260923-213433-3a2932b3` pasó el L2; su sello local quedó `partial` por gates de imagen, motor externo y revisión humana. El sello contiene hashes y resúmenes sanitizados, no binarios, rutas de perfil, tokens ni transcript. No es firma criptográfica ni prueba independiente de interoperabilidad. El coste facturado permanece `null` y la identidad del modelo `unknown` cuando el run CAD no incluye telemetría confiable de un LLM. La herramienta de uso histórico `usage_evidence.py` es independiente y deduplica por respuesta sin copiar el rollout privado.
