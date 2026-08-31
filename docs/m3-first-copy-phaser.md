# M3 first-copy Phaser boundary

## Scope and current qualification

The active M3 vertical slice joins the integrity-checked exact-predicted model
from M2 to physically possible Matthews copy hypotheses, then runs one
independent Phaser search per immutable hypothesis. The Python adapter, parser,
provisional score screen, and typed Nextflow stub route passed local
acceptance on 11 August 2026. The first immutable CD6 route reached Phaser after
replaying the real P0 and P1 evidence, but Phaser rejected the processed mmCIF
before search because it found no scatterers. This is a tool-execution failure,
not a CD6 no-hit. The corrected PDB model boundary passed a local real 8OOX
positive control. Its first immutable CD6 retry completed the full search and
packing calculation with no accepted solution, but exposed a narrow parser gap
for Phaser's terminal `Sorry - No solution` wording. Immutable commit
`4e64ce5bc10c518276a86f2c0870e4c18899f86d` corrected that boundary and
passed the fixed Marmic route: `completed_no_hit`, zero accepted/packed
solutions, no solution files, and a fully cached two-process resume. This
qualifies the bounded route, not a scientific identification or the full P2
gate.

The registered direct-PDB slice subsequently completed 25 independent Marmic
searches and produced 11 parsed PDB/MTZ solutions; six enter the higher-priority
TFZ-only tier. The old version-2 transfer collected those six, while version 3
will make all 11 available through the checksum-gated review operation. The
active slice still excludes
same-component additional copies, refinement, sequence-from-map analysis, and
automatic reviewer approval. Those remain separate gates.

## Exact-model funnel

The `ranking exact-predicted-funnel` command accepts:

- exact predicted `CoordinateSourceRecord` rows;
- confidence-processed `ProcessedModelRecord` rows and their relocatable
  preparation manifest;
- exact catalogue `SequenceGroupRecord` rows;
- candidate-specific Matthews hypotheses;
- MTZ preflight records; and
- the versioned pipeline configuration.

It verifies the processed model checksum and safe relative path, requires exact
coordinate-to-catalogue sequence mapping, rejects physically impossible copy
counts even if they were otherwise retained, excludes failed preflights, and
sorts deterministically. Every ranking feature is retained separately; the
adapter does not create an unexplained scalar score. Profile and configuration
caps are applied before the immutable `MrHypothesis` records are written.

The output contains aggregate JSONL and TSV, a checksum-bearing funnel manifest,
and one single-record `hypotheses/<mrhyp-id>.jsonl` file per selected job. The
single-record files let Nextflow stage and cache each candidate independently
without reparsing or rewriting scientific records in Groovy.

## First-copy command

```bash
pixi run --locked genome-to-diffraction \
  --log-format json \
  --no-progress \
  mr first-copy \
  --hypotheses /absolute/funnel/hypotheses/mrhyp_FULL_SHA256.jsonl \
  --hypothesis-id mrhyp_FULL_SHA256 \
  --sequence-groups /absolute/catalogue/sequence_groups.jsonl \
  --processed-models /absolute/models/processed_models.jsonl \
  --model-preparation-manifest /absolute/models/model_preparation_manifest.json \
  --preflight /absolute/preflight/mtz_preflight.jsonl \
  --mtz /absolute/diffraction/integrated.mtz \
  --phenix-manifest /absolute/software/manifests/phenix.json \
  --threads 1 \
  --outdir /absolute/results/first-copy/mrhyp_FULL_SHA256
```

No Phaser timeout is imposed by default. An operator can provide
`--timeout-seconds`, but unpredictable shared-filesystem startup is not treated
as a reason to impose a short scientific deadline.

The opt-in Phase III multi-crystal application first runs the same
manifest-owned dispatch with `--phase3-diffraction`. Besides the unchanged v1
dispatch files, it publishes `phase3_diffraction_selection.json` and
`phase3_free_r_identity.json` for that crystal. The first record content-binds
the exact MTZ, selected dataset/observation labels, selected space group,
resolution limits, and manifest overrides; the second binds the complete
same-dataset HKL-to-Free-R mapping and leaves an unknown test-value convention
explicitly unresolved. Missing, ambiguous, constant, or cross-dataset Free-R
flags fail before the dispatch directory is created.

Each independent Phase III first-copy task then passes
`--diffraction-selection` and `--derive-phase3-hypothesis-id`. The existing
Phaser adapter derives the schema-v2 identity directly from that exact
hypothesis and diffraction record, retains it in the command evidence, and
passes explicitly qualified space-group and resolution parameters. An
independently supplied bound identity remains supported, but supplying both or
neither identity policy is refused. Historical single-crystal commands and
dispatch evidence are unchanged.

