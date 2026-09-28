# Sincronizar el fork: diagnóstico y procedimiento

Fecha: 2026-09-27. Responsable operativo: el agente que ejecute la sincronización;
Luis solo interviene ante una decisión de producto o un permiso real que falte.
Este procedimiento rige la sincronización cotidiana. El masterplan MCP conserva
sus resultados, pero sus gates de evaluación integral no son requisitos para
integrar cambios del original.

## Qué ocurrió y qué fue responsabilidad del proceso

Git fetch/push no fue el cuello de botella: los pushes medidos tardaron unos
2–3 segundos de ejecución. Sí hubo una integración grande: 112 commits exclusivos
del original, 182 del masterplan y 12 archivos en conflicto, seguida de cuatro
commits nuevos del original. Hubo duplicados de funciones ya absorbidas upstream,
cambios de dependencias y una regresión Windows 1175. Resolverlos y comprobarlos
era trabajo real. No hay evidencia para culpar al modelo ni al antivirus.

Yo añadí demora evitable: no congelé el alcance al empezar; consulté de nuevo
upstream al cerrar y abrí otro ciclo completo; hice validación local y remota sin
decidir antes cuál cubriría cada riesgo; construí un binario después de otro build
de tests con distintas features; inicié otro Cargo que quedó esperando el mismo
target; trasladé requisitos de release a una sincronización; repetí solicitudes de
aprobación del entorno y mensajes sin novedades. Cambiar permisos redujo la
fricción, pero no corrige por sí solo esa planificación.

Además, publicar mediante URL explícita dejó `origin/main` local obsoleto en
`f785e156` aunque GitHub ya estaba en `250d5b4a`. Se actualizó con fetch. El checkout
original sigue deliberadamente en `feat/audited-mcp-save` y contiene el DWG privado;
el operativo es `mcp-upstream-integration`. Confundir estos dos checkouts hace
parecer que el avance se perdió. No se debe actualizar el checkout privado para
disimular esa diferencia.

| Evidencia del último ciclo 70db2a4d | Tiempo medido | Interpretación |
|---|---:|---|
| Suite local, compile + tests | 28 min 50 s | `target/upstream-sync/20260927-120811-df1a0122/test-result.json` |
| Compilación de esa suite | 23 min 48 s | `rust-tests.log`; núcleo ejecutó sus tests en 180.71 s |
| Build dev local | 29 min 34 s | `target/upstream-sync/build-70db2a4d-0ade8c62/build.log`; hubo espera por lock |
| CI Rust | 6 min 53 s | Job `test`, run 36339582448; cargo test 5 min 32 s |
| CI Python | 16 s | Job masterplan-python, mismo run |
| Host Linux | 11 min 15 s | Run 36339584724 |
| Host Windows | 21 min 17 s | Mismo run; 5 min 13 s build, 5 min 32 s IPC, 4 min 7 s post-cache |

Los trabajos se solaparon: **no sumar las filas** ni atribuir toda la espera a
compilar. No se midió de forma completa el tiempo de razonamiento/aprobaciones;
no inventar una cifra ni prometer una reducción porcentual. Evidencia de CI:
[Tests](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36339582448),
[host](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36339584724).

## Un solo ciclo, un solo alcance

1. En el worktree de integración, ejecutar el preflight. Actualiza solo refs,
   verifica las URLs, fija HEAD/fork/upstream, enumera el delta y guarda un JSON.
   Si ya está actualizado, termina sin compilar. El planner no hace merge/push.
2. Usar el SHA `merge_ref` guardado, nunca un `upstream/main` móvil durante el run.
   Resolver conflictos y revisar el diff, incluyendo rutas anteriores en renames.
   Commit del candidato antes de un build que deba identificarse con ese SHA.
