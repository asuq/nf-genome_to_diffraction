# Structural-search interface

## Scope and scientific purpose

M1 structural discovery searches each eligible exact catalogue sequence against
immutable structural-reference resources. Two local providers are implemented:
MMseqs2 searches the qualified PDB SEQRES database directly, while ProstT5
translates catalogue sequences into predicted 3Di strings for Foldseek search
against the qualified PDB100 resource. Both map retained targets to PDB entries
and case-sensitive chain/entity tokens suitable for later coordinate retrieval.

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

`structure-search prostt5-foldseek` additionally requires exactly one ready,
smoke-qualified `pdb_foldseek` and `prostt5` resource prepared by the same
Foldseek version, plus the qualified `pdb_sequences` crosswalk. Its CPU-default
search retains the best three normalised hits per query after preserving up to
1,000 raw Foldseek alignments, uses E-value at most `1e-3`, and requires at least
`0.5` query coverage. GPU execution is available only with explicit `--gpu`.
The requested fields are query/target identifiers, sequence identity, alignment
coordinates and lengths, E-value, bit score, and Foldseek homology probability.
It deliberately does not request query Cα coordinates, TM-scores, LDDT,
rotations, or translations: ProstT5 produces a 3Di sequence, not atomic query
coordinates. This follows the [official Foldseek search and ProstT5
documentation](https://github.com/steineggerlab/foldseek#fast-structure-search-from-fasta-input).

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

pixi run genome-to-diffraction \
  --log-format json \
  --no-progress \
  structure-search prostt5-foldseek \
  --sequence-groups /absolute/catalogue/sequence_groups.jsonl \
  --database-manifest /absolute/databases/database_manifest.json \
  --outdir /absolute/results/prostt5-foldseek \
  --threads 16
```

The equivalent typed DSL2 entry point is `discover_structures.nf`. It runs the
two providers independently and publishes complete `pdb_sequence_search` and
`prostt5_foldseek_search` directories plus standard Nextflow report, timeline,
trace, and DAG files. `-stub-run -profile test` uses only tracked schema-valid
fixtures. A normal run requires the real qualified databases.

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
- `raw/foldseek-results.tsv` and `raw/foldseek.log`: unmodified structural-hit
  evidence and the resolved ProstT5/Foldseek command for the second provider.

All output writes are atomic except the tool-owned raw TSV/log while the command
is running. A non-empty output directory is rejected to prevent mixed evidence.

## Status and failure semantics

| Execution status | Scientific status | Meaning |
|---|---|---|
| `completed_hit` | `hits_found` | At least one configured PDB sequence hit was retained |
| `completed_no_hit` | `no_hit` | Search completed normally but retained no hit |
| `skipped_ineligible` | `not_interpretable` | Catalogue policy or sequence content prevented a valid query |

An unavailable or unqualified database, tool-version mismatch, command failure,
malformed or truncated result, unknown query, duplicate result, invalid metric,
or missing PDB mapping fails the affected provider. Such failures never become
a scientific no-hit and do not count as evidence against a candidate.

## Reproducibility and cache identity

The batch identity includes the adapter version, all effective database IDs,
complete sequence-group input checksum, exact tool version, and every
scientifically effective search parameter. Per-query result identities
additionally bind the exact sequence digest and its eligibility-relevant quality
flags, without being invalidated by unrelated catalogue records. Thread count is
recorded in the command but intentionally does not alter scientific cache
identity. Nextflow binds input files and parameters to its process cache; a
repeated unchanged workflow run must report cached work with `-resume`.

The current interface performs no remote calls and accepts no crystal metadata
or SDS-PAGE values, so those cannot affect local provider identity. Exact AFDB
retrieval, optional remote ESM Atlas access, and provider-aware hit union remain
later M1 work. A ProstT5/Foldseek hit remains structural-family evidence tied to
the submitted catalogue sequence; it is not a predicted atomic query model and
must not be treated as reportable protein identity.

The fixed `structure-search qualify-p1` command verifies the complete direct-PDB
output inventory and checksums, exactly one result per supplied sequence group,
embedded/flattened hit consistency, retrievable model keys, the tracked 8OOX
positive-control family, a completed first Nextflow trace, and a fully cached
resume trace. Its JSON evidence retains the control hits, process/resource trace
fields, result-tree size, and cache counts. Nextflow `rchar`/`wchar` values are
reported as process-I/O counters and are not overinterpreted as physical
database-device bytes.

## Test coverage and present qualification

Focused tests cover both providers' hit/no-hit/ineligible separation, paths
containing spaces, normalised sequence identity, exact PDB/chain mapping,
parameter propagation, explicit GPU activation, valid ProstT5 output fields,
probability bounds, and fail-loud handling of unmapped targets. The Nextflow
acceptance suite checks parser-v2 linting, publication, standard reports, and
cached stub resume.

The direct provider and fixed qualification boundary passed their first real
full-catalogue Marmic run. It retained the exact 8OOX/8OOW family, complete
model keys, a fully cached resume, and measured CPU, memory, process I/O, result
size, and cache state. See the
[P1 direct-PDB qualification](p1-direct-pdb-qualification.md). The full M1 P1
gate still requires real catalogue qualification of ProstT5/Foldseek, exact
AFDB retrieval, the optional-provider policy decision, and provider-aware
evidence union.