The adapter verifies that the hypothesis is queued, independent, first-copy,
and exact-mapped. It revalidates the model path and checksum, observation
labels, space group, preflight status, MTZ checksum, sequence group, and Phenix
manifest before execution. It then calls `phenix.phaser` through the isolated
Phenix subprocess wrapper in a hypothesis-owned directory with:

- `MR_AUTO` mode;
- sequence-based total composition and the hypothesis's expected copy count;
- exactly one searched copy;
- explicit 100% sequence identity for an exact predicted catalogue/model
  mapping, or the registered candidate-to-source identity for a cleaned PDB
  homologue;
- model uncertainty retained through the B values produced by
  `phenix.process_predicted_model` for predicted models, while cleaned PDB
  homologues retain native coordinate B values;
- the preflight-selected observation labels;
- the preflight space group with alternative-space-group search disabled; and
- `task.cpus` passed to Phaser's job control.

The full argument array, model/MTZ/sequence/manifest checksums, adapter version,
threads, and timeout policy are written to `phaser_command.json`. Native and
capture logs are retained. `logging` reports the hypothesis, composition,
resources, status, scores, and rejection reason; `tqdm` reports the bounded
single-job progress interactively and is disabled by `--no-progress` in
scheduled execution.

## Parser and scientific status

The parser uses final packing evidence, not an early advisory. This matters
because the qualified positive log first reported that the top FTF solution did
not pack, then later accepted and packed the refined solutions. That advisory
is retained as a warning without overriding the final table.

Phaser 2.8.4 can express a successful no-solution result either with an explicit
zero-solution count or with a final packing table followed by `Sorry - No
solution`. The latter is terminal zero-solution evidence when it follows any
earlier intermediate count. A successful exit marker alone remains
insufficient and is classified as a parse failure. Exact terminal matching
deliberately excludes `No solution with all components`, which Phaser can use
when partial solutions exist.

The normalised result preserves LLG, LLGI, TFZ, accepted/packed counts, placed
copy count, output coordinate and MTZ checksums, warnings, raw-log pointer, and
the preliminary review class. A solution enters the user-defined higher-priority
screening tier when either strict inequality passes:

```text
top LLG > 50 or top TFZ > 5
```

Equality does not pass either comparison. The numeric screen ranks and annotates
results; it never discards a parsed solution, labels one accepted, or grants
approval. Packing and placed-copy agreement remain separate evidence. The
sensitive disjunction is a prototype triage boundary, not a universal
Phaser-success criterion and not a substitute for Coot inspection, refinement,
or expert review.

Statuses remain distinct:

- `completed_hit`: Phaser completed and produced a parsed coordinate/MTZ
  solution, irrespective of its numeric review tier;
- `completed_no_hit`: Phaser completed and reported no solution;
- `failed_tool_execution`: Phenix returned non-zero;
- `failed_parse`: a nominally completed output was missing or inconsistent;
- `failed_infrastructure`: an explicitly configured adapter deadline expired;
  and
- an input-contract error: an immutable input, identifier, mapping, checksum,
  symmetry, label, or status did not match and execution was refused.

Scientific no-hit records exit successfully so unrelated hypotheses can
continue. Input-contract failures remain loud because continuing would change
the hypothesis identity or risk interpreting the wrong data. The fixed P2
qualification wrapper additionally fails unless the normalised execution status
is `completed_hit` or `completed_no_hit`; a schema-valid tool, parser, or
infrastructure failure is collectable evidence but cannot qualify the route.

## Nextflow boundary, cache, and outputs

`qualification.nf --qualification_stage first_copy` takes coordinate sources,
one
prepared-model directory,
sequence groups, Matthews and preflight JSONL, pipeline configuration, crystal
ID, the crystal MTZ, and the verified Phenix manifest. It builds the bounded
funnel, then fans out the single-record files to independent `process_mr`
tasks. Each task publishes `first_copy_phaser_<mrhyp-id>/` with:

- `normalised_mr_result.json` and `.jsonl`;
- `phaser_command.json`;
- `PHASER.log` when produced;
- the subprocess capture log; and
- solution PDB/MTZ files and their hashes when Phaser produces a solution.

The scientific cache identity is the immutable hypothesis plus the verified
sequence, model, MTZ, preflight, configuration, and Phenix-manifest content.
Nextflow additionally hashes the staged inputs, process script, resolved task
configuration, and environment. Changing any of these creates a different task
rather than silently reusing an old result.

The separate `qualification.nf --qualification_stage diverse_first_copy` entry
point accepts one predicted
coordinate/preparation bundle plus one registered PDB
coordinate/mapping/preparation bundle. It builds a self-contained aggregate
model registry, then reuses the same one-hypothesis-per-Phaser-process boundary:

