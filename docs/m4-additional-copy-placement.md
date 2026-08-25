# M4 additional-copy placement

## Status and scientific purpose

The sequential-copy M4 increment is implemented: for every explicitly approved
first-copy solution, `phenix.phaser` fixes the approved coordinate state at its
placed origin and searches exactly one additional copy of the same component at
each step.
This is comparative evidence for the `ASU = nA` prototype. It does not identify
the protein, prove a copy absent, or implement heteromeric reconstruction.

All approved seeds remain independent alternatives. A child state advances
only when Phaser emits coordinate and MTZ files, reports a packed solution, and
the coordinate output contains exactly the next expected placement count.
Otherwise the parent remains the best supported state. Numeric LLG/TFZ values
and their raw delta are retained but are not a calibrated acceptance
probability.

The normal `main.nf` workflow now reaches this operation through
`--analysis_stage additional_copy`. It accepts an explicit
`--approved_mr_seeds` TSV only; it never edits or fills the decision file. The
stage revalidates the current review package and every decided asset, copies the
approved first-copy solution coordinate as the next search model, and records
that rigid-body derivation alongside the distinct original first-copy model
checksum. A one-copy hypothesis is retained as already complete and does not
receive an invalid copy-two search.

The staging command used by Nextflow is:

```text
genome-to-diffraction mr stage-approved-seeds \
  --review-package mr_seed_review \
  --decisions approved_mr_seeds.tsv \
  --hypotheses mr_hypotheses.jsonl \
  --outdir approved_mr_seed_stage
```

It writes the copied decision file, `validated_mr_seed_decisions.json`,
`approved_seeds.tsv`, `additional_copy_seeds.tsv`, checksum-named model files,
and `live_m4_stage_manifest.json`. Unknown/stale IDs, pre-package timestamps,
placeholder reviewers, unsafe assets, checksum drift, missing model provenance,
and an empty approval set fail the checkpoint before Phaser. Its content
identity binds the review/package, decisions, hypotheses, approved IDs, and both
model checksums. Unit tests cover runnable and already-complete seeds; the
integrated parser-v2 stub and `-resume` test prove the file gate precedes the
sequential-copy fan-out.

Phase III uses a separate clean-break boundary. It does not accept or generate
the normal-workflow approval TSV or schema-v1 validation/stage records:

```text
genome-to-diffraction mr stage-phase3-seeds \
  --review-stage phase3_a_review_stage \
  --review-package-manifest owned_a_package/phase3_review_package_manifest.json \
  --hypotheses mr_hypotheses.jsonl \
  --owned-run-registry completed_unknown_screen \
  --execution-identity phase3_execution_identity.json \
  --owned-parent-run gtd-unknown-screen-... \
  --outdir phase3_seed_stage
```

The output contains `phase3_seed_stage_manifest.json`, the two seed tables,
checksum-named models, and byte-identical snapshots of the canonical package
and decision stage. The stage is revalidated from its content identity,
allow-list, checksums, typed decisions, package evidence, model inventory, and
owned-run provenance before either Phaser or refinement reads it. Reviewed
crystal routes therefore carry no external legacy MR review directory.

`--analysis_stage t12` adds the normal-workflow retained-parent handoff after
that fan-out. The `refinement stage-live` adapter authenticates the approved
stage, exact review package, hypothesis catalogue, every typed copy-series
record, command/log pointer, parent-child transition, and child PDB/MTZ
checksum. For each approved seed it retains the last supported child, or the
first-copy review coordinate when the hypothesis expected one copy or the first
addition ended in a typed failure. It rejects a missing result bundle as an
execution failure instead of silently treating it as scientific evidence.

The handoff publishes `finalists.tsv`, `copy_count_report.tsv`,
`copy_count_report.md`, `t12_stage_manifest.json`, one staged parent PDB, and
one provenance-only Phaser solution MTZ per seed. The finalist's refinement MTZ
is always the original checksum/preflight-bound diffraction file with FreeR
flags. The manifest records all raw attempt metrics and statuses and states
`parent_retained=true` and `failed_addition_proves_absence=false` for every
candidate. Its cache identity binds the decisions, live M4 stage, review,
hypotheses, catalogue crosswalk, preflight, Phenix manifest, diffraction MTZ,
and selected coordinate/solution-MTZ checksums.

## Python interface

The command is:

```text
genome-to-diffraction mr add-copy \
  --review-validation VALIDATED_APPROVAL.json \
  --review-package-manifest mr_seed_review_manifest.json \
  --seed-solution-id sol_SHA256 \
  --hypotheses mr_hypotheses.jsonl \
  --sequence-groups sequence_groups.jsonl \
  --preflight mtz_preflight.jsonl \
  --mtz integrated.mtz \
  --search-model processed_model.pdb \
  --phenix-manifest phenix_install_manifest.json \
  --threads 4 \
  --outdir additional_copy_sol_SHA256
```

The Phase III invocation replaces both legacy approval arguments with the one
canonical authority and also requires its selected diffraction record:

```text
  --phase3-seed-stage-manifest phase3_seed_stage/phase3_seed_stage_manifest.json \
  --diffraction-selection phase3_diffraction_selection.json
```

Supplying either legacy approval argument together with the Phase III stage is
an input-contract failure before Phenix execution. The same exclusivity applies
to `refinement stage-live`; Phase III supplies the seed-stage manifest and no
legacy review-package argument.

