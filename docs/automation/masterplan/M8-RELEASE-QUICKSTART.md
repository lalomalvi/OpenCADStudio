# OpenCADStudio MCP: candidato local de alcance acotado

Este paquete contiene un ejecutable portátil Windows x64 y el CLI determinista `m8_case_cli.py`. **No reconstruye una imagen por sí solo**: recibe un PlanSpec validado. El fixture incluido es sintético. La aceptación integral M7/M8, el recibo directo del modelo y la revisión humana siguen pendientes. El ejecutable de este candidato es local y no está firmado.

## Requisitos

- Windows x64, Python 3.11 o posterior y Pillow instalado con `python -m pip install -r requirements.txt`.
- Una carpeta nueva y escribible para cada ejecución. El CLI solo admite `target/mcp-release/<nombre-nuevo>` dentro del paquete.
- AutoCAD Core Console es opcional para el cotejo L4; no se incluye.

Desde la raíz descomprimida, verifica los archivos antes de ejecutar:

```powershell
python docs/automation/masterplan/m8_release_package.py verify --root .
```

El siguiente caso sintético genera un DWG y una captura en una GUI propia, comprueba guardado/reapertura y cierra esa GUI. Ejecuta `run` **una sola vez** para cada nombre; si una respuesta se pierde, inspecciona ese run, sin repetir la mutación.

```powershell
python docs/automation/masterplan/m8_case_cli.py prepare --run-root target/mcp-release/synthetic-01 --plan docs/automation/masterplan/fixtures/synthetic-wall.planspec.json --binary OpenCADStudio.exe
python docs/automation/masterplan/m8_case_cli.py run --run-root target/mcp-release/synthetic-01 --plan docs/automation/masterplan/fixtures/synthetic-wall.planspec.json --binary OpenCADStudio.exe
python docs/automation/masterplan/m8_case_cli.py verify --run-root target/mcp-release/synthetic-01 --plan docs/automation/masterplan/fixtures/synthetic-wall.planspec.json --binary OpenCADStudio.exe
```

Para un PlanSpec propio autorizado, usa una ruta distinta en `--plan` y un nombre nuevo en `--run-root`. `prepare` congela SHA de entrada, binario, compilador y comandos. `verify` revalida esos SHA junto con DWG, captura y cierre. La sonda `docs/automation/mcp_autocad_probe.ps1` y `m8_case_l4_mixed.py` están incluidos para L4 en una instalación con AutoCAD; la copia sintética debe estar bajo `target/mcp-isolated` y cada sonda usa un directorio nuevo. Un L4 positivo no sustituye la comparación contra la imagen fuente ni L5.
