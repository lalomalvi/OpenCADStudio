# M7 desarrollo: mediciones tipadas a retícula de referencia

Estado: desarrollo exploratorio sobre una imagen ya vista; **no** constituye aceptación M7 ni reconstrucción arquitectónica completa.

## Contrato

`measurement_grid.compile_two_bay` recibe tres longitudes, tres regiones de procedencia en píxeles y confianza. Exige esquema cerrado, números finitos y positivos, regiones dentro de la imagen y concordancia de las longitudes con el oráculo privado congelado antes de la llamada al modelo. La salida es un PlanSpec-1 determinista con seis nodos y siete LINE: perímetro de dos recintos y un separador. Las entidades llevan `classification: inferred`. No se dibujan ni se afirman muros, puertas, espesores, mobiliario o asociaciones de cotas.

`cli_development_trial.py` vincula imagen, prompt, binario, validador y compilador por SHA-256 antes del gate. El comparador de grafo exige coordenadas, aristas y dos regiones cerradas frente al oráculo privado. `cli_development_l4.py` admite un número acotado de LINE y compara cada handle del ejecutor con tipo, capa y extremos en el censo AutoCAD. Los valores de las imágenes, prompts, oráculos, eventos, DWG y capturas permanecen en `target/` ignorado; las pruebas versionadas usan cifras sintéticas distintas.

## Evidencia del corte

Dos solicitudes anteriores de PlanSpec multirrecinto, con prompts y validadores congelados, devolvieron `UNSUPPORTED`; se conservaron como abstenciones separadas y no se reinterpretaron. En una tercera solicitud, Luna mediante Codex CLI entregó el objeto de mediciones. El contrato tipado y el gate de grafo pasaron; OpenCADStudio generó siete LINE y cerró su GUI hija tras guardar el documento sucio. AutoCAD Core Console auditó sin errores, confirmó unidades métricas y contó siete LINE; el cotejo por handle y extremos dio 7/7. Un censo copiado con un extremo adulterado dio 6/7 y `failed_scoped_l4`. La captura fue inspeccionada como retícula de referencia.

El CLI informa uso agregado del turno, pero no entrega un recibo Responses de la llamada ni confirma el modelo efectivo. Quedan abiertos G0/G10, revisión L5, procedencia visual independiente, comparación baseline/candidato, fidelidad del plano completo y experimento reservado. Todas las imágenes disponibles ya son `development_seen`; el usuario no dispone de una sexta inédita. Para nuevos intentos, congelar un protocolo nuevo y conservar cada fallo sin repetir efectos CAD inciertos.
