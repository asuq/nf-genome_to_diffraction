# M0 real-site qualification status

## Gate summary

M0 is the prerequisite for structural discovery. It qualifies the three pilot
inputs, external Phenix runtime, immutable search databases, Matthews reference,
and fixed Marmic P0 loop. No M1 structural-search work may be interpreted until
this gate passes.

| Work package | Current state | Evidence required to close it |
| --- | --- | --- |
| M0.1 Freeze site inputs | In progress | Local genome/annotation and all three MTZ checksums are frozen; operator-held ground truth and SDS/assumption records remain missing |
| M0.2 Positive control | Blocked on scientific metadata | True catalogue sequence, known ASU copy count, trustworthy final model/structure factors where available, and suitable MR model |
| M0.3 Qualify Phenix | Blocked on licensed runtime | A bounded Marmic inventory found no `phenix.xtriage` command, Phenix module, installer, or non-fixture manifest; a user-supplied Linux installer and checksum are required before command smokes and real Xtriage |
| M0.4 Qualify databases | Preparation required on Marmic | The only discovered provenance record is the foundation stub (`file_count: 0`, `status: incomplete`, smoke not run); immutable Foldseek PDB, ProstT5, PDB-sequence, and coordinate-cache resources still require preparation and verification |
| M0.5 Matthews reference | Pending | Selected pipeline hypotheses compared with Phenix/Xtriage without case-specific tuning |
| M0.6 Fixed HPC P0 profile | Deployed; site configuration missing | Commit `1433006` tools are checksum-verified locally and on Marmic; staging failed safely before submission because the protected external P0 path file is absent |
| M0.7 Three-crystal P0 | Pending | Successful first run, all deterministic processes cached on `-resume`, collected logs/results, and interpreted warnings |

This dashboard describes qualification status, not protein-identification
status. The implemented workflow still ends at Task 05.

## Frozen biological catalogue

- Organism: *Methermicoccus shengliensis* DSM 18856.
- RefSeq assembly: `GCF_000711905.1` (`ASM71190v1`), scaffold level.
- Annotation: `GCF_000711905.1-RS_2025_11_20`, released 20 November 2025.
- Provider/pipeline: NCBI RefSeq, PGAP 6.10.
- Assembly type: haploid.
- Protein-coding gene count in the assembly data report: 1,625.
- Proteome SHA-256:
  `f8bbc63da7b0f3cb5f206befd0618264a5582789f46c3400267650777727d416`.

The corresponding genome FASTA, GFF3, GenBank flat file, NCBI data report, and
NCBI dataset catalogue are also frozen in the ignored local qualification
dossier. Raw inputs and their machine-specific paths are not tracked.

## Three-MTZ preparatory inspection

The checks below used Gemmi only. `xtriage_not_run` is present for every record,
so each outcome is `pass_with_review`, not a clean crystallographic pass.

| Crystal | MTZ SHA-256 | Space group | Unit cell (Å, °) | Resolution (Å) | Reflections | Selected observations | Free-R |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| `AD4QS1P4G2_18` | `535cc0b345903a29828db00444d8496fe678be915b9e1162e3416456ba11e993` | `C 1 2 1` | 94.012, 133.421, 116.838, 90, 97.013, 90 | 1.654 | 169,921 | `IMEAN,SIGIMEAN` | present |
| `CD4QS2P2G1_15` | `bc0d81adb37726203a2cfbf4b4b8fdebc4e1b30c01cf9a112b0b75cbc1f5c642` | `P 21 21 2` | 151.184, 152.460, 149.184, 90, 90, 90 | 1.425 | 635,409 | `IMEAN,SIGIMEAN` | present |
| `CD6QS2P2G1_5` | `5eb16c3cc3a21e4b7f22cd611834529801c1829fc0a3156a2b6abc2b3de2f20d` | `I 1 2 1` | 57.023, 54.964, 124.694, 90, 92.609, 90 | 1.526 | 58,707 | dataset-specific `IMEAN,SIGIMEAN` pair | present |

All files were readable and had one selected intensity/sigma pair. This does not
assess anisotropy, translational NCS, twinning, symmetry alternatives, data
quality, molecular identity, or copy count; real Xtriage remains mandatory.

## Fixed P0 execution boundary

The P0 profile extends the accepted foundation-smoke interface without accepting
an arbitrary path or shell fragment on its command line. It fingerprints a fixed
six-line remote configuration during `stage`, refuses a change between staging
and execution, verifies Phenix and database resources, runs Task 05 for the
configured three-crystal manifest, repeats with `-resume`, and fails unless every
deterministic process is reported as cached.

The path file is external to Git and must contain, in order:

1. one canonical allowed site root;
2. catalogue manifest;
3. three-crystal manifest;
4. pipeline configuration;
5. database root; and
6. verified Phenix manifest.

Every child path must resolve below the allowed root. Paths must be canonical,
absolute, regular files/directories, contain only conservative path characters,
and use no symlinks. See the
[six-line example](../conf/hpc-p0.paths.example) and the
[HPC feedback-loop runbook](hpc-feedback-loop.md#p0-real-site-profile).

The first deployed staging probe used immutable commit `1433006` and was
classified `environment_failure`/`stage_failed`; no scheduler job was submitted.
The failure is qualification evidence that the protected site configuration is
not yet installed, not evidence of a pipeline or scientific failure. A bounded
read-only site inventory also confirmed that the existing pilot and
site-acceptance Phenix/database manifests are fixtures. They must not be used to
satisfy this gate.

## Operator-held evidence still required

For at least one positive-control crystal, provide outside pipeline-visible blind
inputs:

- true catalogue protein/sequence-group identity;
- expected ASU copy count and evidence for it;
- trusted final model and structure factors, if they exist;
- a suitable MR model and its relationship to the target;
- SDS-PAGE apparent mass/conditions, or an explicit statement that no SDS
  evidence exists; and
- whether the case is expected to satisfy the prototype assumption `ASU = nA`.

Equivalent records are required for the other two crystals when known. Missing
evidence must remain `unknown`; filenames and Matthews priors must not be used to
invent ground truth.
