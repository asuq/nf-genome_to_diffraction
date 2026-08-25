# Phase III unknown-pass-1 local screen stub

## Scope

This is the smallest local, path-closed scheduling boundary for the fixed
unknown-pass-1 screen. It uses synthetic public-fixture identifiers and bytes;
it does not contain, name, inspect, or analyse an operator dataset. It runs no
Phaser, Phenix, provider, localisation runtime, remote service, or HPC profile,
and cannot support a scientific result.

The fixed stub exposes no input path, crystal selector, ranking threshold, or
attempt-cap parameter. Its Pixi task accepts no arguments. Test-local files are
resolved beneath an ephemeral launch directory, and all tracked contracts are
path-free.

## Exact inputs and outputs

The local builder consumes:

- one strict `PhaseIIIExecutionIdentity` containing one synthetic public
  catalogue, three synthetic MTZ identities, one database identity, source and
  environment identities, all seven required Phenix tool identities, adapter
  versions, and both remote/network booleans fixed false;
- one path-free three-stage index from the owned-run crystallographic staging
  bridge. Each indexed two-file stage is bound to one registry-resolved,
  content-addressed single-crystal package and one `proceed|hold` decision;
- one checksum-verified catalogue preparation, provider preparation, and
  offline-localisation preparation shared across all crystals;
- exactly three local MTZ files; and
- complete ranked A-hypothesis inventories plus every model-backed hypothesis
  file.

The bridge accepts no package path: it resolves all three packages by exact
owned run/crystal/checkpoint, stages only their canonical manifests, and
publishes atomically after a final registry revalidation. The builder resolves
and checksums every local file, verifies the exact indexed three-directory
review-stage root and each canonical decision checksum, compares each MTZ to its
execution artifact, compares every model to its hypothesis checksum, and writes
one content-addressed `UnknownPass1ScreenInventory`. No machine path is retained
in that inventory.

The fixed fixture contains:

- one `ready` crystal with 25 selected A tasks over seven exact models (including
  repeated-model copy hypotheses), one `deferred_cap` candidate, and one
  retained `unsearchable_no_model` candidate;
- one `held` crystal with no A task; and
- one proceeding `empty_no_model` crystal retaining two unavailable candidates
  and scheduling no A task.

Thus Nextflow receives exactly three complete crystal items and exactly 25 A
tasks. Every crystal tuple carries its item record, exact MTZ, complete global
execution identity, staged review directory, and all three shared preparations.
Every A tuple additionally carries its exact model and task record. The complete
three-crystal inventory is retained once at the run boundary rather than copied
into independent child tasks. The stub A adapter emits only
`stub_only_no_scientific_result`; non-stub invocation fails deliberately.

Each selected A task explicitly carries its parent hypothesis's exact
`requested_copy_count` in `1..4`. This field participates in the task's
content-addressed identity, and the complete screen refuses a task whose copy
count differs from its selected hypothesis. The ordinary diverse-model funnel
retains the corresponding explicit `--joint-copy-search` mode. Current
application execution enters through `phase3_application.nf`, where joint mode
is mandatory and has no compatibility switch. It retains all four configured
physically possible alternatives, ignores copy counts above four, and bounds
all selected A hypotheses to 25 per crystal. Historical single-copy execution
remains isolated under the archival root.

## Status, failure, and cache semantics

`ready`, `held`, `empty_no_model`, and `empty_no_hypotheses` are typed scheduling
branches. A hold is not an execution failure, and model absence is not a tool
failure. Duplicate or missing crystals, decisions, MTZs, models, candidate
ranks, allocation ranks, task rows, or shared identities fail before fan-out.
The selected cap is structural (`allocation_rank <= 25`) rather than an exposed
threshold.

The screen inventory, crystal items, A hypotheses, and A tasks are independently
content-addressed. Nextflow task hashes additionally consume all exact file
bytes. The dedicated stub requires the first run to schedule one catalogue,
one provider, one localisation, three crystal-bound review-stage preparations,
three crystal items, and 25 A tasks. Resume must cache all 34 tasks with
unchanged hashes and byte-identical retained outputs. Changing one crystal's
typed candidate inventory then reruns only its own crystal task; the other
33 tasks, including all 25 sibling A hypotheses, remain cached and their
published outputs remain byte-identical.

## Test command and boundary

Run:

```console
pixi run --locked unknown-pass1-screen-stub
```

Focused unit coverage checks exact branch and task counts, the separate
proceeding empty-hypothesis state, canonical write/load stability, MTZ/model and
review mutation, remote-provider/offline-localisation policy refusal, hold
enforcement, exact requested copy propagation/mutation, the 26th-allocation
boundary, and content-ID mutation. Funnel regressions cover copies one through
four, the excluded fifth copy, retained fourth-ranked alternatives, the fixed
25-attempt cap, and unchanged legacy behaviour. Repository Nextflow lint covers
the workflow and modules.

This closes the local registry-to-crystallographic-stage-to-screen wiring and
stub integration. Remote owned-run collection, the qualified first-copy Phaser
adapter, the fixed remote/HPC profile, seed-review packages, and all operator
analyses remain closed.
