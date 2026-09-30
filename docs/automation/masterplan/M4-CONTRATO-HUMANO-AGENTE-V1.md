# M4 · Contrato humano–agente v1 (fase 4a)

**Fecha:** 2026-09-30 · **Plan:** [08 §3](08-PLAN-DE-ESTABILIZACION-20260930.md)
**Estado:** verificado en L0/L1. El L2 con GUI está pendiente hasta la primera aprobación humana real.
**Código:** `plan_contract.py`; puerta en `m8_case_cli.py`

## Qué hace

1. **`review`.** Escribe una hoja de revisión de una página, determinista, en una carpeta nueva que no se sobrescribe. Contiene:
   - lo que se va a dibujar (muros con longitud y espesor, vanos con giro o antepecho, uniones, cotas);
   - los **supuestos** (`source.classification = inferred`) y las **dudas** (`unknown`), con su confianza;
   - los bloqueos y lo no soportado según `dry_run`;
   - lo que se verificará y, explícitamente, lo que **no**;
   - con `--previous`, las diferencias contra la versión anterior del plan.
2. **`approve` y `revoke`.** Solo los usa el humano, en una terminal interactiva.
   - El comando muestra la hoja y exige teclear los primeros 12 caracteres del hash del plan.
   - Si hay dudas, exige además teclear `ACEPTO DUDAS`.
   - La decisión queda en un registro JSONL encadenado: `sequence`, `previous_record_sha256` y `record_sha256`, con escritura sincronizada a disco.
   - La aprobación ata el hash del plan, el `commands_sha256`, las dos hojas y el código del compilador.
3. **Puerta de ejecución.** `m8_case_cli.py run` exige una aprobación vigente del mismo plan **y** de los mismos comandos compilados, registrada por el canal humano. Sin ella no crea carpetas ni abre la GUI.
   - El informe de la corrida guarda `approval_record_sha256`.
   - `verify --approvals` vuelve a comprobarla.
4. **Contrato del caso.** Pasa a `m8-deterministic-case-contract-2` e incluye el hash de `plan_contract.py`. El paquete de release lo incorpora a su lista cerrada.

## Verificado (2026-09-30, Windows, Python 3.13.7)

**`test_plan_contract.py` (15 pruebas):**

- determinismo de la hoja;
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

**`test_m8_case_cli.py` (7 pruebas):**

- con un plan **no aprobado**, `Popen` no se llama y no se crean carpetas;
- con un plan **aprobado**, la puerta deja pasar hasta el lanzamiento de la GUI (simulado);
- `verify` sin atadura de aprobación se rechaza.

**Suites completas:** masterplan 220/220 y automatización 59/59.

**Humo del CLI:**

- `review` escribió la hoja del fixture `synthetic-wall` (hash `DDA61A032A26…`).
- `approve`, lanzado desde el harness de un agente, se negó por falta de terminal interactiva y no creó el registro.

## Pendiente

- **L2 real.** Luis aprueba el fixture sintético en su terminal. Después se corren `prepare`, `run` y `verify` con GUI propia y `--approvals`.
- **Niveles de aprobación** (decisión 7 del plan 08). Hoy todo exige firma humana.
- **Integración con otros flujos.** El contrato solo protege la ruta `m8_case_cli`. Los harnesses que hablan con el MCP directamente no pasan por esta puerta.

## Límites (doctrina, no garantía)

- **Freno de procedimiento, no criptográfico.** Exigir una terminal interactiva lo evita un proceso que simule una terminal o que llame a la API de Python con el canal humano. `AGENTS.md` prohíbe hacerlo. Una firma con llave física queda para después.
- **La cadena tiene un punto ciego.** Detecta alteraciones y huecos intermedios, pero no el recorte del final del registro. Por eso cada corrida guarda el hash de su aprobación como ancla.
- **Qué cubre cada firma.** La aprobación cubre el plan y los comandos compilados. El binario lo cubre el contrato del caso (`prepare`).
- **La hoja no juzga el plan.** Resume lo que el PlanSpec declara; no comprueba que represente fielmente el encargo o la imagen.
