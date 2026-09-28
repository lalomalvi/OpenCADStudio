# Resultados del robustecimiento MCP

**Estado vigente al cierre de sesión:** fork publicado en `b4f41325`; upstream congelado `c623a016`, integración CAD `70db2a4d` y automatización/runner probado `f491490f`. CI completo, GUI sintética nueva y AutoCAD aprobados; CI documental de b4f41325 aprobado en 35 s. [Síntesis de sesión y aprendizajes](CIERRE-SESION-20260928.md), checkpoint corte 160. Las tablas, contadores y pendientes iniciales de este informe se conservan como historia fechada; no representan todos el HEAD actual. Masterplan global parcial.

Fecha de síntesis: 2026-09-27. Fuente: checkpoint 155 y reportes históricos. Hoy se leyeron los resúmenes y la comparación visual; no se repitieron llamadas Luna ni ejecuciones CAD.

## Qué salió del trabajo

Se implementó una infraestructura reproducible para interpretar una imagen mediante datos tipados, validar esos datos, compilar comandos CAD y comprobar el resultado. El cliente persistente resuelve arranque, correlación, plazos y varios fallos de transporte; ante incertidumbre bloquea escrituras. Hay geometría CAD editable y evidencia externa de alcances pequeños y una planta parcial. Todavía no se obtuvo una reconstrucción automática fiable de láminas completas.

## Resultados de ingeniería

| Área | Antes / problema observado | Resultado actual | Límite |
|---|---|---|---|
| Transporte | Consolas y polling improvisados | Cliente persistente, handshake, selección de sesión, readiness y plazos | Recuperación de GUI nueva pendiente |
| Respuesta perdida | Riesgo de repetir comandos | Consulta de operación y conciliación sin replay; prueba de dos hilos con un efecto | No equivale a rollback transaccional |
| Dos procesos mismo ID | Riesgo de duplicar geometría | Una sola LINE en GUI real; segundo cliente recibe request_id_reused | Resultado común entre procesos pendiente |
| Evidencia CAD | Guardar/reabrir en el mismo motor | Hashes, revisiones, captura fenced y AutoCAD por handles/geometría; negativos detectados | Alcances declarados, sin compatibilidad universal |
| Semántica | Baseline: 273 entidades en capa 0, sin cotas/arcos/bloques en ese resultado | PlanSpec, capas/unidades, cotas nativas, puertas/ventanas tipadas y bloques en fixtures | No todos los símbolos/recintos de cada plano |
| Distribución | Scripts y binario separados | CLI y ZIP sanitizado de 20 miembros; extracción y smoke AutoCAD 4/4 | Paquete anterior a último cliente; rebuild necesario |
| Pruebas | Integración experimental sin aceptación general | Último registro: 202 masterplan y 45 automatización; cliente 26 incluido en automatización | No sumar 26 otra vez; integración upstream nueva sin probar |

## Primer pase de las cinco imágenes

Cada caso pidió una región acotada, no toda la lámina. Fuente local: `five-sample-summary-v3.json` y `five-sample-gates-v1.json` en el worktree histórico.

| Caso | Interpretación | CAD y AutoCAD | Conclusión |
|---|---|---|---|
| section-stair | Escogió otra cota horizontal visible | No ejecutado | Fallo métrico conservado |
| admin-hut | Región rectangular válida | Cuatro LINE; L2 y L4 aprobados | Éxito acotado |
| bedroom-bay | Región rectangular válida | Cuatro LINE; L2 y L4 aprobados | Éxito acotado |
| apartment-grid | UNSUPPORTED | No ejecutado | Abstención conservada |
| foundation-bay | Región rectangular válida | Cuatro LINE; L2 y L4 aprobados | Éxito acotado; procedencia de region_px no verificada |

Balance: **3 éxitos acotados, 1 fallo y 1 abstención**. No es 60% de fidelidad de planos. Los casos posteriores reutilizan fuentes de desarrollo; no sustituyen una evaluación independiente.

## Comparación de prompts: repetibilidad

| Región de desarrollo | Prompt inicial | Prompt específico | Mediana inicial / específico | Resultado |
|---|---:|---:|---:|---|
| Ventana oeste, ±5 px | 1/3 aciertos, 2 abstenciones | 3/3 aciertos | 11.705 / 9.262 s | Mejora local exploratoria |
| Puerta noreste, ±8 px | 0/3 aciertos | 1/3 aciertos | 6.742 / 6.779 s | Sigue siendo poco fiable |