3. Elegir las comprobaciones con la tabla siguiente y anotar los IDs ya existentes.
   Verificar `git diff --check`, ascendencia y ausencia de archivos privados.
   La clasificación previa es orientativa: reevaluar el candidato tras resolver
   conflictos. Un path desconocido no se considera documentación.
4. Ejecutar cada gate una vez por contenido, plataforma y configuración. Consultar
   runs existentes del SHA antes de `workflow_dispatch`. Si está vivo, observar ese
   mismo ID; si falla, corregir la causa y ejecutar solo los gates afectados.
5. Tras aprobar lo seleccionado, push sin force a la URL explícita del fork.
   Actualizar `origin/main` y comprobar con `ls-remote`; árbol operativo limpio.
   El original debe ser ancestro del candidato. Publicar un cierre documental
   breve; un nuevo commit de documentación no obliga a recompilar el mismo código.
6. Si upstream avanzó después del snapshot, anotarlo para el siguiente ciclo.
   Solo un cambio urgente identificado justifica ampliar el ciclo actual.

```powershell
# Desde C:/Users/Luis Martinez/.codex/worktrees/mcp-upstream-integration/OPEN CAD
python docs/automation/fork_sync.py --fetch
# Comparar contenido con un SHA que ya tenga resultados acreditados:
python docs/automation/fork_sync.py --tested-ref 70db2a4d
```

Cada ejecución escribe `target/fork-sync/<UTC>-<id>/plan.json`. Sin `--fetch`, el
JSON dice `fresh_remote_refs=false`: es una inspección local, no prueba de actualidad
remota. Exit 0 = preflight sin impedimentos; 2 = cambios de trabajo o divergencia
que se deben resolver; 1 = error/URL inesperada. No lee dibujos ni archivos sin
seguimiento: solo cuenta sus nombres obtenidos de Git, sin publicarlos en el JSON.
El fingerprint omite exclusivamente Markdown en docs y README/AGENTS raíz; cubre
el resto de blobs/modos/rutas. Prueba equivalencia de fuentes, **no** éxito de tests,
compatibilidad binaria ni metadatos de versión de un build nuevo.

## Qué comprobaciones bastan

| Cambio | Gate de sincronización | Qué no volver a ejecutar por costumbre |
|---|---|---|
| Sin delta | Refs y ascendencia | Tests/build/GUI |
| Solo prosa | Diff-check y revisión del documento | Rust, CAD, AutoCAD, pruebas Luna |
| Python de automatización | Suites automation y masterplan; tests focalizados del cambio | Recompilar Rust |
| Rust sin cambio de persistencia/host | CI workspace + regresión específica del riesgo/plataforma | Segundo workspace idéntico local |
| IO, locks o comportamiento Windows | Tests Windows del área; suite Windows amplia si el impacto lo exige | Usar host Python como prueba de todo IO |
| Cargo.lock/codec/kernel/graph, toolchain, workflow o paths desconocidos | Workspace y plataformas afectadas; build/smoke si cambia entrega/persistencia | Asumir que un CI anterior acredita pins nuevos |
| Persistencia/formato DWG-DXF | Build limpio una vez, sonda sintética y comparación externa del alcance cambiado | Repetir toda la cohorte de imágenes |
| Release/instalador | Paquete + compatibilidad + gates propios de release | Convertir toda sincronización en release |

Las dos suites Python se ejecutan con `python -m unittest discover -s
docs/automation -p 'test_*.py' -q` y la variante `-s docs/automation/masterplan`.
Para un cambio del planner basta primero `python -m unittest discover -s
docs/automation -p 'test_fork_sync.py' -v`, seguido de ambas suites si se publica.

Comprobar `python -B -c "import PIL"` antes de las suites gráficas. En esta máquina
Pillow está en el site-packages del usuario; redirigir APPDATA para aislar tests
puede ocultarlo. Mantener un intérprete/entorno ya validado, o su ruta de lectura en
PYTHONPATH con bytecode desactivado (`-B`). No reinstalar ni modificar perfiles
globales por este error. El preflight y sus tests no necesitan Pillow.

