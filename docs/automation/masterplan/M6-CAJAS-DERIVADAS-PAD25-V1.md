# M6.5: cajas derivadas con margen fijo de 25 píxeles

Fecha: 2026-09-24. Tras observar que las cajas originales de Luna recortaban dígitos, se construyó un **nuevo corte exploratorio** con `source_text_crops.py --padding 25`. La transformación es determinista: expandir cada lado 25 píxeles, acotar a las dimensiones de la imagen y conservar tanto `model_region_px` como `region_px` derivada, con hash de los píxeles RGB. No se modifica la salida Luna ni el DWG. El margen se eligió después del fallo; por tanto no es una aceptación precongelada M7 ni un algoritmo general validado.

| Caso | Caja original | Caja derivada, juicio visual del asistente | Evidencia local |
|---|---:|---:|---|
| Caseta administrativa | 5/6; profundidad recortada | 6/6 textos completos, incluida la cota vertical `3.70` | `target/mcp-cli-development/admin-five-bay-measurements-v1/source-box-derived-pad25-v1/review.json`, SHA-256 `78D66EDCB242321BF8BA6090580DE4E45A283E15D827176210AC84293598EEFD`; hoja SHA-256 `475ADAE57A443319726F9F530A38B95804206648EDA4463B3F372D0381DDCB3A` |
| Departamentos | 2/6; cuatro tramos recortados | 6/6 textos completos en el orden de ejes 1–7 | `target/mcp-cli-development/apartment-bottom-chain-v1/source-box-derived-pad25-v1/review.json`, SHA-256 `75457A0FED8F1A35552A850BA7082E61F3F57107E611D30ED13853C30025B25E`; hoja SHA-256 `08A52FCD90DBEC1E23A40BF24F7E5DF567653C3B35024A823157BCA9B5CE786B` |

El verificador recalcula la expansión desde las cajas del evento CLI y la imagen congelada, coteja hashes de fuente, freeze, eventos, manifiesto, hoja y cada recorte, y exige consistencia del juicio con el conteo. El juicio `assistant_visual_manual` es del asistente; no es OCR independiente, correspondencia semántica completa ni revisión humana L5. La geometría L2/L4 de los dos runs sigue acotada a referencias, con textos CAD demasiado pequeños para aprobar legibilidad.

Reproducción local:

```powershell
python docs/automation/masterplan/source_text_crops.py --run-root target/mcp-cli-development/admin-five-bay-measurements-v1 --image '<Screenshot_2.png en Downloads>' --verify-review target/mcp-cli-development/admin-five-bay-measurements-v1/source-box-derived-pad25-v1/review.json
python docs/automation/masterplan/source_text_crops.py --run-root target/mcp-cli-development/apartment-bottom-chain-v1 --image '<imagen de departamentos en Downloads>' --verify-review target/mcp-cli-development/apartment-bottom-chain-v1/source-box-derived-pad25-v1/review.json
```

El siguiente gate requiere evaluar el margen con casos adversariales y otras fuentes sin elegirlo después de mirar el resultado, además de legibilidad CAD y L5. Los fallos de las cajas originales permanecen en [M6-CAJAS-DE-TEXTO-FUENTE-V1.md](M6-CAJAS-DE-TEXTO-FUENTE-V1.md).
