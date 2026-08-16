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

The normal workflow reaches the same adapter with
`--analysis_stage t12` after an explicit MR-seed decision. Its staging command
is fixed by Nextflow:

```text
genome-to-diffraction refinement stage-live \
  --approved-stage approved_mr_seed_stage \
  --review-package mr_seed_review \
  --additional-copy-result additional_copy_SEED ... \
  --hypotheses mr_hypotheses.jsonl \
  --sequence-groups sequence_groups.jsonl \
  --source-records source_records.jsonl \
  --preflight mtz_preflight.jsonl \
  --mtz input.mtz \
  --phenix-manifest phenix_install_manifest.json \
  --outdir live_t12_stage
```

The repeatable result option is omitted when every approved hypothesis already
expects one copy. The adapter accepts no inferred score decision and retains all
approved candidates.

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
- sigma-scaled whole-cell `2mFo-DFc` and `mFo-DFc` CCP4 maps with missing
  observations left unfilled, plus both coefficient/phase pairs in the refined
  MTZ;
- every exact-sequence group that receives a score, ordered by raw score; and
- every source record and compatible locus linked to each exact sequence.

The stable result files are `brief_refinement_result.json[.l]`,
`sequence_map_result.json[.l]`, `t12_command.json`, refined PDB/MTZ/map assets,
and the two bounded raw logs.

T12.5 is a checkpoint, not another scientific computation. The fixed
`t12-review-collect` operation remains the checksum-gated route for a retained
scheduled T12 run. The normal workflow instead invokes
`review build-live-sequence-checkpoint` after every candidate process has
finished; it validates the live stage, exact candidate identities, typed JSON
and JSONL pairs, fixed logs/commands, and every asset checksum without
fabricating a Slurm job result. Both routes publish:

- a primary top-10 and extended top-25 view for every retained finalist;
- the full set of scored catalogue groups, including raw scores and missing
  coverage/segment fields without imputation;
- refined PDB/MTZ, `2mFo-DFc` and `mFo-DFc` CCP4 maps, and the
  sequence-assignment hypothesis PDB for every finalist;
- a genome-annotation crosswalk that preserves every compatible protein ID,
  locus tag, gene name, product, genomic coordinate, and annotation provider;
- per-sequence Matthews copy-number context for copy counts 1--16, including
  the coefficient, solvent fraction, physical status, and transparent prior;
- an HTML review view and unique top-10 sequence-group candidate table; and
- a header-only second approval template requiring an explicit human decision.

No numeric score or refinement statistic removes a finalist or creates an
approval. In the normal path, a typed failed/no-hit finalist remains in the
manifest with its stage parent, Phaser MTZ, diffraction MTZ, result records,
command, and bounded logs even when no scored sequence row exists. The manifest
records unscored catalogue groups separately through the complete and scored
counts in the underlying typed results.

`sequence_from_map.pdb` is not a separately refined model or a final identity
call. Phenix derives it from the refined model, the `2mFo-DFc` map, and the
complete catalogue; the report therefore labels it as a map-derived
sequence-assignment hypothesis. The `mFo-DFc` map is provided separately for
positive and negative residual-density inspection in Coot.

The checkpoint recomputes Matthews context from the checksum-bound MTZ
preflight geometry and each exact candidate sequence mass. This is a physical
copy-number prior only. It cannot prove molecular identity, homomeric content,
or the prototype assumption `ASU = nA`.

## Normal T12.5 process contract

`BUILD_LIVE_SEQUENCE_CHECKPOINT` consumes one `live_t12_stage` directory and
the complete collected list of `t12_<solution-id>` result directories. It emits
one `t12_sequence_checkpoint` directory. It runs only the locked project CLI;
Phenix is not invoked again. Missing/duplicated candidates, changed stage or
asset checksums, unsafe paths, inconsistent JSON/JSONL records, or broken
refinement/sequence identity fail the checkpoint. Typed tool/parse/no-hit
outcomes remain normal retained evidence and produce no fabricated score row.

The process cache key is Nextflow's content identity over the complete stage
directory, ordered candidate-result directories, locked command, process
definition, and project revision. The package identity independently binds the
stage manifest, every typed result/log/command checksum, and all copied assets.
The manifest reports every finalist's refinement and sequence status; the only
decision file produced by the process is header-only. Unit tests cover
successful packaging, typed-failure retention, and changed-parent rejection;
the integrated stub test covers publication and fully cached resume.

## Fixed scientific protocol

The comparison uses one macrocycle of individual coordinate and isotropic ADP
refinement, Phenix random seed `2679941`, no simulated annealing, and no ordered
solvent addition. It preserves the input free-reflection set; missing free flags
or other invalid reflection contracts fail loudly instead of generating a new
comparison set. Map generation uses both `2mFo-DFc` and `mFo-DFc`, CCP4, sigma
scaling, the full cell, and no filled missing observations. The refined MTZ
must contain the standard Coot-compatible `2FOFCWT`/`PH2FOFCWT` and
`FOFCWT`/`PHFOFCWT` pairs; missing pairs
turn the candidate into a typed parse failure.

The output serial is fixed to zero because Phenix increments that value when
constructing its first numbered PDB/MTZ names. The CCP4 map uses its explicit
unnumbered filename. These names are part of the protocol cache identity and
are checked before sequence analysis begins.

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

Before candidate fan-out, the live stage distinguishes scientific and
infrastructure endings. A typed no-addition, unpacked solution, tool failure, or
parse failure retains the last supported parent and remains auditable. An
absent copy-series bundle, broken lineage, unsafe path, changed asset, or stale
review/hypothesis/preflight checksum fails the stage loudly. The live stage
identity binds every checkpoint and input checksum plus the retained PDB and
Phaser-MTZ checksums; `finalists.tsv` points to the original diffraction MTZ,
not the Phaser output MTZ.

## Resources and tests

Viper uses four CPUs and 16 GB per finalist with at most four simultaneous T12
tasks (16 CPUs total) and the site-wide 24-hour scheduler ceiling. The adapter
itself imposes no runtime timeout.

Unit tests cover the fixed command policy, R-value parser, complete-catalogue
ranking/crosswalk, checksum rejection, and all live copy-state endings.
`nextflow-check` parses the typed module/workflow, while `nextflow-stub` verifies
normal-workflow T12 and T12.5 publication plus cached resume without fabricating
scientific success. All 11 retained CD6 finalists have already completed the
preceding single-map Viper Phenix T12 protocol as retained historical evidence;
a fresh dual-map replay is required for the corrected checkpoint. CD6 is an
unknown crystal/diffraction dataset, not a truth-labelled protein control. It
may be heteromeric or otherwise violate `ASU = nA`, so it is useful as a
realistic challenge case but is not sufficient by itself to validate the
single-component prototype. T12.5
additionally tests checksum-gated remote collection, normal live-result
validation, typed-failure retention, path containment, top-10/top-25/full
cardinality, empty approval semantics, and package identity.
