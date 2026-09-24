# PlanSpec v8: obstáculos de despeje de puerta

`planspec-8.schema.json` conserva el contrato CAD de v7 y exige `obstacles` y `swing.leaf_height_m` para cada puerta. Los obstáculos son contexto de QA: el compilador no los dibuja ni incorpora sus coordenadas a los comandos CAD. Todas las coordenadas XY de la huella rectangular son locales al `origin` de PlanSpec, como los nodos; `base_z_m` y `height_m` están en metros sobre z=0. La hoja ocupa z=0 hasta `leaf_height_m`.

Cada obstáculo exige ID estable, `kind` (`fixed_partition`, `furniture` o `annotation`), `min_x_m`, `min_y_m`, `max_x_m`, `max_y_m`, `base_z_m`, `height_m` y `source` con región de imagen, confianza y clasificación. El validador rechaza ID duplicado, huella sin área, base negativa, altura no positiva y altura de hoja fuera de 1.5–4 m. Un obstáculo físico con `base_z_m >= leaf_height_m` no invade el volumen de la hoja. Los límites tangentes al sector circular de 90° no cuentan como penetración interior.

`door_clearance_qa` v3 distingue `blocking` cuando el objeto físico procede de una medición, `review_blocked` cuando su clasificación es inferida o desconocida, y `nonphysical` para anotaciones. Los dos primeros añaden `door_sweep_hits_typed_obstacle` a `quality_blockers` y vuelven `executable=false`. La confianza numérica se conserva en el reporte, pero no se convierte en un umbral de aceptación. Las LINE sin tipo siguen como candidatas de revisión; los contornos declarados conservan su bloqueo independiente.

Fixture adversarial: `fixtures/synthetic-door-obstacle-v8.planspec.json`. Reproducir el preflight sin abrir CAD:

```powershell
python -c "import json,sys;sys.path.insert(0,'docs/automation');from masterplan.planspec import dry_run;p=json.load(open('docs/automation/masterplan/fixtures/synthetic-door-obstacle-v8.planspec.json'));r=dry_run(p);print(r['door_clearance_qa'],r['quality_blockers'],r['executable'])"
python -m unittest discover -s docs/automation/masterplan -p 'test_*.py'
```

El fixture de obstáculo prueba una puerta y una huella rectangular de mobiliario. `fixtures/synthetic-two-door-wall-v8.planspec.json` comprueba por separado dos puertas sin obstáculos en el mismo muro: 20 entidades CAD, incluyendo dos arcos. El compilador limita este perfil v8 a dos puertas del mismo muro; las versiones anteriores conservan su alcance. No acredita colisión de mallas 3D, espesor de hoja, tolerancias de instalación, obstáculos curvos, puertas en muros distintos o unidos, ni legibilidad visual. Mantener estos gates separados antes de usar el resultado como aceptación de un plano real.
