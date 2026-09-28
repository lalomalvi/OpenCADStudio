# Distribución pública: auditoría Git y candidato — 2026-09-28

## Snapshot verificado

Las refs se consultaron en GitHub y se descargaron en una copia Git aislada.
El fetch de la carpeta original no pudo escribir `.git/FETCH_HEAD`; se usó
`target/distribution-audit-20260928.git`, sin cambiar permisos, ramas ni archivos
de esa carpeta. El snapshot queda congelado: avances posteriores del original
pertenecen a otro ciclo.

| Referencia | SHA completo | Interpretación |
| --- | --- | --- |
| `main` público del fork | `06d424a15db0ef74080cfbea5ec628b724b0d064` | Versión Cargo 2026.39.0; incluye masterplan y sincronización anterior |
| `main` público del original | `3754426361e828cb4c0300cb5b36138d623aebfc` | Snapshot del 28 de septiembre |
| Último ancestro original integrado | `c623a016956e5c397351660b91f04bb504bab20d` | Base común comprobada |
| Carpeta y binario local previamente aceptado | `0fa6f0083bc14aa5d2efe9790597b17d9e49f87f` + cambios dirty | Rama histórica `feat/audited-mcp-save`; paquete 2026.38, no candidato público del main actual |

`fork-main...upstream-main`: **191 / 72 commits exclusivos**. Los 191 incluyen
trabajo propio y merges; no representan 191 funcionalidades ni equivalencia
semántica. El fork está sincronizado hasta c623a016, pero no al último original.
El delta nuevo del original afecta 160 archivos: 11,113 inserciones y 1,476
eliminaciones. Incluye pins codec/kernel/graph, persistencia/copia de hatches,
impresión Windows, underlays DWF/DGN y retirada de plugin API v2.

La simulación `git merge-tree --write-tree --name-only` terminó **0, sin conflictos
textuales**, árbol `a8274493d5b2cf763a9612b3d2ee8f84976f3d16`. No se ejecutó ese
árbol ni se fusionó/pushó upstream: esto no acredita regresión funcional.

## Commits, merges, pushes y CI

