# Cierre de sesión: resultados, fallos y aprendizajes

Fecha de cierre: 2026-09-28, zona America/Mexico_City. Cubre el trabajo registrado
en esta conversación, con ensayos de desarrollo desde el 2026-09-23 y cierre de
integración/automatización del 2026-09-27. Esta síntesis enlaza la evidencia existente;
no sustituye ni modifica los informes históricos ni declara completo el masterplan.

## 1. Qué quedó entregado

| Frente | Resultado verificable | Alcance que sigue pendiente |
|---|---|---|
| Integración upstream | Original congelado c623a016, masterplan preservado, conflictos resueltos y fork publicado | No se comprobó si upstream avanzó después del snapshot; próximo ciclo independiente |
| Cliente MCP | Handshake, readiness, correlación estricta, plazos, journaling y bloqueo de escritura incierta | Recuperar una GUI nueva y compartir el resultado entre procesos |
| Imagen a CAD | PlanSpec tipado, validadores, compilación determinista, semántica nativa y trazabilidad por handles | Reconstrucción fiable de la lámina completa |
| QA/persistencia | Capturas cercadas por revisión, guardado/reapertura y comparaciones AutoCAD con negativos | No acredita toda la geometría/simbología de cualquier plano |
| Sincronización | Preflight, snapshot, clasificación del delta y procedimiento persistente en AGENTS/FORK-SYNC | Medir rendimiento sostenido y reducir conflictos propios recurrentes |
| CI y runner | Workflow unificado, gates por rutas, recibos, coordinación sin redispatch y EXE Windows portable reutilizable | Caché/features pendientes; runner de prueba, no release/instalador |

Al revalidar el cierre, HEAD local, origin/main y las dos ramas remotas del fork
coincidían en **b4f41325f35046c57ae83ae4b5b0e2c0eb16358b**, árbol operativo limpio.
El código de automatización probado y productor del EXE es
**f491490f2ab88fcc0e99f3019fce002ea0eb4d89**; b4f41325 solo añadió Markdown.
El código de integración CAD anterior es 70db2a4d. El commit que añade este cierre
será documental; su SHA final se entrega después del push, evitando autorreferencia.
Publicación exclusivamente a **lalomalvi/OpenCADStudio**, sin force ni release.

## 2. Las seis imágenes: qué significa el resultado

Se recibieron seis imágenes. El exploratorio inicial está separado del pase de
cinco casos; no convertir desarrollo sobre esas mismas fuentes en una cohorte
independiente. No volver a pedir una sexta imagen ni API: Luis indicó usar lo disponible.

| Caso del primer pase de cinco | Resultado conservado |
|---|---|
| section-stair | Fallo de interpretación métrica; no se ejecutó CAD |
| admin-hut | Región rectangular: cuatro LINE, L2/L4 aprobados |
| bedroom-bay | Región rectangular: cuatro LINE, L2/L4 aprobados |
| apartment-grid | Abstención UNSUPPORTED, sin CAD en ese pase |
| foundation-bay | Región rectangular aprobada; procedencia de region_px no verificada |

Balance de ese pase: **3 éxitos acotados, 1 fallo y 1 abstención**. No es una
puntuación de fidelidad global. Las extensiones posteriores del apartamento
produjeron una planta parcial de **60 entidades**, cotejada 60/60 en AutoCAD;
adulterar un radio dio 59/60 y fallo. Incluye contorno, algunos tabiques, cuatro
ventanas, dos puertas y cotas. Faltan zonas y la revisión humana L5 integral.
Luis abrió ese resultado y lo valoró positivamente de manera parcial.

| Comparación exploratoria de prompt, tres intentos por brazo | Inicial | Específico | Mediana inicial/específico |
|---|---:|---:|---:|
| Ventana oeste, ±5 px | 1/3 | 3/3 | 11.705 / 9.262 s |
| Puerta noreste, ±8 px | 0/3 | 1/3 | 6.742 / 6.779 s |

La ventana mejoró localmente; la puerta sigue siendo poco fiable. Recortes ya
vistos y prompts ajustados previamente: no extrapolar a planos nuevos ni declarar
costo/velocidad global. Las respuestas fallidas se preservaron sin promoverlas a CAD.
Tablas y rutas: [RESULTADOS-MCP-20260927.md](RESULTADOS-MCP-20260927.md).

