# Structural-search interface

## Scope and scientific purpose

M1 structural discovery searches each eligible exact catalogue sequence against
immutable structural-reference resources. Three providers are implemented:
MMseqs2 searches the qualified PDB SEQRES database directly, while ProstT5
translates catalogue sequences into predicted 3Di strings for Foldseek search
against the qualified PDB100 resource. Both local routes map retained targets to
PDB entries and case-sensitive chain/entity tokens suitable for later coordinate
retrieval. The third route retrieves at most one AlphaFold DB monomer when a
strict UniProt accession is available and both the service sequence and the
downloaded mmCIF polymer match the catalogue digest exactly.

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

`structure-search afdb-exact` additionally requires `source_records.jsonl` and
one ready, smoke-qualified `coordinate_cache` resource. A source
`original_protein_id` is accepted only when it is a strict UniProt accession or
`sp|ACCESSION|...`/`tr|ACCESSION|...` identifier. Otherwise, the optional mapping
TSV must have exactly these headers:

```text
source_record_id	uniprot_accession
```

RefSeq `WP_...` accessions are deliberately not guessed or submitted. The
provider calls the official accession metadata endpoint, accepts only monomeric,
full-sequence protein records, verifies the returned sequence digest, downloads
the advertised mmCIF from an allowlisted official host, parses its polymer with
Gemmi, and verifies that digest again. Multiple exact records are reduced to one
by a fixed preference for the canonical Google DeepMind provider, reviewed
UniProt records, reference-proteome records, and then stable accession/model
ordering. All alternatives and rejections remain in raw query evidence. This is
necessary because the current AFDB contains isoforms, fragments, predictions
from multiple datasets, and complexes; see the [official AFDB FAQ](https://alphafold.com/faq).

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

pixi run genome-to-diffraction \
  --log-format json \
  --no-progress \
  structure-search afdb-exact \
  --sequence-groups /absolute/catalogue/sequence_groups.jsonl \
  --source-records /absolute/catalogue/source_records.jsonl \
  --accession-map /absolute/input/afdb_accessions.tsv \
  --database-manifest /absolute/databases/database_manifest.json \
  --outdir /absolute/results/afdb-exact
```

The equivalent typed DSL2 entry point is `discover_structures.nf`. It runs the
three providers independently and publishes complete `pdb_sequence_search`,
`prostt5_foldseek_search`, and `afdb_exact_search` directories plus standard
Nextflow report, timeline, trace, and DAG files. The AFDB process has the
dedicated `process_network` label; compute-node internet access must therefore
be an explicit site capability. `-stub-run -profile test` uses only tracked
fixtures. A normal run requires the real qualified databases.

## Outputs

- `search_results.jsonl`: one result per input sequence group, including an
  execution status, scientific status, cache key, raw evidence checksums, and
  zero or more embedded normalised hits.
- `structural_hits.jsonl`: the flattened retained-hit stream for downstream
  joins. Every retained PDB hit includes a retrievable namespaced `model_key`
  of the form `pdb:<PDBID>:<identifier-namespace>:<chain-or-entity-token>`.
- `coordinate_sources.jsonl`: for AFDB, the immutable selected coordinate,
  catalogue-sequence checksum, model version, confidence summary, retrieval
  time, checksum, cache path, and CC-BY-4.0 provenance. Its model key is
  `afdb:<modelEntityId>:v<latestVersion>`.
- `search_manifest.json`: provider, adapter, database, tool, parameter, count,
  status, and output-integrity summary.
- `raw/queries.faa`: the exact eligible query batch.
- `raw/mmseqs-results.tsv`: unmodified tabular MMseqs2 result evidence.
- `raw/mmseqs.log`: the resolved command and combined tool output.
- `raw/foldseek-results.tsv` and `raw/foldseek.log`: unmodified structural-hit
  evidence and the resolved ProstT5/Foldseek command for the second provider.
- `raw/api/*.json`, `raw/afdb-query-results.jsonl`, and `raw/http.log`: exact AFDB metadata
  responses, per-sequence selection/rejection evidence, and bounded request
  provenance. Downloaded mmCIF bytes are stored content-addressed below the
  qualified shared coordinate cache.

All output writes are atomic except the tool-owned raw TSV/log while the command
is running. A non-empty output directory is rejected to prevent mixed evidence.

## Status and failure semantics

| Execution status | Scientific status | Meaning |
|---|---|---|
| `completed_hit` | `hits_found` | At least one configured PDB sequence hit was retained |
| `completed_no_hit` | `no_hit` | Search completed normally but retained no hit |
| `skipped_ineligible` | `not_interpretable` | Catalogue policy, sequence content, or absent exact accession mapping prevented a valid query |

An unavailable or unqualified database, tool-version mismatch, command failure,
malformed or truncated result, unknown query, duplicate result, invalid metric,
missing PDB mapping, HTTP/service failure, unsafe redirect, or API/mmCIF
inconsistency fails the affected provider. Such failures never become a
scientific no-hit and do not count as evidence against a candidate. A valid
accession returning HTTP 404 or only non-exact models is `completed_no_hit`; the
rejection evidence preserves why.

## Reproducibility and cache identity

The batch identity includes the adapter version, all effective database IDs,
complete sequence-group input checksum, exact tool version, and every
scientifically effective search parameter. Per-query result identities
additionally bind the exact sequence digest and its eligibility-relevant quality
flags, without being invalidated by unrelated catalogue records. Thread count is
recorded in the command but intentionally does not alter scientific cache
identity. Nextflow binds input files and parameters to its process cache; a
repeated unchanged workflow run must report cached work with `-resume`.

The local providers perform no remote calls. The AFDB cache key additionally
binds the exact sequence digest, candidate accession set, optional mapping-file
checksum, endpoint-field contract, adapter version, and coordinate-cache
resource ID. It sends only mapped public accession strings to AFDB, never a
catalogue sequence. HTTP attempts are bounded and logged; successful metadata
and selected coordinates are retained with checksums. Crystal metadata and
SDS-PAGE values do not enter provider identity. Optional remote ESM Atlas access
and provider-aware hit union remain later M1 work. A ProstT5/Foldseek hit remains
structural-family evidence tied to the submitted catalogue sequence; it is not a
predicted atomic query model and must not be treated as reportable protein
identity.

The fixed `structure-search qualify-p1` command verifies the complete direct-PDB
output inventory and checksums, exactly one result per supplied sequence group,
embedded/flattened hit consistency, retrievable model keys, the tracked 8OOX
positive-control family, a completed first Nextflow trace, and a fully cached
resume trace. Its JSON evidence retains the control hits, process/resource trace
fields, result-tree size, and cache counts. Nextflow `rchar`/`wchar` values are
reported as process-I/O counters and are not overinterpreted as physical
database-device bytes.

## Test coverage and present qualification

Focused tests cover the local providers' hit/no-hit/ineligible separation, paths
containing spaces, normalised sequence identity, exact PDB/chain mapping,
parameter propagation, explicit GPU activation, valid ProstT5 output fields,
probability bounds, and fail-loud handling of unmapped targets. The Nextflow
acceptance suite checks parser-v2 linting, publication, standard reports, and
cached stub resume.

AFDB tests cover explicit RefSeq-to-UniProt mapping, zero-network RefSeq
ineligibility, exact API and parseable-mmCIF sequence agreement, atomic cache
publication, non-exact rejection, and fail-loud coordinate disagreement. The
official live service contract passed a small exact `P69905` retrieval; see the
[P1 exact AFDB qualification](p1-afdb-exact-qualification.md).

The direct provider and fixed qualification boundary passed their first real
full-catalogue Marmic run. It retained the exact 8OOX/8OOW family, complete
model keys, a fully cached resume, and measured CPU, memory, process I/O, result
size, and cache state. See the
[P1 direct-PDB qualification](p1-direct-pdb-qualification.md). The full M1 P1
gate still requires real catalogue qualification of ProstT5/Foldseek, a mapped
pilot/prokaryotic AFDB accession if available, the optional-provider
policy decision, and provider-aware evidence union.
