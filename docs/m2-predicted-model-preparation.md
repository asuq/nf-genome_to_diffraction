# M2 predicted-model preparation

## Scope and current qualification

The first M2 vertical slice prepares an exact sequence-mapped AFDB or ESM Atlas
coordinate for molecular replacement with verified
`phenix.process_predicted_model`. It implements one intentionally bounded
variant: a confidence-pruned, unsplit full predicted model. It does not yet
implement PDB coordinate retrieval, domain splitting, experimental-model
variants, or the candidate funnel. A typed `prepare_models.nf` entry point now
wires the qualified adapter for isolated execution and cached resume; real
fixed-Marmic evidence remains pending.

The adapter was qualified on 10 August 2026 with Phenix 2.1-6048 on macOS
Apple Silicon using the real pilot-derived `Methermicoccus shengliensis`
glutamine-synthetase model. The input is the exact sequence group for
`WP_042685700.1`, mapped explicitly to AFDB accession `A0A832VZP6`; this mapping
must not be generalised to the rest of the proteome.

| Evidence | Qualified value |
| --- | --- |
| Sequence group | `seq_102e653b2ce68310033502e10e60f54e7cb143dc71acd0e964d0cad47f961964` |
| Source coordinate | `coord_f4f853333abe3cf1ac1fcba0ffc5a1bf87a87a73c3562d5bb999c77738344ed7` |
| Source coordinate SHA-256 | `5555477700990be7f61151911153d5cd6089f6c6bafd0dd5388d0d30ae06738b` |
| AFDB source release | model version 6 |
| AFDB mean pLDDT | 93.81 |
| Starting / retained residues | 442 / 429 |
| Retained ranges | `A:3-56`, `A:65-82`, `A:85-313`, `A:315-442` |
| Processed model mass | 48,052.3422 Da, calculated from the retained sequence |
| Processed model SHA-256 | `85bbc57e37096abd9c2c8fa0f21d5c7b809fb75f277c248576a75a45e3dbf4cb` |
| Processed model ID | `model_8af5db867c4ce13ce4ce3acdd2704ce55fef50c157c268e2195dac20c3f20c93` |

The real run initially exposed an invalid parser assumption: Gemmi's
`make_one_letter_sequence()` represents coordinate discontinuities and is not
guaranteed to have one character per retained residue. The corrected adapter
derives one-letter codes residue by residue and independently verifies each
original residue number against the full catalogue sequence. It therefore
retains the deletion pattern without accepting an unmapped output.

## Command

```bash
pixi run --locked genome-to-diffraction \
  --log-format json \
  --no-progress \
  model prepare-predicted \
  --coordinate-sources /absolute/results/afdb/coordinate_sources.jsonl \
  --sequence-groups /absolute/results/catalogue/sequence_groups.jsonl \
  --phenix-manifest /absolute/software/manifests/phenix.json \
  --outdir /absolute/results/model-preparation \
  --coordinate-id coord_FULL_SHA256
```

Omit `--coordinate-id` to process every predicted coordinate source in the
input. Repeating it selects an explicit bounded set. Phenix is sourced only in
the isolated child process described by the verified installation manifest.
No per-command deadline is imposed by default because NFS startup latency is
unpredictable on Marmic; `--timeout-seconds` remains available when an operator
explicitly wants a bound.

## Inputs and validation

The command accepts `CoordinateSourceRecord` and `SequenceGroupRecord` JSONL.
For every selected source it requires:

- provider `afdb` or `esm_atlas`;
- a content-derived `coord_` identifier and unique source record;
- an unchanged, parseable, single-model/single-polymer coordinate file;
- a coordinate SHA-256 matching the source record;
- a recorded source-sequence digest matching exactly one supplied sequence
  group; and
- a full one-based predicted-coordinate mapping to the catalogue sequence
  before confidence processing.

The source checksum is checked again after Phenix returns. The processed model
must be one unsplit mmCIF, preserve the chain identifier, contain only integer
residue positions within the catalogue sequence, and match the expected amino
acid at every retained position.

