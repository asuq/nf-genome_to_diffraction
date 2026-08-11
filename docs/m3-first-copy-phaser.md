# M3 first-copy Phaser boundary

## Scope and current qualification

The active M3 vertical slice joins the integrity-checked exact-predicted model
from M2 to physically possible Matthews copy hypotheses, then runs one
independent Phaser search per immutable hypothesis. The Python adapter, parser,
strict provisional score gate, and typed Nextflow stub route passed local
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

This slice deliberately excludes experimental PDB model variants, domains,
same-component additional copies, refinement, map inspection, sequence-from-map
analysis, ranking reports, and reviewer approval. Those remain separate gates.

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

The adapter verifies that the hypothesis is queued, independent, first-copy,
and exact-mapped. It revalidates the model path and checksum, observation
labels, space group, preflight status, MTZ checksum, sequence group, and Phenix
manifest before execution. It then calls `phenix.phaser` through the isolated
Phenix subprocess wrapper in a hypothesis-owned directory with:

- `MR_AUTO` mode;
- sequence-based total composition and the hypothesis's expected copy count;
- exactly one searched copy;
- explicit 100% sequence identity for the exact catalogue/model mapping;
- model uncertainty retained through the B values produced by
  `phenix.process_predicted_model`, with its validated single-chain PDB output
  supplied to Phaser;
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
the preliminary credibility class. A solution passes the user-defined
provisional score gate only when both inequalities are strict:

```text
top LLG > 100 and top TFZ > 10
```

Equality does not pass. Passing the score gate is still insufficient when the
final solution did not pack or the placed-copy count differs from the requested
one. The rule is a prototype triage boundary, not a universal Phaser-success
criterion and not a substitute for maps, refinement, or expert review.

Statuses remain distinct:

- `completed_hit`: score, final packing, and placed-copy checks pass;
- `completed_no_hit`: Phaser completed but reported no solution, or a produced
  solution failed a scientific gate;
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

`screen_first_copy.nf` takes coordinate sources, one prepared-model directory,
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
processes on resume. The broader P2 gate
still requires a runnable known positive and deliberate no-solution case,
per-crystal smoke enforcement, the top-10/25 review package, and approval-file
validation. No same-component additional-copy search should begin before this
evidence is reviewed.
