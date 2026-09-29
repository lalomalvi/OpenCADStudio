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

### Productor 9e856c50: tres plataformas aceptadas

El [run nativo 36478253841](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36478253841)
terminó success en Windows x64 (109117266039), macOS ARM64 (109117266358)
y macOS Intel (109117265630). Los tres completaron build release --locked,
manifest/hash, instalación fuera del checkout con espacios, repetición/corrupción,
MCP stdio/EOF, GUI y save/reopen/audit sintético. Ambos Mac pasaron también
Finder/LaunchServices; se inspeccionaron sus capturas GUI, Finder y CAD.
Tests [36478254392](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36478254392)
aprobó workspace Rust, Python y hosts Linux/Windows. Receipt exacto del productor
9e856c50f8cdea48448f93e6d36ee770b6f827c1, fingerprint no documental
8e51257a167c8adea7615664c23c7a927103753ac86a73aeadcaf06e831aec4b.
Web 36478254004 también terminó success. Publish fue skipped, sin autorización
ni inputs de tag; ese skip no se presenta como publicación.

| ZIP 2026.39.0, productor 9e856c50f8cd | SHA-256 |
|---|---|
| Windows x86_64, b468feed4391 | b468feed4391657b5eafecf6ace5ab125a7222b5437e7d80e5d50890243af3fe |
| macOS arm64, 08fe49dfcf60 | 08fe49dfcf60556c7068a41f18b2a684da60d6287fc6235abe8d16503c053540 |
| macOS x86_64, 2059b72b29b9 | 2059b72b29b9136d4dc013acc621f89ee8d1bb3ce1aac8636e8b4f674e00c1f0 |

Se descargaron los tres ZIP y se verificaron los SHA contra ambos sidecars,
manifest interno, revisión completa y cada archivo del payload. El Windows
se instaló y aceptó aquí en el slot independiente
C:/Users/Luis Martinez/AppData/Local/Programs/OpenCADStudio Fork Public Candidate/b468feed4391657b/application/OpenCADStudio.exe.
Reporta OpenCADStudio 2026.39+g9e856c50, limpio. La captura GUI fue inspeccionada,
MCP y CAD sintético aprobaron; el PID propio 25716 se cerró. Evidencia local:
target/distribution-port/verify-windows-9e856/summary.json y gui.png.
La instalación histórica y el dibujo privado permanecen independientes.

Windows NotSigned; Mac firma ad-hoc, sin Developer ID/notarización acreditados.
Los runners macOS 15 no prueban hardware del operador, versión mínima macOS 11
ni aceptación de una descarga pública bajo Gatekeeper. Los bundles Mac incluyen
RustPython API 7; no se atribuye ese plugin opcional al ZIP Windows. La limitación
DXF PLANT externa anterior permanece documentada; no se declara paridad global.

### Preparación de la primera distribución pública 2026.40

v2026.40 está libre tanto en tags locales como en el fork remoto al revisar
2026-09-28. Cargo.toml y Cargo.lock se preparan en 2026.40.0 antes del productor;
los paquetes 2026.39 anteriores no se etiquetan como 2026.40.
Todas las operaciones gh de preparación/verificación especifican --repo desde
GITHUB_REPOSITORY. Una fixture con GH_REPO apuntando al original reprodujo la
ruta incorrecta antes de la corrección. Siete pruebas aisladas con repositorios
Git temporales y gh simulado aprobaron después, incluida reejecución y creación
de tag sobre el commit revisado sin un commit vacío de versión. La verificación
rechaza contexto de repositorio ausente antes de cualquier petición gh.
Los logs before/after/seven-tests quedan en target/distribution-port/.

El evento de una release publicada del fork ahora verifica fuente/assets en
read-only; no recompila ni vuelve a subir paquetes ya aceptados. Actionlint
aprobó los workflows afectados. Esta revisión requiere sus propios paquetes
2026.40 y CI sobre su SHA antes de integración/publicación. No se creó tag,
release ni se ejecutó prepare --publish sobre el fork real.