## 3. Qué salió mal y qué hicimos

| Problema observado | Resolución o estado | Aprendizaje conservado |
|---|---|---|
| Arranque/modelo/configuración del ensayo inicial y captura Base64 voluminosa | Cliente/contratos y artefactos compactos; baseline conservado | Identidad debe venir del runtime; bytes de log no equivalen a tokens/costo |
| Métricas visuales y referencias ambiguas | PlanSpec conserva unidades, extremos, caras/ejes e indeterminaciones | No corregir silenciosamente medidas ni usar texto de cota para ocultar otra distancia |
| Puerta, cajas de texto y recortes con confusiones | Gates tipados, negativos y versiones de corrección | Un prompt mejor no garantiza fidelidad; validar antes de mutar CAD |
| Gran divergencia Git y 12 conflictos | Integración modular, consolidación de duplicados y regresión | Upstream ya había absorbido funciones; censar antes de duplicar parches |
| Esquema JSON y parámetros batch inconsistentes | Correcciones verificadas en la integración | Una capacidad anunciada debe ser admitida por el contrato efectivo |
| Fixtures owned_root/DWT incorrectos bajo aislamiento | Fixtures separados y lectura mediante lease existente | Un fallo de test puede ser del fixture; conservar el fallo y comprobar el guard real |
| ReplaceFileW 1175 reproducido | Retry acotado del mismo temporal, con identidad/huella y condiciones verificadas | Nunca convertir recuperación en replay de CAD, delete+write o retry de error incierto |
| Pillow ausente al aislar APPDATA | Dependencia existente usada en lectura; sin reinstalación global | Un perfil aislado puede ocultar paquetes del usuario; separar aislamiento y resolución de dependencias |
| Primer EXE CI, 90a3d269: CI verde, arranque local exit 101 | f491490f incrusta idiomas y CI exige discovery sin locales del checkout | Tests verdes y hash íntegro no prueban portabilidad del artefacto |
| Aviso Windows git-remote-https.exe | Incidente reportado por Luis; causa no identificada, no reproducido | No atribuirlo al CAD, RAM, antivirus o comando específico sin evidencia |

El aviso Git mostraba una lectura inválida de memoria. La consulta de eventos de
Application (IDs 1000/1001, últimas seis horas) no encontró una entrada coincidente;
no se encontró un proceso git-remote-https activo en esa comprobación. Git instalado:
2.55.0.windows.5. Una consulta HTTPS posterior funcionó y confirmó los SHAs remoto/local.
**Esto prueba que el push quedó completo; no prueba que el crash esté corregido ni
permite atribuirlo a una operación nuestra.** Si reaparece: registrar hora/comando,
PID/versión y módulo del evento antes de diagnosticar. No reinstalar ni cambiar
credenciales, registro, perfiles o configuración global a partir de esa captura.

Fallos de arranque conservados en el worktree operativo:

- target/mcp-isolated/20260927-211258-38a5c187/report.json.
- target/ci-flow/startup-20260927-211412-04de7b89/report.json, con stdout/stderr.
- Primer CI [36371884983](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36371884983): aprobado en su alcance, EXE no aceptado como portable.

La regresión Windows, conflictos y suites fallidas están documentados en
[M0-UPSTREAM-SYNC-20260927.md](masterplan/M0-UPSTREAM-SYNC-20260927.md) y cortes 156–157.

## 4. Demoras: responsabilidad y cambios del proceso

Git fetch/push no fue el cuello de botella medido. Sí añadimos trabajo evitable:
ampliar upstream al cerrar, repetir builds locales/remotos sin decidir cobertura,
competir por el mismo target Cargo, mezclar sincronización con requisitos release,
consultar demasiado y repetir aprobaciones ya otorgadas. Se dejó el diagnóstico en
[FORK-SYNC.md](FORK-SYNC.md); no atribuir toda la demora al modelo o a Windows.

Reglas adoptadas:

