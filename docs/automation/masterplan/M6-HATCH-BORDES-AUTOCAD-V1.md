# M6.6: bordes HATCH en AutoCAD, corte 129

## Alcance y fuente

El fixture L2 histórico `target/mcp-isolated/20260923-224419-hatch-1bf27e3a/report.json` (SHA-256 `5FB661F0EAA3A8EB3A0CF9F0F3DEDD2A62A712A7E892A3F4D254EF176E5819E6`) contiene dos DWG sintéticos guardados y reabiertos. Antes de editar, la PLINE `64` tiene vértice (24,0); después de editarla internamente, tiene (25,0). El HATCH `65` declara un único camino de tres segmentos LINE y referencia a `64`.

La sonda `mcp_autocad_probe.ps1` ahora emite `HATCHEDGE` y `HATCHREF` a partir de `entget` en AutoCAD Core Console. El comparador `mcp_hatch_external_compare.py` exige SHA del censo reportado por la sonda, el SHA del DWG congelado, AUDIT 0/0, entrada intacta, tres bordes ordenados a 1e-6 y la referencia al contorno por handle. No admite otros caminos o tipos de borde en este corte.

## Resultados

| Estado | DWG SHA-256 | AutoCAD | Comparador |
| --- | --- | --- | --- |
| Antes | `E2A84DD74F7D968B076E2D2A97B40996E4E5AC4917227EFA4065060A449B3008` | `target/mcp-external/20260924-144150-autocad-343e4aae/report.json`, AUDIT 0/0, SHA intacto, salida limpia; reporte SHA `A2E696185B672155F0AE15DFA540806F74E875DECDB08D667914BFEF74FC0CD8` | 3/3 bordes (x=24) y referencia `65→64`; veredicto SHA `342978121C40DB22E5AD4AB8FC7E98693868C39D5D0EB8EF8F4D2A093014B0D9` |
| Después | `16B7F0936D18BA4AEC2D698AACBACC092907C102D12C2AEA772477E4A9F1C56F` | `target/mcp-external/20260924-144153-autocad-1dc072cd/report.json`, AUDIT 0/0, SHA intacto, salida limpia; reporte SHA `6483A1BB8D6D748C85A8466F837812F596986D8C3EE9C18B9668384DD8F3EB37` | 3/3 bordes (x=25) y referencia `65→64`; veredicto SHA `488A0A9B147B45E06972F1FA34B5C2C1AF32E008B478EA7B56A6CEA4C5411C8A` |

La primera sonda de exploración `20260924-144050-autocad-04ae5a08` solo volcó DXF bruto y pasó AUDIT; los intentos `144123-autocad-2694a115` y `144127-autocad-14fbeb06` fallaron al cargar LISP por un paréntesis faltante en el extractor. Se conservan como evidencia de fallo; la corrección se ensayó en nuevos runs.

Cuatro pruebas L1 del comparador pasaron: caso positivo, borde adulterado, handle de referencia adulterado y hash de censo distinto. Suites: automatización 36/36 y masterplan 171/171.

**Límite:** AutoCAD leyó los dos DWG y confirmó la ruta persistida. La edición de PLINE se ejecutó previamente en OpenCADStudio, no dentro de AutoCAD. Esto acredita interoperabilidad externa de ambos estados, no actualización asociativa por una edición nacida en AutoCAD. La prueba usa un triángulo y `INSUNITS=4` históricos; no acredita perfil métrico ni legibilidad HATCH en una planta.
