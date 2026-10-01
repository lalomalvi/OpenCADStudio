# M4 · Contrato humano–agente v1 (fase 4a)

**Fecha:** 2026-09-30 · **Plan:** [08 §3](08-PLAN-DE-ESTABILIZACION-20260930.md)
**Estado:** verificado en L0/L1 y en **L2 acotado** (2026-09-30), con la primera aprobación humana real. La hoja se amplió el 2026-10-01, verificada en L0/L1. L4 externo pendiente.
**Código:** `plan_contract.py`; puerta en `m8_case_cli.py`

## Qué hace

1. **`review`.** Escribe una hoja de revisión determinista en una carpeta nueva que no se sobrescribe. Contiene:
   - lo que se va a dibujar, en una tabla por grupo del PlanSpec:
     - nodos con coordenadas;
     - muros con extremos, longitud, espesor y capa;
     - vanos con muro, posición desde el inicio, ancho y giro o antepecho;
     - uniones;
     - líneas con extremos y longitud;
     - círculos con centro y radio;
     - cotas con sus extremos y coordenadas, eje, tipo de referencia, valor y texto;
     - vínculos de cota: muro, cara o eje, y estación de cada extremo;
     - colocación de cotas: `offset_m` y capa;
     - símbolos de puerta y de ventana, con las líneas que los forman;
     - obstáculos con su caja.

     Cada tabla muestra como máximo 60 filas. Si un grupo tiene más, la tabla dice cuántas faltan y la cabecera marca las tablas como **PARCIALES**: entonces la hoja no basta y hay que revisar el PlanSpec íntegro. La hoja no lista los contornos de `topology` ni el `dimension_style`;
   - los **supuestos** (`source.classification = inferred`) y las **dudas** (`unknown`), con su confianza;
   - los bloqueos y lo no soportado según `dry_run`;
   - lo que se verificará y, explícitamente, lo que **no**;
   - con `--previous`, las diferencias contra la versión anterior del plan.
2. **`approve` y `revoke`.** Solo los usa el humano, en una terminal interactiva.
   - El comando muestra la hoja y exige teclear los primeros 12 caracteres del hash del plan.
   - Si hay dudas, exige además teclear `ACEPTO DUDAS`.
   - La decisión queda en un registro JSONL encadenado: `sequence`, `previous_record_sha256` y `record_sha256`, con escritura sincronizada a disco.
   - La aprobación ata el hash del plan, el `commands_sha256`, las dos hojas y el código del compilador.
   - `status` distingue la última decisión de si `run` la aceptaría hoy (`usable_by_run`), con la misma función que usa la puerta.
3. **Puerta de ejecución.** `m8_case_cli.py run` exige una aprobación vigente del mismo plan **y** de los mismos comandos compilados, registrada por el canal humano. Sin ella no crea carpetas ni abre la GUI.
   - El informe de la corrida guarda `approval_record_sha256`.
   - `verify --approvals` vuelve a comprobarla.
4. **Contrato del caso.** Pasa a `m8-deterministic-case-contract-2` e incluye el hash de `plan_contract.py`. El paquete de release lo incorpora a su lista cerrada.

## Verificado (Windows, Python 3.13.7; 2026-09-30, ampliado el 2026-10-01)

**`test_plan_contract.py` (22 pruebas):**

- determinismo de la hoja;
- nodos, líneas y círculos con su geometría;
- cotas con extremos y coordenadas, vínculos con cara o eje y estación, y colocación con `offset_m`; si cambia `offset_m`, cambia la hoja;
- símbolos de ventana con sus seis líneas;
- dudas y diferencias de vínculos y colocaciones nombran su cota;
- tope por grupo con aviso y cabecera «completas» o «PARCIALES»;
- `status` informa si `run` aceptaría la aprobación;
- supuestos y dudas tomados de `source.classification`;
- giro de puerta y antepecho de ventana;
- un prefijo equivocado no registra nada;
- sin aceptar las dudas, no se aprueba;
- un plan cambiado después de revisarlo no se aprueba;
- una hoja editada se rechaza;
- un resumen JSON editado (p. ej. marcar como ejecutable un plan con bloqueos) no desbloquea la aprobación;
- un plan no ejecutable no se aprueba;
- un registro alterado se rechaza;
- la cadena enlaza decisiones sucesivas;
- revocación, canal no humano y comandos distintos bloquean la puerta;
- diferencias contra la versión anterior;
- la carpeta de revisión no se sobrescribe.

