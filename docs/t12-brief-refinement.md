# T12 brief refinement, maps, and sequence narrowing

## Purpose and boundary

T12 compares every retained M4 finalist with one fixed, conservative Phenix
protocol. It does not approve a structure, force a unique sequence/locus, or
discard a candidate because refinement or sequence scoring is poor. The output
is evidence for Coot review and the second file-based checkpoint.

The first increment is exposed by `refine_finalists.nf` and the Python command:

```text
genome-to-diffraction refinement brief ...
```

## Inputs and outputs

Each finalist row supplies its immutable solution ID, exact-sequence group,
best supported M4 copy count, checksum-bound parent PDB, the original
FreeR-bearing diffraction MTZ, and diffraction resolution. The corresponding
Phaser solution MTZ remains staged and checksum-bound as provenance but is not
used as the refinement observations file. Shared inputs are the complete
exact-sequence-group catalogue, its source-record/locus crosswalk, and a
verified Phenix 2.1-6048 manifest.

The MTZ preflight's checksum-bound selected observation labels are passed
explicitly to `phenix.refine`; files containing both merged and anomalous
intensity arrays are therefore not resolved by an implicit Phenix choice.

The adapter retains:

- the exact `phenix.refine` and `phenix.sequence_from_map` argument arrays;
- initial/final `R_work` and `R_free`, available geometry metrics, warnings,
  logs, versions, and input/output checksums;
- a sigma-scaled whole-cell `2mFo-DFc` CCP4 map with missing observations left
  unfilled;
- every exact-sequence group that receives a score, ordered by raw score; and
- every source record and compatible locus linked to each exact sequence.

The stable result files are `brief_refinement_result.json[.l]`,
`sequence_map_result.json[.l]`, `t12_command.json`, refined PDB/MTZ/map assets,
and the two bounded raw logs. Top-10 and top-25 rendering and the second approval
template remain the next T12.5 increment.

## Fixed scientific protocol

The comparison uses one macrocycle of individual coordinate and isotropic ADP
refinement, Phenix random seed `2679941`, no simulated annealing, and no ordered
solvent addition. It preserves the input free-reflection set; missing free flags
or other invalid reflection contracts fail loudly instead of generating a new
comparison set. Map generation uses `2mFo-DFc`, CCP4, sigma scaling, the full
cell, and no filled missing observations.

`phenix.sequence_from_map` receives the complete catalogue in one checksum-bound
multi-FASTA file. Its score is ranking evidence, not a calibrated probability.
Unscored groups remain distinguishable from low scores, and duplicate sequences
remain one exact-sequence group mapped back to all compatible source records.

## Failure and cache semantics

Input/checksum errors fail the candidate before Phenix. A non-zero Phenix exit
is `failed_tool_execution`; exit zero without required model/MTZ/map assets is
`failed_parse`; sequence analysis is `skipped_ineligible` when refinement did
not produce its required assets. Candidate-level failures use Nextflow
`errorStrategy 'finish'`, so the other finalists continue.

The cache identity includes protocol version, solution/group/copy identity,
parent PDB/MTZ checksums, complete catalogue/crosswalk checksums, Phenix-manifest
checksum, resolution, and thread count.

## Resources and tests

Viper uses four CPUs and 16 GB per finalist with at most four simultaneous T12
tasks (16 CPUs total) and the site-wide 24-hour scheduler ceiling. The adapter
itself imposes no runtime timeout.

Unit tests cover the fixed command policy, R-value parser, complete-catalogue
ranking/crosswalk, and checksum rejection. `nextflow-check` parses the typed
module/workflow, while `nextflow-stub` verifies publication and cached resume
without fabricating scientific success. Real acceptance still requires all 11
retained CD6 finalists to run through the verified Viper Phenix installation.
