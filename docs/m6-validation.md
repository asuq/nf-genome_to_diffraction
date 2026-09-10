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

Coordinate URLs remain trusted preparation metadata only. After model policy,
one bounded login/controller-labelled stage resolves selected PDB entries
through the qualified cache and materialises checksum-addressed local objects.
Case workers receive only that local registration bundle; they receive neither
the database manifest nor URL or credential authority and never perform HTTPS.
Scientific no-hit and the deliberate missing-model control produce typed empty
stage bundles instead of falling back to worker-side acquisition.

## Leakage and truth isolation

The leakage-controlled track excludes any model chain with at least 70% target
sequence identity and at least 80% coverage. The exclusion applies to PDB,
AFDB, and every other enabled model route. Exact deposited target coordinates
are excluded from both positive tracks. MMseqs2 18.8cc5c performs the pinned
identity/coverage calculation. The 8AI1 case is predeclared leakage-model-
scarce, giving an 11-case leakage correct-family denominator. Operational
family evidence retains the full 12-case denominator.

Truthless shared discovery retains a fixed envelope of at most 25 ranked hits
per query and model route. This is an execution bound, not a scientific
threshold and does not alter the frozen protocol. Operational cases restore
the historical first three hits per route before policy evaluation. Leakage
cases instead apply the runner-visible 70% identity/80% coverage evidence to
the complete discovery envelope and only then retain the first three safe hits
per route. Thus an excluded leading trio cannot hide a safe fourth hit. Every
policy exclusion and post-policy cap deferral remains a deterministic retained
annotation; an all-excluded candidate produces a typed
`completed_no_model` policy result.

After that unchanged policy, M6 retains every accepted model-bearing sequence
group in `eligible-candidates/`, with all catalogue groups and source records
preserved separately in the case bundle. Provider rank is diagnostic: there is
no preliminary top-25 protein or coordinate-mapping cut. Offline registration
uses the observed finite mapping count, with the existing maximum of three
coordinate hits per group. The production first-copy funnel then applies the
unchanged 25-hypothesis execution budget; one hypothesis is one initial-copy
task, not necessarily a unique protein or coordinate file.

The coordinate stage binds the accepted-hit checksum to the trusted model-policy
bundle and fails on changed joins or unavailable qualified cache objects. The
case task verifies the same policy, eligible-input and registration checksums
before model preparation. Cache contracts are
`m6-coordinate-stage-v2-eligible-inventory` and
`m6-nextflow-case-v3-eligible-inventory`. Shared PDB registration now accepts a
positive explicit finite mapping bound, including inventories above 1,000;
its ordinary default of 25 is unchanged. Storage limits and offline failure
semantics still apply.

Local RF-G4 admission regression uses synthetic coordinates and the real
registration, model preparation, Matthews enumerator and production funnel.
It retains 31 eligible proteins/93 model records and admits a provider-rank-31
candidate while scheduling exactly 25 one-copy tasks, with the same hypothesis
IDs as direct production admission. This is local code-path qualification, not
native MR evidence or completion of RF-G4.

M6 now builds the actual production MR-seed review package for every scheduled
hypothesis. `seed_advancement.jsonl` retains all scheduled results in shared
review-priority order, including ineligible and cap-deferred states. Provider
rank does not order continuation. The fixed truth-blind policy recommends at
most five inspectable `completed_hit` states with selected zero-clash packing
and either literal one-copy or explicitly evidenced coupled-tNCS placement,
never more placed copies than the retained expectation. No new numerical score
threshold is introduced; the completed-hit classification remains the existing
adapter's output.

`benchmark_advancement.json` is explicit benchmark-only execution authority,
not human approval. It binds the production review, exact hypotheses, Matthews
evidence, complete recommendations, 25-hypothesis/five-seed caps and policy
identity. Copy children revalidate assets, joins, the shared ordering and the
selected inventory. The production approval template stays empty. Ordinary
additional-copy and Phase III workflows still require their own human gates;
there is no general CLI bypass. M6's search copy uses the original prepared
model, not a possibly two-copy placed parent. The fixed parent remains separate.

