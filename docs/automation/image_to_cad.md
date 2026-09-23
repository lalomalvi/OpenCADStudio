# Image-to-CAD reconstruction acceptance

This protocol evaluates whether one explicitly named vision model can turn a
raster plan into an editable CAD drawing through the OpenCADStudio MCP. It does
not treat visual plausibility as geometric proof.

## Frozen boundary

- The source JPG/PNG is read-only and its SHA-256 is recorded before and after.
- The model is `gpt-6-luna` at `medium` reasoning. No second model, manual
  tracing, OCR service, vectorizer, source DWG/DXF, copy/paste, `embed_image`,
  or direct entity-record injection is allowed.
- OpenCADStudio commands, its geometry kernel, MCP reads, viewport captures,
  audit, and `save_verified` are allowed. The same model may inspect captures
  and correct its own work.
- A known dimension is required for metric-scale scoring. Without one, the run
  may establish shape/topology fidelity only and must report scale as unknown.
- Hidden geometry, illegible text, ambiguous line weight, and information not
  present in the raster are reported as unresolved; they are never invented.

## Required run artifacts

Each run gets a new absolute directory and retains:

1. `RUN-CONTRACT.json`: model snapshot, reasoning, source path/hash/dimensions,
   calibration, allowed tools, tolerances, and output paths.
2. `MODEL-TRANSCRIPT.jsonl`: model messages and MCP calls without secrets.
3. `COMMANDS.jsonl`: request IDs, script chunks, completion indexes, revisions,
   failures, corrections, and changed handles.
4. `AUDIT.json`: target-format audit immediately before delivery.
5. `SAVE-VERIFIED.json`: explicit DWG version, reopen result, semantic manifest,
   and output SHA-256.
6. `FINAL.png`: final OCS viewport capture and a human-review checklist.
7. `VERDICT.json`: criterion-by-criterion pass/fail/unresolved result. A partial
   result is not promoted to success.

## Execution order

1. Hash and inspect the raster. Record image quality and one scale anchor when
   metric accuracy is required.
2. Ask Luna for a structured inventory: visible extents, layers, repeated
   symbols, primitives, annotations, dimensions, ambiguities, and an ordered
   construction plan.
3. Create a blank drawing. Discover every unfamiliar command manifest before
   executing it.
4. Build in bounded `run_script` chunks. Keep strict mode enabled. After every
   chunk, read entity counts/bounds and query critical intersections; after each
   major region, capture the viewport for Luna's self-review.
5. Correct through new request IDs and explicit commands. Do not replace the
   failed transcript or hide partial edits.
6. Reject any drawing containing a raster-image entity. Audit the requested
   DWG/DXF version, call `save_verified` to a new absolute path, reopen it, and
   capture the reopened result.
7. Confirm the source hash is unchanged and no OpenCADStudio lock remains.

## Acceptance gates

All hard gates must pass:

- exactly one permitted model was used;
- no forbidden tracing/vectorization/input source was used;
- every script finished with zero unconsumed tokens and no waiting command;
- no raster-image entity exists in the output;
- all finite-geometry, duplicate-handle, dangling-reference, reopen, semantic
  manifest, and target-version checks pass;
- the delivered file hash and source-image before/after hashes are recorded;
- all declared unresolved items are visible in the verdict.

Fidelity is reported in separate categories rather than one inflated score:

- topology: connectivity, closed boundaries, intersections, repetitions;
- geometry: calibrated lengths/radii/angles and relative placement;
- semantics: entity types, layers, blocks, text, dimensions, and hatches;
- visual: registered image comparison plus human inspection of legibility and
  draw order.

The first acceptance should use a clean, bounded 2D architectural or mechanical
plan with one readable dimension. A successful simple-plan run authorizes a
harder cohort; it does not establish universal JPG-to-CAD fidelity.
