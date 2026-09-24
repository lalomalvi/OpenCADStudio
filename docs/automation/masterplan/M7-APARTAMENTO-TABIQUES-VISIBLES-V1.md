# M7 desarrollo: tres tabiques visibles sobre el contorno de departamentos

Fecha: 2026-09-24. Fuente: imagen de departamentos ya vista en desarrollo, SHA-256 `0CD0B310FC337C18704B658B41DF49ABB63E2F398893273BBFCFD503B2134057`. Ninguna imagen ni salida del modelo se incorpora a Git. Este trabajo **no** es cohorte inédita ni aceptación M7. La fuente y el DWG privado del usuario no se modificaron.

## Intentos conservados

| Run local | Resultado |
|---|---|
| `apartment-interior-wall-discovery-v1` | Luna devolvió seis bandas. Revisión de fuente del asistente: las primeras tres corresponden a tabiques visibles; la cuarta atraviesa una abertura y las dos últimas invaden el contorno del baño. Sin CAD. Eventos SHA `CAA115413C672359E73B028594BE265C4A90177AF56CB7B6448BAB33C886180F`. |
| `apartment-interior-walls-v2` | Oráculo visual de tres bandas congelado antes de llamar a Luna, freeze SHA `EE7A0B9EA15C750B089D616807765D405A9526794F847093F3196242856D8CE1`. Luna confundió la pared de entrada con la primera división. `failed_plan_gate`, sin CAD; reporte SHA `F5A4727A2E98194D7C6EDF067199A86F1B3A3CA8150150DCA16D081CF51425B2`. |
| `apartment-interior-walls-v3` | Prompt supervisado con tres zonas aproximadas, freeze SHA `C613702AF6B5F5F996F6CCDFB8626D78829DF14DB21A5F264E527566BBBD9CA7`. Luna unió la banda de entrada con la segunda división y empezó la tercera en B; `failed_plan_gate`, sin CAD; reporte SHA `AA616FE0A08585F520DAAA29BBB42938BC92D9F01815B13E0A3A886F86744300`. |
| `apartment-interior-walls-derived-v1` | Se **seleccionaron después de ver el resultado** los primeros tres segmentos del descubrimiento v1. No es una cuarta muestra de Luna ni un pase ciego. Freeze SHA `F7245FE2D196E86E162B12CB391257C258B837C1DBDE70E60F6FDCFC7F9C6AE3`; reporte L2 SHA `C146D2D4146FAA05D9D3BD43FC8BBAD2333549E3D41016C4C829734716084F90`. |

`pixel_interior_walls.py` exige tres segmentos verticales numerados, extremos próximos al oráculo visual, longitud mínima, banda superior e imagen/calibración válidas. Compila centros de línea, no polígonos de muro. El run derivado une esos tres LINE con los trece del perímetro v3 congelado; `model_reuse.selection` marca la selección posterior. GUI hija propia guardó/reabrió, produjo 16 LINE y cerró. DWG SHA `1A4A324C9F5A954F0CA02A6F3F724E3FB3964426A1DCD4FC87C0A7A647B8ED47`; captura SHA `E01C745AC899B69D6EF498836D205C6C3376E90F87C7E7CA80B5D2A16D854774`.

AutoCAD Core Console sobre una copia sintética auditó 0 errores/0 correcciones, `INSUNITS=6`, 16 LINE y hash de entrada intacto; reporte SHA `007623C080CC8A805EF5F8950F554070E27CF7004609878202710858042A602A`. `interior_walls_l4.py` cotejó por handle 16/16 extremos a 1e-6; veredicto SHA `671B58F53E883A7E55A1812BF74D7FAF4F9592A2150C6057CA34A9FCBD3C7AC1`. Una copia del censo con un extremo de `wall1` adulterado y hash coherente falló 15/16; veredicto SHA `093AB563CF3C083D177B598ABACC75EFB677655FD2050ABF28481BDA5415120E`.

La captura CAD es un **esqueleto parcial**. Faltan tabiques horizontales segmentados por huecos, puertas/ventanas, baño/cocina, cotas asociadas a esta planta, semántica de espesor y mobiliario. La revisión visual es del asistente, no L5 humana. La telemetría JSONL de Codex CLI no certifica identidad efectiva ni da recibo directo de Responses. Dos nuevos prompts fallaron incluso bajo supervisión; ningún dato justifica la aceptación de M7 o M8.

## Continuación concreta

Congelar en una nueva versión el oráculo para las bandas horizontales y los huecos de esta misma imagen antes del próximo modelo; separar una línea por cada tramo sólido. Comprobar cruce de aberturas y solape con el perímetro antes de CAD, conservar toda abstención y comparar por fuente, captura y AutoCAD. La cohorte de cinco imágenes sigue siendo desarrollo; no pedir otra imagen ni API. Mantener pendientes L5, uso/modelo directo, plano integral y comparación baseline/candidato.
