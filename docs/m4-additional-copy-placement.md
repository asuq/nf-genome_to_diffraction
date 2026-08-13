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

`screen_additional_copies.nf` consumes a two-column TSV
(`seed_solution_id`, `search_model`) and fans out one isolated process per
approved seed. A genuine candidate-specific contract failure makes the run fail
after other submitted siblings finish; it does not kill the remaining
comparison immediately. Scientific tool/no-addition outcomes are written as
normalised records and return successfully. The workflow supports stub and
resume tests. The operation's content
identity binds the adapter version, review and seed IDs, parent/model/sequence/
MTZ/Phenix hashes, and the generated parameter-file hash.

Each search-model file is a content-tracked Nextflow input, so no redundant
model-index channel is required. The adapter and workflow place copy two from
each first-copy seed and advance an authenticated supported child one copy at a
time through copy 3..n. A comparative copy-count report, brief refinement, map
generation, sequence-from-map searching, and the second review checkpoint are
the next M4 increments. They must build on the typed child state rather than
overwriting the retained parent.

## Test coverage

Unit tests cover packed advancement from both `completed_hit` and explicitly
approved `completed_no_hit` parents, rejection of failed/unpacked/wrong-copy
parents, scientific no-additional-solution, strict parent retention,
search-model checksum drift, copy-two-to-copy-three lineage and coordinate
checks, the expected-copy stopping boundary, and finish-after-sibling-failure
orchestration.
The repository stub/resume suite exercises the Nextflow entry point under parser
v2. Real installed-Phenix qualification on Marmic remains required before this
increment is accepted as integrated.
