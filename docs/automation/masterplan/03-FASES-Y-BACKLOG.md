# Fases, dependencias y backlog ejecutable
Estado inicial de todas las tareas: pendiente. La planificación es amplia; ejecutar un hito acotado por sesión y actualizar evidencia/estado. Estimaciones son orientativas, no fechas comprometidas.

## Corte de ejecución 2026-09-23

| ID | Estado | Evidencia / límite |
|---|---|---|
| M0.1–M0.4 | passed | Git/remotos/AGENTS, matriz de ocho commits y 28 paths en `M0-INTEGRACION.md`; baseline generado por código sin leer el DWG |
| M0.5 | passed | Rama de implementación y merge explícito; build debug, smoke del mismo binario, 13/13 tests MCP y suite lib 1665 passed, 24 ignored; commit de código `6db1b790` publicado en `origin/main` y rama de respaldo |
| M1.1–M1.3 | passed L1 | Biblioteca reutilizada por tres harnesses; 15 pruebas sintéticas de transporte en el corte nuevo |
| M1.4 | passed L1/L2 | Estados formales de disponibilidad, deadline y un solo launch; GUI fría aislada verificada |
| M1.5 | passed L1/L2 | Sesión seleccionada por ID y handshake; document_id/revision exigidos antes de editar |
| M1.6 | passed scoped L1/L2 | Journal atómico local por sesión/lote; reinicio de MCP a mitad de `run_script` recuperó 3 entidades sin duplicación por el mismo ID; journal corrupto/operación desconocida bloquean nuevas mutaciones. Reinicio de GUI no evaluado |
| M2.1 | passed scoped L1/L2 | Descubrimiento concurrente 0/1/20/100 y conexión directa; 10 muestras del binario final con 100 descriptores sintéticos privados: p50 1900.45 ms, p95 conservador 1907.2 ms en esta máquina |
| M2.2 | passed scoped L1/L2 | Heartbeat/identidad Win32 y cuarentena L2; descriptor creado con DACL protegido owner+SYSTEM, rechazo de ACL ampliado; journal privado y recuperación tras reinicio MCP. ACL heredados antiguos fallan cerrado |
| M2.3 | passed scoped L1/L2 | `close_document` con política `require_saved` y `shutdown_owned_session` solo para GUI hija del MCP; PID/inicio/binario/raíz, rechazo dirty/foreign, cierre e idempotencia L2 |
| M2.4 | partial L1/L2 | Modales iniciales diagnosticados y salida propia verificada; más modalidades/caídas pendientes |
| M3.1, M3.2, M3.3, M3.5 | partial L1/L2 | 84 respuestas únicas reproducen 9,797,952 tokens históricos sin exportar rollout; PNG sintético 1024×506 con documento/revisiones y hash, trace RPC sanitizado, AUDIT/SAVE/VERDICT/ARTIFACTS/SEAL v2 verificados. Sin render-fence explícito ni tiempos CAD por fase |
| M4.1, M4.2, M4.4, M4.5, M4.6 | partial L1/L2 | PlanSpec v1 estricto y dry-run determinista de líneas/círculos; L2 sintético produjo 3 entidades y mapa ID→handle. Cotas nativas y capas distintas de 0 quedan unsupported |
| M5 censo | passed scoped L2 | 634 comandos registrados, SHA de catálogo; matriz comando→PlanSpec→MCP→persistencia en `M5-CENSO-CAPACIDADES.md`. La presencia no acredita semántica |
| M5.2 arcos/polilínea | partial L2 | ARC nativo radio 5 y PLINE `is_closed=true`, tres vértices, handles distintos y tipos preservados en reapertura interna del DWG sintético; anchura/uniones/ángulos completos y motor externo pendientes |
| M6.4 | partial L1/L2 | ARC y PLINE comparados por handle, coordenadas, radio, ángulos, vértices, cierre, ancho y grosor pre/post reapertura interna con tolerancia 1e-6; defectos sembrados detectados. Otras entidades y motor externo pendientes |
| M3 restante, M4.3 y M4 semántico, M5 restante, M6 restante, M7–M8 | pending | No aceptar gates posteriores por los L1/L2 sintéticos |

El owner_role de M0–M2 es la sesión ejecutora. Reproducir L1 con `python -m unittest discover -s docs/automation -p test_mcp_client.py -v` y `cargo test --lib mcp::tests`. El L2 sintético se reproduce con `python docs/automation/mcp_isolated_smoke.py` después del build. Sus gates CAD no prueban imagen, motor externo ni revisión del usuario. El caso original continúa partial.

## Dependencias
M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8.
Se permite investigar capacidades M5 mientras M1–M3 avanzan, pero no aceptar calidad ni rendimiento antes de contratos y telemetría estables.

