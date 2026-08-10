# P1 exact AlphaFold DB provider qualification

## Result

The T7.4 exact-accession provider passed a live public-control retrieval on
10 August 2026. It produced one `completed_hit` result and one immutable
coordinate-source record for UniProt `P69905` without submitting an amino-acid
sequence to a remote service.

This is an adapter/service-contract qualification, not evidence about the
`Methermicoccus shengliensis` pilot and not a protein-identification result.

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

## What this qualifies

- the current API field names used by adapter version `afdb-exact-v1`;
- accession-only metadata retrieval from an official AFDB host;
- safe advertised-mmCIF download and current AFDB v6 parsing;
- exact source/API/coordinate sequence equality;
- namespaced model identity, checksums, confidence, licence, and cache
  provenance; and
- ordinary successful `completed_hit` semantics.

## Remaining limitations

- The pilot RefSeq catalogue is expected to contain `WP_...` protein IDs. These
  are intentionally `skipped_ineligible` until a separately reviewed exact
  UniProt mapping TSV is supplied; they are not called AFDB no-hits.
- The provider does not search AFDB by sequence, accept fragments or complexes,
  infer RefSeq-to-UniProt mappings, or use AFDB confidence as proof of the
  crystal identity.
- The fixed Marmic P1 gate still needs provider-aware evidence union and a
  mapped pilot/prokaryotic accession if one is available. Optional ESM Atlas is
  a separate policy decision.
