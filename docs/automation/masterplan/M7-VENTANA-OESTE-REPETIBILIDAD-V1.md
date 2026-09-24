# M7.3 piloto de repetibilidad: ventana oeste

Fecha: 2026-09-24. Alcance: `development_seen`, una sola imagen ya usada de `IMAGENES MUESTRA` y un solo recorte de ventana oeste. No es la cohorte reservada ni aceptación M7. No se abrió el DWG privado y esta prueba no ejecutó CAD.

Se congelaron antes de las seis invocaciones la fuente SHA-256 `0CD0B310FC337C18704B658B41DF49ABB63E2F398893273BBFCFD503B2134057`, el recorte (360,535)–(430,685) ampliado 8× SHA `20BC689DE6C2031E4EC9C558AF064299CE54CABFBC6E60A209F729E3F41B4714`, el oráculo original (393,564)→(393,654) ±5 px, dos prompts y la secuencia intercalada `baseline,candidate` repetida tres veces. Freeze: `target/mcp-cli-development/west-window-repeatability-v1/freeze.json`, SHA `CD6873F3A338EEB1E75599B3385A6328B8F8FF3C9D845FC37FC0FE1200F36439`. El prompt candidato se reutilizó de la observación exitosa del corte 132; por tanto, el diseño es exploratorio y favorece al candidato. El baseline pide ambos extremos y permite abstención.

`m7_window_repeatability.py` creó una intención por casilla, validó hashes de fuente, recorte, prompts, ejecutable CLI, código y huella de máquina, invocó una vez por casilla `codex exec -m gpt-6-luna` con esfuerzo medium y acceso de solo lectura, sin timeout corto, y conservó eventos, stderr, duración y resultado. Nunca reintentó una casilla. El CLI identifica el modelo **solicitado**, pero su JSONL no incluye recibo directo de identidad efectiva ni de uso del proveedor. La telemetría de tokens es el agregado emitido por CLI.

| Brazo | Dentro de ±5 px | Abstenciones | Mediana | p95 nearest-rank (n=3) | Tokens entrada/salida CLI |
|---|---:|---:|---:|---:|---:|
| Baseline | 1/3 | 2 | 11.705191 s | 17.476512 s | 64,899 / 90 |
| Candidato | 3/3 | 0 | 9.261565 s | 9.512064 s | 65,082 / 120 |

El evaluador convirtió coordenadas del recorte 8× al original antes de aplicar el oráculo. Las tres observaciones candidatas fueron (395.375,565)→(395.375,654.75), (393.125,565)→(393.125,654.75) y (395.75,564.875)→(395.75,654.5). El baseline observó (393.5,564.5)→(393.5,654.625) una vez. Las otras dos salidas `unsupported` se conservan; no se cuentan como aciertos. Resumen completo: `target/mcp-cli-development/west-window-repeatability-v1/summary.json`, SHA `BD9D023B5B2A35884F10C1D775A9EF5AADD3E2801D37F93A5A762C5F70787A71`. Los seis `slot-XX` guardan intención, eventos crudos, stderr y hashes. Ningún resultado se sustituyó.

Interpretación: la formulación específica fue más repetible **en este recorte visto**, y las duraciones descritas son de seis llamadas individuales en esta máquina; n=3 no permite inferencia general de velocidad ni costo hasta aceptación. No hubo aleatorización ciega, variación de casos, comparación integral de pipeline, CAD, revisión humana L5 ni recibo Responses directo. Las seis imágenes/casos reservados y la matriz de 36 casillas no se simulan con estos datos. Tres pruebas L0 adicionales verifican conversión de coordenadas y rechazo de recorte/eventos adulterados. Fuente y salidas quedan fuera de Git.

Reproducción sin reejecutar Luna: `python docs/automation/masterplan/m7_window_repeatability.py summarize --root target/mcp-cli-development/west-window-repeatability-v1 --source <ruta-de-Páginas-de-Volumenes-1_1.jpg> --cli <ruta-del-codex-cli>`; el resumen existente se puede cotejar byte a byte. No ejecutar de nuevo `run-slot` sobre las seis intenciones consumidas.
