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
| M0.4 Qualify databases | Qualification implementation hardened; real preparation required on Marmic | Anchored full verification, symlink-aware inventories, non-empty known-query smokes, SEQRES target validation, public mmCIF mapping, and atomic coordinate-cache publication are tested; no real site resources have yet passed them |
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

## Database qualification readiness

The M0.4 implementation was audited before any terabyte-scale site download.
The original command construction matched Foldseek's documented
`databases PDB`, `databases ProstT5`, and FASTA-to-PDB search path, but an exit
status of zero alone could previously mark an empty smoke result as passed.
`verify_only` also trusted mutable resource sidecars and did not rerun the
bounded queries.

The hardened boundary now requires all four coupled resources for PDB Foldseek
qualification and provides the following controls:

- a frozen expected database manifest and separately supplied SHA-256 are
  mandatory for `verify_only`;
- content IDs are recomputed, `current` links must resolve to direct resource
  children, internal symlinks are inventoried, and unlisted or escaping paths
  fail;
- protein SEQRES records require a supported target form, declared-length
  agreement, an accepted residue alphabet, and a lossless suffix token; the
  suffix is not silently labelled as an entity or chain namespace;
- MMseqs2 and ProstT5/Foldseek use a fixed public ubiquitin query, require the
  expected `1ubq_A` target at E-value <= `1e-5`, bit score >= `30`, and query and
  target coverage >= `0.90`, and retain checksummed query, result, tool-log, and
  mapping evidence;
- the 1UBQ SEQRES sequence must have the fixed 76-residue query hash; its public
  RCSB mmCIF is parsed by entity, the legacy suffix is resolved through
  `_entity_poly.pdbx_strand_id`, the entity must be a polypeptide, and the
  canonical coordinate sequence hash must match SEQRES;
- that coordinate is published by content hash with atomic replacement,
  immutable content-addressed provenance metadata, a verified digest index, and
  a per-source advisory lock; and
- anchored verification reruns all three bounded operations, compares selected
  identity/score/coverage and output hashes, rechecks the cached coordinate
  without network access, and retains a structured verification sidecar.

All preparation and verification operations using the same database root are
serialised by one advisory exclusive lock under `tmp/locks`. Lock waiting,
acquisition, and release are logged, with bounded terminal progress and a
configurable timeout. The lock prevents two cooperating administrative runs
from racing; it cannot protect against unrelated programs that write into the
database root without taking the same lock.

Incomplete resource staging is retained for diagnosis and blocks a new build of
that resource. No automatic cleanup or second database-sized download is
allowed; recovery or removal is a separate, reviewed administrative action.

The large-build compute-node preflight must complete before a database payload
starts. It requires an explicit scratch directory on a filesystem distinct from
the durable database root, operator-reviewed required capacities for both
filesystems, pinned Foldseek/MMseqs2/aria2 tooling, and dry-run reachability of
the exact Foldseek PDB/ProstT5 and RCSB SEQRES/1UBQ URLs. The resulting JSON
records pass or failure, device and byte measurements, tool versions, fixed
routes, and `large_payload_started: false`. It sends no biological input or
credentials. Generic login-node connectivity is not qualifying evidence.

The public-resource transport boundary is also fail-safe. A partial download is
resumable only when its atomically recorded URL, effective redirect URL,
validator, completed byte count, and prefix SHA-256 all match. Resumed responses
must return the exact requested `Content-Range` and unchanged representation;
otherwise the transfer restarts or fails without promotion. Storage monitoring
uses only explicit active write roots between full start/end reconciliations,
checks filesystem headroom continuously, and terminates the command process
group rather than only its parent. This reduces metadata pressure on Marmic NFS
without weakening the 1.8 TB project cap.

Every anchored verification sidecar now distinguishes
`inventory_metadata_and_functional_smoke` from
`full_checksums_and_functional_smoke` and records the Boolean checksum mode.
The fixed 45-minute P0 job uses only the bounded level. Full-checksum database
qualification remains a distinct long administration gate and must not inherit
the routine `stage`/`submit` approvals.

These are implementation tests, not site qualification. Real M0.4 evidence
still requires one immutable Marmic preparation, the frozen manifest/checksum,
real command logs, full inventory verification, and measured I/O/runtime. The
fixed 45-minute P0 allocation is not yet justified for a bytewise audit on the
observed slow NFS; database qualification and Task 05 should not be conflated
until that timing is measured. Compute-node outbound network access is also
unconfirmed, so the first real preparation must use a reviewed site route or an
offline/adopted snapshot rather than assuming internet access.

The identifier and command assumptions follow the
[RCSB file-download conventions](https://www.rcsb.org/docs/programmatic-access/file-download-services)
and [Foldseek's official documentation](https://github.com/steineggerlab/foldseek).

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
seven-line remote configuration during `stage`, separately binds the frozen
database-manifest SHA-256, refuses a change between staging and execution,
verifies Phenix and performs bounded anchored database revalidation, runs Task 05
for the configured three-crystal manifest, repeats with `-resume`, and fails unless every
deterministic process is reported as cached.

The path file is external to Git and must contain, in order:

1. one canonical allowed site root;
2. catalogue manifest;
3. three-crystal manifest;
4. pipeline configuration;
5. database root;
6. frozen database manifest; and
7. verified Phenix manifest.

Every child path must resolve below the allowed root. Paths must be canonical,
absolute, regular files/directories, contain only conservative path characters,
and use no symlinks. See the
[seven-line example](../conf/hpc-p0.paths.example) and the
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
