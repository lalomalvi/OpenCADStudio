# M7 desarrollo: segundo pase sobre las cinco imágenes disponibles

Fecha: 2026-09-24. Se usó Codex CLI con modelo solicitado `gpt-6-luna`, esfuerzo `medium`, imagen adjunta, sesión efímera, sandbox de solo lectura y configuración de usuario ignorada. Las llamadas no tuvieron un timeout breve impuesto por el evaluador. El CLI conserva JSONL y tokens agregados, pero no entrega identidad efectiva autenticada ni recibo Responses individual. Cada nuevo prompt y criterio visual se congeló localmente antes de invocar. Todas las fuentes, prompts, resultados, DWG y PNG están en Downloads/`target`, fuera de Git.

## Resultado por imagen

| Imagen de desarrollo | Mejor alcance verificado hasta ahora | Estado |
|---|---|---|
| Sección de escalera | El segundo pase, limitado a cota horizontal inferior y desnivel de niveles, devolvió `UNSUPPORTED`; reporte `target/mcp-cli-development/section-level-reference-v1/report.json` SHA-256 `E2ADD6CAE792D7E19DCC59D10ECD480CD4D88828FA383F4576FC839B5570F968`. No hubo CAD. El primer pase métrico fallido y abstenciones intermedias se conservan. | `abstained` en este pase |
| Caseta administrativa | Luna extrajo anchos consecutivos 3.50, 4.00, 4.00, 3.50, 2.85 m y profundidad de referencia 3.70 m. El compilador produjo retícula inferida de cinco franjas (12 nodos, 16 LINE), L2 cerrado y AutoCAD L4 16/16. | `partial_scoped` |
| Recámaras | El pase previo de dos anchos más profundidad produjo una retícula de dos franjas con AutoCAD L4; se conserva sin repetir. | `partial_scoped` |
| Departamentos | Luna extrajo seis cotas inferiores entre ejes 1–7: 2.58, 2.85, 2.58, 2.85, 1.00, 2.00 m. Compilación determinista: seis cotas nativas y total calculado 13.86 m, con soporte geométrico **inferido y solo de referencia**. L2 cerrado; AutoCAD L4 cotejó cuatro LINE y siete DIMENSION, 11/11. | `partial_scoped` |
| Cimentación | El pase anterior de una franja de referencia pasó CAD/AutoCAD 4/4; se conserva sin repetir. | `partial_scoped` |

La retícula de la caseta aplica la profundidad impresa de la caseta a las cinco franjas solo como convención de referencia: no demuestra profundidades, muros, puertas ni sanitarios de los otros recintos. El soporte dibujado bajo la cadena de departamentos no afirma un muro real en la imagen. Las capturas inspeccionadas muestran geometría de referencia; los textos de las cotas de departamentos son demasiado pequeños para aprobar legibilidad L5. La revisión posterior de cajas exactas se registra en [M6-CAJAS-DE-TEXTO-FUENTE-V1.md](M6-CAJAS-DE-TEXTO-FUENTE-V1.md): 5/6 cajas de caseta y 2/6 de departamentos contienen completo el texto; ambos casos fallan procedencia de caja. No hubo oráculo visual independiente ni L5.

## Evidencia del segundo pase

| Caso | Fuente congelada y salida | L2 y L4 | Negativo |
|---|---|---|---|
| Caseta, cinco franjas | Freeze `0C57D41E1892C7643A5ED84253DC2F6E2C167B640A101A06D6A5389EFB6763B5`; JSONL `E7CC73D3066E5113E133D923F856048BD1C9BBD7F78FEC6564384FE0F6D8B987` | Reporte `43AC5FA069422D325B8311F13AB60B5E13043250A9575461C0F7CE9B1850E953`; DWG `F62FE5E54C73A48A871F528EE8D8E7976B13ED72D07D28A5B3A9D28A07CECE14`; AutoCAD `0F2FC411820BB7488EF896001DD753C798B36B355D7E50222C4DA1086DAC7B19`; veredicto 16/16 `BF22B2FE1E112E8F27AF0D726F2B6473146A1141CB7CBF3C891EEA3D08339F4B` | Copia con extremo alterado 15/16, veredicto `7D6C5C73329FF98586457731CC772EDDF63CF222F4252DCB07E1E9D22DB9F7AA` |
| Departamentos, seis tramos | Freeze `A673CDFA98AE812FCD1FF32909ECAA4B96CEFEB0CD8B3C44EE3F0E86B3BF4B4C`; JSONL `4F586938B5D0BE6F3D87B2D1285082DB7966B70A3070C6EC278EF6B775843C4F` | Reporte `1F72D2E0C9F4ABE649A52353FD3E862EB0070731F0957335E40FA658145231F1`; DWG `21C1399DA1CF31702202D8567171C4FB7E2A8AB4D31474758D5B1958974B09B0`; AutoCAD `36FB268B88CFB010FFF041CF3FE839E95F68342FB856A5A474169B4720536149`; veredicto 11/11 `E7323A39441BF3710230DD6FAD0CC3CAC9DBBA5481E3753EEFFF52363982C920` | Copia con referencia DXF14 alterada 10/11, veredicto `6A01071CA6A9360231DEC50EF072A2F00D5A17DE301BA95DC7FD1F3B6BBC6D9C` |

El uso CLI agregado fue 16,385 entrada/148 salida en caseta; 17,688 entrada/218 salida en departamentos; 16,410 entrada/6 salida en la abstención de sección. Esto no es facturación ni uso directo del proveedor. El resultado de las cinco imágenes es **4 parciales acotados y 1 abstención en el mejor pase**, no cinco planos reconstruidos ni una cohorte inédita. El sexto detalle permanece como ensayo histórico de desarrollo. M7 y M8 siguen abiertos: faltan fidelidad de lámina completa, identidad/uso Responses directos, baseline/candidato comparable, supervisor, L5 y gates G0–G10.
