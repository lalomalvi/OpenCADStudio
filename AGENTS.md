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
- Existing user authorization for merging/pushing the fork remains valid. Ask only
  for missing information or permissions actually required by the environment.
- Preserve private drawings/images and historical evidence; never stage them.
  Use explicit paths when staging. No force push or reset to discard user work.
- Keep routine sync acceptance independent from the M7/M8 product evaluation.
  Close a sync with SHAs, required results and one short continuation record.