**`test_m8_case_cli.py` (10 pruebas):**

- con un plan **no aprobado**, `Popen` no se llama y no se crean carpetas;
- lo mismo en `run` con aprobación **revocada**, con aprobación por **canal no humano** y con aprobación de **otros comandos compilados**;
- con un plan **aprobado**, la puerta deja pasar hasta el lanzamiento de la GUI (simulado);
- `verify` sin atadura de aprobación se rechaza.

**Suites completas:** masterplan 230/230 y automatización 59/59 (2026-10-01, con Pillow en un entorno aislado).

**Humo del CLI:**

- `review` escribió la hoja del fixture `synthetic-wall` (hash `DDA61A032A26…`).
- `approve`, lanzado desde el harness de un agente, se negó por falta de terminal interactiva y no creó el registro.

## L2 con aprobación humana real (2026-09-30)

**Aprobación.** Luis revisó la hoja del fixture `synthetic-wall` (hash `DDA61A032A26…`) en su PowerShell y tecleó el prefijo.

- Registro: una decisión, cadena válida, canal `interactive_tty`.
- Registro `9B8AADB7B321925C6AF378336379E276C7C712EA15003994310B33CAEF75D61C`, 2026-09-30T08:06:31Z.

**Negativo con CLI y binario reales.** El fixture `synthetic-room`, sin aprobar, fue rechazado por `run`: «Human approval required before opening the GUI». La carpeta de la corrida solo contiene `contract.json`: sin perfil, sin CAD y sin GUI lanzada.

**Positivo.** `prepare`, `run` y `verify` con `--approvals`, sobre el plan aprobado:

- `run` dio `passed_scoped_l2` en 10 s:
  - 4 entidades añadidas, igual a las compiladas;
  - GUI propia con perfil aislado, cerrada con `exited`.
- `verify` dio `passed_scoped_l2` con `human_approval: rechecked`.

| Pieza | SHA-256 |
|---|---|
| Contrato | `3934D967247BC068494AE725BBB3A23E89F72C1720567BE3140CC5B8A30C05CE` |
| Informe | `F4E62EDD3D086F1F07C3A96845868BC079DD2388FFD6D06067ABBD4815F2F68B` |
| DWG | `80E7F98F7A5889F2B88717F09476EAFE749CAB2B5FD92A39CA652BED178A0977` |
| Captura | `08D45D440725BCDF4BD1FB0D3C194324012E525C8C702359694CF619AD0E603A` |
| Aprobación | `9B8AADB7B321925C6AF378336379E276C7C712EA15003994310B33CAEF75D61C` |

La evidencia queda en `target/mcp-release/l2-contrato-aprobado-20260930`, fuera de Git.

**Binario usado.** Artefacto de CI `target/distribution-port/runner-07f63cbe/OpenCADStudio.exe`:

- revisión `09794ab6`, un merge de integración del 28-sep;
- perfil **debug**;
- SHA-256 `94F01706…`, que coincide con su `runtime.json`.

**No es el código auditado** (`26bce00a`): difiere en 24 archivos de `src/`. No había un binario del código actual:

- el instalado en `%LOCALAPPDATA%\Programs\Open CAD Studio` es v2026.38, release, revisión `0d023d26`;
- la v2026.40.1 que el informe 06 da por instalada no apareció en la ruta del fork.

El L2 prueba la **puerta del contrato de punta a punta**, no la build de la GUI. La sesión abierta de Luis no se tocó.

## Pendiente