Tres intentos por brazo, recortes ya vistos y candidato ajustado previamente. No inferir rendimiento general ni costo por plano. Son duraciones CLI y uso agregado CLI, sin recibo directo de identidad/uso del proveedor. Las seis respuestas de la puerta no se promovieron a CAD; cinco fallos permanecen registrados.

## Planta parcial y comparación visual

El artefacto más avanzado tiene **60 entidades**: incluye contorno, algunos tabiques, cuatro ventanas, dos puertas y cotas. AutoCAD cotejó 60/60; adulterar un radio produjo 59/60 y fallo. Esto confirma que el CAD coincide con el PlanSpec de ese alcance, sin convertirlo en copia completa de la fuente.

La superposición muestra estructura azul, ventanas magenta y puertas naranja. Se ven recintos, espesores, mobiliario y otras zonas aún faltantes. Las cotas y soportes técnicos no forman parte de esa superposición; consultar el manifiesto. La revisión humana L5 sigue pendiente.

Ruta local de la comparación: `C:/Users/Luis Martinez/.codex/worktrees/mcp-robustness-masterplan/OPEN CAD/target/mcp-review/apartment-east-divider-northeast-door-v2/review-side-by-side.png`.

## Dónde consultar evidencia

En `C:/Users/Luis Martinez/.codex/worktrees/mcp-robustness-masterplan/OPEN CAD`:

- Índice general: `docs/automation/masterplan/00-INDICE.md`.
- Historia y continuación: `docs/automation/masterplan/05-CHECKPOINT-Y-CONTINUACION.md`, corte 155.
- Cinco casos: `docs/automation/masterplan/M7-CINCO-MUESTRAS-V1.md` y `M7-CINCO-CASOS-GATES-V1.md`.
- Tablas de prompts: `docs/automation/masterplan/M7-VENTANA-OESTE-REPETIBILIDAD-V1.md` y `M7-PUERTA-NORESTE-REPETIBILIDAD-V1.md`.
- Planta parcial: `docs/automation/masterplan/M7-REVISION-VISUAL-PLANTA-PARCIAL-V2.md` y `M7-APARTAMENTO-PUERTA-NORESTE-V1.md`.
- Cliente: `docs/automation/mcp_client.md`, `masterplan/M1-DOS-CLIENTES-MISMO-ID-V1.md` y `M1-PERDIDA-GUI-SINTETICA-V1.md`.
- Entrega: `docs/automation/masterplan/M8-RELEASE-CANDIDATO-B79E-V1.md` y `M8-CI-FORK-V1.md`.

Las fuentes, capturas, DWG y logs privados permanecen locales, fuera del repositorio publicado. No abrir el DWG privado para consultar estos resultados.

## Actualización del original: estado de esta sesión

Original `315df5cd`, fork main `f785e156`, masterplan `7e61e98c`: 112 commits nuevos del original; fusión simulada contra masterplan con 12 archivos en conflicto. El informe `MASTERPLAN-ESTADO-Y-UPSTREAM-20260927.md` enumera rutas, hallazgos y orden de verificación.

Se creó mediante Codex un worktree nuevo `C:/Users/Luis Martinez/.codex/worktrees/mcp-upstream-integration/OPEN CAD` desde `7e61e98c`. El primer intento fue rechazado por permisos. Después Luis habilitó solicitudes de aprobación y la ejecución autorizada permitió fetch, crear `codex/mcp-upstream-sync-20260927` y fusionar el original. Los 12 conflictos se resolvieron preservando las funciones de ambas ramas; el estado verificable de pruebas/publicación está en [M0-UPSTREAM-SYNC-20260927.md](masterplan/M0-UPSTREAM-SYNC-20260927.md). No se cambiaron ACL, safe.directory ni políticas, ni se abrió el DWG privado.

M0 aprobado; M1 L1/L2 acotado; M2–M6 parciales; M7/M8 sin aceptación global. Próximos pasos: integrar original, regresión y paquete vigente, resolver recuperación GUI, ampliar fidelidad y obtener revisión visual humana.

### Regresión de la integración