- El [PR #1](https://github.com/lalomalvi/OpenCADStudio/pull/1) del masterplan está
  cerrado y fusionado el 28 de septiembre, merge 5a8d8f4e. La segunda integración
  upstream es 70db2a4d. Los commits posteriores de operación/CI/documentación
  llegan hasta 06d424a1; tanto `main` remoto como la rama de sincronización apuntan
  allí.
- Se revisaron 150 ramas locales en la copia inicial: **146** tienen la misma
  punta en la rama remota homónima; **3** carecen de esa rama remota pero ya son
  ancestros del main público; **1**, `main` local, difiere porque sigue en f55e3532.
  Esto no incluye los cambios sin commit de distribución ni el candidato nuevo.
- 147 puntas locales son ancestros de main. Las otras son `main`, la rama
  histórica de save auditado y `fix/pline-test-stack`; no deben fusionarse por
  nombre o por conteo. La ascendencia por SHA no identifica cambios absorbidos
  manualmente o con otro SHA.
- En el original, PRs **1454, 1455 y 1460** constan fusionados. **1452 y 1453**
  constan cerrados sin `merged_at`. El código de save auditado se incorporó
  mediante dddf60d7, titulado `Add audited, versioned MCP save workflow (#1452)`;
  no describir el PR 1452 como un merge GitHub.
- [CI de f491490f](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36373266340)
  completó test, masterplan Python, host Windows/Linux y sync-verification con
  éxito. [CI de 06d424a1](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36387848305)
  aprobó selección/cierre, omitiendo Rust/Python/host por alcance documental.
  No son ejecuciones nuevas de esas suites en 06d424a1 ni checks de distribución.
- La API de releases del fork devuelve `[]`. La consulta ordinaria de cuenta y
  GraphQL devolvió 401, pero `gh api user --jq .login`, ejecutado con el permiso
  correspondiente, confirmó **lalomalvi**. El acceso autenticado está disponible;
  no hace falta pedir otro login por aquel 401. No se imprimieron credenciales ni
  se cambió autenticación. Las credenciales Git de push no se probaron con una
  escritura remota durante esta auditoría.

## Preparación realizada

Candidato aislado: rama **codex/desktop-distribution**, base 06d424a1, en
`C:/Users/Luis Martinez/.codex/worktrees/desktop-distribution/OPEN CAD`.
Commit de implementación local: **b8268a9c4922052aac114e7485449d0a5c6b6072**.
Se trasladaron únicamente las fuentes de distribución mediante una lista
explícita; no se incluyeron dibujos privados, perfiles ni informes ajenos.

Se resolvieron los cuatro conflictos del traslado conservando las instrucciones
de sincronización, la documentación/API ampliada y la configuración privada
automática de los tests. El smoke usa el catálogo MCP ampliado del main, no el
conteo antiguo de 18 operaciones. Se adaptó el staging del plugin RustPython al
CARGO_TARGET_DIR compartido y la inspección Mach-O para distinguir el ID propio
de un dylib de una dependencia externa. La firma del plugin sigue dentro del
bundle macOS; no se presume una notarización.

El flujo público del fork ahora prepara una **release draft**: la promoción
pública ocurre solo después de los tres jobs nativos y la verificación de assets,
hashes y procedencia del tag. Los reintentos conservan el draft y su commit; un
tag heredado sin el entrypoint de distribución del fork se rechaza antes de crear
una release. Las notas identifican el desktop/MCP del fork y no prometen web.

Pruebas del traslado: **8 límites aprobados, 1 integración con paquete real
omitida** hasta reconstruir el candidato; **5 pruebas de preparación de release
aprobadas** contra repositorios temporales locales, incluyendo draft/reintento y
rechazo de tag heredado. Actionlint, sintaxis Python/shell y diff-check pasaron.
La evidencia Windows del
[paquete anterior](audit-20260928.md) sigue válida para ese binario y alcance;
no acredita un paquete 2026.39 del candidato.

## Orden de publicación

1. Decidir e integrar el snapshot upstream congelado en un ciclo propio, si la
   primera distribución debe incluir los 72 commits nuevos; comprobar su delta.
2. Construir desde un commit limpio del candidato y ejecutar los gates native
   Windows/macOS ARM64/Intel de desktop-distribution. La preparación local de
   workflows no sustituye esos resultados. La revisión manual en el Mac de Luis
   puede hacerse después; la CI nativa es independiente de esa revisión.
3. Corregir los fallos reales de paquete/GUI/Finder que revelen los runners.
   Definir credenciales de firma si se requiere distribución confiable por el SO.
4. Seleccionar un tag/version del fork consistente con los manifests, revisar
   notas y checksums, y publicar con autorización explícita. No reutilizar como
   release el ZIP dirty 2026.38 instalado localmente.

Esta revisión no ejecutó push, merge de upstream, dispatch ni creación de release.
El JSON detallado de ramas y la simulación quedan bajo `target/` en la carpeta
original; los cambios anteriores y la aplicación instalada se conservaron.

## Ciclo de integración y distribución: continuación del 28 de septiembre

Se congeló upstream en **3754426361e828cb4c0300cb5b36138d623aebfc** y se
integró, sin conflictos, en **71a430c0f256acee0b7ebfcdec578344d0d41dc8**.
El avance posterior fdfe2429 (README de plugins) queda para otro ciclo.
El checkout privado original no se actualizó ni se incluyeron sus dibujos.

El candidato **07f63cbe550cea5bd081d45f5b55286d213507ab** se publicó, sin
force, en `codex/desktop-distribution`. El remoto confirmó ese mismo SHA.
[PR draft #2](https://github.com/lalomalvi/OpenCADStudio/pull/2) conserva
la revisión antes de integrar en main. No se creó una release ni un tag.

El workflow Windows host ejecuta ahora toda la suite unitaria de la biblioteca
sobre su productor existente, además del IPC. Esto cubre el riesgo IO Windows
del delta upstream y no introduce una segunda compilación del test ejecutable.

Resultados observados en el
[run Tests 36462634738](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36462634738):
workspace Rust, masterplan Python y host Linux aprobados; host Windows todavía
activo al escribir esta continuación. El
[check web 36462634300](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36462634300)
aprobó. Estos resultados pertenecen a 07f63cbe, no a la corrección posterior.

El [primer run nativo 36462634245](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36462634245)
detectó el mismo fallo previo al build en ambos Mac: resolver el enlace Homebrew
`rustup` hasta `rustup-init` alteró argv[0] y el comando rechazó `toolchain`.
La corrección conserva el nombre absoluto de invocación del proxy y añade una
regresión Unix ejecutable. `diagnose --logs` conserva ahora el JSON del bloqueo
incluso si el diagnóstico falla; sin `--logs` sigue siendo de lectura.
La comprobación local de esa corrección en Windows aprobó 8 tests y omitió 2
(la regresión Unix y la integración con el paquete aún en construcción).
Eso no acredita la corrección nativa Mac: requiere su siguiente run.

El siguiente candidato, **0ec62b707eb19ac815f09401a52c5ee3598c9b83**, publicó la
corrección del proxy. Ambos runners Mac superaron diagnóstico y regresión Unix
antes de entrar al build, en
[desktop 36464719436](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36464719436).
Esto confirma el bloqueo previo corregido; no equivale a paquete/GUI/Finder aprobados.

Al enviar ese candidato, el coordinador consultó antes de que GitHub mostrara
el run automático del PR y creó el dispatch 36464719819. Se canceló únicamente
ese duplicado y se conservó
[Tests automático 36464719765](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36464719765).
El claim original se mantiene como evidencia, sin redispatch. La corrección
posterior del coordinador consulta PRs abiertos en el SHA exacto: si su trigger
automático aún no aparece, informa `awaiting_pull_request_run` sin dispatch.
Sus tres regresiones y las suites locales de automatización (59) y masterplan
(202) aprobaron; no requieren una compilación Rust local.

### Fallos concretos y sondas conservadas

El primer productor Windows pasó build release, empaquetado, protocolo del EXE
instalado y cinco pruebas de preparación de release. Generó
`OpenCADStudio-fork-2026.39.0-09794ab62401-windows-x86_64-c13061039322.zip`,
SHA-256 `c130610393229d960a0be990093c97eed8b8e4547b6ee25e64ce078c8ad7a973`.
Falló después, al negociar MCP a través de PowerShell 5.1: la codificación UTF-8
con BOM de Console.InputEncoding añadía una preámbulo al pipe raw de .NET
Framework. No se acreditó la aceptación completa de ese paquete y no se publicó.
La corrección crea el child con UTF-8 sin BOM, restaura inmediatamente la
codificación anterior y mantiene copia de bytes; la regresión del paquete incluye
ahora un subprocess con la codificación UTF-8 que reveló el fallo en CI.
La regresión local sobre el binario fork instalado anterior pasó initialize,
cuatro herramientas y EOF limpio; no se hicieron operaciones CAD en esa sesión.

El runner debug del host Windows pasó los gates unitarios e IPC reales. Su
productor fue **09794ab62401114f049ecbb73e743967fef22715**, merge temporal del PR;
Actions informaba head **07f63cbe**. Se descargó y se comprobaron todos sus hashes,
y el árbol Git de ambos SHAs resultó idéntico. No se atribuye el binario a 07f63cbe.
Los workflows de Tests/host/desktop pasan ahora el head SHA del PR explícitamente
al checkout para que fuente, binary y receipt tengan una sola identidad.

Una sonda propia fuera del checkout usó ese productor debug verificado en una
carpeta TEMP nueva con espacios. El primer ensayo agotó captura: tras cerrar los
diálogos iniciales, `--new` había dejado la pantalla Start sin viewport. La
corrección crea primero un dibujo vacío solamente en la sesión de PID/EXE propios.
Su segundo ensayo pasó GUI renderizada y save/reopen/audit de DWG 2000/2013/2018
más DXF 2000. Se inspeccionó el PNG del editor; la instancia de prueba se cerró.
Esto es una sonda del productor histórico debug, no instalación de una release.
Evidencia local: `target/distribution-port/probe-fixed-ci-09794ab6/`.

AutoCAD 2025 abrió los tres DWG sintéticos en read-only y devolvió
`Total errors found 0 fixed 0` en los tres. Los tres procesos alcanzaron el límite
25 s después de `_.QUIT` y fueron terminados por la sonda: exit -1,
ForcedTermination=true. Se conserva esa limitación; no se afirma salida limpia
ni fidelidad CAD global. Logs bajo el subdirectorio synthetic-cad de la sonda.

El workflow conserva ahora los ZIP ya construidos si falla un gate posterior,
para poder investigar el mismo productor sin recompilarlo. Eso no cambia el gate
de publicación: exige success de los tres jobs nativos. También conserva la
caché de dependencias ante fallo de empaquetado/GUI; no cambia jobs ni features
de una ejecución ya iniciada.
