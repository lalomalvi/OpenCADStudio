# M5.3: dos decimales y cero final en cotas nativas

Fecha: 2026-09-24. La variante `legible_fixed_25cm_v2` conserva la altura de texto 0.25 m y añade a PlanSpec v8/v9 el contrato opcional `dimension_style.decimal_format="fixed_2"`. El compilador emite `DIMSTYLE SET ... dimdec 2` y `dimzin 0`; el comando nativo de OpenCADStudio valida enteros dentro de rango antes de mutar el estilo. Las variantes previas permanecen sin ese campo y sus hashes históricos no se reinterpretan.

Según la [tabla DXF oficial de Autodesk](https://help.autodesk.com/cloudhelp/2023/ENU/AutoCAD-DXF/files/GUID-F2FAD36F-0CE3-4943-9DAD-A9BCD2AE81DA.htm), los códigos DIMSTYLE 271 y 78 corresponden a DIMDEC y DIMZIN. El probe AutoCAD ahora registra ambos junto a tamaño de texto, flecha, gap, escala y factor en `dimension_styles`; los reportes antiguos de ocho campos siguen legibles. El comparador del run v2 exige los valores por cada uno de los siete handles de cota.

Se reutilizó **la misma salida Luna** del run `apartment-bottom-chain-v1`; no hubo solicitud nueva al modelo. El freeze v2 vincula hash de eventos, reporte de origen, compilador y binario recién compilado. La fuente sigue siendo una cadena inferior de referencia, no el plano completo.

| Gate | Resultado | Evidencia local |
|---|---|---|
| Build y L0 | `cargo build --bin OpenCADStudio` pasó; tests masterplan y automatización, `py_compile` y diff check pasan antes de publicar | Binario SHA-256 `ABAFF8AEED6E7DE9BC6D7D67D7E97202A0A648F12186B0E978F5DCCD405B36B8` |
| L2 | GUI hija cerrada, DWG y captura. La captura inspeccionada muestra `1.00`, `2.00`, los otros cuatro tramos y total `13.86` legibles | `target/mcp-cli-development/apartment-bottom-chain-fixed2-v2/report.json` SHA-256 `4B284A3807CDCB062B7E8F9D204E3FC773493BD31016990ADB8E492530F0C7B6`; DWG SHA-256 `685115ECD3A2E8FC5C494D826F79EDD78D2B693C4A3E35153E179EAABC45AC28`; PNG SHA-256 `15EBD9494B2AADA5C88D56946379FE1154C9E34867DA13F67AC7C05501198E0D` |
| L4 AutoCAD | AutoCAD Core Console 25.0.162.0.0: audit 0/0, INSUNITS 6, 11/11 entidades por handle/medida/referencia; siete estilos de cota leídos con DIMDEC=2, DIMZIN=0, DIMTXT=0.25, DIMASZ=0.08, DIMGAP=0.02 | Reporte `target/mcp-external/20260924-113948-autocad-c9857ccc/report.json` SHA-256 `19C455834AA046C0A6468283EBF61B93397B9875BA5BC8DF729049AD4EBFFB00`; veredicto `target/mcp-cli-development/apartment-bottom-chain-fixed2-v2/external-verdict.json` SHA-256 `EB7A49D434FDAA772B45D64FF32028505D35D15B6A34C7E6C5F667DD50A0C1F0` |
| Adversarial | Copia de censo/reporte con DIMDEC=1 en un handle, hash de copia recalculado; el comparador la rechazó con salida 1 y `AutoCAD native dimension style differs` | `target/mcp-cli-development/apartment-bottom-chain-fixed2-v2/negative-style/report.json` SHA-256 `3AE47720767C3150A389E47C707BDB5FE917050D31082519CB4BF2E7D6BC2F0F` |

Este corte prueba formato y persistencia de estilo para siete cotas nativas de una referencia sintética derivada de medidas de imagen, no la asociatividad al editar, legibilidad en otras escalas, L5 humana ni fidelidad del plano completo. El DWG privado permanece sin abrir.
