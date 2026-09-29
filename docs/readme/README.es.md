<p align="center"><a href="../../README.md">English</a> · <a href="README.es.md">Español</a></p>

<p align="center"><img src="../../assets/logo.svg" width="112" alt="Logotipo de OpenCADStudio, CAD de código abierto"></p>

# OpenCADStudio — CAD y MCP para un ecosistema BIM abierto

**Fork de CAD de código abierto mantenido por Luis Martínez ([lalomalvi](https://github.com/lalomalvi)) para desarrollar la capa de dibujo y automatización de un ecosistema BIM orientado a arquitectura, ingeniería y construcción (AEC).** Parte de [OpenCADStudio, creado por Hakan Seven](https://github.com/HakanSeven12/OpenCADStudio), y combina dibujo 2D, modelado 3D en Rust, flujos DWG/DXF y una interfaz nativa **Model Context Protocol (MCP)** para clientes de IA compatibles.

Luis desarrolla este fork comunitario como parte de su trabajo en un ecosistema BIM abierto y de su colaboración con la iniciativa [OpenAEC Foundation](https://open-aec.com/), de Países Bajos. El propósito es llevar ese trabajo a herramientas instalables, operaciones inspeccionables, entregables CAD trazables y flujos de ingeniería que puedan revisarse.

[Web del fork](https://lalomalvi.github.io/OpenCADStudio/es-ES/) · [Abrir CAD en navegador](https://lalomalvi.github.io/OpenCADStudio/app/) · [Descargar 2026.40.1](https://github.com/lalomalvi/OpenCADStudio/releases/tag/v2026.40.1) · [Instalación Windows](../install/windows.md) · [Instalación macOS](../install/macos.md) · [API MCP](../automation/API-SPEC.md)

## Descargar, instalar y abrir

**La versión 2026.40.1 está publicada para Windows x64, macOS Apple Silicon y macOS Intel.** Cada arquitectura tiene su propio ZIP, checksum `.zip.sha256` y manifiesto de procedencia `.zip.json`. Descarga los tres archivos correspondientes desde la [release de este fork](https://github.com/lalomalvi/OpenCADStudio/releases/tag/v2026.40.1).

| Plataforma | Paquete de la release | Guía completa |
|---|---|---|
| Windows x64 / MSVC | `OpenCADStudio-fork-2026.40.1-196b1b7c554a-windows-x86_64-89d9222bd46a.zip` | [Verificar, instalar, abrir y localizar el EXE](../install/windows.md) |
| macOS Apple Silicon | `OpenCADStudio-fork-2026.40.1-196b1b7c554a-macos-arm64-0c5abd0690cb.zip` | [Instalar el bundle y abrir desde Finder](../install/macos.md) |
| macOS Intel | `OpenCADStudio-fork-2026.40.1-196b1b7c554a-macos-x86_64-1e6cedd0bddc.zip` | [Instalación en Mac Intel](../install/macos.md) |

Para instalar manualmente, verifica el checksum y extrae todo el contenido en una carpeta nueva del usuario. Abre `application/OpenCADStudio.exe` en Windows o `OpenCADStudio.app` en macOS; conserva juntos los recursos. El CAD empaquetado no necesita Rust, Git ni Python para ejecutarse. El helper opcional necesita **Python 3.11+**.

Para automatizar la descarga, instalación y apertura verificada, ejecuta desde una copia de este fork:

```powershell
# Windows — PowerShell
& '.\scripts\desktop.ps1' download --tag v2026.40.1
& '.\scripts\desktop.ps1' open
& '.\scripts\desktop.ps1' path
```

```bash
# macOS — terminal nativa Apple Silicon o Intel
bash scripts/desktop-macos.sh download --tag v2026.40.1
bash scripts/desktop-macos.sh open
bash scripts/desktop-macos.sh path
```

`download` verifica e instala el paquete de la arquitectura actual. `open` verifica una GUI aislada y la deja abierta. `path` imprime el ejecutable instalado con ruta absoluta. `mcp` inicia stdio sobre ese mismo binario; es una operación distinta de abrir la GUI. Clonar descarga el código; la instalación y apertura requieren completar estos pasos.

**Firma:** Windows 2026.40.1 está NotSigned; ambos bundles Mac tienen firma ad-hoc, sin Developer ID/notarización acreditados. El checksum acredita integridad, no identidad del publicador ni aceptación de Gatekeeper/SmartScreen. CI nativo pasó en macOS 15; macOS 11 como mínimo configurado y el Mac del operador siguen sin comprobarse. Las guías mantienen las protecciones del sistema.

## Por qué existe este fork

El trabajo BIM conecta dibujos, geometría, información de ingeniería y personas. Este fork desarrolla la parte CAD y de automatización, con interfaces explícitas entre el editor, el cliente de IA, su ejecutor y quien revisa el resultado.

El trabajo se concentra en:

- **Entrega de escritorio utilizable:** paquetes verificados, instalaciones por usuario, rutas inequívocas y GUI/MCP funcionando fuera del repositorio.
- **Automatización independiente del cliente:** una interfaz MCP nativa para descubrir sesiones, inspeccionar dibujos, ejecutar operaciones y capturar resultados.
- **Entregables CAD trazables:** versiones DWG/DXF explícitas, auditoría, reapertura, hashes y evidencia conservada.
- **Flujos abiertos de ingeniería:** conexión del trabajo CAD con un ecosistema BIM mediante contratos documentados e integraciones validadas por separado.
- **Colaboración con el original:** integración de snapshots revisados y contribuciones acotadas, preservando autoría y licencia GPL.

### Capacidades actuales y dirección BIM

| Área | Estado |
|---|---|
| Base CAD | Dibujo DWG/DXF nativo, herramientas 2D y modelado 3D heredados de OpenCADStudio |
| IA y MCP | Endpoint stdio y herramientas documentadas de sesiones, lectura, ejecución y captura |
| Distribución | Paquetes publicados y verificados Windows x64, Mac ARM64 e Intel |
| Robustez imagen → CAD | Campaña en curso con alcance acotado, contratos y evidencia; ver el [checkpoint](../automation/masterplan/05-CHECKPOINT-Y-CONTINUACION.md) |
| Interoperabilidad BIM | Dirección del ecosistema; conectores IFC/IFCX/BCF y garantías de intercambio requieren implementación y aceptación propias |

2026.40.1 acredita la distribución CAD/MCP aquí descrita. Autoría BIM completa, certificación IFC, conformidad de ingeniería y fidelidad CAD global tienen alcances de aceptación separados.

## OpenAEC y atribución del proyecto

[OpenAEC](https://open-aec.com/) desarrolla, apoya y promueve software de código abierto para la cadena AEC. Su sitio presenta Open CAD Studio, de Hakan Seven, como un proyecto comunitario alineado con su ecosistema. La iniciativa tiene su sede en Dordrecht, Países Bajos.

| Rol | Referencia |
|---|---|
| Proyecto CAD original y autor | [Hakan Seven / OpenCADStudio](https://github.com/HakanSeven12/OpenCADStudio) |
| Este fork y su mantenedor | [Luis Martínez / lalomalvi](https://github.com/lalomalvi), [repositorio del fork](https://github.com/lalomalvi/OpenCADStudio) |
| Contexto de colaboración de Luis | [Iniciativa OpenAEC Foundation](https://open-aec.com/) |
| Distribución y verificación del fork | [Releases](https://github.com/lalomalvi/OpenCADStudio/releases), [auditoría](../install/public-distribution-audit-20260928.md) |

Este README documenta el propósito y los avances del fork. La aplicación, código y contribuciones originales conservan su atribución. La [demo web original](https://www.opencadstudio.com) se mantiene por separado; las releases de este repositorio entregan el escritorio/MCP del fork.

## MCP nativo para automatización CAD

| Herramienta | Función |
|---|---|
| `ocs_sessions` | Descubrir sesiones, estado de arranque e identidad del editor |
| `ocs_read` | Inspeccionar capacidades, estado del documento, registros, geometría y resultados |
| `ocs_execute` | Solicitar operaciones del editor, cambios de registros y lotes secuenciales |
| `ocs_capture` | Capturar una imagen acotada del viewport o ventana para revisión |

El cliente debe arrancar el ejecutable instalado con `--mcp`. Usa su ruta absoluta real como `command` y `["--mcp"]` como `args`. El comando `config` genera la configuración instalada y puede incluir el perfil aislado de una GUI abierta y verificada:

```powershell
& '.\scripts\desktop.ps1' config
& '.\scripts\desktop.ps1' verify --gui
```

```bash
bash scripts/desktop-macos.sh config
bash scripts/desktop-macos.sh verify --gui
```

`verify --gui` cierra únicamente su sesión de prueba. Las aceptaciones usan perfiles privados y fixtures sintéticas. Se preservan dibujos y sesiones del usuario. Protocolo, resultado visual, persistencia e interoperabilidad CAD independiente conservan evidencias distintas.

Consulta la [guía operativa MCP](../automation/README.md), [especificación API](../automation/API-SPEC.md), [guía de cliente](../automation/mcp_client.md) y [contrato para agentes](../install/agents.md).

## Capacidades CAD heredadas

- Lectura y escritura DWG/DXF con versiones objetivo explícitas.
- Líneas, polilíneas, curvas, sombreados, referencias a objetos, capas, bloques y referencias externas.
- Texto, cotas, tablas, espacio modelo/papel, viewports y estilos de trazado.
- Primitivas sólidas, extrusión, revolución, barrido, loft, operaciones booleanas y teselación ACIS.
- Renderizado GPU con `wgpu`, impresión/PDF en escritorio y plugins en procesos separados.
- Núcleo Rust compartido entre escritorio y navegador; interfaz en 21 idiomas.

![Espacio CAD heredado del proyecto OpenCADStudio original](../../site/workspace.png)

Documentación de plugins: [arquitectura](../plugin-architecture.md), [plantilla](../plugin-template/README.md), [registro](../../plugins/README.md). Los bundles Mac incluyen RustPython; el ZIP Windows no incluye ese plugin opcional. Plugins de escritorio y capacidades de navegador tienen alcances distintos.

## Verificación y límites conocidos

Fuente de los paquetes publicados: [`196b1b7c554a17299fd546850614db4bfc77de7a`](https://github.com/lalomalvi/OpenCADStudio/commit/196b1b7c554a17299fd546850614db4bfc77de7a), Cargo **2026.40.1**, Rust **1.98.1**, build release limpio con **Cargo.lock / --locked**.

- [CI nativo de distribución](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36519975664): tres plataformas aprobadas, incluidos paquetes, instalación, recursos, corrupción, MCP, GUI y CAD sintético; ambos Mac aprobaron Finder.
- [CI de workspace y hosts](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36519903206): Rust workspace, automatización Python y hosts reales Windows/Linux aprobados.
- Windows local verificó el mismo paquete publicado, fuera del checkout, con GUI aislada y dibujos sintéticos.

La release pública v2026.40.1 corrige la descripción PLANT e incluye el reloj web corregido y los nueve commits upstream congelados en 60f35e2b. Sus DWG 2000/2013/2018 y DXF 2000 generados en Windows pasan AutoCAD AUDIT con cero errores, cinco entidades, salida limpia y hashes intactos. La web pública abre Drawing1 vacío sin nuevos errores de consola. v2026.40 y sus nueve archivos originales se conservan intactos. Estas pruebas acotadas no acreditan paridad CAD global ni edición/exportación web completa. Consulta la [auditoría de distribución](../install/public-distribution-audit-20260928.md).

## Compilar y contribuir

Las guías [Windows](../install/windows.md) y [macOS](../install/macos.md) incluyen requisitos nativos, diagnóstico y el recorrido build → paquete → instalación → apertura. La distribución usa Rust **1.98.1** y **--locked**; no se declara un MSRV inferior probado. Los scripts no instalan dependencias globales silenciosamente.

```bash
git clone https://github.com/lalomalvi/OpenCADStudio.git
cd OpenCADStudio
```

Luego sigue la guía de tu plataforma. El desarrollo Linux desde fuentes permanece disponible; la matriz publicada del fork cubre Windows y las dos arquitecturas Mac. El desarrollo web heredado utiliza `wasm32-unknown-unknown`, Trunk y wasm-bindgen-cli; su compilación se evalúa por separado de los paquetes nativos.

Se aceptan [pull requests acotados para este fork](https://github.com/lalomalvi/OpenCADStudio/pulls), con problema, alcance, revisión de fuente y evidencia. Para contribuciones al CAD original, consulta [upstream](https://github.com/HakanSeven12/OpenCADStudio). Sigue la [política de seguridad](../../SECURITY.md) para reportar vulnerabilidades.

## Documentación y registro del trabajo

- [README principal en inglés](../../README.md)
- [Instalación Windows](../install/windows.md) e [instalación macOS](../install/macos.md)
- [API MCP](../automation/API-SPEC.md) y [guía de automatización](../automation/README.md)
- [Masterplan imagen → CAD](../automation/masterplan/00-INDICE.md) y [checkpoint vigente](../automation/masterplan/05-CHECKPOINT-Y-CONTINUACION.md)
- [Procedimiento de sincronización upstream](../automation/FORK-SYNC.md)
- [Auditoría de distribución pública](../install/public-distribution-audit-20260928.md)

Las versiones inglesa y española describen el propósito y entrega actuales del fork. Las demás traducciones conservan contenido de upstream; las guías y auditorías enlazadas gobiernan la distribución específica del fork.

## Licencia y crédito

OpenCADStudio y este fork se distribuyen bajo [GNU GPL v3](../../LICENSE). Al redistribuir, conserva los avisos de copyright, licencia y obligaciones de código fuente. Hakan Seven y los contribuidores originales conservan el crédito por el CAD de base; los cambios del fork tienen su autoría en el historial Git.

Para apoyar el desarrollo original: [GitHub Sponsors de Hakan Seven](https://github.com/sponsors/HakanSeven12).