## M0 — Baseline e integración reproducible
Objetivo: una base implementable sin perder carriles anteriores.
- M0.1 Inventariar ramas, remotos, HEAD, cambios locales y AGENTS.md.
- M0.2 Comparar origin/main con codex/image-to-cad-hardening y mapear las 28 modificaciones por origen: PLINE, PSETUP, previews, save_verified, fuentes, run_script.
- M0.3 Revisar duplicados/equivalencias de commits y elegir integración explícita; no cherry-pick indiscriminado ni merge de toda la rama sin revisión.
- M0.4 Preservar hashes del caso, baseline disponible y anexos de correcciones. Separar métricas calculadas de afirmaciones del modelo.
- M0.5 Crear rama de implementación desde base resuelta y manifest de build.
Entregables: BASELINE.json sanitizado, matriz de commits/capacidades y checkpoint.
Aceptación: árbol limpio salvo archivos identificados del usuario; build reproducible identificado; sin cambio del original; plan de integración escrito antes de merge.
Verificación: diff completo, dependencias/lockfiles, pruebas focalizadas de cambios integrados.
Tamaño: 1 sesión.

## M1 — Cliente persistente y disponibilidad
- M1.1 Reutilizar mcp_smoke/mcp_acceptance/mcp_reconstruction_eval; extraer biblioteca de transporte, no otro cliente ad hoc.
- M1.2 Handshake/version negotiation, stdout solo protocolo y stderr drenado para evitar deadlock.
- M1.3 IDs correlacionados, cola limitada, timeouts monotónicos, EOF/JSON inválido y respuestas fuera de orden.
- M1.4 starting/ready, polling con backoff y deadline; no abrir otra GUI por un arranque lento.
- M1.5 Selección explícita entre varias sesiones y protección por document_id/revision.
- M1.6 Consulta de operación después de timeout de mutación; no reejecutar con ID nuevo.
Aceptación: arranque frío y conexión caliente; desconexión tras mutación no duplica entidades; sesión ambigua se rechaza; comandos incompletos fallan con progreso recuperable.
Evidencia: traces de fallos inyectados y flujo real pequeño, sin imagen del usuario.
Tamaño: 1–2 sesiones.

## M2 — Sesiones, propiedad y cierre
- M2.1 Descubrimiento acotado con PID/inicio/binario/handshake, cache y sondeo paralelo limitado.
- M2.2 Heartbeat y descriptores obsoletos; cuarentena segura con rutas absolutas.
- M2.3 close_document y shutdown_owned_session; preservar documentos ajenos y cambios sin guardar.
- M2.4 Idempotencia del cierre, diagnóstico de modalidad y estados waiting_user.
Aceptación: fixtures con 0/1/20/100 descriptores muertos; tiempo no crece linealmente por un segundo cada uno; PID reutilizado no se cierra; cliente desconectado no borra proceso vivo; salida guardada y sesiones ajenas intactas.
Medir p50/p95; objetivo provisional discovery p95 <2 s con 100 entradas locales muertas, ajustar justificadamente antes de la medición.
Tamaño: 1–2 sesiones.

## M3 — Telemetría, artefactos y evidencia automática
- M3.1 Uso por respuesta/turno/run y supervisor con cobertura y deduplicación.
- M3.2 Timestamps de entrada/salida; separar espera del modelo, transporte, CAD y render.
- M3.3 ArtifactRef, negociación de imagen/recurso/ruta, recortes y render-fence.
- M3.4 Registro append-only con referencia a PNG; redacción de credenciales y configuración privada.
- M3.5 Generador de AUDIT, SAVE, VERDICT y SEAL desde resultados reales; validación de esquema y hashes.
- M3.6 Presupuestos, checkpoint y reanudación al alcanzar límite.
Aceptación: sumas de uso reproducen 9,797,952 del baseline sin duplicados; un hash cambiado falla; identidad ausente queda unknown; captura vieja se detecta; exportación no contiene secretos; costo facturado queda null si no disponible.
Objetivo: reducir tamaño de log excluyendo binarios; medir además tokens realmente recibidos, sin equiparar ambas cosas.
Tamaño: 2 sesiones.

## M4 — PlanSpec y conciliación
- M4.1 JSON Schema versionado e inventario de procedencia por elemento.
- M4.2 Validación unidades/origen/escala/IDs/finitud/referencias y confianza.
- M4.3 Grafo de cotas con caras/ejes y extremos; reporte de conflictos/indeterminación.
- M4.4 Compilador puro y determinista con manifiestos cacheados por build.
- M4.5 Dry-run que devuelve comandos/capacidades faltantes sin crear dibujo.
- M4.6 Trazabilidad ID→comando→handle y correcciones localizadas.
Aceptación: cadenas con diferentes referencias no producen falso conflicto; texto 2.50 sobre distancia 2.54 se rechaza; misma especificación produce mismo hash de comandos; unidades mixtas requieren conversión explícita; ningún error de validación muta CAD.
Tamaño: 2–3 sesiones.

