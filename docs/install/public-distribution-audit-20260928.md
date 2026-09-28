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
- La API de releases del fork devuelve `[]`. REST pública funciona; GraphQL de
  `gh pr list` devolvió 401. Antes de un dispatch/publicación se debe comprobar
  acceso autenticado para esa operación; este error no prueba que falten las
  credenciales Git de push.

## Preparación realizada

Candidato aislado: rama **codex/desktop-distribution**, base 06d424a1, en
`C:/Users/Luis Martinez/.codex/worktrees/desktop-distribution/OPEN CAD`.
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
