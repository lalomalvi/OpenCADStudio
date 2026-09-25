# M1: pérdida de GUI propia durante lote sintético

Estado: `passed_fail_closed` L2 acotado; recuperación completa de GUI no aceptada.

## Protocolo

`docs/automation/mcp_gui_loss_smoke.py` crea un perfil nuevo bajo `target/mcp-isolated`, arranca una GUI hija propia y verifica PID y ejecutable del descriptor seleccionado. Crea un documento vacío y envía un `run_script` de 60 líneas sintéticas con `wait_seconds=0`. Exige respuesta `running` y un journal durable antes de terminar **solo** el proceso `Popen` que creó. Después consulta la operación por ID una vez y prueba que una mutación nueva de la misma sesión se bloquee localmente, sin alcanzar `ocs_execute`. No abre ni guarda el DWG privado ni usa imágenes.

## Resultado observado

- Binario debug SHA-256 `C9B62173B628D56B70DC86B18FC3D35A8D85988EAD173AE9568E78BEE2EC6F02`.
- Run `target/mcp-isolated/20260925-030448-gui-loss-a7cbcbcd`; reporte `gui-loss-report.json` SHA-256 `08D64FE569A5AE7331C912951079255BCB127A6C22A58F843293A3C83A71A103`.
- PID propio 2816, sesión `33fc415760862004d08f988adb81c4ce`; respuesta inicial `running`, `completed_commands=0`, request ID `gui-loss-batch-784befa6923d40c2b13c5e92d817eaff`.
- El journal existía antes de perder la GUI; SHA-256 en ese instante `F190B85C12B31E395CFA16183E6D4ABF2ADBEF9939DFC3231977E5E7D26D9C81`.
- La GUI terminó con código 1. La consulta de recuperación devolvió `ToolError`, código `invalid_arguments`, tras una sola llamada de lectura. La mutación posterior devolvió `UncertainMutation` y **no** produjo otra llamada a herramienta.
- `py_compile` del arnés y `git diff --check` pasaron. Reporte y perfil permanecen fuera de Git.

Esta prueba confirma **cierre seguro** ante la pérdida de esa GUI. No reconstruye una operación en una GUI nueva ni demuestra que los 60 comandos se completaron o guardaron; el lote era deliberadamente incierto. Un protocolo futuro de recuperación deberá conciliar el journal, documento, revisión y operaciones realmente persistidas antes de permitir cualquier continuación. Ningún reenvío automático de la mutación original está autorizado por este resultado.