Regresión local del 2026-09-27: Rust workspace **1996 passed, 0 failed, 27 ignored**; Python **202 masterplan y 45 automatización**. Smokes sintéticos previos: tres entidades guardadas/reabiertas, captura fenced, dos clientes sin duplicación y AutoCAD 3/3 por geometría/handle, unidades m y AUDIT 0/0. Se corrigió el reemplazo Windows 1175 sin repetir comandos CAD, con revalidación y límite de cinco intentos. Los fallos previos se conservan. Consultar [el informe de integración](masterplan/M0-UPSTREAM-SYNC-20260927.md) para distinguir binarios/runs y estado vigente de CI/publicación. Estos resultados no reconstruyen zonas nuevas de las seis imágenes.

## Cierre verificable de sincronización — 2026-09-27

Código integrado y publicado en main del fork al redactar: `70db2a4d5af8fcb61cb6973519c8d073ccae2f40`. Incluye el masterplan `7e61e98c0bf377eb4bf2d96e086f83e0d32e02ff`, la primera fusión `5a8d8f4e8c58ffa012b66ecfd72ee60db789f72e` y upstream `c623a016956e5c397351660b91f04bb504bab20d`. La comprobación final detectó cuatro commits posteriores a 315df5cd: actualización 2026.39, normalización de referencias inexistentes de flechas de cotas y pins codec 42b44d2/kernel 4e67cd7/graph d89a9c5. Se integraron seis archivos sin conflictos, preservando guardado protegido y controles del fork.

La primera fusión 5a8d8f4e aprobó CI 36333224806 y host 36333227070; su binario limpio SHA256 61F4F435BA22C838DB823E876D01D2B864B817BDED055D1D4FB86BEE5FFD7072 pasó L2 en target/mcp-isolated/20260927-104620-99f01cff y AutoCAD en target/mcp-external/20260927-113346-autocad-2590969f. Esa evidencia es histórica y no acredita los nuevos pins.

| Verificación de 70db2a4d | Resultado | Evidencia |
|---|---|---|
| Rust workspace local | 1999 passed, 0 failed, 27 ignored; 31 grupos | target/upstream-sync/20260927-120811-df1a0122/rust-tests.log |
| CI Rust/Python masterplan | completed/success | [36339582448](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36339582448) |
| Host Linux/Windows, IPC real | completed/success | [36339584724](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36339584724) |
| Build limpio | exit 0, revisión declarada 70db2a4d | target/upstream-sync/build-70db2a4d-0ade8c62/report.json |
| L2 GUI sintética | tres entidades, guardado/reapertura/captura fenced, cierre de GUI | target/mcp-isolated/20260927-191801-9790b619/report.json |
| AutoCAD independiente | 3/3 geometrías/handles a 1e-6, INSUNITS 6, AUDIT 0/0, DWG intacto | target/mcp-external/20260927-191848-autocad-92d13e1b/report.json |

SHA256: log Rust `174278B36EC75B795199F4C8D3EDB5933DBE89B42BCFED95B77C70F75B6F3227`; binario `DF1B60B188CEB65708C1B30DE2BBB62484E501BA806F2C69CFF4B54EAFB5F75F`; reporte L2 `A1E591821DBFA7536C6A6626771A7E0DDA0234D019B884734A9168BEB2509E9F`; reporte AutoCAD `4D9C63A5C5CFC092A400413B37C0D9B51839BB0621194CC5C25BEB535C3C5A96`. Los 202 tests Python masterplan y 45 automatización locales del corte anterior siguen registrados; el CI nuevo verifica el masterplan del SHA vigente. Ignoradas no son aprobadas. Los tests de normalización de flechas DWG/DXF forman parte de la nueva regresión; no se afirma evaluación externa de cotas en este fixture de tres primitivas.

Main se avanzó sin force únicamente en lalomalvi/OpenCADStudio. El siguiente commit solo documenta estos resultados; no altera el código probado. Su SHA final se verifica al publicar y se entrega en la respuesta de cierre, evitando autorreferencia imposible del documento. No hubo release, publicación al autor ni inclusión de CAD, imágenes, binarios, perfiles o claves. Fallos, originales, seis casos y paquetes históricos permanecen intactos.

Pendientes: M1 conciliación de GUI nueva y resultado común multiproceso; M3 identidad/uso directos; M7 fidelidad integral, evaluación controlada y revisión humana L5; M8 paquete reconstruido del código vigente y aceptación. Sin aceptación global del masterplan. La planta de 60 entidades sigue siendo parcial; las comparaciones de prompts ventana 1/3→3/3 y puerta 0/3→1/3 no se mejoraron con reintentos ocultos.
