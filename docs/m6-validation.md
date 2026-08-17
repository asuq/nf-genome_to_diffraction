# M6 independent validation protocol

Status: **protocol approved; scientific execution held for corrected evidence
contracts and multi-item validation**.

The truth-facing source of record is
[`benchmarks/m6/protocol.yaml`](../benchmarks/m6/protocol.yaml). This document
explains the execution boundary; it does not duplicate or override the frozen
values in that contract.

## Scientific purpose and limits

M6 tests whether the accepted single-component prokaryotic prototype retains
and advances the correct catalogue family under operational and
leakage-controlled conditions while failing closed on open-set, ambiguous, and
assumption-violating inputs. It is an internal engineering benchmark. It does
not estimate population sensitivity or specificity and does not establish
generalisation.

The three unknown operator crystals `AD4QS1P4G2_18`, `CD4QS2P2G1_15`, and
`CD6QS2P2G1_5` are absent from M6 and remain post-M6 exploratory inputs.
Heteromer controls test abstention only; this milestone does not reconstruct
heteromers.

## Frozen inventory

The protocol contains exactly 63 typed cases:

- 12 operational positives from distinct RCSB 30% sequence clusters with no
  overlap to the 11 M5 positive clusters;
- the same 12 positives with leakage-controlled model availability;
- 12 target-absent correct-catalogue controls;
- eight wrong-related-proteome controls whose exact target sequences are
  absent;
- four known heteromeric `ASU = nA` assumption violations; and
- 15 edge/hardening controls covering duplicate loci, missing PDB models,
  wrong SDS mass, non-top Matthews hypotheses, map-only MTZs, equivalent and
  conflicting observation columns, disabled/rate-limited remote providers, and
  missing Phenix.