```bash
pixi run -e hpc nextflow run qualification.nf \
  --qualification_stage diverse_first_copy \
  -profile local \
  --predicted_coordinate_sources /absolute/predicted/coordinate_sources.jsonl \
  --predicted_prepared_models /absolute/predicted/model-preparation \
  --pdb_coordinate_sources /absolute/pdb-registration/coordinate_sources.jsonl \
  --coordinate_hit_mappings /absolute/pdb-registration/coordinate_hit_mappings.jsonl \
  --experimental_prepared_models /absolute/pdb-model-preparation \
  --sequence_groups /absolute/catalogue/sequence_groups.jsonl \
  --matthews /absolute/matthews/matthews_hypotheses.jsonl \
  --preflight /absolute/preflight/mtz_preflight.jsonl \
  --config /absolute/input/config.yaml \
  --crystal_id CRYSTAL_ID \
  --maximum_first_copy_jobs 25 \
  --mtz /absolute/input/integrated.mtz \
  --phenix_manifest /absolute/software/manifests/phenix.json \
  --outdir /absolute/results/diverse-first-copy \
  --cache_root /absolute/cache/diverse-first-copy
```

Each Phase III hypothesis carries the deterministic
[MR resource plan](mr-resource-allocation.md). Marmic first attempts request
4/6/8 CPUs, 16/24/32 GB, and 12/18/24 hours according to reflection,
coordinate, copy-count, and bounded symmetry workload. The allocated CPUs are
passed to `phaser.keywords.general.jobs`. One classified infrastructure or
resource retry multiplies all three requests by `task.attempt` under the
16-CPU/64-GB/48-hour caps. Slurm owns aggregate admission; no process-local
concurrency cap is imposed.

Selection reserves exact mappings, then round-robins deterministically over
`(sequence_group_id, coordinate_provider, model_variant_type)` buckets so one
source class cannot consume the entire early queue. It applies the
configuration caps, the profile ceiling (smoke 25, pilot 200, extended 1,000),
and the optional stricter `maximum_first_copy_jobs` execution cap. The fixed
`p2-diverse` operation supplies 25 independently of the pilot configuration.
This is a hard safety bound, not a claim that 25 models are scientifically
sufficient. All ranking features and excluded counts remain inspectable in
`funnel_manifest.json`.

The test profile retains work only inside the harness's disposable `/tmp` root
so its required `-resume` assertion is meaningful; the temporary root is
removed by the harness after acceptance. Production retention remains governed
by the selected site profile.

## Test evidence and remaining P2 work

Focused tests cover real-format final-packing parsing, both observed
no-solution forms, the early packing advisory, missing final packing, exact
command construction, strict LLG/TFZ equalities, separate tool and parse
failures, MTZ checksum drift, paths containing spaces, and the CLI's no-timeout
default. The
funnel tests cover impossible-copy exclusion, inspectable features,
deterministic hard caps, model checksum drift, path traversal, and one-file-per-
hypothesis fan-out. Ruff, strict mypy, parser-v2 lint, a full stub run, published
outputs, and cached resume pass locally.

The fixed, checksum-gated Marmic P2 route is implemented and passes its
complete fake Git/Slurm/Nextflow/Phenix lifecycle, including fixed-input
resolution, normalised no-hit handling, failure-status rejection, bounded
collection, and cached resume. Immutable commit
`df153bebc0d1f02f6caaa9b8653fb8872aefbc65` replayed the qualified database,
P0, P1, one-hypothesis funnel, and cached P2 resume. Phaser then returned
`failed_tool_execution` with `INPUT: No scattering in coordinate file` for the
processed mmCIF. The PDB correction's next immutable replay completed Phaser
successfully: 76 translations entered packing, zero were accepted, no output
solution files were written, and the top translation TFZ was 5.11. This is a
scientific no-hit, but the adapter classified it as `failed_parse` because that
real log omitted the synthetic fixture's explicit zero-count phrase. The
parser correction's immutable replay reproduced the raw result, normalised it
as `completed_no_hit`, completed the outer job successfully, and cached both P2
processes on resume. The broader P2 gate still requires scheduled
positive/incorrect-model controls. The top-10/25 review and approval boundary is
implemented as described below. The first real Marmic P2-diverse panel completed
all 25 Phaser hypotheses under the superseded `LLG > 100` and `TFZ > 10`
policy. It independently recorded 11 packed single-copy placements. Recomputing
the preserved raw scores under the user-approved `LLG > 50` or `TFZ > 5` policy
classifies six in the higher-priority screen through the TFZ branch; all
six also have accepted packing and one placed copy. None passes through LLG.
The highest TFZ is 5.5, so these remain sensitive screening candidates rather
than proven structures. Review-package generation also exposed a contract bug
for no-solution records with no stored `score_gate_passed` field. A corrected
current-policy immutable replay then reproduced the same six raw candidates,
stored the intended classifications, and passed cache/provenance audits. Its six
checksum-bound PDB/MTZ/log bundles have been collected and mechanically
validated as readable, one-chain solutions with matching PDB/MTZ space group
and the expected map-coefficient columns. Scheduled controls and human
map/packing inspection remain required before same-component additional-copy
search begins.