For copy 3..n, repeat the command with both arguments pointing to the
immediately preceding supported child:

```text
  --parent-result previous/additional_copy_result.jsonl \
  --parent-coordinate previous/PHASER.1.pdb
```

These arguments are inseparable. The typed result must be a supported
`completed_hit` child of the same approved seed, review, hypothesis, sequence
group, and expected-copy hypothesis; its coordinate checksum and observed
placement count must match. A failed or unsupported addition cannot become the
next parent, and an already complete `n`-copy state cannot advance beyond its
hypothesis.

The workflow uses `--until-expected` to perform this bounded sequence for each
approved seed. It writes every copy-specific child in a separate directory,
plus `additional_copy_series_results.jsonl` and
`additional_copy_series_summary.json`. The series stops at expected `n` or the
first unsupported addition. All attempted and parent states remain available;
the stop is not an absence claim and does not remove the candidate from later
human comparison.

Inputs are authenticated against their prior records:

- the approval must name the current review package and seed;
- the review manifest and parent coordinate must match their recorded hashes;
- the parent must be a successfully parsed, packed, typed result containing
  exactly one placed copy; `completed_hit` and score-annotated
  `completed_no_hit` parents are both eligible after explicit approval;
- the hypothesis, exact catalogue sequence, observation labels, and MTZ
  preflight must agree;
- the MTZ hash must match preflight; and
- the search-model hash and identity parameter must match the original
  first-copy command record.

Phenix is invoked only through the verified installation manifest. The adapter
writes `add_copy.eff`, defining `fixed_parent` with
`solution_at_origin = True`, defining a separate `search_copy` ensemble, and
searching one copy. The exact catalogue sequence and full expected copy count
define composition. No adapter timeout is imposed unless the caller explicitly
sets one.

## Outputs and failure semantics

Each copy-specific attempt directory contains:

- `additional_copy_result.json` and `.jsonl`;
- `phaser_command.json` and `add_copy.eff`;
- the captured/native Phaser log; and
- child PDB/MTZ files when Phaser emits them.

The typed result records immutable attempt, review, seed, parent, child,
hypothesis, and sequence-group IDs; parent/attempted/expected copy counts; raw
LLG, LLG delta, and TFZ; placement and packing evidence; file hashes; warnings;
and separate execution status. `parent_retained` is always true and
`failed_addition_proves_absence` is always false.

- A packed result with exactly parent count plus one placement is
  `completed_hit` and supports that child count.
- A valid zero-solution run is `completed_no_hit` and retains its immediate
  parent count.
- Unpacked or incomplete parsed solutions are retained as evidence but do not
  advance the best-supported count.
- Tool, parse, input-contract, and infrastructure failures remain distinct and
  do not become scientific no-hit claims.

## Nextflow and cache identity

`qualification.nf --qualification_stage additional_copy` consumes a seed TSV
containing
`seed_solution_id`, `search_model`, and `search_model_sha256` (with optional
stage metadata columns) and fans out one isolated process per approved seed
that requires another copy. A genuine candidate-specific contract failure makes the run fail
after other submitted siblings finish; it does not kill the remaining
comparison immediately. Scientific tool/no-addition outcomes are written as
normalised records and return successfully. The workflow supports stub and
resume tests. The operation's content
identity binds the adapter version, review and seed IDs, parent/model/sequence/
MTZ/Phenix hashes, and the generated parameter-file hash.

Each search-model file is a content-tracked Nextflow input, so no redundant
model-index channel is required. The adapter and workflow place copy two from
each first-copy seed and advance an authenticated supported child one copy at a
time through copy 3..n. The normal workflow now feeds every retained best state
into brief refinement, map generation, and sequence-from-map searching. The
remaining normal-workflow M4 boundary is publication of the second review
checkpoint from those typed T12 results.

## Copy-count report

`genome-to-diffraction mr copy-report --results SERIES.jsonl --outdir REPORT`
validates every contiguous parent-child series and publishes typed JSONL, TSV,
Markdown, and a checksum-bound manifest. It compares the Matthews-intended
count with the best empirically supported count and retains the terminal raw
LLG, TFZ, LLG delta, packing, placement, and execution evidence. A series that
stops early is flagged for possible residual content or special-position
review and explicitly states that copy absence was not proven. The Marmic M4
profile runs this report automatically for every retained candidate.

## Test coverage

Unit tests cover packed advancement from both `completed_hit` and explicitly
approved `completed_no_hit` parents, rejection of failed/unpacked/wrong-copy
parents, scientific no-additional-solution, strict parent retention,
search-model checksum drift, copy-two-to-copy-three lineage and coordinate
checks, the expected-copy stopping boundary, and finish-after-sibling-failure
orchestration.
The repository stub/resume suite exercises both the standalone and normal
Nextflow entry points under parser v2. The adapter has completed real installed-
Phenix qualification on retained Viper CD6 evidence. The live T12 selector has
focused tests for expected-one, expected-count-reached, unsupported-after-
supported, typed tool-failure, and changed-child-checksum outcomes. Its normal
workflow connection passes local parser-v2 stub and fully cached resume; a clean
fixed truth-labelled operational matrix supplies the M5 real-data acceptance
boundary. The three unknown operator crystals are deferred until after M6 and
do not gate this adapter.
