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

### Entitlements macOS: bloqueo revelado por ARM64

El job ARM64 **109071790316** del run **36464719436** completó los builds
release de la aplicación, thumbnailer, launcher y plugin RustPython API v7,
y codesign verificó el bundle/appex. Falló después al leer los entitlements
por pipe: Homebrew Python 3.14 reportó `io.UnsupportedOperation: File or
stream is not seekable` al ejecutar `plistlib.load(sys.stdin.buffer)`.
La corrección usa `plistlib.loads(sys.stdin.buffer.read())`: el comando exacto
se comprobó con un subprocess de stdin no seekable, aceptando sandbox=true
y rechazando sandbox=false. Sintaxis bash y diff-check pasaron en Windows.
Eso no acredita la corrección nativa Mac ni notarización; requiere su próximo
productor. El log bundle y el summary originales se conservan en
`target/distribution-port/evidence-macos-arm64-0ec/`.

### Binding CI y límite externo DXF

El [run Tests 36467984171](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36467984171)
terminó con success en workspace Rust, masterplan Python, hosts Windows/Linux y
sync-verification. El receipt descargado y validado identifica exactamente
**5d60eff15b5ed45e15d2b70d4ccc64688db626dd**, con scopes
rust_workspace/python/host y fingerprint
`07df1e8d211b183cc991a71f378dd67f2af4c67a5085efff5454f1fb75fe8987`.
Así se comprobó el binding corregido, no solo el color del check.
Una comparación diferencial en el mismo entorno UTF-8 confirmó que el wrapper
anterior devuelve RPC -32700, mientras el corregido devuelve el initialize
esperado y EOF limpio. Resultado: `target/distribution-port/bom-differential.json`.

La sonda externa adicional del DXF 2000 sí abrió el archivo y contó las cinco
entidades de Model, pero AutoCAD AUDIT encontró **2 errores, 0 fixed**, ambos
por Description Unprintable del linetype PLANT. Se conservó el dibujo y el log,
sin reparación. La fixture histórica Windows 2026.38 produjo exactamente los
mismos dos errores de PLANT y las mismas cinco entidades en una copia read-only;
source/copy SHA-256 iguales:
`7df8d518c65340d4140dd6f1b5a6a1ba350320926e3b13125598b5907bff94ba`.
El asset PLANT también coincide en el baseline 0fa6f008.
Esto es una limitación externa preexistente de ese caso DXF, no se atribuye a
la integración actual. No se declara auditoría externa DXF limpia, reparación,
ni fidelidad CAD global. Ambos procesos alcanzaron el límite y se terminaron.
Evidencia de comparación: `target/distribution-port/baseline-dxf-0fa/report.json`.


### Windows release 5d60eff1: instalación y aceptación nativa

El job Windows **109082774535** del [run nativo 36467983856](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36467983856)
terminó **success**, incluyendo empaquetado, instalación fuera del checkout,
stdio PowerShell 5.1 con UTF-8, GUI y CAD sintético. Su ZIP clean/release es
`OpenCADStudio-fork-2026.39.0-5d60eff15b5e-windows-x86_64-88c04dcb8cb2.zip`,
36,956,267 bytes, SHA-256
`88c04dcb8cb2da990d467bd4e0fe573f4d9ca92fae9e445f60f7fe7e59d47e74`.
Se verificaron manifest y sidecars; productor completo
`5d60eff15b5ed45e15d2b70d4ccc64688db626dd`, Rust 1.98.1,
Cargo.lock SHA-256 `efad57764dcdb1341518c2947862411cd01eda41af1d96600f2f7d0c64dc975c`.
No tiene firma Authenticode (NotSigned).

Se instaló y verificó el mismo release aquí, en un directorio separado:
`C:/Users/Luis Martinez/AppData/Local/Programs/OpenCADStudio Fork Public Candidate/88c04dcb8cb2da99/application/OpenCADStudio.exe`.
Reporta `OpenCADStudio 2026.39+g5d60eff1`, sin dirty. GUI renderizada inspeccionada,
MCP en ese EXE y save/reopen/audit sintético pasaron. El PID propio 11336 se cerró;
la instalación/sesión histórica del usuario permanece independiente.
Evidencia: `target/distribution-port/verify-windows-5d60/summary.json` y `gui.png`.

