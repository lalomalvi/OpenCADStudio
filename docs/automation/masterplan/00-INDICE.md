# Masterplan de robustecimiento MCP y reconstrucción CAD
Versión 1.0 · 2026-09-23 · Estado: planificación; implementación futura pendiente.

Actualización M0/M1: ver [M0-INTEGRACION.md](M0-INTEGRACION.md), [BASELINE.json](BASELINE.json), [mcp_client.md](../mcp_client.md) y el corte vigente en [05-CHECKPOINT-Y-CONTINUACION.md](05-CHECKPOINT-Y-CONTINUACION.md). Los contratos acotados de obstáculos M6.3 y cota de eje M4/M5 están en [OBSTACLE-QA-V8.md](OBSTACLE-QA-V8.md) y [AXIS-SPAN-DIMENSION-V8.md](AXIS-SPAN-DIMENSION-V8.md). La tabla siguiente conserva el estado inicial histórico.

## Propósito
Convertir el ensayo Luna → MCP → OpenCADStudio en un flujo reproducible, medible y recuperable que genere CAD editable con precisión declarada. Este plan abarca arranque, transporte, ejecución, evidencia, consumo, semántica CAD, evaluación e integración. El programa probado fue OpenCADStudio; LibreCAD no participó.

## Lectura y autoridad
1. [01-BASELINE-Y-CORRECCIONES.md](01-BASELINE-Y-CORRECCIONES.md): hechos, métricas y límites del ensayo.
2. [02-ARQUITECTURA-Y-CONTRATOS.md](02-ARQUITECTURA-Y-CONTRATOS.md): responsabilidades y contratos propuestos.
3. [03-FASES-Y-BACKLOG.md](03-FASES-Y-BACKLOG.md): ejecución, dependencias y aceptación.
4. [04-EVALUACION-Y-PUBLICACION.md](04-EVALUACION-Y-PUBLICACION.md): pruebas, métricas, integración y recuperación.
5. [05-CHECKPOINT-Y-CONTINUACION.md](05-CHECKPOINT-Y-CONTINUACION.md): rutas, estado y prompt para otra sesión.

Los contratos aceptados de cada evaluación prevalecen sobre objetivos orientativos. No cambiar umbrales después de observar resultados: emitir otra versión y otro run. La aprobación del plan no convierte las propuestas en funcionalidades implementadas.

## Estado inicial
| Hito | Estado |
|---|---|
| Ensayo original con Luna | Parcial; persistencia interna aprobada, fidelidad no aceptada |
| Auditoría previa sin abrir DWG | Realizada; observaciones corregidas en este plan |
| Masterplan | Documento inicial listo para revisión |
| M0 integración reproducible | Pendiente |
| M1–M8 | Pendientes |
| Verificación externa DWG | Pendiente |
| Revisión visual del usuario | Pendiente |

## Alcance y límites
La sesión de cierre publica documentación y respalda el código previamente desarrollado en una rama. No incorpora automáticamente las 28 modificaciones experimentales a main. El siguiente trabajo empieza por M0 y M1; mantiene el plano original y el ensayo histórico intactos. No requiere redibujar el caso para iniciar.

Unidades, permisos, validación, límites, identidad de sesión y recuperación deben residir en código verificable. El modelo propone interpretación y decisiones visuales; no certifica por sí mismo su identidad, integridad, costo o conformidad.

## Definición de terminado
Una versión candidata requiere todos los gates técnicos y de fidelidad de su alcance aprobados, costo y latencia medidos, limitaciones explícitas, evidencia reproducible, revisión del diff, publicación en el fork correcto y checkpoint suficiente para continuar sin esta conversación. Una única reconstrucción no permite declarar compatibilidad universal.