Un resultado reutilizable debe identificar SHA, árbol/contenido, plataforma,
comando/features/toolchain, conclusión y log. Coincidencia de fuentes + misma
configuración permite reutilizar su resultado documentado. Ni el nombre del run,
ni un check verde de otro SHA, ni un test omitido acreditan ese gate.

El workflow Tests usa ahora `ci_scope.py` para seleccionar jobs: prosa ejecuta
solo selección/diff-check y cierre; Python de automatización ejecuta sus suites;
Rust, manifest, assets, workflows o rutas desconocidas ejecutan workspace, Python
y host Linux/Windows. Cambios del propio selector/empaquetador requieren alcance
completo. El host es reusable y Tests lo invoca; su antiguo disparo automático por
PR/tag se retiró para no iniciar dos verificaciones. El dispatch independiente
permanece solo para diagnóstico explícito.

El check estable `sync-verification` siempre debe terminar: exige `success` de
cada job requerido y genera `sync-evidence/verification.json`. Un `skipped`,
cancelado o fallo no acredita un gate requerido. Las omisiones justificadas por
el alcance se enumeran sin llamarlas tests aprobados. Debe ser el check requerido
si se configura protección de rama; no se cambia esa protección automáticamente.

En el mismo SHA, Tests puede reutilizar un recibo completo de un run previo que
GitHub confirma `completed/success`, con política y cobertura coincidentes. Un
recibo solo Python no habilita omitir host/Rust. La API debe poder leerlo; si no
puede, CI realiza la verificación solicitada en vez de asumir que pasó.

```powershell
# Después de publicar la rama candidata; observar lo existente antes de iniciar:
python docs/automation/fork_sync_ci.py --start --base <SHA-fork-congelado>
# Consultar el mismo candidato sin iniciar ni reintentar nada:
python docs/automation/fork_sync_ci.py --base <SHA-fork-congelado>
# Obtener el runner probado. Para un cierre solo Markdown usar su SHA productor:
python docs/automation/fork_sync_ci.py --artifact --reuse-ref <SHA-probado>
```

El coordinador valida URLs y revisión de la rama remota. Antes de dispatch usa
un claim atómico por SHA bajo `target/fork-sync-ci`; un timeout conserva el claim
y no reenvía la mutación. Es exclusión local del worktree, no un lock distribuido
entre equipos. Si hay fallo o evidencia insuficiente, informa los IDs y requiere
resolver la causa; no relanza automáticamente. Si el dispatch quedó incierto,
consultar GitHub y resolver ese claim explícitamente, nunca borrarlo por timeout.

El host Windows empaqueta el EXE y plugin que ya construyó y probó, sin recompilar.
Incluye `runtime.json` con SHA/fingerprint, `rustc -Vv`, comando/features, versión,
tamaños y hashes. El coordinador descarga a un directorio nuevo y verifica esas
propiedades antes de devolver la ruta. Un cierre Markdown puede usarlo si la
fuente no documental es idéntica; sigue declarando la revisión original del EXE.
No se ejecuta al descargarlo y no se presenta como release/instalador. Artefactos
expirados, ausentes o alterados no se reutilizan. No atribuir al runner pruebas IO
Windows que el host Python no ejecuta: una regresión IO exige su test específico.

El runner debug portátil usa `--features rust-embed/debug-embed`: incrusta idiomas
que un build debug normal busca en el checkout donde se compiló. Antes de subir
el artefacto, CI oculta temporalmente su propia carpeta locales, verifica discovery
MCP y la restaura incluso ante fallo. Ese ensayo se restringe al checkout de CI;
no se ocultan recursos en el equipo del usuario. El primer artefacto 90a3d269 falló
localmente por esta dependencia de idiomas y queda como ensayo histórico fallido.

## Ritmo, presupuesto y eliminación del trabajo repetido

