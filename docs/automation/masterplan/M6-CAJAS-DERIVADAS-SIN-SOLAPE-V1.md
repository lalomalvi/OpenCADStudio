# M6.5: rechazo de cajas derivadas que mezclan regiones vecinas

Fecha: 2026-09-24. La expansión fija de 25 píxeles del corte previo ahora se rechaza si dos cajas derivadas tienen área común. El control opera antes de crear cualquier manifiesto y se repite al verificar una revisión existente. Evita presentar un mismo píxel como evidencia independiente de dos textos cercanos; no detecta textos vecinos no declarados por el modelo.

Una prueba sintética adversarial coloca dos cajas de 10×10 píxeles con 10 píxeles de separación. Con padding 10, la expansión se solapa y `create` falla antes de escribir el directorio de evidencia. Las cajas exactas sin padding siguen permitidas. La suite masterplan pasó 141/141. Los dos reviews reales de padding25 se revalidaron 6/6 cada uno, sin solape. Las cajas originales fallidas 5/6 y 2/6, el segundo prompt `UNSUPPORTED` y las fuentes permanecen intactos.

El gate sigue siendo **exploratorio**: el margen se eligió tras observar el fallo, las dos hojas fueron juzgadas por el asistente y no hay L5 ni prueba sobre todos los tipos de texto del plano. M7/M8 no se promueven.