### Cierre del candidato público 2026.40, productor af002fa1

Fuente exacta **af002fa17a795892792ecae26e87cfb5886047b9**, Cargo 2026.40.0,
Rust 1.98.1, release clean, Cargo.lock SHA-256
5d6fea0a4d311b1f21bd613f3e5c70b3b687a58975cd730f092c4f8dda9a9f98.
[Tests 36484188997](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36484188997)
y Web 36484188602 terminaron success. Receipt descargado y validado por SHA,
estado real del run y cobertura completa Rust workspace/Python/host. Fingerprint
c51431bc23c5727951e0e3cc8d104df686b5ba04ff499762e041914db159253c.

[Distribución 36484188603](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36484188603)
terminó success: Windows **109136935476**, ARM64 **109136935339** e Intel
**109136935042**. Los tres completaron todos los gates nativos y las siete
pruebas de preparación de release sin publicación externa. Ambos Mac pasaron
Finder/LaunchServices; sus capturas GUI/Finder/CAD se inspeccionaron. Publish
**109149609493 skipped**, intencional y sin tag/input de publicación.

| Paquete ZIP: prefijo OpenCADStudio-fork-2026.40.0-af002fa17a79- | Bytes | SHA-256 |
|---|---:|---|
| windows-x86_64-69be418ef7ba.zip | 36,952,066 | 69be418ef7ba23ed43f028fb25adcf279cd02b69306b4291139c0ba092cd3588 |
| macos-arm64-d0c5afe63aed.zip | 44,136,604 | d0c5afe63aed22c8ea5800ef77fd15796b6228481d9ec70e0b747c4cd79b3477 |
| macos-x86_64-d7a417f444f2.zip | 47,716,620 | d7a417f444f2ce38d063046c312e06a87ab7e363601c43d9a058d88ede46a91d |

Se verificó cada ZIP contra .zip.sha256 y .zip.json, manifest interno y cada
archivo del payload: Windows 3, ARM64 13, Intel 13. Todas las fuentes coinciden
con af002fa1; no se usa ningún paquete previo como si fuera 2026.40. Informes y
paquetes locales: target/distribution-port/release-2026.40-package-verification.json,
receipt-af002fa1.json y package-{windows,macos-arm64,macos-intel}-af002/.
La evidencia seleccionada de ambos Mac y Windows se conserva en evidence-*-af002/;
no incluye perfiles ni descriptores privados.

El Windows exacto se instaló y verificó también aquí:
C:/Users/Luis Martinez/AppData/Local/Programs/OpenCADStudio Fork Public Candidate/69be418ef7ba23ed/application/OpenCADStudio.exe.
Versión OpenCADStudio 2026.40+gaf002fa1, fuente limpia. MCP stdio/EOF y las cinco
versiones negociadas aprobaron; GUI Drawing1 inspeccionada y CAD sintético pasó.
El PID propio **3572** se cerró. Evidencia: verify-windows-af002/summary.json,
gui.png y synthetic-cad/20260928-152520/viewport.png.
No se repitió AutoCAD: no hay cambios CAD entre el productor externo 5d60eff1 y
este cierre; su resultado DWG acotado y la limitación DXF PLANT siguen separados.

En ARM64, GUI PID 24855 y Finder relay 25346 / GUI 25353. En Intel, GUI 60163 y
Finder relay 61026 / GUI 61033. Las aplicaciones verificadas estaban fuera del
checkout, bajo /Users/runner/work/_temp/OCS per user application with spaces/,
en slots d0c5afe63aed22c8 y d7a417f444f2ce38 respectivamente. La aceptación
manual del Mac del operador, mínimo macOS 11 y confianza de descarga pública
no quedan acreditados por estas pruebas macOS 15.

Windows permanece NotSigned; ambos Mac ad-hoc sin Developer ID ni notarización
acreditados. Las notas revisables y los nueve assets ZIP/checksum/manifest están
preparados; no se creó tag ni release. v2026.40 debe apuntar a af002fa1, fuente de
estos paquetes. Primero verificar assets reales del draft y luego confirmar la
release pública, únicamente con la autorización pendiente de publicación.

