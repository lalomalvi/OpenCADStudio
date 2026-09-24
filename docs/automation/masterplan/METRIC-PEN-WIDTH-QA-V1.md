# Grosores explícitos en DWG y PDF, alcance sintético v1

`python docs/automation/mcp_metric_content_smoke.py target/debug/OpenCADStudio.exe --pen-widths` conserva el fixture de dos LINE, TEXT y DIMLINEAR del contrato de contenido. Aplica `set_properties` a las LINE por handle con `LineWeight::Value(13)` y `Value(70)` (centésimas de milímetro) antes de guardar. Al reabrir verifica que ambos valores persisten. Exporta PDF A4 a 1:100 y 1:50 con el page setup Model correspondiente.

El oráculo raster a 100 dpi toma muestras lejos de extremos, intersecciones y glifos: el trazo horizontal de 0.13 mm ocupa 1 px y el vertical de 0.70 mm, 3 px en ambos PDF. La relación con el grosor físico es compatible con el tamaño de píxel de 0.254 mm; la cuantización impide inferir el grosor exacto desde una sola imagen. El arnés exige jerarquía y anchura constante entre las dos escalas, además del oráculo geométrico/textual anterior.

La sonda AutoCAD L4-14 emite DXF 370 por handle y coteja 13/70 contra el reporte L2. Conserva las comparaciones de dos LINE, TEXT, DIMLINEAR, estilo, Model4, INSUNITS6, AUDIT0/0, hash de fuente y DWG intacto. Una copia sintética del reporte que cambia el valor esperado de la primera LINE a 70 se rechaza `semantic_mismatch`. El reporte original y el DWG permanecen sin cambios.

Esto acredita dos grosores directos de entidad y su contraste en dos escalas sobre una fixture. No acredita `ByLayer` con capas configuradas, CTB/STB, color→pluma, transparencias, grosores de todas las primitivas, impresora física, legibilidad humana ni plano complejo. El PDF mantiene glifos vectoriales sin texto extraíble en esta ruta.