1. Congelar upstream/base/candidato una vez; nuevos commits quedan para otro ciclo.
2. Un solo productor Cargo por target; commit limpio antes de etiquetar el binario.
3. Elegir gates por delta real. Base ausente o path desconocido exige alcance conservador.
4. Observar IDs existentes antes de enviar; timeout de observación no significa fallo.
5. Conservar el claim de dispatch incierto. Es exclusión local, no lock distribuido.
6. Verificar SHA, política, cobertura y conclusión; skipped/ignored no son aprobados.
7. Reutilizar EXE probado con manifiesto/hash/configuración, declarando su SHA productor.
8. Actualizar origin/main después del push por URL; no confundir el checkout privado con el operativo.
9. No pedir de nuevo autorización vigente. Si el sandbox rechaza, registrar la razón y resolver sin eludirlo.
10. Un cierre de prosa no exige repetir Rust, CAD, AutoCAD ni el modelo.

## 5. Aceptación final que podemos reutilizar

| Evidencia | Resultado | Fuente |
|---|---|---|
| CI completo de f491490f | success: Rust, Python, host Linux/Windows y sync-verification | [36373266340](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36373266340) |
| Rust Linux | 1979 passed, 0 failed, 26 ignored; 31 grupos | target/fork-flow-acceptance/f491490f2ab8/test.log |
| Python | 202 masterplan + 56 automation aprobados | masterplan-python.log en esa carpeta |
| Focalizadas del flujo | 7 aprobadas, incluidos negativos y timeout sin segundo envío | test_ci_flow.py; actionlint aprobado |
| Reutilización y no duplicación | Tres flags false con recibo real; --start devolvió mismo run aprobado | reuse-selection.json, reuse-flags.txt y report.json en esa carpeta |
| Runner descargado, GUI nueva | 3 entidades, save_verified/reapertura, captura fenced y GUI salida | target/mcp-isolated/20260927-213257-a5240283/report.json |
| AutoCAD independiente | 3/3 geometrías/handles a 1e-6, INSUNITS 6, AUDIT 0/0, entrada intacta | target/mcp-external/20260927-213325-autocad-88e2fb33/report.json |
| Cierre de b4f41325, solo prosa | success en 35 s; Rust/Python/host skipped, validated=[] | [36374426564](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36374426564), target/fork-flow-acceptance/doc-close.json |

Run completo corregido: **12 min 23 s**, con jobs solapados. Cero nuevas
compilaciones Cargo locales durante la mejora de automatización. Dos candidatos
nativos distintos por un defecto real de portabilidad. No prometer porcentaje
sostenido de aceleración ni sumar jobs solapados. El 1999/0/27 del workspace Windows
de 70db2a4d y el 1979/0/26 Linux de f491490f tienen plataforma/SHA distintos:
no sumarlos, ni presentarlos como pérdida de tests sin investigar esas diferencias.

Runner local: target/fork-sync-ci/runtime-f491490f2ab8-1a5b51be/OpenCADStudio.exe.
SHA256 EXE b643d02729224542a03c26abcf020a11af7ae4924156e9ad75b16b68c8fdde3a;
rustc 1.98.1 MSVC, revisión f491490f2ab8, feature rust-embed/debug-embed.
Hashes y rutas detallados: corte 159 del [checkpoint](masterplan/05-CHECKPOINT-Y-CONTINUACION.md).
Al cerrar se comprobaron existencia y hashes de los seis reportes de aceptación/fallo
del flujo. No se volvieron a ejecutar sus comandos ni a abrir sus dibujos.

## 6. Qué NO hicimos / pendientes para otra sesión

| Prioridad | Trabajo pendiente | Próximo alcance verificable |
|---|---|---|
| 1, M1 | Conciliación de GUI nueva y resultado común multiproceso | Contrato de identidad/estado y pruebas sintéticas de caída: un solo efecto y recuperación explícita, sin replay incierto |
| 2, M3 | Identidad/uso directos del modelo | Distinguir solicitado/efectivo/desconocido y vincular recibos reales sin inventar consumo; no pedir claves en chat |
| 3, M7 | Plano integral, fidelidad y repetibilidad, L5 humana | Congelar un alcance y oracle antes del run; puertas/referencias ambiguas deben abstenerse o resolver evidencia |
| 4, M8 | Paquete vigente y aceptación de entrega | Reconstruir desde código limpio aprobado, extracción/smoke/gates completos; el runner debug actual no lo sustituye |
| Mantenimiento | Caché/features, rendimiento sostenido y patches duplicados | Medir en otro delta real; no cambiar configuración para ganar una cifra sin evidencia |
| Incidente | Crash git-remote-https sin diagnóstico causal | Investigar solo si reaparece con hora/evento identificables; no repetir publicaciones ya completas |

