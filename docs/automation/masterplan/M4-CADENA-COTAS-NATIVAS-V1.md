# M4.3/M5.3: cadena sintética de cotas nativas v1

Fecha: 2026-09-24. Alcance probado: un muro horizontal recto de 4 m, sin aperturas ni uniones, con tres cotas de eje `DIMLINEAR` (1.5 m, 1.5 m y 3.0 m). Las referencias declaradas se validan contra el mismo muro y sus estaciones; el grafo v3 rechaza conflictos acumulados antes de enviar comandos CAD.

`dry_run` de PlanSpec v8/v9 compila de dos a ocho cotas de eje de un solo muro positivo horizontal o vertical. Ordena los comandos por estación e ID, conserva capas y estilo, verifica que la línea quede fuera del espesor del muro y rechaza cotas superpuestas cuando sus rangos se cruzan y sus offsets están demasiado próximos. El alcance de QA de posición es la línea de cota en 2D; no mide cajas de texto, flechas ni colisiones visuales completas.

## Evidencia congelada

| Gate | Resultado | Evidencia local |
|---|---|---|
| L0 | 136/136 pruebas masterplan, 32/32 automatización; fixture SHA-256 `0778F86459F7220898C139121834431333920D59D87ABD9143837CC442FF9145`; conflicto de cierre, solape y línea interior bloqueados | `fixtures/synthetic-wall-axis-chain-v8.planspec.json` |
| L2 | `passed_l2_internal`; GUI hija cerrada; 3 medidas nativas 1.5/1.5/3.0 m iguales antes y después de guardar/reabrir | `target/mcp-multi-axis-chain/20260924-110134-aead407b/report.json`, SHA-256 `A35446AA2648A7DF212FB82F2616987566D9D7655A3BD23150BCA88D14200BE1` |
| L4 | AutoCAD Core Console 25.0.162.0.0: audit 0 errores/0 reparaciones, INSUNITS 6, siete entidades por handle y cotejo de extremos, medidas y referencias 7/7 | `target/mcp-external/20260924-110221-autocad-0d6d7875/report.json`, SHA-256 `991A11D76D9C759D5546859C1000618C0B9D27019ABB59BE46A28F1FEA3EB5E4`; `target/mcp-multi-axis-chain/20260924-110134-aead407b/external-verdict.json`, SHA-256 `69ECBE30028A4A17E377774B90AB52E52C731D68DF907CD34881F935CE6426D5` |
| L4 adversarial | Copia del censo y reporte con una referencia DXF14 alterada: 6/7, `failed_scoped_l4`, salida 1. Originales y DWG intactos | `target/mcp-multi-axis-chain/20260924-110134-aead407b/negative-census/negative-verdict.json`, SHA-256 `BD86DFFAD41726F43E6BC803BB7FB76EDD204C193D0DCFF4DE1598B290D0B496` |

El DWG sintético tiene SHA-256 `EC304D1F61C2EF9465E30854545775099B078C8A5CE807D0D52AF48E01BB8EE4`. La inspección de captura muestra muro y tres líneas de cota; la legibilidad de los textos, en particular la cota total, sigue pendiente de L5. No se ensayó una imagen fuente, Luna, el DWG privado ni un plano completo. La rama vertical y cualquier equivalencia entre muros siguen sin L2/L4. Esta evidencia no cierra M4.3/M5.3 general ni M7/M8.

## Reproducción

Desde la raíz del repositorio con el binario local compilado:

```powershell
python docs/automation/masterplan/multi_axis_chain_smoke.py
pwsh -NoProfile -File docs/automation/mcp_autocad_probe.ps1 -SyntheticDwg '<copia del DWG sintético de L2>' -ExpectedInsunits 6 -TimeoutSeconds 120
python docs/automation/masterplan/multi_axis_chain_l4.py --fixture docs/automation/masterplan/fixtures/synthetic-wall-axis-chain-v8.planspec.json --l2 '<reporte L2>' --external '<reporte AutoCAD>' --output '<veredicto nuevo>'
```

El probe externo opera sobre una copia sintética; no apuntar al DWG original del usuario. El comparador exige fuente inalterada, audit, unidades, conteo, tipos y concordancia por handle, medición DXF42, referencias DXF13/14 y posición DXF10 con tolerancia de 1e-6 m. Los reportes históricos quedan sin reinterpretar.
