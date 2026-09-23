# Cliente MCP persistente — corte M1 L1

`mcp_client.py` abre un único proceso `OpenCADStudio --mcp` por instancia, negocia `2026-07-28` con `server/discover`, comprueba Tasks, correlaciona respuestas JSON-RPC por ID aunque lleguen fuera de orden y drena `stderr` sin publicarlo. La cola se limita a 64 solicitudes pendientes. Cada RPC tiene timeout monotónico; los Tasks tienen deadline total. EOF, JSON inválido y respuestas sin estructura fallan cerrado.

`ready_session(launch_if_none=True)` hace un solo intento de arranque. Si el servidor informa `still starting`, sondea con backoff hasta el deadline sin lanzar otra GUI. Si hay más de una sesión, exige `session_id` explícito. El estado formal `starting/ready` con razón y `retry_after_ms` aún requiere contrato de servidor (M1.4 parcial).

Todas las llamadas `tool("ocs_execute", ...)` de los harnesses pasan por `mutate`. El cliente exige `request_id`, rechaza reutilizarlo con otro contenido y conserva un journal en memoria. Si se pierde la respuesta, consulta `ocs_read operation` con el mismo ID; jamás envía de nuevo la mutación. Una operación ausente, aún en curso o sin respuesta verificable produce `UncertainMutation` y detiene la escritura. `run_script` puede quedar incierto después de perder la respuesta porque la consulta nativa de operación no expone aún el estado del lote del servidor: queda para M1.6. El journal durable y la conciliación entre procesos son M3/M1 pendientes.

Los tres harnesses `mcp_eval.py`, `mcp_acceptance.py` y `mcp_reconstruction_eval.py` reutilizan el mismo transporte. `mcp_smoke.py` conserva solicitudes JSON crudas para validar el wire format de forma independiente. Los harnesses antiguos todavía eligen o cierran modales sin política de propiedad del documento; no se ejecutan contra sesiones de usuario en este corte. La comprobación de `document_id` y revisión antes de cada edición y el cierre controlado son pendientes de M1.5/M2.

Reproducción L1 sin CAD ni planos privados:

```sh
python -m unittest discover -s docs/automation -p test_mcp_client.py -v
python -m py_compile docs/automation/mcp_client.py docs/automation/mcp_eval.py docs/automation/mcp_acceptance.py docs/automation/mcp_reconstruction_eval.py
```

El fixture `tests/fixtures/mcp_stdio_fake.py` cubre arranque lento, sesiones ambiguas, respuestas fuera de orden, pérdida de respuesta tras un efecto, operación desconocida, fallo explícito, EOF, JSON inválido y presión en `stderr`. El smoke del binario de desarrollo existente comprueba el protocolo real sin lanzar GUI con `launch_if_none:false`. Es L1 real de stdio, no L2 CAD ni una nueva evaluación de imagen.
