# M7.3: repetibilidad exploratoria de la puerta noreste

Fecha: 2026-09-25. Alcance: una sola región **ya vista** de `Páginas de Volumenes 1_1.jpg`, sin CAD nuevo. No constituye cohorte reservada, evaluación integral ni aceptación M7. El DWG privado no se abrió ni se modificó.

`m7_door_repeatability.py` congeló antes de ejecutar el recorte histórico 8× `(1040,475)–(1170,575)`, fuente SHA `0CD0B310FC337C18704B658B41DF49ABB63E2F398893273BBFCFD503B2134057`, recorte SHA `0E153FE5A1B8B923446C2AEC62CEC4713274564EC5759BD91DD8B7E750C73ED2`, oráculo previo a la primera observación `(1090,501),(1090,550),(1145,550)` ±8 px y los dos prompts históricos de [M7-APARTAMENTO-PUERTA-NORESTE-V1.md](M7-APARTAMENTO-PUERTA-NORESTE-V1.md). Freeze `target/mcp-cli-development/northeast-door-repeatability-v1/freeze.json`, SHA `483E3A45F25E2B242678DF01913FE0213078A204B9EB1240550EC84DEDA63C8A`.

Se intercalaron `baseline,candidate` tres veces con `gpt-6-luna` medium solicitado por Codex CLI, solo lectura y sin timeout corto. Cada casilla tuvo intención durable antes de una sola llamada; eventos, stderr, tiempo y uso agregado CLI quedaron fuera de Git. No hubo reintentos ni sustitución de resultados. El intento de repetir `slot-00` fue rechazado por la raíz ya existente antes de llamar a Luna. El candidato es el prompt v2 **ajustado tras el fallo v1**; la comparación favorece al candidato y sigue siendo exploratoria.

| Prompt | Aciertos ±8 px | Abstenciones | Mediana | p95 nearest-rank (n=3) | Tokens entrada/salida CLI |
|---|---:|---:|---:|---:|---:|
| Inicial v1 | 0/3 | 0 | 6.741713 s | 16.619229 s | 65,850 / 156 |
| Corregido v2 | 1/3 | 0 | 6.778887 s | 6.803504 s | 66,027 / 156 |

Los tres fallos v1 eligieron la punta en el trazo superior corto, alrededor de `(1109,501)`. El v2 acertó una vez `(1145.375,548.5)`, pero en dos repeticiones devolvió puntas cortas cerca de `(1109,549)`. Los centros de ambas jambas sí permanecieron dentro del oráculo en los seis intentos. El resultado único exitoso de v2 del corte original sigue siendo válido como observación aislada, pero **no demuestra repetibilidad**. El evaluador clasificó las cinco respuestas fallidas antes de cualquier ejecución CAD; la regla tipada del compilador existente confronta punta, bisagra y longitud de abertura. Ninguna de estas seis respuestas se promovió a PlanSpec ni a CAD.

Resumen `target/mcp-cli-development/northeast-door-repeatability-v1/summary.json`, SHA `A16AC7F2ECD3FC917E09F37F1EF0CB0B503EC764D41D67A83AD1C035AEF57E45`. Sus seis registros enlazan hashes de intentos, eventos y resultados. Tres pruebas del evaluador cubren acierto, punta corta y abstención; la suite completa se verifica en el checkpoint. El CLI informa solo el modelo solicitado y uso agregado, no identidad efectiva ni recibo directo del proveedor. Una región conocida, tres repeticiones por brazo, caché y latencias variables impiden inferencia de velocidad/costo hasta aceptación. El siguiente diseño debe desambiguar geométricamente el símbolo o abstenerse; no tratar otro ajuste de prompt en esta misma región como evidencia ciega.

Revisión sin repetir llamadas: ejecutar `python docs/automation/masterplan/m7_door_repeatability.py summarize --root target/mcp-cli-development/northeast-door-repeatability-v1 --source <ruta-de-Páginas-de-Volumenes-1_1.jpg> --cli <ruta-del-codex-cli>` y cotejar el resumen con el SHA anterior. No invocar de nuevo `run-slot` sobre las seis intenciones consumidas.