El snapshot original 37544263 es ancestro del productor y del cierre; main
06d424a1 también es ancestro, por lo que la integración puede hacerse por
fast-forward sin sustituir las revisiones probadas. El avance documental fdfe2429
observado después del snapshot permanece para el siguiente ciclo. El checkout
histórico y sus archivos privados se preservan.

Este cierre cambia exclusivamente Markdown. Se conserva el productor af002fa1
junto con sus resultados nativos, toolchain y receipt completos. El fingerprint
no documental debe coincidir antes del push. [skip ci] en el commit documental
evita repetir los mismos gates solo para cambiar la etiqueta de evidencia;
no acredita pruebas nuevas ni oculta un fallo pendiente.


### Publicación autorizada y verificada — 2026-09-28

Luis autorizó explícitamente crear/publicar v2026.40 con el estado de firma
revisado y pidió explicar el propósito BIM y su colaboración con OpenAEC en el
README. El tag anotado v2026.40 se creó sobre af002fa17a795892792ecae26e87cfb5886047b9,
sin mover main ni sobrescribir tags. Se creó draft del fork y se subieron los
nueve assets revisados. verify-native --allow-draft descargó los assets reales
y aprobó checksums, manifests, todos los payload hashes y fuente/tag. Solo
entonces se promovió y verify-native volvió a aprobar la release pública.