Cache identities are `m6-nextflow-seeds-v3-production-review` and
`phenix-add-copy-mr-v9-m6-truth-blind`. Commands and series/parent receipts record
`execution_authority_kind=truth_blind_m6_benchmark`, the advancement ID/checksum
and `human_approval_granted=false`. In the existing additional-copy result
contract, `review_id` carries this `m6advance_...` audit ID for benchmark runs;
it must not be reported as a human decision. Already-at-expectation states emit
a zero-attempt child receipt only after the same authority/model checks.

Synthetic tests exercise production-order parity and permutation stability,
packing/copy-state exclusions, exact result partitioning, unchanged human gates,
authority tampering and an additional-copy adapter call with only the external
Phenix invocation simulated. The refreshed input integration milestone passes
the complete locked gate, including 1,871 Python tests and all workflow/cache
and packaging checks. Exact-source CI, reviewed-site input qualification and
native known-control/four-arm qualification remain outstanding.

`stage_inventory.json` now records the production-ordered scheduled hypotheses,
their catalogue digests, review/recommendation ranks and authenticated executed
continuations. Each stage reports unique proteins, unique model IDs,
sequence/expected-copy states and hypothesis tasks separately. A seed at its
expected count has an explicit executed continuation receipt with zero native
additional-copy attempts. Missing, duplicate, foreign or changed receipts fail;
they cannot silently become advanced seeds. Native command, parameter, log,
result and supported-child assets are checksum-bound, including the original
model, parent chain and diffraction input. Refinement children must match their
retained finalist tasks. Case aggregation rederives stages from retained raw
evidence before export.

The frozen numerical thresholds and 25-task/five-seed scope are unchanged.
Their corrected stage bindings are:

| Metric | Evidence counted |
| --- | --- |
| `top_25`, `top_10` | Earliest target hypothesis in production scheduling order, within 25 or 10 tasks |
| `recommended_top_5` | Target membership in the bounded production recommendation; separately reported |
| `top_5` | Target with an authenticated executed continuation among the five recommendations |
| `target_provider_rank` | Earlier provider diagnostic only; never a top-k gate |

The truth-side target join uses catalogue sequence digests even when no provider
ranking row exists. The non-top-Matthews edge requires the corresponding
sequence/expected-copy state in scheduled, completed first-copy evidence;
retention alone or an execution failure does not pass it. A completed scientific
no-hit demonstrates execution reachability, not identity or correct copy count.

Current cases/tracks use schema 3.0 and
`m6-nextflow-case-evidence-v3-stages`/`m6-nextflow-run-v3-stages`; finalist receipt
validation is `m6-nextflow-finalists-v2-receipts`. Collected evidence and evaluator
reports use schema 1.2. Older tracks remain archival-verifiable but cannot enter
corrected acceptance. Rendered task identities, local stubs and the maintained
HPC smoke/parent contracts advance together. Synthetic regressions cover stage
separation, count conservation, receipt tampering, zero-attempt continuation,
non-top-copy execution and byte-identical assembly under completion reordering;
these are not native scientific qualification.

The blind search tasks do not receive target truth or the protocol. The
query-relative filter consumes only normalised amino-acid metrics plus the
existing checksum-bound runner model-policy object. The separately existing
trusted exact-deposition removal still uses the narrow protocol transition; no
new private target or family field enters runner input or search cache identity.

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

For ordinary cases, the trusted preparer applies a strict Gemmi whitelist
before the reflection object reaches the runner. It reuses the deterministic
preflight observation selection, retains only `H,K,L`, that selected
value/sigma pair (or anomalous quartet), and exactly one recognised Free-R
array from that observation dataset or the shared base dataset 0. Assigned
flags must be integral and non-constant. Unassigned flags are preserved only
where every selected observation value/sigma is also absent. Missing or
conflicting observation selections, missing or ambiguous Free-R columns,
infinite/non-integral or constant assigned flags, missing flags on measured
rows, duplicate HKLs, and changed HKL-to-flag membership abort
preparation. FWT/PHWT, FC/PHIC, other map/phase columns, and all other source
columns are therefore absent from ordinary runner objects and cannot affect the
runner archive/cache identity. The two frozen `map_only_mtz` edge cases remain
deliberate exceptions because their purpose is to exercise typed no-observation
handling; they are not ordinary scientific inputs.

