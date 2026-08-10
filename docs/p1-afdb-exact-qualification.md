# P1 exact AlphaFold DB provider qualification

## Result

The T7.4 exact-accession provider passed two live retrievals on 10 August 2026.
The first froze the current service contract with reviewed UniProt `P69905`.
The second used the public exact mapping from pilot RefSeq protein
`WP_042685700.1` to UniProt `A0A832VZP6`. Each produced one `completed_hit`
result and one immutable coordinate-source record without submitting an
amino-acid sequence to a remote service.

The second result qualifies an exact pilot-catalogue mapping and model-retrieval
path. It is still structural evidence for one catalogue protein, not evidence
that this protein explains a pilot crystal and not a protein-identification
result.

## Frozen public control and observed evidence

- Public sequence source: reviewed UniProtKB entry
  [`P69905`](https://www.uniprot.org/uniprotkb/P69905/entry), haemoglobin subunit
  alpha, 142 amino acids.
- Catalogue-sequence SHA-256:
  `14725a10598943a7aa719eed7d24c7fee599192a6c63c75b051ee6f156341242`.
- Metadata request: official AFDB accession-prediction API for `P69905`.
- Metadata response: HTTP 200, 1,987 bytes, SHA-256
  `af907bb73c411790ac6a24764314287e5cd331c0ed5b13eae9924ce45b27d8f9`.
- Selected model: `AF-P69905-F1`, model version 6; normalised model key
  `afdb:AF-P69905-F1:v6`.
- Reported mean pLDDT: 98.06. This is preserved as provider confidence and is
  not treated as experimental validation.
- Coordinate response: HTTP 200, 137,559-byte mmCIF, SHA-256
  `eb7adbdd79775b0d694bacfa4b29872e05f4e56af26af880960d755c3036e230`.
- Gemmi parsed one unique 142-residue polymer. Its canonical sequence digest
  matched both the AFDB metadata sequence and the supplied public catalogue
  sequence exactly.
- The coordinate and provider metadata were published under the initialised
  content-addressed AFDB cache namespace with CC-BY-4.0 provenance. AFDB states
  that its data are available under that licence on its
  [official download page](https://alphafold.ebi.ac.uk/download).

The live output contracts were reloaded through `StructuralSearchResult` and
`CoordinateSourceRecord`; both validated. Unit coverage separately verifies
explicit RefSeq-to-UniProt mapping, zero-network behaviour for unmapped
`WP_...` records, non-exact rejection, path spaces, atomic cache publication,
and fail-loud API/mmCIF sequence disagreement.

## Pilot-derived public mapping

The current UniProt record for
[`A0A832VZP6`](https://www.uniprot.org/uniprotkb/A0A832VZP6/entry) explicitly
cross-references RefSeq `WP_042685700.1`. The sequence is the 442-residue
glutamine synthetase in the exact 8OOX pilot-control family. Its catalogue,
UniProt API, and parsed AFDB mmCIF sequences all had SHA-256
`102e653b2ce68310033502e10e60f54e7cb143dc71acd0e964d0cad47f961964`.

- Minimal live-control accession-map input SHA-256:
  `4527500b2983053d3a815b0e9ee6cc8d12023d68aac637bfa00175cdb724fbd3`.
- AFDB metadata response: HTTP 200, 2,398 bytes, SHA-256
  `76380f83f13c9fbb0abb64348a96ce22a4e1f29c7c629ab58ea38dbe915d3790`.
- Selected model: `AF-A0A832VZP6-F1`, version 6; normalised model key
  `afdb:AF-A0A832VZP6-F1:v6`.
- Reported mean pLDDT: 93.81. This remains predicted-model confidence, not
  experimental validation or a crystallographic score.
- Coordinate response: 426,502-byte mmCIF, SHA-256
  `5555477700990be7f61151911153d5cd6089f6c6bafd0dd5388d0d30ae06738b`.
- Normalised structural-hit output SHA-256:
  `9b6663aac0fa2ac7f90a079a4ce707cb833441c2e100c8edd0a74413119dcef8`.
- Search-manifest SHA-256:
  `0f1d4ca9e282e03e3cabc837f2ff239af0c5f38dbcc9f43ab9b7e2c53ccf969a`.

The reviewed public mapping is tracked at
[`benchmarks/public-controls/afdb_accessions.tsv`](../benchmarks/public-controls/afdb_accessions.tsv).
Its SHA-256 is
`a4c0abc3a6b6efc69a8272c25a724a67c4452c5dc65cef815ecdfb66779c5d1d`.
The live check used a minimal public-control source record; the tracked file
instead binds the deterministic source-record ID from the frozen pilot import,
whose import ID matched the real P1 import exactly. It binds only
`WP_042685700.1` and does not imply a whole-proteome mapping.

This exact mapping is deliberately narrow. The unrelated UniProt proteome
`UP000600363` belongs to MAG assembly `GCA_013330515.1`, not pilot assembly
`GCF_000711905.1`, and must not be used as a whole-catalogue crosswalk.

## What this qualifies

- the current API field names used by adapter version `afdb-exact-v1`;
- accession-only metadata retrieval from an official AFDB host;
- safe advertised-mmCIF download and current AFDB v6 parsing;
- exact source/API/coordinate sequence equality;
- namespaced model identity, checksums, confidence, licence, and cache
  provenance; and
- ordinary successful `completed_hit` semantics.

## Remaining limitations

- Other pilot `WP_...` protein IDs remain `skipped_ineligible` until a
  separately reviewed exact UniProt mapping is supplied; they are not called
  AFDB no-hits. The single qualified cross-reference is not extrapolated to the
  rest of the assembly.
- The provider does not search AFDB by sequence, accept fragments or complexes,
  infer RefSeq-to-UniProt mappings, or use AFDB confidence as proof of the
  crystal identity.
- The fixed Marmic P1 gate still needs this reviewed mapping passed through its
  immutable run inputs and provider-aware evidence union. Optional ESM Atlas is
  a separate policy decision.
