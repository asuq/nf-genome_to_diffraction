# Structural-search interface

## Scope and scientific purpose

M1 structural discovery searches each eligible exact catalogue sequence against
immutable structural-reference resources. The first provider is a local
MMseqs2 search against the qualified PDB SEQRES database. It maps every retained
target to a PDB entry and case-sensitive chain/entity token suitable for later
coordinate retrieval.

A structural hit is model or protein-family evidence. It remains tied to the
supplied `sequence_group_id` and cannot introduce an external sequence as a
reportable catalogue identity. The direct PDB route does not perform molecular
replacement and does not claim that a hit explains a crystal.

## Inputs and requirements

`structure-search pdb-sequence` requires:

- canonical `sequence_groups.jsonl` records from trusted catalogue import;
- a qualified `database-manifest` containing exactly one ready
  `pdb_sequences` resource with a passed smoke test;
- `pdb_seqres` and `target_mapping.tsv` below that resource root; and
- the exact MMseqs2 version recorded in the resource provenance.

Queries containing non-standard residues, records excluded by catalogue policy,
and sequences above the configured length cap are retained as explicit
ineligible results rather than silently dropped. The default bounded search uses
25 targets per query, E-value at most `1e-5`, query coverage at least `0.5`, and
a maximum query length of 10,000 residues. Alignment mode 3 is requested so the
reported `fident` fraction comes from the alignment rather than an estimated
identity; the field scale follows the
[official MMseqs2 user guide](https://mmseqs.com/latest/userguide.pdf).

## Command-line and workflow entry points

```bash
pixi run genome-to-diffraction \
  --log-format json \
  --no-progress \
  structure-search pdb-sequence \
  --sequence-groups /absolute/catalogue/sequence_groups.jsonl \
  --database-manifest /absolute/databases/database_manifest.json \
  --outdir /absolute/results/pdb-sequence \
  --threads 16
```

The equivalent typed DSL2 entry point is `discover_structures.nf`. It publishes
the complete `pdb_sequence_search` directory and standard Nextflow report,
timeline, trace, and DAG files. `-stub-run -profile test` uses only tracked
schema-valid fixtures. A normal run requires the real qualified database.

## Outputs

- `search_results.jsonl`: one result per input sequence group, including an
  execution status, scientific status, cache key, raw evidence checksums, and
  zero or more embedded normalised hits.
- `structural_hits.jsonl`: the flattened retained-hit stream for downstream
  joins. Every retained PDB hit includes a retrievable namespaced `model_key`
  of the form `pdb:<PDBID>:<identifier-namespace>:<chain-or-entity-token>`.
- `search_manifest.json`: provider, adapter, database, tool, parameter, count,
  status, and output-integrity summary.
- `raw/queries.faa`: the exact eligible query batch.
- `raw/mmseqs-results.tsv`: unmodified tabular MMseqs2 result evidence.
- `raw/mmseqs.log`: the resolved command and combined tool output.

All output writes are atomic except the tool-owned raw TSV/log while the command
is running. A non-empty output directory is rejected to prevent mixed evidence.

## Status and failure semantics

| Execution status | Scientific status | Meaning |
|---|---|---|
| `completed_hit` | `hits_found` | At least one configured PDB sequence hit was retained |
| `completed_no_hit` | `no_hit` | Search completed normally but retained no hit |
| `skipped_ineligible` | `not_interpretable` | Catalogue policy or sequence content prevented a valid query |

An unavailable or unqualified database, MMseqs2 version mismatch, command
failure, malformed or truncated result, unknown query, duplicate result, invalid
metric, or missing PDB mapping fails the provider. Such failures never become a
scientific no-hit and do not count as evidence against a candidate.

## Reproducibility and cache identity

The batch identity includes the adapter version, database ID, complete
sequence-group input checksum, MMseqs2 version, and every scientifically
effective search parameter. Per-query result identities additionally bind the
exact sequence digest and its eligibility-relevant quality flags, without being
invalidated by unrelated catalogue records. Thread count is recorded in the
command but intentionally does not alter the scientific cache identity. Nextflow
binds the input files and parameters to its process cache; a repeated unchanged
workflow run must report cached work with `-resume`.

The current interface performs no remote calls and accepts no crystal metadata
or SDS-PAGE values, so those cannot affect direct PDB search identity. Exact
AFDB retrieval, optional remote ESM Atlas access, ProstT5/Foldseek structural
search, and hit union remain later M1 work.

The fixed `structure-search qualify-p1` command verifies the complete direct-PDB
output inventory and checksums, exactly one result per supplied sequence group,
embedded/flattened hit consistency, retrievable model keys, the tracked 8OOX
positive-control family, a completed first Nextflow trace, and a fully cached
resume trace. Its JSON evidence retains the control hits, process/resource trace
fields, result-tree size, and cache counts. Nextflow `rchar`/`wchar` values are
reported as process-I/O counters and are not overinterpreted as physical
database-device bytes.

## Test coverage and present qualification

Focused tests cover hit/no-hit/ineligible separation, paths containing spaces,
normalised sequence identity, exact PDB/chain mapping, parameter propagation,
and fail-loud handling of unmapped targets. The Nextflow acceptance suite checks
parser-v2 linting, publication, standard reports, and cached stub resume.

The direct provider and fixed qualification boundary are implemented
functionality, not yet a passed P1 scientific gate. P1 still requires the real
full-catalogue Marmic run, then the remaining approved M1 providers and evidence
union. The first real run must retain the 8OOX structural family, complete model
keys, cache reuse, and measured CPU, memory, process I/O, result size, and
cache-hit rate.
