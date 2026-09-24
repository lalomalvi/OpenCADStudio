# Dos muros ortogonales unidos con una puerta explícita

## Alcance ejecutable

PlanSpec v5–v9 acepta exactamente dos muros rectos con una unión `orthogonal_union`, igual espesor y capa, y una sola abertura `door` declarada sobre `join.wall_a_id`. Se mantiene el contorno exterior sin las líneas interiores de la intersección. El compilador divide ambas caras del primer muro en los extremos del hueco, agrega dos jambas y emite una hoja abierta y un arco de 90°. Cada pieza tiene ID estable y se traza a su fuente/handle. La distancia desde el extremo del hueco más cercano a la unión debe superar `ancho de puerta + medio espesor`; el otro extremo queda estrictamente dentro del muro. Una violación falla antes de ejecutar CAD.

No se infieren uniones por proximidad. Puertas en el segundo muro, dos o más puertas, huecos en la esquina, muros no ortogonales, espesores/capas distintos, cotas vinculadas a la unión y colisiones espaciales generales siguen fuera del alcance. `analyze_door_clearance` inspecciona líneas y obstáculos declarados; el margen a la unión es una guarda geométrica del compilador, no una prueba general de barrido de puerta contra cualquier edificio.

## Oráculo y evidencia

Fixture: `fixtures/synthetic-joined-door.planspec.json` (dos muros de 4 y 3 m, espesor 0.2 m, puerta de 0.9 m a 1 m del extremo inicial). Oráculo: 14 entidades Model (13 LINE, 1 ARC), hueco entre x=1 y x=1.9, jambas, hoja abierta y arco sin línea interior de unión. L2 valida ejecución, IDs→handles, capas, auditoría, DWG reabierto, recuento y captura con render fence. L4 AutoCAD Core Console deriva posiciones del fixture independiente del comando compilado, coteja 14 handles, capas, extremos y centro/radio/ángulos de arco con tolerancia 1e-6, exige Model14, INSUNITS6, AUDIT0/0 y hash DWG intacto. El negativo cambia el handle esperado de una jamba en una copia del reporte; L4 debe rechazarlo. La regresión usa el fixture de unión sin puerta anterior.

Esta evidencia valida el caso sintético acotado. No acredita planos arbitrarios, múltiples uniones, cotas de muro unido, legibilidad general ni cohortes inéditas M7/L5.