## MR seed review checkpoint

`genome-to-diffraction review build-mr-seed` joins the immutable diverse-funnel
hypotheses to exactly one normalised result bundle each. Its required inputs
are the hypotheses and funnel manifest, aggregate normalised results, published
per-hypothesis result root, sequence groups, source-protein records, Matthews
hypotheses, and resolved pipeline configuration. The fixed `p2-diverse` job
runs this operation only after every hypothesis has a terminal scientific
result and before it writes the final summary.

The operation publishes:

- `mr_seed_candidates.tsv`, retaining model/sequence provenance, source loci,
  copy and Matthews/SDS context, raw LLG/LLGI/TFZ, packing, placed-copy
  agreement, warnings, and asset links;
- a self-contained `mr_seed_candidates.html` view with the same independent
  fields and an explicit warning that its lexicographic order is not a
  calibrated probability;
- `mr_seed_approval_candidates.tsv`, which states whether approving each
  current item requires an override reason;
- an empty, schema-valid `approved_mr_seeds.tsv` template, so scheduled work
  never creates or implies an approval; and
- `mr_seed_review_manifest.json`, binding every `sol_...` identifier to the
  hypothesis, normalised result, funnel, command, log, and result-asset
  checksums.

Ranking is deterministic and inspectable: Coot-inspectable asset availability,
completed-hit/no-hit/failure class, the strict raw `LLG > 50` or `TFZ > 5`
screen, packing, searched-copy agreement, raw LLG, raw TFZ, and immutable funnel
order. Primary and extended labels apply to the first 10 and 25 distinct
sequence-equivalence groups from the resolved configuration. They allocate
review attention; they are not posterior probabilities or automatic biological
assignments. Every parsed solution's PDB, MTZ, command, normalised result, and
log is copied for Coot review. The configured finalist cap applies only to
ancillary Phaser files such as `.sol` and rotation files. The retained remote
P2 publication remains the authoritative full result.

The checksum-gated HPC review collector also transfers the candidate TSV, HTML
report, approval-candidate TSV, and empty approval template recorded by the
manifest. Consequently, every Coot-inspectable solution and the exact decision
table that describes it travel together; shortlist labels and the numeric
screen do not remove files from this handoff.

The review operation always recomputes the current strict raw score screen from
the normalised LLG and TFZ fields. A missing stored `score_gate_passed` field is
permitted and evaluates to the recomputed result, which is false for a
no-solution record with no numeric scores. A result that records the superseded
`LLG > 100` and `TFZ > 10` policy is explicitly reclassified from its raw scores
without altering the source record. Under the current policy, a present stored
Boolean must agree exactly with the recomputation; an explicit contradiction or
unknown policy fails loudly. Packing and placed-copy evidence remain separate
review fields and never substitute for human judgement.

`genome-to-diffraction review validate-mr-seeds` takes the generated manifest,
a human-edited review-decision TSV, and an output JSON path. It verifies the
package and copied-output checksums, content-derived package and `sol_...`
identities, the `mr_seed` checkpoint, non-duplicate current item IDs, reviewer
and UTC timestamp, and at least one explicit `approve`. An approval requires a
non-empty `override_reason` only when no Coot-inspectable PDB/MTZ solution exists; this
does not rewrite its preliminary score-screen class.
Unknown, stale, edited, pre-package, placeholder, empty, or wrong-checkpoint
decisions fail with an input-contract error before downstream execution. A
successful validation writes a content-derived `rev_...` record; it does not
start additional-copy placement.

The review cache identity is the funnel and all joined input checksums, every
content-derived solution ID, the shortlist sizes, the result-asset retention
cap, and package creation timestamp. Unit tests cover a credible hit, a
scientific no-hit override, a no-solution result without a stored gate, an
explicit stored/recomputed gate contradiction, schema-valid empty template,
stale identifiers, edited review output, result-path traversal, and approval
provenance. The fake Git/Slurm/Nextflow lifecycle covers package creation,
fixed summary binding, bounded compact collection, and checksum-gated
inspectable-asset collection. The corrected real Marmic replay produced and
bound the version-2 package; its six score-priority bundles were collected
without caller-supplied paths or candidate identifiers. Version 3 expands the
same secure transfer to every parsed solution. Human inspection remains required.
