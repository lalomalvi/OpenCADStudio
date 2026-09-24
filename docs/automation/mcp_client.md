# Cliente MCP persistente — M1 y primer corte M2

`mcp_client.py` abre un único proceso `OpenCADStudio --mcp` por instancia, negocia `2026-07-28` con `server/discover`, comprueba Tasks, correlaciona respuestas JSON-RPC por ID aunque lleguen fuera de orden y drena `stderr` sin publicarlo. La cola se limita a 64 solicitudes pendientes. Cada RPC tiene timeout monotónico; los Tasks tienen deadline total. EOF, JSON inválido y respuestas sin estructura fallan cerrado.

`ready_session(launch_if_none=True)` consume `absent`, `starting`, `ready` y `failed`; respeta `retry_after_ms`, el deadline y un único intento de lanzamiento. Una sesión ambigua exige `session_id` explícito. El servidor publica PID, ejecutable e instante de creación del proceso obtenido del SO en Windows, sin token. Al conectar la sesión seleccionada, valida el ID hexadecimal, rechaza enlaces en el descriptor y hace un nuevo handshake autenticado. El sondeo inicial usa hasta 16 workers y 250 ms por descriptor. Diez repeticiones locales con 100 descriptores sintéticos muertos dieron p50 1869.7 ms y p95 conservador 1909.1 ms; es una medición de esta máquina, no una garantía de producción.

Todas las llamadas `tool("ocs_execute", ...)` de los harnesses pasan por `mutate`. El cliente exige `request_id`, rechaza reutilizarlo con otro contenido y conserva un journal en memoria. Usa `document_id` y `revision` de la sesión leída. Si se pierde una respuesta, consulta `ocs_read operation` con el mismo ID; jamás reenvía la mutación. El servidor conserva el progreso de `batch` y `run_script` en el proceso MCP; la consulta puede avanzar desde el siguiente paso. Si muere ese proceso, el progreso en memoria se pierde: journal durable y conciliación entre procesos siguen pendientes. Una operación no verificable produce `UncertainMutation` y detiene nuevas ediciones.

Los tres harnesses `mcp_eval.py`, `mcp_acceptance.py` y `mcp_reconstruction_eval.py` reutilizan el mismo transporte. `mcp_smoke.py` conserva solicitudes JSON crudas para validar el wire format independientemente. `waiting_input` bloquea ediciones posteriores cuando procede de un comando; `close_modal` puede revelar otro modal y exige releer `state`. Los harnesses antiguos aún carecen de política de propiedad/cierre y no se ejecutan contra sesiones de usuario en este corte.

Reproducción L1 sin CAD ni planos privados:

```sh
python -m unittest discover -s docs/automation -p test_mcp_client.py -v
python -m py_compile docs/automation/mcp_client.py docs/automation/mcp_eval.py docs/automation/mcp_acceptance.py docs/automation/mcp_reconstruction_eval.py
cargo test --lib mcp::tests
cargo build --bin OpenCADStudio
python docs/automation/mcp_isolated_smoke.py
```

El fixture `tests/fixtures/mcp_stdio_fake.py` cubre arranque lento, sesiones ambiguas, respuestas fuera de orden, pérdida de respuesta tras un efecto, lote en curso, operación desconocida, modal encadenado, fallo explícito, EOF, JSON inválido y presión en `stderr`. El L2 usa un perfil hijo propio en `target/mcp-isolated`: identifica PID/binario, crea tres entidades sintéticas, audita, guarda DWG verificado, coteja SHA-256 y confirma salida. Los reportes y DWG sintéticos quedan fuera de Git. Los dos fallos iniciales se conservan como fallos. No se abrió el DWG del usuario. `mcp_cleanup_isolated.py` solo se usa con directorio y PID propios; informa si QUIT fue rechazado desde Start. Cierre propio formal, política de documento sucio, heartbeat y cuarentena siguen pendientes en M2.
