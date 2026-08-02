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
| M0.3 Qualify Phenix | Local runtime and three real Xtriage smokes qualified; Marmic installation in progress | Phenix 2.1-6048 macOS arm64 passes all seven command probes and all three frozen MTZ files complete real Xtriage; the durable Marmic Linux installation, its real manifest, and equivalent Marmic results are still required |
| M0.4 Qualify databases | Preparation required on Marmic | The only discovered provenance record is the foundation stub (`file_count: 0`, `status: incomplete`, smoke not run); immutable Foldseek PDB, ProstT5, PDB-sequence, and coordinate-cache resources still require preparation and verification |
| M0.5 Matthews reference | Pending | Selected pipeline hypotheses compared with Phenix/Xtriage without case-specific tuning |
| M0.6 Fixed HPC P0 profile | Deployed; site configuration missing | Commit `1433006` tools are checksum-verified locally and on Marmic; staging failed safely before submission because the protected external P0 path file is absent |
| M0.7 Three-crystal P0 | Local Xtriage evidence available; Marmic P0 pending | Successful scheduled first run, all deterministic processes cached on `-resume`, collected logs/results, and interpreted warnings |

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

## Verified Phenix installer transfer

The user supplied the Phenix 2.1-6048 Linux x86-64 self-extracting installer.
The local and Marmic-staged copies are both 3,610,320,749 bytes and have
SHA-256
`a2455e281f11241debdb25d9788ada8337420b9ff4c92935f97157f0cc9b9795`.
This proves transfer integrity only. The staged copy is on ephemeral,
login-node-local memory storage and is not visible to Slurm compute nodes. A
batch installation to a durable, versioned Marmic prefix was subsequently
started. At the latest bounded observation it was still extracting files, so no
Marmic command, manifest, or real Xtriage result is yet qualified. The
current-runtime link must not be updated until repository verification passes.

## Local Phenix verifier qualification

The separately supplied Phenix 2.1-6048 macOS arm64 installer is 3,531,737,697
bytes with SHA-256
`e4082d63609cf08ce3f1a72f4d498749b86e7f04ef9dbaa70278cc94ed48eebd`.
Installation to a per-user, versioned prefix completed in 12 minutes 34 seconds
and occupied approximately 12.35 GiB.

The first verification exposed a real command-interface convention: in this
release, `phenix.xtriage`, `phenix.phaser`, and `phenix.maps` print valid help
but return exit status 1. The verifier now accepts that status only when the
specific command's expected help signature is present, while still rejecting
tracebacks, import failures, dynamic-loader failures, and missing signatures.
The other four required commands must return zero.

The installer-preserved tree was recovered without reinstalling, using the
immutable failed-manifest SHA-256 and recovery implementation revision
`688e3b64a7671fae63fc5f6e54cbd99537119785`. The resulting manifest records
Phenix `2.1-6048`, a verified environment checksum, and seven passed command
checks. An independent second verification also passed all seven commands. The
stable link was published only after success, and the failed manifest remained
byte-identical.

This qualifies the installer/verifier boundary on macOS arm64. It does not
qualify the Marmic Linux runtime, prove that a real MTZ can be analysed, or
close M0.3.

## Local three-MTZ Xtriage qualification

All three frozen MTZ files completed real `phenix.xtriage` through the verified
macOS manifest at repository revision
`71a549af65ea5b01fca0661999e0bbac958be8ec`. Every file retained its selected
intensity/sigma pair and existing Free-R column. The generated JSONL records
were independently revalidated with the typed `MtzPreflightRecord` contract.

| Crystal | Decision | Selected reflections / MTZ rows | Completeness | Mean I/sigma | TNCS | Twinning | Symmetry | Review warnings |
| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |
| `AD4QS1P4G2_18` | `pass_with_review` | 127,776 / 169,921 | 75.1553% | 12.4 | Not detected | Not detected | Not assessed | Completeness below 90%; Patterson peak review |
| `CD4QS2P2G1_15` | `pass_with_review` | 532,346 / 635,409 | 83.7033% | 7.9 | Not detected | Not detected | Not detected | Completeness below 90%; direction-dependent resolution limit |
| `CD6QS2P2G1_5` | `pass` | 57,222 / 58,707 | 97.4589% | 9.9 | Not detected | Not detected | Not detected | None from the conservative automated rules |

Xtriage's selected-observation low-resolution limit differs from the MTZ-wide
row limit for `CD4QS2P2G1_15` (107.352 versus 149.184 A) and
`CD6QS2P2G1_5` (39.553 versus 62.283 A). Both values and both row counts are
reported; neither is silently substituted for the other.

For `AD4QS1P4G2_18`, the final Xtriage verdict says no significant
pseudotranslation, while the off-origin Patterson peak is 19.179% with
p-value 0.01151. Because Xtriage notes that values below 0.05 may indicate weak
pseudotranslation or an anomalous-scatterer self-vector, this is a review
warning rather than a positive TNCS classification. `CD4QS2P2G1_15` has an
explicit direction-dependent resolution-limit warning. `CD6QS2P2G1_5` has an
outer-shell anisotropy-noise Z value of 9.95, but the command-line report does
not emit Phenix's explicit anisotropy issue classification; the status remains
`not_assessed` and the quantitative value is retained for expert review.

The result JSONL and Markdown report have SHA-256 values
`3832a12d9fbe72400f93157b013ae2cf3acf3a8793d45a67755fc9af2f5331e5`
and
`0b3b78bb0db07a910b65798d0075d8d41f4316360cf13283012421834eb9f5e0`,
respectively. Raw MTZ paths, licensed-software logs, and exact local output
paths remain outside Git. These local results demonstrate real execution and
parser behaviour; M0.3 still requires the Marmic Linux manifest and scheduled
P0 evidence.

## Marmic NFS installation diagnosis

A bounded, read-only snapshot was taken while the Linux installer was spending
hours in package extraction. The destination was an NFSv4.0 hard TCP mount with
32 KiB read/write request sizes and no pNFS. CPU, memory, free space, inode
capacity, and the client network interface were not saturated. Three extractor
workers were instead blocked in uninterruptible `rpc_wait_bit_killable` state.

During a 10-second sample, approximate average NFS operation latencies were
263 ms for reads, 56 ms for writes, 62 ms for opens, 31 ms for creates, and
15--28 ms for common metadata operations. There were no new RPC retransmissions
or interface errors in that sample. The high-confidence operational diagnosis
is server-side storage/metadata latency or export contention, exacerbated by a
small-file-heavy installation. The mount's NFS version and 32 KiB request size
may amplify the effect but are site-administrator decisions, not repository
settings.

For future large software installations, ask the Marmic administrators for the
site-approved software filesystem and whether the current NFS export settings
are intentional. A single-file container or image may reduce metadata pressure
only if site policy and the Phenix licence permit it. Do not copy or relocate an
installed Phenix prefix blindly because its environment can contain embedded
absolute paths.

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
