# M2 experimental PDB model preparation

## Scope

This first experimental-coordinate slice converts each registered direct-PDB
hit mapping into one deterministic, Phaser-readable cleaned source-chain model.
It implements only the handoff's initial source-chain variant. It does not yet
adapt the PDB sequence to the catalogue candidate, prune side chains, choose a
domain, combine chains, or construct an ensemble. Consequently, a prepared
model remains experimental homologue evidence linked to a supplied catalogue
sequence group; it is not a claim that the external PDB sequence is the crystal
identity.

The implementation uses the Pixi-locked Gemmi runtime and no licensed Phenix
command. It requires one structural model and one coordinate chain matching the
registered case-sensitive author-chain token. It removes non-polymer residues
and hydrogens, retains alternate conformations and their occupancies, remaps the
single output chain to `A` for portable PDB output, and verifies that the output
preserves the observed polymer sequence. Multi-model entries and unknown
observed residues fail rather than being reduced by an unstated policy.

## Commands and workflow

```bash
pixi run --locked genome-to-diffraction \
  --log-format json \
  --no-progress \
  model prepare-experimental \
  --coordinate-sources /absolute/pdb-registration/coordinate_sources.jsonl \
  --coordinate-hit-mappings /absolute/pdb-registration/coordinate_hit_mappings.jsonl \
  --sequence-groups /absolute/catalogue/sequence_groups.jsonl \
  --outdir /absolute/results/pdb-model-preparation
```

Repeat `--mapping-id coordmap_FULL_SHA256` to process an explicit reviewed
subset; omitting it processes every supplied mapping. The typed DSL2 equivalent
is:

```bash
pixi run -e hpc nextflow run qualification.nf \
  --qualification_stage prepare_experimental_models \
  -profile local \
  --coordinate_sources /absolute/pdb-registration/coordinate_sources.jsonl \
  --coordinate_hit_mappings /absolute/pdb-registration/coordinate_hit_mappings.jsonl \
  --sequence_groups /absolute/catalogue/sequence_groups.jsonl \
  --outdir /absolute/results/pdb-model-preparation \
  --cache_root /absolute/cache/nf-genome-to-diffraction-pdb-models
```

## Inputs, outputs, and identity

The adapter joins three strict JSONL streams:

- PDB `CoordinateSourceRecord` values with immutable source paths and SHA-256;
- `CoordinateHitMappingRecord` values preserving PDB entry/entity/chain,
  candidate/source sequence digests, and the search alignment; and
- the trusted catalogue `SequenceGroupRecord` values.

It publishes:

- `processed_models.jsonl`, one `ProcessedModelRecord` per selected mapping;
- `models/<sha-prefix>/<sha256>.pdb`, deduplicated by exact output bytes; and
- `model_preparation_manifest.json`, containing input checksums, Gemmi version,
  per-model paths and checksums, source completeness, candidate coverage,
  sequence identity, exact/homologue state, quality flags, and output checksum.

`model_id` binds the source-coordinate digest, mapping identity and alignment,
source residue ranges, variant policy, Gemmi version, every processing
parameter, and the resulting model digest. The observed-residue mass is
calculated from the exact cleaned coordinate sequence. Source-chain completeness
and candidate query coverage remain separate fields; neither is silently
treated as the other.

## Logging, progress, and failure semantics

Structured `logging` records each checksum verification and completed mapping.
`tqdm` reports validation and model progress on an attached terminal;
`--no-progress` suppresses it for Nextflow and automation. Diagnostic logs use
standard error and the CLI summary uses standard output.

The adapter publishes only successful model records. Missing/duplicate IDs,
checksum drift, source/group sequence mismatches, unsafe files, a non-PDB
source, absent or ambiguous chains, multiple structural models, empty or
unknown polymers, changed output sequence, non-exact mass, or invalid observed
coverage fails loudly. These are execution/input failures, not scientific
no-hits and not negative evidence against the catalogue candidate. Because the
models directory is content-addressed, already published identical bytes are
verified and safely reused; the output directory itself must otherwise be
empty.

## Test coverage and qualification state

Unit tests exercise paths containing spaces, source/group/mapping joins,
checksum drift, water and hydrogen removal, output-chain remapping, observed
sequence preservation, model mass/checksum/identity, homologue quality flags,
structured records, and progress suppression. Parser-v2 lint plus a full
`-stub-run` and `-resume` exercise
`qualification.nf --qualification_stage prepare_experimental_models` and
standard Nextflow
reports.

The software boundary is implemented but not yet qualified on the real Marmic
direct-PDB candidates. Its output now feeds the implemented
`ranking diverse-first-copy-funnel` boundary alongside the qualified predicted
model bundle. That funnel verifies every source/model/mapping checksum, keeps
experimental and predicted source classes explicit, round-robins across
sequence-group/provider/variant buckets, and enforces at most 25 first-copy jobs
per crystal in smoke mode. It publishes an aggregate content-addressed model
registry so each selected Phaser task consumes the exact model referred to by
its immutable hypothesis.

The next real gate is to register a bounded candidate set from the immutable P1
results, prepare these source-chain models on Marmic, run
`qualification.nf --qualification_stage diverse_first_copy`, and inspect the
selected count before Phaser
submission. Sequence-adapted/side-chain-pruned and clear-domain variants remain
later calibrated additions, not blockers for this first feedback run.