- **Niveles de aprobación** (decisión 7 del plan 08). Hoy todo exige firma humana.
- **Una aprobación sirve para más de una corrida.** Cada carpeta de corrida se ejecuta una sola vez, pero la misma aprobación habilita varias corridas del mismo plan y los mismos comandos. Queda por decidir si debe ser de un solo uso o acotada por alcance.
- **Repetir el L2 con un binario release del código vigente** (B19).
- **Integración con otros flujos.** El contrato solo protege la ruta `m8_case_cli`. No pasan por esta puerta:
  - los harnesses que hablan con el MCP directamente;
  - los scripts de ensayo que abren su propia GUI (p. ej. `apartment_door_trial_v10.py`).

  Los puentes L4 que llaman a `verify` con tres argumentos reciben `human_approval: not_rechecked`. Si su dictamen debe revalidar la aprobación, hay que pasarles el registro.

## Doble auditoría (Codex, 2026-09-30)

**Veredicto:** bloqueó el push por dos motivos:

- privacidad en el commit documental previo, en su versión local, que publicaría rutas locales, el programa de un proyecto privado y nombres y hashes de entregables;
- un commit nuevo añadido mientras auditaba.

**De la fase 4a, se corrigió en la ronda siguiente:**

- `status` informaba «approved» sin mirar canal ni comandos. Ahora reporta `usable_by_run`.
- La hoja solo contaba líneas, círculos y otros grupos. Desde esa ronda muestra la geometría de líneas, círculos y obstáculos y las coordenadas de los nodos; cotas y símbolos de ventana quedaron incompletos hasta la segunda auditoría.
- Las pruebas de integración de `run` no cubrían revocación, canal ajeno ni comandos alterados. Ahora sí.
- La guía rápida afirmaba que un agente «no puede» aprobar. Se precisó que es un freno de procedimiento.

**Confirmado sin cambios:**

- la puerta actúa antes de escribir nada y exige ambos hashes;
- la cadena y la atadura de la hoja resisten las alteraciones probadas;
- los límites declarados abajo son correctos.

## Segunda auditoría (Codex, 2026-10-01)

**Veredicto:** bloqueó la primera rama candidata por tres motivos:

- la hoja no mostraba los extremos ni los vínculos de las cotas, ni su `offset_m`, ni las líneas de los símbolos de ventana; además, «geometría completa» y el tope de 60 filas no describían lo que de verdad se ve;
- afirmaciones de «publicado» antes de publicar;
- un PID histórico en el commit documental.

**De la fase 4a, se corrigió:**

- La hoja muestra los extremos y coordenadas de cada cota, sus vínculos y su colocación con `offset_m`, y las seis líneas de cada símbolo de ventana.
- Las dudas y diferencias de vínculos y colocaciones nombran su cota; antes salía `?`.
- La cabecera dice si las tablas están completas o son parciales. El resumen JSON lo registra en `detail_rows_hidden`, con esquema `m4-plan-contract-review-2`.
- Hay cinco pruebas nuevas o ampliadas. Las cinco fallan contra el código anterior: se comprobó.

Los otros dos motivos se corrigieron en el historial redactado (08 §11).

## Límites (doctrina, no garantía)

- **Freno de procedimiento, no criptográfico.** Exigir una terminal interactiva lo evita un proceso que simule una terminal o que llame a la API de Python con el canal humano. `AGENTS.md` prohíbe hacerlo. Una firma con llave física queda para después.
- **La cadena tiene un punto ciego.** Detecta alteraciones y huecos intermedios, pero no el recorte del final del registro. Por eso cada corrida guarda el hash de su aprobación como ancla.
- **Qué cubre cada firma.** La aprobación cubre el plan y los comandos compilados. El binario lo cubre el contrato del caso (`prepare`).
- **La hoja no juzga el plan.** Resume lo que el PlanSpec declara; no comprueba que represente fielmente el encargo o la imagen.
- **Una hoja parcial no bloquea.** Con tablas «PARCIALES», aprobar exige leer el PlanSpec íntegro; la puerta no lo comprueba.
