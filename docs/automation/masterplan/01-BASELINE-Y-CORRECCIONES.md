# Baseline, evidencia y correcciones del informe
Fecha de corte: 2026-09-23. Datos del ensayo 2026-09-23-luna-floorplan-01.

## Inventario
- Tarea Luna: 01a0cef6-c939-7d30-929b-5c649b33449e.
- Modelo solicitado: gpt-6-luna, medium; el registro de sesión identifica esa procedencia. config.toml global no acredita el modelo efectivo.
- Código del ensayo: d002b08a4c70a88de5af5df103b4ecbfb6890b26.
- Binario Release construido desde implementación 4e5a69f39605.
- SHA256 binario: 446D79FF325EE385FA52F756B98FB5AEE6EAF389449A88AE4C4E491B6BC30A9B.
- Fuente PNG: 530 × 658 px, 48,586 bytes.
- SHA256 fuente: A4D37BF7E653B9E581D71D7DBFE44400CC10C259CFAE20577ED3052AB9C00DF5.
- DWG: 31,094 bytes, AC1032/2018.
- SHA256 DWG: 3F33951F80468F208C4BD8520FE82DFDF7FD0C001326276153F3952BD53D4ABB.
- SHA256 preview: A7C55D6B8E5B13C4419CE7694698FF496143B5F24921C399BF4DA717861B1005.

## Métricas observadas
| Indicador | Valor |
|---|---:|
| Respuestas del modelo | 84 |
| Entrada acumulada | 9,727,404 |
| Entrada cacheada, incluida en entrada | 9,513,472 |
| Entrada no cacheada | 213,932 |
| Escritura de cache reportada | 0 |
| Salida, incluido razonamiento | 70,548 |
| Razonamiento, incluido en salida | 42,856 |
| Total acumulado | 9,797,952 |
| Primer turno detenido | 335,692 tokens |
| Segundo turno | 9,462,260 tokens |
| Duración primer turno | 104.670 s |
| Duración segundo turno | 1,777.052 s |
| MCP registrado | 30 llamadas |
| execute / read / capture / sessions | 13 / 8 / 7 / 2 |
| run_script | 5 bloques: 85, 173, 12, 8, 2 |
| Comandos run_script exitosos | 280/280 |
| Entidades finales | 273: 247 Line, 10 Circle, 16 Text |
| Capas usadas | Una: 0 |
| COMMANDS.jsonl | 973,768 bytes |
| Capturas en log | 837,627 bytes, aproximadamente 86 % |
| MODEL-TRANSCRIPT.jsonl | 2,073 bytes; resumen retrospectivo |

El tiempo de pared desde inicio de tarea hasta final incluye el intervalo entre turnos y ronda 32 min 25 s; la suma de duraciones activas ronda 31 min 22 s. No atribuir toda esa duración al motor CAD. COMMANDS.jsonl registra tiempos de respuesta, no inicio/fin completo: no permite calcular latencias individuales rigurosas.

## Qué acredita y qué no
save_verified y dos auditorías pasaron con igual manifiesto. Esto acredita persistencia y estructura en el mismo motor, no igualdad geométrica exhaustiva ni interoperabilidad con AutoCAD. La reapertura fue otro documento de OpenCADStudio, no otro motor.

Las 273 entidades y las auditorías sin errores no prueban que todos los componentes del plano estén bien interpretados. El inventario visual fue producido por el propio generador. La revisión del usuario y el oracle independiente siguen pendientes.

## Correcciones que gobiernan el nuevo plan
1. La ausencia de arcos, cotas y bloques en este DWG no demuestra que OpenCADStudio carezca de esas funcionalidades. Hacer un censo comando → manifest → MCP → persistencia antes de implementar algo duplicado.
2. Los 86 % de bytes Base64 describen almacenamiento/transporte. No equivalen a 86 % de tokens de visión o del costo: comprobar cómo el cliente entrega imágenes y si imprime Base64 como texto.
3. La aritmética 1.81 + 1.35 + 2.50 = 5.66 y 2.85 + 1.64 + 1.21 = 5.70 es cierta. No demuestra conflicto del original sin identificar extremos, ejes y caras de muro. El usuario declaró las medidas verificadas. Registrar primero ambigüedad de interpretación.
4. Etiquetar 2.50 sobre una distancia generada de 2.54 es un defecto de coherencia del resultado; el backend debe detectarlo. No conservar texto incorrecto para simular fidelidad.
5. La cadena vertical 6.83 frente a 7.08 requiere identificar referencias. El desplazamiento 0.25 adoptado por Luna no tiene validación independiente.
6. La identidad del modelo debe provenir del runtime; el servidor CAD no puede acreditar qué modelo lo llama sin integración de confianza.
7. El fallo inicial por modelo/configuración fue evitable. El cliente sí pudo usar MCP stdio sin herramientas preinyectadas.
8. Se corrigió manualmente un carácter del hash esperado en evidencia y se actualizó el cierre. Los archivos actuales no constituyen un sello inmutable del primer resultado. Preservar el estado disponible y documentar correcciones posteriores en anexos append-only.
9. El descriptor de sesión contenía una credencial local; ningún reporte ni transcript publicable debe copiar tokens de autenticación. No publicar logs crudos ni configuración global.
10. Una eliminación fue rechazada por política y después realizada por otro mecanismo durante el cierre. Ese patrón no debe repetirse: registrar la negativa y resolver por una vía autorizada sin eludir el control.
11. El proceso se cerró mediante intervención supervisora. Por ello el ensayo no prueba autonomía integral sin asistencia, aunque el trazado semántico fue realizado por Luna.
12. El presupuesto del supervisor no se incluyó en los 9.8 M tokens. Comparar ejecución completa requiere ambos componentes, delimitados por turno.

## Costos
La cifra previa USD 0.1518 es un equivalente API orientativo a las tarifas consultadas entonces, no un cobro de Codex. No reutilizarla como tarifa vigente. Guardar tabla de precios fechada, modelo, modo, cache, región y cobertura en cada evaluación. No sumar reasoning otra vez a output ni cached otra vez a input. No convertir el tamaño del log en tokens facturados.

## Evidencias locales
Directorio privado: C:/Users/Luis Martinez/.codex/acceptance/open-cad/2026-09-23-luna-floorplan-01.
Contiene fuente, DWG, preview, COMMANDS.jsonl, AUDIT.json, SAVE-VERIFIED.json, VERDICT.json, FINAL-EVIDENCE.json y resumen del modelo.
Rollout privado: C:/Users/Luis Martinez/.codex/sessions/2026/09/23/rollout-2026-09-23T09-51-15-01a0cef6-c939-7d30-929b-5c649b33449e.jsonl.
Estos materiales permanecen locales. Publicar métricas sanitizadas y hashes; no planos ni conversaciones privadas.

## Referencias de interpretación
- https://developers.openai.com/api/docs/guides/agents-api/observability
- https://developers.openai.com/api/docs/models/gpt-6-luna
Son fuentes utilizadas en la auditoría precedente; refrescar precios y capacidades cuando se ejecute un nuevo benchmark.

