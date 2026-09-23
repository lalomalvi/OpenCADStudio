# M0 — decisión de integración (2026-09-23)

Base comprobada: `origin/main` = `a069d7f146c27a18255f2a47d733bf678385feae`; rama experimental `codex/image-to-cad-hardening` = `d002b08a4c70a88de5af5df103b4ecbfb6890b26`. Árbol inicial limpio. `origin` es el fork `lalomalvi/OpenCADStudio`; `upstream` es `HakanSeven12/OpenCADStudio`. No hay `AGENTS.md` dentro del repo; aplica `C:/Users/Luis Martinez/AGENTS.md`. La rama de implementación parte de `origin/main`: `codex/mcp-persistent-client`.

El merge documental `ed8dbaf2` incorporó solo el masterplan. Los nueve commits de la rama experimental (ocho de implementación/pruebas y uno de evidencia) tienen como ancestro `133bfddb` y no son equivalentes a los commits documentales. Se revisaron los 28 paths del diff; no hay cambios de dependencias ni lockfiles. El código experimental se integra como merge explícito en esta rama, conservando ambos historiales y sin cherry-picks duplicados. No se usa el ensayo privado para probar esta integración.

| Commits | Capacidad y paths principales | Decisión |
|---|---|---|
| `ff41e5f9` | PLINE, `src/app/automation.rs` | Integrar corrección de stack en test |
| `8ae418e4` | PSETUPIN, `src/app/update/page_setup_import.rs` | Integrar test de rutas Windows |
| `0790d341` | Preview, `src/io/print_to_printer.rs` | Integrar aislamiento de impresión de prueba |
| `d6f61617` | `save_verified`, auditoría y versiones, `src/app/*`, `src/io/mod.rs`, `src/mcp.rs`, docs | Integrar contrato y pruebas existentes |
| `fb33ecef` | Harness MCP/AutoCAD y evidencia sintética | Integrar; adaptar cliente MCP en M1 |
| `01e1710b` | Encuadre SDF, `src/scene/camera_ops.rs` | Integrar corrección y evidencia histórica |
| `b8446692` | Diálogo de fuentes, `src/ui/window/missing_fonts.rs` y control | Integrar para continuidad del carril experimental |
| `4e5a69f3`, `d002b08a` | `run_script` y evidencia Release | Integrar implementación; conservar evidencia como histórica, sin reinterpretarla |

El diff contiene documentación y JSON de métricas, no PNG/DWG ni `COMMANDS.jsonl` privados. La revisión de secretos y el diff final son gates de publicación. La evidencia histórica de la rama no sustituye pruebas sobre el merge. M1 no implica que el servidor ya exponga un estado formal `starting/ready`: el cliente sondea la condición existente y el contrato formal queda pendiente.