[Release pública 2026.40](https://github.com/lalomalvi/OpenCADStudio/releases/tag/v2026.40),
publishedAt 2026-09-28T22:23:47Z, isDraft=false, isPrerelease=false, nueve assets
uploaded con los tamaños/hashes de la tabla anterior. El evento published
inició [Release 36492126353](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36492126353),
que terminó success verificando en read-only; no recompiló paquetes nativos.
El workflow web heredado también arrancó (36492126137); su publicación se
registra por separado y no establece aceptación nativa.

Se ejecutó también el helper real download --tag v2026.40 desde la API pública,
sin sustituir el ZIP por un artifact CI. Verificó e instaló/reutilizó el slot
Windows 69be418ef7ba23ed; fuente, hash y MCP stdio/EOF volvieron a coincidir.
Evidencia: target/distribution-port/public-download-verification-2026.40/summary.json;
ZIP descargado en target/distribution-port/public-download-2026.40/.

README principal y español describen ahora al mantenedor Luis Martínez
(lalomalvi), su propósito de desarrollar la capa CAD/MCP de un ecosistema BIM y
la colaboración con la iniciativa OpenAEC Foundation declarada por él. El sitio
oficial https://open-aec.com/en/ verifica el contexto AEC, Dordrecht/Países Bajos
y la atribución de OpenCADStudio original a Hakan Seven como proyecto comunitario.
No se atribuye al fork certificación IFC ni integración IFC/IFCX/BCF aceptada.
La documentación conserva créditos/licencia y distingue avances de dirección BIM.
Firma confiable, prueba del Mac del operador y mínimo macOS 11 siguen pendientes.

El paquete descargado públicamente también se abrió con el helper: GUI Drawing1
renderizada inspeccionada, mismo EXE/commit/hash y MCP aprobado. PID propio
12768, left_open=true, configuración privada; la GUI se dejó abierta.
Evidencia: target/distribution-port/public-open-verification-2026.40/summary.json
y gui.png. No se modificaron dibujos privados ni la instalación histórica.
Los enlaces relativos de ambos README y sus fences se comprobaron; diff-check
aprobó. Esta actualización es exclusivamente Markdown, con las mismas fuentes
no documentales que el productor público, y no exige recompilar paquetes.

## Corrección posterior: web y descripción PLANT (candidato)

Base del fork: 9dc82a6d2376bae3136db101f1e61054d86945a7. Preflight actualizado
2026-09-28T23:21Z observa upstream 0a3dab12e3e92b2be6adb368ce617669364c0671,
siete commits posteriores; se reservan para otro ciclo. Esta corrección no
mueve el tag ni sustituye los nueve assets públicos v2026.40.

Web 36492126137 falló después de compilar WASM: el token personalizado de
las gráficas devolvió HTTP 401. El candidato utiliza github.token, acepta cero
estrellas y una sola release (la más reciente sigue excluida de la historia),
genera un snapshot vacío cuando Discussions está deshabilitado y toma la URL
real de Pages. La web del fork usa sus enlaces/repositorio, canonicals, sitemap,
manifest y navegación bajo /OpenCADStudio/; no copia el CNAME de upstream.
Las 21 traducciones y dos pruebas focalizadas aprobaron localmente. La prueba
nueva se incorpora al check web CI. Deploy y URLs públicas aún requieren
verificación remota antes de llamarlos aprobados.

La sonda aislada en target/distribution-port/dxf-plant-isolation-20260928/
conservó las cinco entidades y los hashes de ambos DXF: baseline reprodujo dos
advertencias Description Unprintable PLANT; cambiar solo esa descripción a
Plant pattern produjo Total errors found 0 fixed 0. El catálogo modifica
exclusivamente dicha descripción, conserva segmentos, shapes, longitudes y
unidades. No reescribe archivos existentes del usuario. La codificación general
de descripciones DXF arbitrarias sigue fuera de esta corrección acotada.
Ambas sondas terminaron forzadamente porque QUIT esperaba confirmar descarte;
se debe responder Yes en la siguiente verificación privada de solo lectura.
Aún falta acreditar el DXF exportado por el binario nuevo, no solo la copia.

No se encontraron certificados de firma de código en CurrentUser/My ni en
LocalMachine/My. La firma confiable requiere una credencial del editor externa;
no se crea una autofirmada ni se cambia SmartScreen. Prueba del Mac del operador,
notarización y mínimo macOS 11 continúan separados.

## Integración de la corrección Windows; Mac Intel continúa separado

Productor limpio 84721ff5a20c8e891a09705fa6c0aa500a760149, Rust 1.98.1,
Cargo.lock sin cambios, versión 2026.40+3.g84721ff5. Tests 36498042994 terminó
success: rust_workspace, python y host Windows/Linux validados; fingerprint
aeaf00200aef337ef9eb8afb12cea73be2848d35d4fc5c7810486e634c361d71.
Web check 36498042575 aprobó WASM, 21 idiomas y regresiones del fork.
En distribución 36498042609, Windows y Mac ARM terminaron success, incluyendo
GUI/MCP, CAD sintético y Finder en ARM; Mac Intel seguía en construcción al
preparar esta integración. No se declara aprobado ni se publican paquetes nuevos.

Windows local (Windows 11 Pro 10.0.26200, x64) verificó e instaló el ZIP
OpenCADStudio-fork-2026.40.0-84721ff5a20c-windows-x86_64-64e4f04ec085.zip,
SHA-256 64e4f04ec085f350e7df478d0558cef68e1cbb66648163f7d284bd260ea54e73,
en %LOCALAPPDATA%/Programs/OpenCADStudio Fork Windows Fix Candidate/
64e4f04ec085f350/application/OpenCADStudio.exe. PID propio 19596, GUI abierta
con perfil privado. GUI y dibujo sintético renderizados inspeccionados. MCP
stdio/EOF, cinco versiones y cuatro herramientas aprobaron en ese mismo EXE.

AutoCAD 2025 READ_ONLY aceptó DWG 2000/2013/2018 y DXF 2000 nuevos: cinco
entidades, AUDIT 0/0, cero advertencias PLANT, salida natural 0 y hash intacto
en los cuatro. El DXF exportado coincide con el aislamiento corregido:
2d000252c22ea72ca051ad09de827daac0602de02b579b165b50fda73809b3cc.
No se acredita paridad global de formatos. El primer intento de la sonda quedó
preservado: colisión de nombres de perfil DWG/DXF con el mismo stem; se corrigió
solo la sonda, sin recompilar el producto.

Evidencia: target/distribution-port/verify-windows-84721ff5/,
external-windows-84721ff5-complete/results.json y tests-84721ff5/verification.json.
La GUI pública anterior y las instalaciones históricas siguen preservadas.
La release pública v2026.40 conserva af002fa1 y sus nueve assets originales.
Windows sigue NotSigned, Mac ARM ad-hoc sin notarización; no hay certificado de
firma de código local utilizable. El despliegue web se inicia como hotfix de main
sin mover el tag. Su aceptación pública se documentará al terminar.

## Recuperaciones y cambio de API de estadísticas (2026-09-29 UTC)

Mac Intel del productor 84721ff5 terminó failure: Cargo agotó 3600 s. Se preservó
summary.json y el log de intento 1 en evidence-intel-84721ff5-attempt1-failed/.
La caché post-failure terminó success. La revisión automática rechazó inicialmente
la recuperación al confundirla con timeout de observación; se comprobó el estado
completed/failure, SHA exacto, cero jobs vivos y AGENTS.md:18 (observation timed out).
Con esa evidencia se autorizó recuperar solo Intel: intento 2, job 109200373670.
Windows y ARM se reutilizan sin recompilación y sin publicar nuevas releases.

Web 36502732198 compiló WASM y generó el sitio, pero falló con 403 al listar
stargazers. GitHub documenta una restricción desde julio 2026 a administradores/
colaboradores: https://docs.github.com/en/rest/activity/starring. Se sustituye
la lista de identidades por /stargazers/history (agregados semanales/días), probado
con el fork real y validación de totals/counts; no se inventan estrellas cuando
falla la API. Se mueve la comprobación de datos y ambas suites web antes de Cargo.
El crédito del banner se corrigió a Hakan Seven, confirmado por la API del perfil.
Estos cambios son de web/Python; Rust, Cargo.lock, catálogo y scripts/packaging
nativos permanecen idénticos al productor 84721ff5, cuyo SHA se conserva.


## Candidato nativo aprobado; fallo web reproducido al crear dibujo

Distribución 36498042609 aprobó las tres arquitecturas del productor limpio
84721ff5 en intento 2. Solo Intel se recuperó: paquete, instalación en ruta con
espacios, GUI/MCP, CAD sintético y Finder aprobaron. Windows/ARM conservaron su
éxito inicial. Se inspeccionaron capturas Intel y se comprobaron los tres ZIP,
sidecars y los 29 archivos de payload en candidate-84721ff5-package-verification.json.
Intel SHA-256: ad01f1cfda7280b6750461b6253c15511ada34f1d06bdcebc3fa215edb66f43d.
Los candidatos no se publicaron; v2026.40 conserva af002fa1 y nueve assets.

PR #4 quedó integrado en c04266c2 tras Tests 36504854347 verified completo
(Rust/Python/hosts Windows y Linux), fingerprint
36b57af82b8a6c6ec9b40011cc47a18b3255f95c7b88c6545c2d9b7a9042ddd5.
Pages 36507372549 success desplegó c04266c2: consulta agregada, suites web,
WASM y publicación aprobaron. La sonda HTTP acreditó 53 requests, 21 idiomas,
canonicals/manifest/rutas, JS/CSS y el WASM realmente referenciado por el HTML.
El primer intento de sonda buscó además un nombre WASM de reserva sin uso:
HTTP 404; se conservó y corrigió solo la sonda, sin reconstrucción del sitio.

La página española y Start de la aplicación renderizaron, pero Dibujo nuevo
reprodujo panic: std/src/sys/time/unsupported.rs:13:9, time not implemented on
this platform. No se declara aceptado el editor web por haber compilado o cargado
Start. Fallo preservado: public-web-browser-c04266c2-failed.json; el receipt de
Start aislado sigue histórico. Crear el primer viewport invoca std::time::Instant
para el sello de revisión de render; la ruta de control compartida también usa
ese reloj. Se sustituye por iced::time::Instant en esas dos rutas y sus tipos:
Iced fijado 23604ff reexporta web-time 1.1.0, reloj web en wasm y std::time::*
en hosts nativos. No cambia Cargo.lock ni el algoritmo/orden de captura.
La corrección debe aprobar compilación WASM y crear un dibujo real en el navegador;
el recibo c04266c2 no acredita este Rust nuevo. Los paquetes nativos anteriores
conservan su productor y sus resultados; no se atribuye al nuevo SHA su versión.


## Cierre de candidatos y web pública (2026-09-29 UTC)

PR #3 quedó integrado por fast-forward en 42dddd1a; PR #4 en c04266c2;
PR #5 integra la corrección del reloj web.
Tests 36508707491 aprobó el productor 87c321a4c4519cefcc5ca6343a2cfd1d636d294f:
Rust workspace, Python y hosts reales Windows/Linux. Recibo verified con fingerprint
76226d700f508cc8eb5bb04598ce85971dc59079153da5da5dedeedb2031377a.
Evidencia: target/distribution-port/tests-87c321a4/verification.json y log completo.

Distribución 36498042609 terminó success en el intento 2 del mismo productor
84721ff5a20c8e891a09705fa6c0aa500a760149. Solo Intel se recuperó: su compilación,
instalación en ruta con espacios, protocolo, GUI/CAD y Finder aprobaron. Windows
y ARM conservaron sus éxitos del intento 1 sin recompilar. Se inspeccionaron
las capturas GUI/Finder y dibujo sintético de ambas arquitecturas Mac. Los tres
ZIP, sidecars, procedencia, fuente limpia y los 29 payloads fueron comprobados;
resultados candidate-84721ff5-package-verification.json y
candidate-84721ff5-sidecar-verification.json (JSON externo/nombre/hash coincidentes). SHA-256:

- Windows: 64e4f04ec085f350e7df478d0558cef68e1cbb66648163f7d284bd260ea54e73.
- Mac ARM: 79cc957bb6830afbf9e243750fece230e0cee6db2a51fc91e0daeb1a67c1f02d.
- Mac Intel: ad01f1cfda7280b6750461b6253c15511ada34f1d06bdcebc3fa215edb66f43d.

Pages 36510352906 desplegó el hotfix de main 87c321a4 con build_main=true, sin
mover el tag. La consulta agregada de estrellas y tres regresiones del sitio
aprobaron antes de Cargo. Sitio propio https://lalomalvi.github.io/OpenCADStudio/:
21 páginas/traducciones, canonicals, manifest/scope, sitemap/robots, release.json,
JS/CSS y magic WASM verificados por HTTP. site-version.txt y app/release.json
identifican 87c321a4 y versión base 2026.40. Se inspeccionaron la portada española y el CAD web; después de Dibujo nuevo,
la pestaña Drawing1 y el viewport renderizaron sin panic ni errores de consola.
Esto acredita creación/apertura del documento vacío en navegador, no edición/
exportación web completa, CAD de escritorio ni paridad de formatos.
Evidencia: target/distribution-port/public-web-87c321a4.json, pages-87c321a4-verified.json.
La regresión anterior c04266c2 se conserva y queda supersedida por esta
prueba New drawing del módulo 4c2ebc3a4d2471ad; errores anteriores del tab no
se atribuyen al nuevo módulo. Receipt: public-web-browser-87c321a4.json.
README inglés/español enlazan la web del fork; la demo upstream conserva su crédito.

Los paquetes candidatos 84721ff5 están listos para preparar una siguiente release,
pero no están publicados. v2026.40 conserva af002fa1 y sus nueve assets originales.
Siguen separados: certificado confiable Windows, Developer ID/notarización Mac,
prueba en el Mac del operador, mínimo macOS 11 y compatibilidad Windows 10.
Los siete commits nuevos de upstream del preflight se reservan al siguiente ciclo.
Este cierre modifica solo Markdown: fuente no documental idéntica a 87c321a4,
por lo que conserva su recibo completo y no exige reconstrucción nativa ni WASM.
