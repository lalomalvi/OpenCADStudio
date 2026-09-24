# M6.5: revisión de cajas de texto de cota en imagen fuente

Fecha: 2026-09-24. `source_text_crops.py` verifica el hash de la imagen congelada, extrae exactamente los píxeles de cada `source_regions` devuelto por Luna y crea una hoja de contactos sin imprimir las medidas esperadas. El manifiesto contiene los hashes de píxeles por recorte; `--verify-review` coteja imagen, eventos, manifiesto, hoja y juicio visual. El juicio se identifica como `assistant_visual_manual`, nunca como OCR independiente ni L5 del usuario.

| Run de desarrollo | Resultado sobre las cajas originales | Evidencia local |
|---|---|---|
| Caseta, cinco franjas | 5/6 textos completos. La caja de profundidad contiene solo `70`; falta el `3.`. `failed_source_box_containment`. | `target/mcp-cli-development/admin-five-bay-measurements-v1/source-box-review-v1/review.json`, SHA-256 `1C995C93A072EC6779D30C48FAC1A787DF9890D998F5E536DDC49EC01A3B28FB`; hoja SHA-256 `4C83EB363722B428EEEE11645E3A625F1B0FDF688A69B4103E5B22674C9993C6` |
| Departamentos, seis cotas | 2/6 textos completos. En cuatro cajas se cortan dígitos iniciales o finales. `failed_source_box_containment`. | `target/mcp-cli-development/apartment-bottom-chain-v1/source-box-review-v1/review.json`, SHA-256 `31E88CB6819314FE3AD74F865E57764C65579EEC7620070775DAB7CA34E4BBF7`; hoja SHA-256 `C0EAD7412712B9F788D8926D164BF097EFC65F89B7663A23516DB4B04D426AFB` |

Los valores métricos coinciden con las cotas visibles en la imagen amplia, y AutoCAD cotejó la geometría de referencia, pero **la procedencia por cajas declarada por el modelo falla**. Los veredictos L2/L4 miden persistencia y geometría del alcance, no corrigen esta falla. No se alteraron ni los eventos Luna ni los DWG originales.

Un nuevo prompt de departamentos exigió que Luna encerrara íntegro cada texto con margen blanco. La respuesta fue `UNSUPPORTED`, sin CAD: `target/mcp-cli-development/apartment-bottom-chain-v2/report.json`, SHA-256 `0C7481828CFE794A812142F51E2FA5886DAB70057641BBD8695F9AAEBE8A9D6C`. Se conserva como un segundo intento separado; no reinterpreta el primero. M6.5 sigue parcial y G2 de M7 no pasa. Para continuar hay que generar cajas verificables o usar un mecanismo de correspondencia de fuente más fiable, con revisión visual humana L5.

Reproducción del vínculo y veredicto local, desde la raíz del repositorio:

```powershell
python docs/automation/masterplan/source_text_crops.py --run-root target/mcp-cli-development/admin-five-bay-measurements-v1 --image '<Screenshot_2.png en Downloads>' --verify-review target/mcp-cli-development/admin-five-bay-measurements-v1/source-box-review-v1/review.json
python docs/automation/masterplan/source_text_crops.py --run-root target/mcp-cli-development/apartment-bottom-chain-v1 --image '<imagen de departamentos en Downloads>' --verify-review target/mcp-cli-development/apartment-bottom-chain-v1/source-box-review-v1/review.json
```

Las hojas, juicios y nombres de fuente permanecen bajo `target/` ignorado. El código de verificación y este resumen no incluyen archivos privados.