AutoCAD 2025, en read-only y perfiles separados, abrió los DWG 2000/2013/2018
producidos por ese release: cinco entidades Model por archivo, **0 errores**,
**exit 0 y ForcedTermination=false** en los tres. Los hashes antes/después coinciden.
Este nuevo resultado no reescribe las terminaciones de la sonda debug histórica.
El DXF 2000 vuelve a dar cinco entidades y los **dos errores PLANT** conocidos,
exit -1/terminación al límite, sin cambio de hash. No se declara paridad global.
Evidencia: `target/distribution-port/verify-windows-5d60/synthetic-cad/20260928-132023/external-audit.json`.

El job ARM64 **109082774946** del mismo run también falló en la lectura de
entitlements por pipe, después de compilar y verificar codesign. Su bundle.log
se conservó en `target/distribution-port/evidence-macos-arm64-5d60/`;
su caché nativa se guardó al terminar. La corrección 034aff93 todavía requiere
el siguiente productor; no se presenta como aceptación Mac.

### Enlaces de distribución y aviso de actualización del fork

La revisión encontró rutas runtime de descarga/actualización todavía dirigidas
al original. Se cambian el API de latest, el aviso de actualización, CHANGELOG,
el botón web OCS Desktop y la descarga del aviso de plugins a las releases del
fork. No se cambian créditos, registro de plugins ni fuentes del original.
El detector usa nuestros ZIP, checksum y manifest, con URLs del fork y estado
uploaded, distingue Windows x64/Mac ARM64/Mac Intel y rechaza drafts, prereleases,
paquetes incompletos, dirty o ambiguos. No anuncia una distribución Linux que
este flujo no entrega. La comprobación solo habilita un aviso; la instalación
sigue verificando los hashes/procedencia reales.
Dos regresiones Rust cubren selección por arquitectura, sidecars ausentes,
assets vacíos/no subidos, origen upstream, dirty y duplicados. Su ejecución
queda en el siguiente CI; no se atribuyen al Windows 5d60 ya aceptado.


### Cierre Intel 5d60 y aislamiento de la caché CI

El job Intel **109082775311** del run 36467983856 terminó con el mismo fallo
plistlib no-seekable después de codesign válido. El build/paquete duró
71 min 45 s; la aplicación inicial compiló en 51 min 49 s y el plugin en
18 min 07 s. La segunda llamada del bundle reutilizó la app en 6,90 s.
La caché terminó de subir 1,102,909,974 bytes a las 20:05:46 UTC.
Log completo y bundle.log preservados bajo `target/distribution-port/`.

Se publicó **63d3cafe6b916ab8566e819304ed2bdb08a109b3** sin force y ls-remote
confirmó el SHA. Los triggers automáticos iniciaron Tests **36476970489**,
Web **36476970156** y desktop **36476970328**. El coordinador esperó el PR;
no agregó un dispatch. Los dos Mac del último run fallaron **antes del build**:
la caché Cargo había restaurado el directorio fijo `target/desktop-logs/preflight`,
y diagnose, correctamente, rechazó sobrescribirlo con FileExistsError.
Ese fallo no ejecutó la corrección de entitlements ni demuestra un fallo Rust.
El productor Windows y Tests seguían activos al registrar esta observación.

El workflow cambia todos los logs de preflight/build/install/GUI/Finder a un
subdirectorio por run/attempt de RUNNER_TEMP, fuera del target cacheado. Antes
preserva la carpeta de logs restaurada en otra ubicación temporal independiente;
no borra evidencia ni altera compilaciones. El helper CI valida los límites
absolutos de workspace/temp y rechaza un directorio raíz con reparse point.
Solo los resúmenes/logs/PNGs de la ejecución nueva se seleccionan para artifacts;
los perfiles/descriptores quedan fuera de esa selección y de la caché Cargo.

Una sonda PowerShell con directorios propios y espacios verificó que el move
conserva el hash del registro sintético y retira el estado de target. Otra
fixture junction fue rechazada antes de moverla y permaneció intacta.
Actionlint y diff-check aprobaron. Es comprobación del aislamiento CI local,
no aceptación nativa Mac; el siguiente run debe completar ese recorrido.