Public coordinates and structure factors come from the
[RCSB file-download service](https://www.rcsb.org/docs/programmatic-access/file-download-services).
RefSeq protein catalogues are frozen from
[NCBI Datasets genome packages](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/reference-docs/data-packages/genome/).
The protocol records every URL, size, and SHA-256. RCSB 30% and 70% sequence
cluster snapshots are independent partitions and are not assumed to be nested.
Their exact target lines and frozen set differences are private truth-side
cross-checks, not substitutes for the all-route identity calculation.

## Leakage and truth isolation

The leakage-controlled track excludes any model chain with at least 70% target
sequence identity and at least 80% coverage. The exclusion applies to PDB,
AFDB, and every other enabled model route. Exact deposited target coordinates
are excluded from both positive tracks. MMseqs2 18.8cc5c performs the pinned
identity/coverage calculation. The 8AI1 case is predeclared leakage-model-
scarce, giving an 11-case leakage correct-family denominator. Operational
family evidence retains the full 12-case denominator.

The opaque runner archive never contains the tracked protocol or private truth
map. A trusted preparer emits anonymised catalogue IDs, sanitised MTZ metadata,
per-case configuration, and model-policy objects. `benchmark build-m6-runner`
verifies every object, renames it by SHA-256, emits only opaque `M6Cnnn` case
IDs, scans every byte for PDB/accession/sequence/cluster truth tokens, and
writes a deterministic tar archive. During execution, catalogue import,
preflight, discovery, MR, copy search, refinement, and sequence assessment read
only opaque inputs. A narrow trusted transition reads the tracked protocol only
to remove the exact deposition and enforce the approved all-route leakage
threshold. Truth-side case assessment occurs only after both collected result
checksums are fixed.

Each fresh runner case emits a checksum-bound identity decision:
`reported`, `ambiguous`, or `abstained`. It also emits typed edge observations
whose success is derived from actual Matthews, MTZ, provider-authorisation,
HTTP-response, model-route, or Phenix-validation records. The trusted collector
carries identity decisions unchanged, joins PDB/entity attempts against the
private verified family sets, and makes a reported wrong open-set identity or
contradicted edge observation produce `HOLD`. Historical v1 evidence remains
readable but cannot enter corrected M6 acceptance.

## Commands and artefacts

Protocol validation:

```bash
pixi run --locked genome-to-diffraction benchmark check-m6-protocol \
  --protocol benchmarks/m6/protocol.yaml
```

Trusted source preparation verifies the frozen RCSB coordinate, reflection,
30%/70% cluster-snapshot, and RefSeq files. It verifies target cluster-line
checksums and frozen 30%-minus-70% family counts, strips coordinate and
catalogue identifiers from runner-visible inputs, and keeps the schema-1.1
private case/family truth map outside the runner bundle:

```bash
pixi run --locked genome-to-diffraction benchmark prepare-m6-inputs \
  --protocol benchmarks/m6/protocol.yaml \
  --rcsb-root .untracked/m6/public-rcsb \
  --catalogue-root .untracked/m6/refseq-core \
  --catalogue-root .untracked/m6/refseq-assumptions \
  --outdir .untracked/m6/prepared
```

Runner construction requires a local preparation manifest whose 63 cases each
provide a checksum-fixed catalogue, MTZ, and analysis configuration. Optional
model-policy or fault-control objects carry only runner-visible behaviour:

```bash
pixi run --locked genome-to-diffraction benchmark build-m6-runner \
  --protocol benchmarks/m6/protocol.yaml \
  --preparation-manifest .untracked/m6/preparation.json \
  --outdir .untracked/m6/runner \
  --archive .untracked/m6/runner.tar
```

The output is `runner_manifest.json`, a content-addressed `objects/` directory,
and a deterministic archive. The runner-archive SHA-256 is its cache key.
Changed protocol bytes, input bytes, model policy, Phenix manifest, database
manifest, or parameters must invalidate the applicable cache identity.

Runner-side qualification has no truth input. It validates all 63 opaque
cases, every content-addressed object, FASTA/MTZ/JSON media contract,
observation-column states, and the retain-all/annotation-only policy:

```bash
pixi run --locked genome-to-diffraction benchmark verify-m6-runner \
  --runner-root .untracked/m6/runner \
  --report .untracked/m6/input-qualification.json
```

The reviewed Viper qualification profile streams only an explicitly confirmed
archive below `.untracked/`, revalidates it on both sides of the transfer, and
requests one CPU and 4 GB because it performs no search or Phenix work:

```bash
nf-gtd-hpc-test --no-progress m6-inputs-stage \
  --revision HEAD \
  --archive .untracked/m6/runner.tar \
  --confirm-archive-sha256 ARCHIVE_SHA256
nf-gtd-hpc-test --no-progress submit m6-inputs --run-id RUN_ID
```

This qualification run is pre-execution evidence and is not one of the two
scientific run IDs in the final M6 evidence contract. The opaque catalogues do
not expose RefSeq accessions, so AFDB accession lookup is disabled in this
benchmark bundle; PDB-sequence and local ProstT5/Foldseek discovery remain the
enabled model routes, and the leakage transition applies to every enabled
route.

The two scientific run IDs are staged and submitted separately from the same
confirmed runner archive:

```bash
nf-gtd-hpc-test --no-progress m6-scientific-stage \
  --revision HEAD \
  --archive .untracked/m6/runner.tar \
  --confirm-archive-sha256 ARCHIVE_SHA256 \
  --track operational
nf-gtd-hpc-test --no-progress submit m6-operational --run-id RUN_ID

nf-gtd-hpc-test --no-progress m6-scientific-stage \
  --revision HEAD \
  --archive .untracked/m6/runner.tar \
  --confirm-archive-sha256 ARCHIVE_SHA256 \
  --track leakage
nf-gtd-hpc-test --no-progress submit m6-leakage --run-id RUN_ID
```

Scientific staging binds the checksum-validated Viper runtime database
configuration and the fixed Viper Phenix manifest. It does not reuse the
legacy P0 single-root path file, which cannot represent Viper's separate
database and licensed-software mounts.

Each track retains its full raw output remotely, emits compact case evidence
and a deterministic gzip of every candidate rank, verifies all output
checksums, and performs a fully cached Nextflow `-resume` pass. No search or
Phenix task is silently repeated during that resume check. The execution model
is detailed in [the Nextflow/Slurm architecture](execution-architecture.md).

Truth-side evaluation:

```bash
pixi run --locked genome-to-diffraction benchmark collect-m6-evidence \
  --protocol benchmarks/m6/protocol.yaml \
  --private-truth-map .untracked/m6/prepared/private_truth_map.json \
  --operational-collection .untracked/hpc-test/OPERATIONAL_RUN/collected \
  --leakage-collection .untracked/hpc-test/LEAKAGE_RUN/collected \
  --output .untracked/m6/collected-evidence.json
pixi run --locked genome-to-diffraction benchmark evaluate-m6 \
  --protocol benchmarks/m6/protocol.yaml \
  --evidence .untracked/m6/collected-evidence.json \
  --report .untracked/m6/evaluation.json
```

The evidence contract carries both Viper run IDs; source, nf-helper, Pixi-lock,
Phenix, database, runner-manifest, and runner-archive identifiers; bounded
resource maxima; replay/resume/cache/partial-output/interface outcomes; and one
assessment for every opaque case.

## Gates

All candidates and parent/child attempts must be retained. LLG and TFZ remain
ranking annotations and never delete candidates. Correctness requires zero
exact false assignments across the 20 open-set negatives, 4/4 heteromer
abstentions, 2/2 duplicate-locus ambiguities, every edge outcome typed,
complete provenance, deterministic and `-resume` equivalence, correct cache
invalidation, no silent partial output, and a bounded interface.

Operational minimums are top-25 10/12, top-10 8/12, top-5 6/12,
correct-family 10/12, credible seed 9/12, and true copy 8/12. Leakage-controlled
minimums are respectively 8/12, 6/12, 4/12, 7/11 eligible, 6/12, and 5/12.
Any missed correctness or performance gate produces `hold`; the evaluator does
not drop, round, or relabel cases.

## Execution and failure semantics

M6 uses separate operational/open-set and leakage/hardening Viper stages. Each
starts with a 2-CPU/8-GB Nextflow driver. Independent child tasks are submitted
to Slurm; batched MMseqs2 and Foldseek jobs may request 32 CPUs/16 GB, while all
other child jobs retain smaller allocations. The ceiling is 24 hours per Slurm
job, not a tool timeout. Slurm controls aggregate and Phenix concurrency, which
are measured rather than capped.

The 29 frozen catalogues are imported independently and deduplicated to 70,864
unique sequences. MMseqs2 searches one batch capped at 100,000 sequences/30
million residues. Foldseek searches deterministic batches capped at 10,000
sequences/3 million residues. This avoids reloading the target database and
ProstT5 model once per sample while retaining every catalogue candidate.

Candidate-specific no-hit, no-model, ambiguity, assumption violation, remote
disabled/rate-limited, and conflicting-column outcomes are completed scientific
states. Missing or changed inputs, truth leakage, checksum mismatch, malformed
contracts, stale cache reuse, missing Phenix, partial output, or an unbounded
remote operation fail loudly with a typed failure class. Code changes follow
only after collected terminal evidence demonstrates a software defect.

## Test coverage

Focused unit tests validate the exact 63-case balance, positive copy-count
coverage, M5/M6 cluster separation, the 11-case leakage denominator, failure on
case relabelling, accept and hold evaluator paths, 100% retention and zero-false
assignment gates, unexpected execution-failure holds, deterministic runner
archives, byte-level rejection of a truth-bearing runner object, all-route
model exclusion, compact truth joins, output-checksum replay, cache
invalidation, deterministic query batching, Nextflow fan-out, child-job
resource evidence, cross-track truthless-store isolation, and the fixed Viper
resource profiles. A two-case Viper `-stub-run` must then prove real child Slurm
submission without generating acceptance evidence. The complete locked
repository gate remains required before an immutable Viper candidate is staged.