## Fixed processing policy

The adapter records and pins the scientifically relevant Phenix settings:

- target format `mmcif`;
- B-value field interpreted as `plddt` on the 0–100 scale;
- low-confidence removal enabled; and
- compact-region/domain splitting disabled for this first full-model variant.

Low-confidence removal and pLDDT interpretation are recorded even where they
match Phenix defaults because they materially define the model. Disabling
domain splitting prevents this initial slice from silently generating an
unbounded variant family. Domain models will be a separate, explicit policy.

## Nextflow boundary

`prepare_models.nf` takes the AFDB/Atlas `coordinate_sources.jsonl`, exact
catalogue `sequence_groups.jsonl`, and verified Phenix installation manifest.
Its single `process_phenix` task runs in nf-helper's compute-node `/scratch` on
Marmic and publishes one complete `predicted_model_preparation` directory. The
entry point deliberately does not retrieve coordinates or choose candidates;
the upstream discovery evidence and reviewed mapping remain separate inputs.

The fixed P1 path supplies the tracked one-row
`WP_042685700.1`/`A0A832VZP6` mapping to a bounded login-node prefetch because
Marmic compute nodes reject outbound HTTPS. Staging imports the immutable
catalogue, retrieves and sequence-verifies exactly one public model, and records
checksums for every hand-off file. The compute job verifies that record, runs
the remaining discovery branches offline, then runs and resumes model
preparation with a separate cache. It fails if the prefetch or model preparation
does not yield exactly one record, or if the model task is not cached on resume.
This protects the real vertical slice without generalising one accession
mapping to the remaining proteome.

## Outputs and identity

The output directory contains:

- `processed_models.jsonl`, validated `ProcessedModelRecord` objects;
- `model_preparation_manifest.json`, relocatable model/log paths and residue
  counts;
- `models/<sha-prefix>/<sha256>.cif`, content-addressed processed models; and
- `raw/<coordinate-id>/phenix.process_predicted_model.log`, the complete native
  command log.

The processed-model ID includes the source coordinate ID and checksum, source
sequence digest, exact full-sequence alignment, retained residue ranges, variant
type, adapter version, Phenix build, Phenix-manifest checksum, resolved
processing parameters, and processed-model checksum. Raw log text and run time
are excluded because Phenix writes timestamps to its log; they cannot change
scientific identity.

The model mass is recalculated from the retained amino-acid sequence and is not
copied from the full catalogue protein. This is the mass available for later
model-completeness and MR bookkeeping; Matthews copy-number hypotheses continue
to use the full candidate sequence mass.

## Failure and status semantics

A successful record uses `completed_success`. Checksum drift, unknown or
duplicate IDs, unsupported experimental coordinates, and coordinate-to-sequence
mismatches are input-contract failures. A non-zero/timeout Phenix execution or
missing/ambiguous output is a tool-execution failure. An unreadable mmCIF,
unknown residue, insertion code, chain change, or residue-level mapping failure
is a parse failure. These failures must not be converted into scientific
negative evidence against the candidate.

Complete command output is retained in the raw log. The raised diagnostic
contains at most the final 16 KiB and 40 lines, keeping structured logs useful
without flooding the scheduler record. `logging` reports batch and per-model
counts; `tqdm` reports validation, checksum, and model progress when attached to
an interactive terminal.

## Tests and remaining gate

Focused tests cover content addressing, exact residue mapping, paths with
spaces, output contracts, source checksum drift, and bounded native failure
tails. Parser-v2 lint and stub execution cover the typed Nextflow entry point,
published directory, and cached resume. The real Phenix run above is the current
T8.4 evidence. M2 remains open until the fixed Marmic Nextflow path passes and
the repository also provides reviewable PDB chain/entity/range retrieval,
bounded experimental and domain variants, and a candidate funnel whose job
count is known before Phaser submission.
