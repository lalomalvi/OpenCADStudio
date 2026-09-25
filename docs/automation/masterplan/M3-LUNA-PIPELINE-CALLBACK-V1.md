# M3/M7 — callback reservado Luna a CAD v1

`luna_pipeline.run_reserved_pipeline` exige adaptadores construidos antes de `run_once`. El journal reserva una casilla y llama una sola vez a `request_luna_once`; la respuesta directa pasa por `interpret_response`, con versión y límite de comandos fijados por el caller. Solo entonces entrega el compilado al ejecutor CAD inyectado. El supervisor inyectado recibe la ruta de evidencia CAD, nunca el oráculo reservado. Los dos objetos directos de Responses permanecen en memoria y `Observation` transmite sus recibos para el sobre sanitizado.

Una excepción tras la reserva, incluido JSON inválido, cambio de modelo, timeout CAD o fallo del supervisor, consume la casilla como `uncertain`. No hay bucles de reintento. Si falta supervisor, el resultado no alcanza `completed`; aun con ambos recibos, `completed` conserva `gates=unevaluated` y no acredita calidad.

Las pruebas L0 con adaptadores falsos comprueban orden, una sola llamada Luna, PlanSpec inválido sin CAD, pérdida de respuesta CAD sin repetición, y rechazo de cliente con reintentos antes de reservar. El ejecutor CAD real, su identidad de GUI/documento y el cliente supervisor directo siguen pendientes; esta frontera inyectada aún no demuestra L2, L3 ni evaluación G0–G10. No se abrieron imágenes privadas ni DWG.