Each ordinary local preparation case must carry a content-addressed, path-free
sanitisation record binding the output MTZ checksum, exact retained labels,
reflection count, assigned/unassigned flag counts, selected observation
identity, and sorted HKL and HKL-to-Free-R digests. Schema 1.1 and contract v2
encode flag presence explicitly in the membership digest, keeping absent
distinct from numeric zero without changing the MTZ values. For example,
5E0K includes 2,122 rows with no measured observations and source status `x`
([unreliable, unused measurements](https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/Items/_refln.status.html));
their unassigned flags remain unassigned. The runner builder requires and
independently validates
that record against the prepared reflection object but deliberately does not
serialise it into the blind runner manifest. Original coordinate and
structure-factor resource checksums,
sizes, PDB-source provenance, and the unchanged frozen protocol remain in the
trusted `source_inventory.json`/private boundary outside the runner.

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
private case/family truth map outside the runner bundle.

The operator approved an in-place reference refresh on 2026-09-10. Current
snapshot/family bindings and RefSeq bundle checksums supersede the original
August source requirements; case identities, thresholds and leakage rules are
unchanged. Retain downloads, preparation outputs, private truth, runner archives
and verification records under repository `.untracked/`, not `/tmp`.

Trusted MTZ sanitisation accepts one Free-R array either in the selected
observation dataset or the shared base dataset 0, as produced by
[Gemmi's CIF-to-MTZ conversion specification](https://gemmi.readthedocs.io/en/stable/program.html#cif2mtz).
Flags scoped to another observation dataset remain an error. The canonical
runner MTZ places observations and flags together while proving unchanged HKL,
observation values and exact HKL-to-Free-R membership; no flags are regenerated.

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
  --preparation-manifest .untracked/m6/prepared/preparation.json \
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

The reviewed input-qualification profile streams only an explicitly confirmed
archive below `.untracked/`, revalidates it on both sides of the transfer, and
requests one CPU and 4 GB because it performs no search or Phenix work.

Marmic first requires its explicit owned site identity. After deploying the
same checked commit, initialise only that fixed missing record through the
reviewed create-only operation:

```bash
pixi run --locked nf-gtd-hpc-test --config .untracked/config.marmic.json \
  --no-progress marmic-site-configure --revision FULL_COMMIT
```

The operation verifies the installed dispatcher checksum and refuses an
unexpected existing record. P0 readiness alone does not establish this M6
prerequisite. Keep using the explicit site configuration for staging and all
owned-run operations.

Stage and submit the confirmed archive:

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
confirmed runner archive. Both reviewed sites require an immutable commit on
`main`:

```bash
nf-gtd-hpc-test --no-progress m6-scientific-stage \
  --revision HEAD \
  --archive .untracked/m6/runner.tar \
  --confirm-archive-sha256 ARCHIVE_SHA256 \
  --source-branch main \
  --track operational
nf-gtd-hpc-test --no-progress submit m6-operational --run-id RUN_ID

nf-gtd-hpc-test --no-progress m6-scientific-stage \
  --revision HEAD \
  --archive .untracked/m6/runner.tar \
  --confirm-archive-sha256 ARCHIVE_SHA256 \
  --source-branch main \
  --track leakage \
  --operational-parent-run-id OPERATIONAL_RUN_ID
nf-gtd-hpc-test --no-progress submit m6-leakage --run-id RUN_ID
```

Scientific staging binds the checksum-validated selected-site runtime database
configuration, its exact reviewed Nextflow profile and execution policy, and a
run-owned Apptainer cache. Viper retains its fixed site-manifest Phenix
binding. Marmic reuses the independently frozen Phenix manifest and checksum
already qualified by the Phase III control profile; it does not infer that
path from Viper's incompatible site configuration. Both final tracks must use
the same reviewed site and its exact frozen policy checksum. The controller
accepts only `main`; the retired development branch fails before archive
inspection or transfer.

Leakage staging and final truth-side collection both authenticate the exact
successful operational parent. The leakage first-pass child inventory permits
`CACHED` only for catalogue import, PDB search, and ProstT5/Foldseek search;
every track-specific task must be newly `COMPLETED`, and the resume inventory
must be entirely `CACHED`. Final collection rehashes the operational precheck
and requires every reused truthless task hash and complete child-file inventory
to equal its operational parent.

For both input-only qualification and scientific staging, if the reviewed site
has no usable bare Git mirror, the controller retries only that exact classified
staging failure. Both use the same existing checksum-bound,
size-limited immutable source checkout first, followed by the independently
confirmed M6 runner archive. The dispatcher verifies the exact commit, locked
environment, pinned helper, source checksum, and runner inventory before the
run becomes stageable; arbitrary uploads and broader transport retries are not
enabled. Temporary transport files stay in the owned local run directory under
repository `.untracked/`; the confirmed runner archive is unchanged. Input-only
staging still requires no database or Phenix configuration and submits no job
until the separate fixed-profile submit operation.

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

The evidence contract carries both owned selected-site run IDs; source,
nf-helper, Pixi-lock, Phenix, database, runner-manifest, and runner-archive
identifiers; bounded
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

M6 uses separate operational/open-set and leakage/hardening reviewed-site stages. Each
starts with a 2-CPU/8-GB Nextflow driver. Independent child tasks are submitted
to Slurm. MMseqs2 retains 32 CPUs/16 GB at both sites. Marmic Foldseek uses
32 CPUs/192 GB under `m6_nextflow_slurm_marmic_v2`; Viper's unchanged v1 policy
retains 32 CPUs/16 GB. All other child jobs retain their existing smaller
allocations. The ceiling is 24 hours per Slurm
job, not a tool timeout. Slurm controls aggregate and Phenix concurrency, which
are measured rather than capped.

The operator approved the Marmic correction after a qualified production batch
used 64.6 GiB peak RSS, exceeding the old 16-GB cap. The current
[Marmic v2 policy](../benchmarks/m6/execution-nextflow-marmic-v2.yaml) is bound
through staging, execution, collection and evaluation; the former Marmic v1
identity cannot enter current acceptance. Resource limits are read from that
verified policy rather than a shared hard-coded memory value. The policy
checksum already participates in search cache keys, so changing resources
invalidates cached search evidence even for identical query groups. A small
native known-control qualification is required before the full benchmark;
local tests and the existing stub smoke do not satisfy that requirement.

The refreshed 29 catalogue objects are imported independently and contain
70,870 distinct raw sequences before import filtering (the historical source
contained 70,864). Qualification records bind the actual imported/searchable
inventory rather than assuming a historical count. MMseqs2 searches one batch capped at 100,000 sequences/30
million residues. Marmic Foldseek searches deterministic batches capped at
128 sequences; Viper retains its 10,000-sequence cap. Both retain the existing
3-million-residue bound. This avoids reloading the target database and
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
resource evidence, cross-track truthless Nextflow-cache isolation, and the fixed Viper
resource profiles. The MTZ regression additionally proves FWT/PHWT/FC/PHIC are
omitted, HKL/observations/Free-R are exact, target-derived coefficient mutations
do not change sanitised bytes or identity, invalid arrays fail closed, and the
runner-visible MTZ cannot recover the omitted columns. A two-case Viper
`-stub-run` must then prove real child Slurm
submission without generating acceptance evidence. The complete locked
repository gate remains required before an immutable Viper candidate is staged.

The local full-graph cache probe separately changes one checksum-bearing
protocol input and requires the exact ten-task downstream closure while all 16
unaffected tasks and child outputs remain byte-identical. It also deletes one
required child from a cached catalogue bundle and requires an explicit
`hold_missing_required_child` verifier outcome; an unchanged published aggregate
does not establish child completeness. This focused probe is not remote M6
acceptance evidence. The current per-track `cache_invalidation_verified` field
checks content-key sensitivity only; it cannot close the real mutation gate.
M6 acceptance still requires a separately checksum-bound observed mutation
record from the fixed execution authority.