M0 aprobado; M1 acotado; M2–M6 parciales; M7/M8 sin aceptación global. No hubo
cohorte independiente nueva, evaluación integral aceptada, release ni actualización
al repositorio del autor. El cierre documental actual no amplía esos alcances.
La ventana histórica de tres horas se cerró; los avances posteriores respondieron
a nuevas instrucciones de Luis. No crear una automatización nueva para este cierre.

## 7. Dónde está todo y qué conservar

- **Operativo:** C:/Users/Luis Martinez/.codex/worktrees/mcp-upstream-integration/OPEN CAD,
  rama codex/mcp-upstream-sync-20260927. Aquí continuar y publicar al fork.
- **Historia de imágenes y paquetes:** C:/Users/Luis Martinez/.codex/worktrees/mcp-robustness-masterplan/OPEN CAD,
  HEAD 7e61e98c, rama codex/mcp-m8-release-candidate. No actualizar para simular un cierre.
- **Original de Luis:** C:/Users/Luis Martinez/Desktop/PROYECTOS DE CODIGO/02. EN DESARROLLO/OPEN CAD,
  HEAD 0fa6f008, rama feat/audited-mcp-save. Conserva originales y archivos privados.
- **Comparación visual:** worktree histórico, target/mcp-review/apartment-east-divider-northeast-door-v2/review-side-by-side.png.
- **Índice de casos, prompts y salidas:** RESULTADOS-MCP-20260927.md y masterplan/00-INDICE.md.
- **Registros nuevos del flujo:** target/fork-flow-acceptance; los binarios/perfiles/logs
  permanecen locales, fuera de Git. Los artefactos GitHub tienen retención finita;
  una ruta/documento no garantiza que sigan disponibles en otra máquina.

No borrar, archivar ni limpiar worktrees/perfiles/target para cerrar esta sesión.
No leer/abrir/hash/modificar el DWG privado, no publicar imágenes/CAD/binarios,
conversaciones, tokens o perfiles. Conservar fallos y negativos junto con éxitos.

## 8. Prompt listo para retomar

> Continúa OpenCADStudio desde el worktree mcp-upstream-integration, rama actual.
> Lee AGENTS.md, este cierre, FORK-SYNC.md, 00-INDICE.md, sus cinco documentos base y
> checkpoint corte 160. Verifica árbol, remotos, HEAD/main local-remoto y evidencia
> antes de editar. La automatización probada es f491490f; b4f41325 cerró su prosa.
> Comprueba igualdad no documental para cualquier cierre posterior, y manifiesto,
> SHA productor, configuración, hash y cobertura antes de reutilizar recibos/runner.
> No recompiles ni reenvíes por timeout o Markdown. Prioriza M1: conciliación segura
> de GUI nueva y resultado multiproceso con fixtures sintéticos y un efecto único;
> documenta contrato y gate antes de mutar. Después M3 procedencia directa, M7 plano
> integral/comparación controlada/L5 y M8 paquete vigente/aceptación. Las seis fuentes
> son desarrollo: no pedir otra imagen ni API, no repetir slots Luna/IDs/perfiles.
> El crash git-remote-https está sin causa identificada; no tratarlo como resuelto.
> Si sincronizas, preflight, un upstream congelado y gates por delta; no perseguir
> upstream durante el ciclo. Preserva originales/fallos y no abras/lees/hash/modifiques
> el DWG privado. Commit/push sin force solo a lalomalvi/OpenCADStudio cuando pasen
> los gates elegidos; nunca al autor. Termina con SHA local/remoto, evidencia, tiempo,
> alcance pendiente y prompt de continuidad. No declares completo M7/M8 por un CI verde.
