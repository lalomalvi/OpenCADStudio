# M8.1: CLI reproducible para un caso PlanSpec determinista

Estado: **partial scoped L0/L2/L4**, 2026-09-24. Esta ruta no llama a Luna ni reproduce una imagen: demuestra que una entrada PlanSpec y un contrato congelado pueden producir CAD editable, verificable y comparable externamente sin reconstruir los scripts de la sesión.

## Uso desde la raíz del worktree

Requiere el binario compilado target/debug/OpenCADStudio.exe, Python con las dependencias del proyecto y, para L4, AutoCAD Core Console. Escoger un nombre nuevo bajo target/mcp-release para cada corrida; nunca reutilizar la salida.

1. Preparar contrato, sin abrir CAD:

       python docs/automation/masterplan/m8_case_cli.py prepare --run-root target/mcp-release/mi-caso-01 --plan docs/automation/masterplan/fixtures/synthetic-wall.planspec.json --binary target/debug/OpenCADStudio.exe

2. Inspeccionar target/mcp-release/mi-caso-01/contract.json. Vincula SHA de PlanSpec, binario, compilador, ejecutor y CLI, comandos y cuatro entidades esperadas. Ejecutar una sola vez:

       python docs/automation/masterplan/m8_case_cli.py run --run-root target/mcp-release/mi-caso-01 --plan docs/automation/masterplan/fixtures/synthetic-wall.planspec.json --binary target/debug/OpenCADStudio.exe

3. Revalidar reporte, DWG y captura sin abrir CAD:

       python docs/automation/masterplan/m8_case_cli.py verify --run-root target/mcp-release/mi-caso-01 --plan docs/automation/masterplan/fixtures/synthetic-wall.planspec.json --binary target/debug/OpenCADStudio.exe

El comando run solo usa una GUI hija aislada. No repite una mutación si el run ya empezó; verificar o reconciliar el reporte antes de crear **otro** run. El contrato alterado o un plan/binario/código distinto se rechaza antes de iniciar GUI. La salida registra model_call=false y external_l4=pending hasta que se ejecute la sonda independiente. Los archivos del run quedan ignorados bajo target.

Para repetir L4 en esta máquina, copiar el DWG verificado a un directorio nuevo bajo target/mcp-isolated, ejecutar docs/automation/mcp_autocad_probe.ps1 con -SyntheticDwg y -ExpectedInsunits 6, y pasar su report.json a m8_case_l4.py junto con el plan, binario y run-root. El comparador v1 acepta solo comandos LINE; no convierte ese resultado acotado en cobertura de todos los tipos CAD.

## Resultado congelado de referencia

El run target/mcp-release/synthetic-wall-v1 usó el fixture sintético y el binario SHA C9B62173B628D56B70DC86B18FC3D35A8D85988EAD173AE9568E78BEE2EC6F02. Contrato SHA 5D3A461CA77363FCE69463B01368558C90C0051F01E4F3613A3E11FDED3BD97E; L2 report.json SHA 79F27C9A739D1E4E1ECD9449717070FAAC773FEC7D7B57F665CA6C4391229BC7, cuatro entidades, GUI cerrada, DWG SHA 174CBBAA892F641309F846BCB33B46C079DA9079EA23519D38F1F7273C07A940 y captura SHA 08D45D440725BCDF4BD1FB0D3C194324012E525C8C702359694CF619AD0E603A. verify pasó.

AutoCAD Core Console reabrió una copia sintética: AUDIT 0/0, INSUNITS6, cuatro LINE, SHA intacto y salida limpia. Reporte target/mcp-external/20260924-151336-autocad-1075f15b/report.json SHA B9C5AA6FDE581C8715B7396236BC4CFDE914523C9878DC84AF4361D2B8A10E6E. El comparador dio 4/4, veredicto SHA 54D8D68C04023AE5C0D01BBC276EE03E7D8493D0BD69CCAC0073B7B35F2DF4D9; un extremo adulterado, con hash de censo recompuesto, dio 3/4 y SHA 714A50F653024235C0A823CBC01C8B4D7842360565C63C6EB7D243A847114A99.

Reejecutar el mismo run falló antes de GUI con never replay. En target/mcp-release/synthetic-wall-contract-negative se alteró entity_count 4→5 y run rechazó Frozen contract differs antes de crear perfil/GUI. Cuatro pruebas L1 del CLI cubren preparación/verificación de contrato, contrato adulterado, replay y restricción de ruta.

## Pendientes M8

Faltan build limpio de release y hash, CLI del recorrido imagen→modelo→PlanSpec, validación L4 general, revisión de compatibilidad/diff, paquete sanitizado, checks/PR/merge en el fork y gates M7. Este corte no autoriza merge ni aceptación de la reconstrucción de planos.
