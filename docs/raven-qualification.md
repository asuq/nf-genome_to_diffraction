# Raven release qualification

The internal `nf-gtd-raven` task now accepts fixed control, M6 and reviewed
continuation stages through the same owned login controller used by
[identification](raven-identification.md). It exposes no arbitrary command,
workflow path or extra Nextflow argument. Independent hypotheses, chains and
finalists remain items in the existing Nextflow graphs.

This is qualification preparation. Local tests do not establish installed
Phenix, native Raven, M6, unknown-crystal or release acceptance.

## Source, site and input authority

Identification keeps its existing schema-1.0 launch. Release qualification uses
the separate `RavenQualificationLaunch` schema-2.0
[ownership contract](../src/genome_to_diffraction/schemas/raven.py), validated by
[raven_qualification.py](../src/genome_to_diffraction/hpc/raven_qualification.py).
Store identical private local `run.json` and remote `launch.json` records using
the existing client configuration and run ownership. No migration or scientific
record is inferred from directory recency.

Each qualification launch binds:

- the fixed stage and its matching run ID, account and owner;
- exact clean source commit/tree, helper commit, observed Pixi version and
  actual lock checksum;
- the licensed Phenix manifest and its checksum;
- successful exact-source CI run/job evidence, copied as
  `exact-source-ci.json` inside the input bundle;
- the owner's completed Raven smoke launch, terminal state and assessment
  checksums, using the same account and runtime; and
- the complete regular-file input inventory.

The smoke's selected cases must all have native completed hit/no-hit records,
matching retained checksums and Slurm task/resource evidence. Its controller
exit alone is insufficient. Its original source identity stays historical.
Changed release science receives fresh qualification.

All executable paths, inputs, source snapshots, work, temporary files and
caches stay under the approved `/ptmp/USER/nf-genome_to_diffraction` root.
The maintained Raven profile supplies the 250-outstanding-task submission guard
below the observed 300-submission account limit. The inspected account permits
eight running jobs. Raven keeps its mandatory 24-hour limit; the temporary
Marmic identification cap does not apply.

Before constructing a launch, stage its already reviewed inputs as regular
files. At the root write `raven-qualification-inputs.json` with exactly
`schema_version: "1.0"`, `source_commit`, `control_id` and `parameters`.
Parameter values are paths relative to this root. `control_id` is one of
`7L6G`, `3U7Q` or `9ECN` for fixed controls and null for other stages.
The stage's exact parameter names are declared in the module; unknown names,
escaping paths, symlinks, missing inputs and changed files are rejected.
`input_identity(root)` derives the `ravenqualificationinputs_` content ID
over every file, including the document and CI evidence. The input bundle is
immutable after its launch record is written.

This route does not deploy source, install tools, transfer private inputs or
retire the owner's identification run. Complete those separately authorised
preparations using the existing migration procedure before starting a new run.

## Fixed operations

| Stage | Existing execution |
| --- | --- |
| `control-first-copy` | Fixed first-copy control hypotheses in `qualification.nf` |
| `control-additional-copy` | Reviewed sequential-copy workflow |
| `control-refinement` | Existing bounded finalist workflow |
| `control-composition-attempts` | Selected composition-attempt workflow, including distinct negative controls |
| `control-reopening` | Reviewed no-A workflow, stopping at its next owned A package |
| `m6-operational`, `m6-leakage` | Full unchanged partitions in `m6_validation.nf` |
| `m6-comparison-initial`, `m6-comparison-continuation` | The two separately frozen [comparison stages](m6-ranking-comparison.md) |
| `unknown-single-component` | Existing reviewed continuation application |
| `unknown-pass2` | Existing RG7-validated composition/no-A application |

Known-control reopening uses a portable manifest with `schema_version: "1.0"`,
`crystal_id`, `parent_run_id` and the exact `paths` listed by
[raven_controls.py](../src/genome_to_diffraction/hpc/raven_controls.py). Its
validation task reuses the same source/parent/package/selection checks as
unknown pass 2 and requires an explicit reviewed reopening request. It cannot
admit an unknown crystal. It does not require the later RG7 closure evidence.

Unknown single-component launches require the exact screen parent and staged
handoff. The existing validator rechecks original reviewed crystal bytes,
including the explicit Free-R selection, before both first execution and
resume. Unknown pass 2 revalidates its portable input inventory, source tree,
current finding-ledger checksum and complete RG7 evidence before dispatch.
No rank or benchmark result supplies a human decision.

## Replay, resources and collection

The controller runs a first phase and its cached replay. Failed first execution
stops replay. Each phase has a retained trace and command; cancelled or failed
controllers retain available native diagnostics. Missing terminal task evidence
is a controller failure.

M6 uses [its Raven execution policy](../benchmarks/m6/execution-nextflow-raven-v1.yaml):
the existing per-task limits of 32 CPUs, 16 GB and 24 hours, existing bounded
search batches and Raven's scheduler admission. CPU and memory semantics have
not changed. The login controller is recorded separately from Slurm workers;
the existing local coordinate-staging task remains a controller stage.

The leakage launch additionally binds its original runner archive and the
completed operational parent's launch/state/summary/checksum digest. It must
use the identical source, input bundle and runtime, and only that parent's
completed cache. First/resume child checksums, actual scheduled hypotheses,
native statuses and full case partitions remain verified. Raven collection
feeds the existing 63-case truth-side collector and unchanged acceptance
criteria. Comparison records cannot substitute for full M6.

Use the existing fixed client commands:

```text
pixi run --locked nf-gtd-raven --config CONFIG start --run-id RUN_ID
pixi run --locked nf-gtd-raven --config CONFIG status --run-id RUN_ID
pixi run --locked nf-gtd-raven --config CONFIG logs --run-id RUN_ID --tail 200
pixi run --locked nf-gtd-raven --config CONFIG collect --run-id RUN_ID
```

Collection preserves commands, logs, JSON records, coordinates, both traces,
resolved allocations and failed-attempt diagnostics within the existing
12-GiB archive and 128-MiB file bounds. Large MTZ assets remain on Raven and
are explicitly indexed by checksum. Oversized or unsafe collection fails
instead of silently dropping evidence. Collection never converts a native
failure into a no-hit or a reusable scientific cache.

Unit checks cover stage restrictions, source/CI mutation, completed smoke
requirements, failure retention, replay and both Raven records through the
full M6 collector. The real Nextflow reopening check executes the shared
authority validator, schedules one selected stub hypothesis, verifies cached
replay and rejects an unknown-crystal mutation. Native qualification remains
required before release gates can close.