- Antes de trabajar, o una vez por jornada activa: un fetch y preflight; sin delta,
  finalizar. No se instala una automatización diaria no solicitada.
- Un candidato, un conjunto de checks y un cierre por ciclo. Conservar target/cache
  del worktree operativo. Los perfiles sintéticos se aíslan sin borrar caches.
- Preflight: objetivo <=2 min. Prosa: <=5 min. Python: <=10 min. Nativo: publicar
  una previsión basada en los jobs vigentes; con cambios de pins, 20–40 min sigue
  siendo plausible. Son objetivos operativos, no garantías ya medidas.
- Al superar 5 min sin avance de fase, comprobar una vez el proceso/run real,
  estado, CPU o log y separar cola, lock, compilación y tests. Un timeout de
  observación no es un fallo del trabajo. No cancelarlo por cumplir una cifra.
- Ajustar jobs de Cargo a memoria disponible; `-j 1` se eligió conservadoramente y
  limita paralelismo. No cambiar jobs, features o caché a mitad del candidato.
- Consultas CI espaciadas y mensajes en cambios de fase; no un relato de cada poll.
  No pedir de nuevo una autorización ya otorgada; el permiso técnico del sandbox
  se solicita solo cuando la herramienta lo exige.

## Implantación y aceptación

| Acción | Estado/entrega | Evidencia necesaria |
|---|---|---|
| Diagnóstico y procedimiento único | Implementado en este documento | Logs y duraciones de arriba |
| Preflight, snapshot, destinos y selección conservadora | Implementado en fork_sync.py | Tests con repos sintéticos + ejecución real |
| Aprendizaje persistente para futuros agentes | AGENTS.md raíz y enlace en README/índice | Archivo versionado, no memoria informal |
| Separar jobs CI por rutas, host reusable, recibo y coordinador | Aprobado en f491490f, CI 36373266340 | 56 tests automation + 202 masterplan; recibo completo, reutilización real y un solo run del candidato |
| Reutilizar runner Windows con hashes | Aprobado: EXE descargado y verificado, sin build local | Arranque portátil, L2 nuevo y AutoCAD 3/3; rutas/hashes en corte 159 |
| Evitar segundo build local | Usar el artefacto probado de host CI | No atribuirle una revisión de commit documental posterior |
| Reducir post-cache o unificar features Cargo | Pendiente de medición posterior | No cambiar caches/features para ganar una cifra sin evidencia |
| Reducir conflictos recurrentes | En cada integración | Inventario corto de parches propios: MCP/IO/captura/QA; retirar duplicados ya absorbidos solo con revisión y pruebas |

El workflow cambiado requiere una aceptación completa de su candidato, una sola
vez. Luego los ejemplos de prosa/Python usan únicamente sus gates. No es posible
garantizar que una futura integración con regresiones dure pocos minutos. Sí se
puede evitar repetir trabajo sin una razón y dejar visible por qué cada gate se
ejecuta. La aceptación medida y sus límites están en el corte 159 del checkpoint.
El próximo ciclo medirá si la mejora se sostiene con otro delta.

## Cierre y continuación

Cerrar con: upstream congelado, SHA de código verificado, SHA local/remoto final,
checks y enlaces, duración por fase, limitación concreta y próximo paso. Registrar
solo esa ficha en el checkpoint; no copiar el mismo informe entero a cuatro archivos.

Prompt: «Sincroniza únicamente lalomalvi/OpenCADStudio siguiendo AGENTS.md y
docs/automation/FORK-SYNC.md. Ejecuta el preflight, congela un SHA de upstream,
elige los gates por el delta real, reutiliza evidencia comprobada y publica sin
force solo al fork cuando pasen. Conserva originales/privados. No persigas nuevos
commits durante el ciclo ni conviertas esta tarea en release o evaluación M7/M8.
Termina con SHA local/remoto, resultados y duración por fase.»
