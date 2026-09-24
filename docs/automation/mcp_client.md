# Cliente MCP persistente — M1 y primer corte M2

`mcp_client.py` abre un único proceso `OpenCADStudio --mcp` por instancia, negocia `2026-07-28` con `server/discover`, comprueba Tasks, correlaciona respuestas JSON-RPC por ID aunque lleguen fuera de orden y drena `stderr` sin publicarlo. La cola se limita a 64 solicitudes pendientes. Cada RPC tiene timeout monotónico; los Tasks tienen deadline total. EOF, JSON inválido y respuestas sin estructura fallan cerrado.

`ready_session(launch_if_none=True)` consume `absent`, `starting`, `ready` y `failed`; respeta `retry_after_ms`, el deadline y un único intento de lanzamiento. Una sesión ambigua exige `session_id` explícito. El servidor publica PID, ejecutable e instante de creación del proceso obtenido del SO en Windows, sin token. Al conectar la sesión seleccionada, valida el ID hexadecimal, rechaza enlaces en el descriptor y hace un nuevo handshake autenticado. El sondeo inicial usa hasta 16 workers y 250 ms por descriptor. Diez repeticiones locales con 100 descriptores sintéticos muertos dieron p50 1869.7 ms y p95 conservador 1909.1 ms; es una medición de esta máquina, no una garantía de producción.

Todas las llamadas `tool("ocs_execute", ...)` de los harnesses pasan por `mutate`. El cliente exige `request_id`, rechaza reutilizarlo con otro contenido y conserva un journal en memoria. Usa `document_id` y `revision` de la sesión leída. Si se pierde una respuesta, consulta `ocs_read operation` con el mismo ID; jamás reenvía la mutación. El servidor guarda el progreso de `batch` y `run_script` en `automation/batch-journal` del perfil local mediante reemplazo atómico y `sync_all` antes de cada paso. Tras reiniciar solo el proceso MCP, la consulta carga el journal exacto, pregunta por el paso activo en la GUI y continúa con la revisión esperada. Un journal corrupto, una operación no verificable o una revisión cambiada detienen nuevas ediciones. El journal contiene comandos y resultados locales, sin token; no se publica ni se copia a Git. La recuperación tras reinicio de GUI sigue sin aceptar.

Los tres harnesses `mcp_eval.py`, `mcp_acceptance.py` y `mcp_reconstruction_eval.py` reutilizan el mismo transporte. `mcp_smoke.py` conserva solicitudes JSON crudas para validar el wire format independientemente. `waiting_input` bloquea ediciones posteriores cuando procede de un comando; `close_modal` puede revelar otro modal y exige releer `state`. Los harnesses antiguos aún carecen de política de propiedad/cierre y no se ejecutan contra sesiones de usuario en este corte.

Reproducción L1 sin CAD ni planos privados:

```sh
python -m unittest discover -s docs/automation -p test_mcp_client.py -v
python -m py_compile docs/automation/mcp_client.py docs/automation/mcp_eval.py docs/automation/mcp_acceptance.py docs/automation/mcp_reconstruction_eval.py
cargo test --lib mcp::tests
cargo build --bin OpenCADStudio
python docs/automation/mcp_isolated_smoke.py
```

El fixture `tests/fixtures/mcp_stdio_fake.py` cubre arranque lento, sesiones ambiguas, respuestas fuera de orden, pérdida de respuesta tras un efecto, lote en curso, operación desconocida, modal encadenado, fallo explícito, EOF, JSON inválido y presión en `stderr`. El L2 usa un perfil hijo propio en `target/mcp-isolated`: identifica PID/binario, crea tres entidades sintéticas, audita, guarda DWG verificado, coteja SHA-256 y confirma salida. Los reportes y DWG sintéticos quedan fuera de Git. Los fallos iniciales se conservan como fallos. No se abrió el DWG del usuario.

`shutdown_owned_session` es una operación del servidor, no un `QUIT` genérico. Solo se admite cuando este mismo proceso MCP lanzó la GUI; exige PID, hora de creación del SO, ejecutable y `owned_root` canonicalizado. Relee el estado, rechaza modales, comandos activos, documentos sucios y archivos fuera de esa raíz. La cola de la GUI repite esas comprobaciones inmediatamente antes del cierre. El servidor confirma la salida del proceso hijo y devuelve la misma respuesta al repetir el ID. `mcp_owned_shutdown_smoke.py` comprobó rechazos dirty/foreign y cierre propio L2. Quedan pendientes cierre explícito de pestañas, heartbeat, ACL Windows y cuarentena de descriptores.

`mcp_journal_restart_smoke.py` conserva la GUI sintética, corta el proceso MCP con el primer paso aún en curso, inicia otro MCP en el mismo perfil, consulta el lote por ID y confirma tres entidades en el DWG verificado. No recupera sesiones ajenas ni presupone que una GUI reiniciada preserve operaciones en memoria. Los directorios de fallos anteriores se conservan aparte.
