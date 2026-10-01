# Working on this fork

For synchronizing upstream or publishing this fork, follow
[`docs/automation/FORK-SYNC.md`](docs/automation/FORK-SYNC.md).

- Publication destination: `https://github.com/lalomalvi/OpenCADStudio.git` only.
  Upstream `HakanSeven12/OpenCADStudio` is a read source.
- Start with `python docs/automation/fork_sync.py --fetch`. Reuse a suitable clean
  integration worktree. Freeze the returned upstream SHA for this cycle.
- Select checks from the actual changed paths before starting expensive work.
  Documentation does not require rebuilding CAD; Python-only tooling requires
  Python checks. Native/dependency changes require the relevant platform coverage.
- Reuse successful checks only with verified source/environment/scope equivalence.
  A source fingerprint alone is not a passing test. Do not run the same gate again
  merely to change an evidence label or because a documentation commit was added.
- Keep one Cargo producer per target directory. Commit the source before a build
  that must report its revision. Preserve the worktree cache and historical runs.
- Observe existing run/process IDs; do not restart because observation timed out.
  Report progress when the phase changes; avoid minute-by-minute repetitions.
- Use `python docs/automation/fork_sync_ci.py --start --base <frozen-fork-sha>`
  after publishing the candidate branch. It observes an existing unified Tests
  run before dispatching. Do not separately dispatch Python host check: Tests
  calls it when required. A failed/uncertain dispatch claim is preserved.
- Reuse the successful Windows runner with `fork_sync_ci.py --artifact --reuse-ref
  <tested-sha>`; keep its producer SHA/version. Verify hashes before executing it.
  The receipt must cover the required scope; omitted jobs are not passed tests.
- Existing user authorization for merging/pushing the fork remains valid for routine
  fork synchronization only; it does not cover the MCP stabilization cycle below.
  Ask only for missing information or permissions actually required by the environment.
- Preserve private drawings/images and historical evidence; never stage them.
  Use explicit paths when staging. No force push or reset to discard user work.
- Keep routine sync acceptance independent from the M7/M8 product evaluation.
  Close a sync with SHAs, required results and one short continuation record.

## Desktop installation

- For desktop download/install/open requests, complete the operational contract
  in [docs/install/agents.md](docs/install/agents.md) and the platform guide.
- This fork is `lalomalvi/OpenCADStudio`; do not substitute upstream releases.
- Preserve user DWG/DXF files, sessions and historical evidence. Use isolated
  synthetic fixtures and a private configuration for GUI acceptance.
- Use Cargo.lock (`--locked`). Keep protocol, GUI, CAD and publication results
  distinct. Do not declare native compatibility from script syntax checks.
- No release publication or global tool installation is implied by offline tests.


## Web acceptance

- For this fork, use its verified GitHub Pages origin and repository links;
  never carry upstream CNAME/domain settings into the fork deployment.
- A green WASM build, valid HTTP assets or the Start page do not establish editor
  acceptance. Create an isolated empty drawing and inspect the rendered viewport
  and console; preserve any panic with its source/module identity.
- Keep browser GUI, desktop GUI/MCP, CAD interoperability and native publication
  results separate. A web-only fix does not relabel earlier native packages.

## MCP improvement continuity

For MCP evaluation, performance and hardening work, start with §11 "Estado vigente"
of [the stabilization plan](docs/automation/masterplan/08-PLAN-DE-ESTABILIZACION-20260930.md):
current location, verified results, broken or partial items, next steps, pending
decisions and the commands that recompute every figure. It builds on
[the independent audit](docs/automation/masterplan/07-AUDITORIA-INDEPENDIENTE-MCP-20260930.md)
and [the earlier consolidated report](docs/automation/masterplan/06-INFORME-MAESTRO-Y-MEJORAS-20260929.md).
This cycle is local-only: do not push based on historical publication authorization.

- Human-agent plan contract: an agent may write a PlanSpec review with
  `plan_contract.py review`, but never runs `approve` or `revoke`, never writes an
  approval registry and never emulates an interactive terminal to satisfy it. Only
  Luis approves plans. Without an active approval, `m8_case_cli.py run` must not
  open the GUI.
- Pushes of this cycle require, in order: a frozen commit SHA; a Codex audit of
  that exact range with no new commits while it runs (double audit); a
  publishability review (no absolute local paths, private project programs or
  private deliverable names/hashes anywhere in the history being published); and
  Luis's explicit approval of that frozen range.
