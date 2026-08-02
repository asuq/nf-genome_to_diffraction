# Initial Marmic prototype test report

## Scope

This report records the real Task 05 prototype test completed on Marmic on
2 August 2026. It covers trusted catalogue import, independent MTZ preflight,
candidate-specific Matthews enumeration, publication, and Nextflow resume. It is
not a protein-identification result.

The tested code was commit `d920efb` (`fix(catalogue): preserve compound and
multi-locus CDS`). The runtime used Python 3.14.6, Nextflow 26.04.6, Java 21, and
Pixi 0.74.0 from the locked Linux `hpc` environment. The `marmic` profile came
from the pinned `external/nf-helper` submodule.

## Inputs and controls

- Organism: *Methermicoccus shengliensis*.
- Assembly: RefSeq `GCF_000711905.1` (`ASM71190v1`).
- Crystal dataset identifier: `CD6QS2P2G1_5`.
- MTZ SHA-256:
  `5eb16c3cc3a21e4b7f22cd611834529801c1829fc0a3156a2b6abc2b3de2f20d`.
- Observation labels:
  `IMEAN_Msheng_CD6QS2P2G1_5,SIGIMEAN_Msheng_CD6QS2P2G1_5`.
- Free-R label: `FreeR_flag`.
- Review mode: `prepare`; execution profile mode: `pilot`.
- Xtriage was deliberately skipped because a verified real Phenix installation
  was not available to this run.
- Repository fixture manifests were used to exercise the prepared-database and
  Phenix contract boundaries. No structural search or Phenix command consumed
  those fixtures.

The public genome and annotation checksums and the MTZ checksum were verified
before execution. Raw inputs and generated results remain outside Git.

## Execution history

The initial driver job `624608` failed loudly during catalogue import while the
input-contract and MTZ-preflight processes completed. The failure was:

```text
genomic.gff: conflicting locus records for 'WP_157203009.1'
```

Inspection showed this was a valid biological annotation pattern rather than a
corrupt record. After the catalogue adapter fix:

- driver job `624612` resumed the same output directory and Nextflow cache;
- input validation and MTZ preflight were reused from cache;
- catalogue-import job `624613` completed in 5 seconds;
- Matthews-enumeration job `624614` completed in 7 seconds;
- the driver completed in 1 minute 55 seconds with 287 MB peak RSS; and
- a second driver, job `624615`, completed in 50 seconds and reported all four
  processes as cached.

No work directory or partial result was deleted between failure and resume.

## Annotation findings

RefSeq protein accessions are not guaranteed to map one-to-one to genomic CDS
loci. Three repeated protein identifiers were present in the supplied GFF:

- `WP_157203009.1` is one programmed-frameshift CDS represented by two segments
  at the same locus (`BP07_RS08515`). GenBank represents the same feature as a
  compound `join` on the reverse strand. The compatible segments must be merged,
  not treated as conflicting loci.
- `WP_042684251.1` occurs at four distinct compatible loci.
- `WP_052353039.1` occurs at two distinct compatible loci.

The importer now groups compound GFF rows using stable feature/locus identity,
checks contig, strand, locus tag, gene, and product compatibility, and merges the
coordinate span. True conflicts still fail loudly. Distinct loci sharing one
protein accession produce separate source records linked to the same exact
sequence group.

GenBank line wrapping also introduced whitespace after a hyphen in one product
description. Annotation prose is now normalised for whitespace and line-wrap
hyphenation before GFF/GenBank compatibility checks; biological identifiers and
coordinates are not normalised this way.

The resulting catalogue contained:

- 1,621 input FASTA protein records;
- 1,625 source-locus records;
- 1,621 exact sequence groups; and
- 1,620 sequences eligible for the search FASTA.

Quality flags were preserved in the outputs: one source record had
`compound_cds_segments_merged`, six had `multiple_compatible_loci`, and one had
`excluded_below_minimum_length`. These are diagnostic states, not evidence of a
protein identity.

## MTZ preflight findings

Gemmi independently obtained:

- decision `pass_with_review` and execution status `completed_warning`;
- space group `I 1 2 1`, with general-position multiplicity 4;
- unit cell `57.023, 54.964, 124.6943, 90, 92.6089, 90`;
- cell volume 390,413.314 A^3 and ASU volume 97,603.328 A^3;
- resolution range 62.283-1.526 A;
- 58,707 reflections;
- selected mean-intensity/sigma observations; and
- an existing `FreeR_flag` column.

The only warning was `xtriage_not_run`. Completeness, mean I/sigma, anisotropy,
translational NCS, twinning, and symmetry diagnostics therefore remain
unassessed. A real Phenix/Xtriage run is required before treating the preflight as
a clean crystallographic pass.

## Matthews enumeration findings

Sixteen copy counts were evaluated for each of the 1,620 eligible exact sequence
groups, yielding 25,920 hypotheses. Cross-format counts were:

| Status | Hypotheses |
| --- | ---: |
| Physically plausible | 4,413 |
| Requires review | 506 |
| Physically impossible | 21,001 |
| Retained for downstream use | 4,860 |
| Total | 25,920 |

All 25,920 hypotheses had SDS-PAGE status `unavailable`; no apparent-mass band
was supplied for this test. The ranking backend was
`broad_solvent_centrality_v1_uncalibrated`. Its values are transparent physical
priors, not calibrated probabilities or protein-identification evidence.

## Acceptance evidence

- All 1,625 source-protein, 1,621 sequence-group, 1 MTZ-preflight, and 25,920
  Matthews JSONL records passed their Pydantic contracts.
- JSONL, TSV, and Parquet row counts agreed for every tabular output.
- The search FASTA contained 1,620 records.
- Nextflow published report, timeline, trace, and DAG artefacts.
- The final scope record was
  `task05_preflight_complete_downstream_deferred`.
- Local validation passed Ruff formatting and linting, strict mypy, 115 pytest
  tests, Nextflow parser checks, and both stub entry points.

## Interpretation and next work

This pilot demonstrates that the implemented Task 04/05 boundary runs on the
Marmic Slurm site, preserves difficult RefSeq locus semantics, publishes typed
outputs, and resumes correctly. It does not identify the crystal protein.

The next scientifically meaningful validation steps are a verified real
Phenix/Xtriage preflight, inclusion of documented SDS-PAGE evidence when
available, preparation and verification of the real structural-search databases,
and implementation of the deferred structural-search and molecular-replacement
stages. The direct PDB search backend and primary HPC container pattern remain
explicit future decisions.

See the [Marmic prototype runbook](marmic-prototype-runbook.md) for the
reproducible operating procedure.
