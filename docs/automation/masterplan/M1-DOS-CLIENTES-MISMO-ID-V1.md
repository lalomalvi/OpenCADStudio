# M1: dos procesos MCP, un request ID y una GUI sintética

Estado: `passed_no_duplicate` L2 acotado. La prueba demuestra una sola entidad; no promete resultado compartido entre procesos ni recuperación completa de GUI.

## Protocolo

`docs/automation/mcp_cross_client_smoke.py` crea un perfil nuevo bajo `target/mcp-isolated`, lanza una GUI hija propia y abre dos procesos MCP separados. Ambos autentican la misma sesión, comprobando PID y ejecutable. Tras crear un documento vacío, dos hilos liberados por la misma barrera envían la misma orden `LINE 0,0 10,0` con el mismo `request_id`, documento y revisión. El censo `ocs_read audit` debe encontrar exactamente un `Line`. Al terminar, el arnés cierra los MCP y termina solo su GUI hija. No lee imágenes ni DWG privado; no guarda un DWG.

## Evidencia

- Primer intento `20260925-035124-cross-client-c3ff4566`, reporte SHA `C51B5C4D00EC416C02ED8AD0481E9131EAB21105A4D2026A0D1A74209E7E624C`: falló **antes** de cualquier mutación porque el segundo cliente no vio la sesión en un sondeo inicial. Se preserva.
- Segundo intento con reintento de lectura solo en el arnés `20260925-035154-cross-client-fa4c5621`, reporte SHA `64E757B6DCC030A64F456F96EADCE593E4EBEB8AACA09F3565E675E777F3A431`: `passed_no_duplicate`.
- Se trasladó ese reintento acotado al cliente cuando `session_id` y `wait_for_existing=True`: una sesión seleccionada ausente de un único sondeo se vuelve a buscar sin `launch_if_none`. El test L1 `selected_transient` cubre el caso; la selección ambigua sigue fallando.
- Run con el nuevo cliente, desde el arnés versionado: `target/mcp-isolated/20260925-035332-cross-client-404bc190/report.json`, SHA `B8706B390E13C2B673772D6A699FDD69750E3803AD4047EFDFB2B5060A6687A5`. Binario debug SHA `C9B62173B628D56B70DC86B18FC3D35A8D85988EAD173AE9568E78BEE2EC6F02`. Una llamada devolvió `completed`; la otra `ToolError request_id_reused`. Auditoría 0 errores/0 advertencias, `manifest.total=1`, `by_type.Line=1`, GUI hija salida.
- Local: cliente 26/26, masterplan 202/202, automatización 45/45, `py_compile` del arnés y `git diff --check` pasaron.

La respuesta `request_id_reused` del segundo proceso se debe a que cada conexión tiene identidad de cliente propia. Se acepta como **fallo cerrado sin duplicar geometría**, no como un resultado idempotente compartido. El journal durable del servidor, la conciliación multiproceso tras un crash y la recuperación de una GUI perdida son contratos separados; esta prueba no los acepta en general.