## M5 — Semántica CAD profesional
Primero censar soporte existente; identificar falta en generación, manifest, transporte o motor.
- M5.1 Capas y estilos parametrizados por perfil; asignación verificable.
- M5.2 Arcos nativos y polilíneas cerradas, espesores/uniones.
- M5.3 Cotas nativas medidas y asociatividad demostrada al editar.
- M5.4 Bloques/INSERT para componentes repetidos, preservando unidades y rotación.
- M5.5 HATCH y contornos; legibilidad y grosor por escala.
- M5.6 Biblioteca paramétrica local versionada y procedencia; opción de reconstrucción fiel sin sustituir símbolos arbitrariamente.
- M5.7 Perfil de unidades, escala, textos y plantilla métrica.
Aceptación: mover referencia actualiza cota si se afirma asociatividad; arcos no se degradan a segmentos sin declarar; bloques conservan transformaciones; capas/estilos sobreviven guardado; funciones ausentes quedan unsupported.
Tamaño: 2–4 sesiones según censo.

## M6 — QA geométrica y persistencia
- M6.1 Detectar duplicados, degenerados, contornos abiertos e intersecciones no deseadas.
- M6.2 Separar bounds arquitectónicos de bounds de cotas/anotaciones.
- M6.3 Aperturas vinculadas a muro, puertas/ventanas y colisiones por categoría.
- M6.4 Comparación de coordenadas/radios/ángulos/propiedades pre/post save con tolerancias, no solo conteos.
- M6.5 QA visual por zonas y reporte de ambigüedades sin inventar datos.
- M6.6 Validación en otro motor; identificar producto, versión y conversiones. LibreCAD/DXF no se presenta como prueba DWG nativa.
Aceptación: defecto sembrado es detectado; reapertura en mismo motor se etiqueta interna; verificación externa ausente queda pending; resultado parcial no se promueve a éxito.
Tamaño: 2 sesiones.

## M7 — Evaluación controlada y optimización
- M7.1 Congelar protocolo v2 y cohortes: desarrollo vs reserva.
- M7.2 Repetir caso histórico solo como regresión conocida; reservar planos inéditos.
- M7.3 Baseline vs pipeline con igual modelo/effort/hardware; tres repeticiones por caso.
- M7.4 Ablaciones: cliente preparado, compactación, artefactos, PlanSpec, compilador y QA regional.
- M7.5 Comparar low vs medium únicamente después de protocolo específico; no mezclar con baseline medium.
- M7.6 Registrar asistencia supervisora, reintentos y abandonos; sumar costo hasta aceptación, no solo intentos exitosos.
Aceptación: ninguna mejora de velocidad degrada gates obligatorios; reporte por caso, medianas y p95 donde muestra suficiente; resultado estadístico limitado si muestra pequeña.
Objetivos exploratorios por plano simple: 12–20 respuestas, 2–4 M entrada, 20–35 k salida, 8–15 min, 3–4 capturas. No son garantías.
Tamaño: 2–3 sesiones y disponibilidad de casos.

## M8 — Entrega e integración
- M8.1 Release candidate con build/hash, contrato, CLI y guía rápida.
- M8.2 Pruebas proporcionales, revisión de diff, compatibilidad y recuperación.
- M8.3 PR al fork, checks, merge explícito y verificación remota.
- M8.4 Notas de release, limitaciones, checkpoint y prompt de continuación.
- M8.5 Propuesta upstream separada, solo con autorización de envío al autor.
Aceptación: usuario puede repetir un caso mediante entrada+contrato; no necesita improvisar Python ni reconstruir la conversación; evidencia local verificable y paquete publicable sanitizado.
Tamaño: 1 sesión.

## Orden de prioridad
P0: identidad verificable, arranque/recuperación, coherencia dimensional, evidencia íntegra y privacidad.
P1: cierre/descubrimiento, cliente estable, artefactos, PlanSpec y semántica.
P2: optimización de tokens, biblioteca ampliada y comparación de modelos.
No ahorrar tokens eliminando controles P0.

## Registro por tarea
Cada tarea mantiene: ID, estado (pending/in_progress/passed/failed/partial/blocked), owner_role, commit, dependencias, evidencias, comando reproducible, limitaciones y siguiente acción.
El responsable es la sesión ejecutora; no se presupone trabajo paralelo de agentes. Un bloqueo no detiene tareas independientes y autorizadas.
