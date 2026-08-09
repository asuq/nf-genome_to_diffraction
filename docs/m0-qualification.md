# M0 real-site qualification status

## Gate summary

M0 is the prerequisite for structural discovery. It qualifies the three pilot
inputs, external Phenix runtime, immutable search databases, Matthews reference,
and fixed Marmic P0 loop. No M1 structural-search work may be interpreted until
this gate passes.

| Work package | Current state | Evidence required to close it |
| --- | --- | --- |
| M0.1 Freeze site inputs | In progress | Local genome/annotation and all three MTZ checksums are frozen; operator-held ground truth and SDS/assumption records remain missing |
| M0.2 Positive control | Qualified with the public same-organism 8OOX control | Offline revalidation and real local Task 05 bind the exact RefSeq sequence, known two-copy ASU, deposited model/structure factors, and exact plus homolog MR models; the copy-two hypothesis is retained without changing the ranking heuristic, and this does not identify any blind pilot crystal |
| M0.3 Qualify Phenix | Local and Marmic runtimes qualified; three real Xtriage smokes qualified locally | Phenix 2.1-6048 passes all seven command probes on macOS arm64 and Marmic Linux x86-64; all three frozen MTZ files complete local real Xtriage, while equivalent Marmic real-MTZ and scheduled P0 evidence remain required |
| M0.4 Qualify databases | Revised boundary passed real PDB build/copy-back; SEQRES case-semantics fix locally qualified and retry pending | The 100-CPU `/dev/shm` build published PDB Foldseek after full destination checksums, then exposed a valid upper/lower-case chain pair in the frozen RCSB snapshot; the corrected parser preserves both, but no real site manifest has yet passed the complete gate |
| M0.5 Matthews reference | Local method matrix and positive-control retention qualified; site parity follows M0.3 | Eleven real comparisons cover all frozen MTZs, the 8OOX ground-truth sequence, and multiple copy regimes; blind-pilot identity/copy interpretation remains separate |
| M0.6 Fixed HPC P0 profile | Current local controller and Marmic dispatcher installed; create-only configuration boundary qualified | The bounded readiness interface verifies Pixi 0.74.0 and can atomically validate/install the protected seven-line file, but the real external P0 configuration is still absent; no P0 run has been staged or submitted |
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

## Public same-organism positive control

The operational M0.2 positive control is PDB 8OOX, a type I glutamine
synthetase from *M. shengliensis* DSM 18856. It uses the same frozen
`GCF_000711905.1` RefSeq proteome as the pilot catalogue and binds target
`WP_042685700.1` to the full-length 442-residue coordinate sequence with exact
sequence SHA-256
`102e653b2ce68310033502e10e60f54e7cb143dc71acd0e964d0cad47f961964`.
The crystallographic ground truth is a single protein species with two copies
in the asymmetric unit; the biological dodecamer is recorded separately and is
not substituted for the ASU copy count.

The checksum-frozen public sources include deposited target coordinates and
structure factors, an exact-family MR model, and a homolog MR model. The
derived autoPROC-labelled MTZ has SHA-256
`f72540f651191b00986b0dbca881156c863dc794a0ac3520ced14d092500804d`.
An offline preparation rerun on 9 August 2026 reused and revalidated every
source, exact catalogue mapping, derived MTZ, and both MR models without network
access. Its ignored preparation manifest has SHA-256
`f4d7be0b68e68c130973975fa8f2298e6a17cb4d432c165c02280195cec0861a`.

Real local Task 05 then imported the complete same-assembly RefSeq proteome and
ran Phenix 2.1-6048 Xtriage on the deposited autoPROC-labelled MTZ. The exact
target group retained the known two-copy hypothesis at rank four, with
`V_M = 4.8855` Å³/Da and solvent fraction `0.7482`. A separate fixed
`mmtbx.matthews` run also ranked two copies fourth (`V_M = 4.87`, solvent
fraction `0.747`, printed probability `0.050`). The pilot retention cap was
therefore raised from three to four: this is the smallest bounded execution cap
that preserves the control under both independent orderings, not a fitted
probability and not a change to `broad_solvent_centrality_v1_uncalibrated`.

The Task 05 preflight, catalogue-import manifest, Matthews JSONL, and Phenix
comparison have SHA-256 values
`8a62f756466bac1259756e02605e899413f69b4336e6b75583c89f050a079507`,
`44cfa1e9e07e4e9db91f2516049d274d20149ef84e92da8dde0b2ff92f9b3919`,
`d80cc97593a7a996a663de9cbd061b77cc38155267407fa4da60d3e0711deb9b`,
and
`3f206203097ee60ff7041a6027c54ac7eceeddd1816cac33a58a2dab5cdfa934`,
respectively. An identical `-resume` execution reported validation, catalogue
import, MTZ preflight, and Matthews enumeration as cached. The run used the
schema-valid foundation database fixture because Tasks 04/05 validate but do
not consume structural-search databases; it is not evidence for M0.4.

This closes the operational-control requirement, not the blind-pilot identity
requirement. The three operator pilot identities, copy counts, and `ASU = nA`
statuses remain `unknown` until independent evidence is supplied. The control's
deposited target coordinates are used only for evaluation; its exact MR model is
an intentional non-blind execution control and its homolog model supports the
later leakage-controlled challenge.

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
The local and checksum-gated Marmic copies were both 3,610,320,749 bytes and had
SHA-256
`a2455e281f11241debdb25d9788ada8337420b9ff4c92935f97157f0cc9b9795`.
The installer was staged only on login-node-local `/tmp`; it was not exposed to
Slurm compute nodes or committed to Git.

The official batch installer completed on 8 August 2026 in a durable canonical
versioned prefix without a mutable current-runtime link. The resulting manifest
has status `verified`, records Phenix `2.1-6048`, Linux x86-64, glibc 2.39, the
installer checksum above, environment SHA-256
`9b52b63861b3a6bc1f762f605f933545a7c5179ed6552082da92884dab70539f`, and seven
passed required-command probes. Its SHA-256 is
`50a0a6dd90194c6bac5739de64a359ed4340cc7b1b2fc17dbb61cb774718f5be`.
An independent manifest-based verification at repository revision
`aa113770fb661a22b22310335edfdad4e52df0cc` passed the same seven probes. Exact
site paths, licensed installer contents, and logs remain outside Git.

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

This qualifies the installer/verifier boundary on macOS arm64. The independent
Marmic verification recorded above also qualifies the Linux x86-64 runtime. The
help-mode probes do not prove that a real MTZ can be analysed on Marmic and do
not by themselves close M0.3.

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
parser behaviour; the Marmic Linux manifest is now qualified, while equivalent
Marmic real-MTZ execution and scheduled P0 evidence remain required.

## Local Matthews method-reference probe

The fixed `matthews reference-check` boundary was exercised with local Phenix
2.1-6048 and the frozen `CD6QS2P2G1_5` MTZ. The selected catalogue group was the
lexicographically first exact, unflagged 357-residue sequence group. That rule
was deterministic and declared before comparison; it is not an assertion that
this sequence is the crystallised protein. The report therefore remains a
method probe, not a positive control.

The command resolved only `mmtbx.matthews` inside the verified Phenix prefix,
verified its `n_residues` help signature, and ran the fixed MTZ plus
`n_residues=357` interface. The executable SHA-256 is
`07227a24698efba3ff11788c4a86d43a1d320e5630836fdd45f00286c6472412`;
the frozen MTZ and sequence digests are
`5eb16c3cc3a21e4b7f22cd611834529801c1829fc0a3156a2b6abc2b3de2f20d`
and
`0f0a48c7d67076d2aa2d875cb70e2836f2769b3f91095ea1a787e4c2d1ee5858`.
Machine-specific paths and the licensed-tool log remain in the ignored local
qualification dossier.

| Quantity | Phenix residue-count reference | Pipeline exact sequence mass |
| --- | ---: | ---: |
| ASU volume (Å³) | Same frozen preflight geometry | 97,603.3285 |
| Selected monomer mass (Da) | 40,165.9788 implied by printed `V_M` | 40,457.5391 |
| Plausible copy counts | 1 | 1 |
| Best/first copy count | 1 | 1 |
| `V_M` at one copy | 2.4300 | 2.4125 |
| Solvent fraction at one copy | 0.4940 | 0.4902 |

The implied-mass difference was 0.7259%, the absolute `V_M` difference was
0.0175, and the solvent-fraction difference was 0.00385. All three disclosed
method-compatibility checks passed under the predeclared 5% average-residue
versus exact-composition engineering bound. That bound is not an empirical
probability and was not fitted to this case. The comparison ID is
`mref_f8bd340894e14d32bd829221e05fbb4df9dfb89b92cf9db4068b762f85a64e0c`.

### Predeclared percentile matrix

Before inspecting any additional Phenix result, the exact-mass, unflagged
catalogue groups were sorted by `(length_aa, sequence_group_id)`. Nearest-rank
10th, 50th, and 90th percentiles were selected from 1,617 eligible groups, then
the same three groups were tested against every frozen MTZ. This rule samples
different mass and copy regimes without choosing sequences to make a result
pass.

| Probe | Sequence digest | Length (aa) | Exact mass (Da) |
| --- | --- | ---: | ---: |
| P10 | `5189c15a4848afc461ca0b66522ac6cac431dd64aa37e724208c75e9b19d588d` | 88 | 10,028.5485 |
| P50 | `20046deaac838f77d743fd57625f1ce68a3162f9b6693496dcabdf24711adcbd` | 249 | 29,366.2533 |
| P90 | `59e1cf3e41e952e65ce4d1658c83760064430446c11e9db53b7460effb4c4432` | 497 | 53,337.9635 |

| Crystal | Probe | Status | Copy sets | Ordering | Maximum mass-model difference |
| --- | --- | --- | --- | --- | ---: |
| `AD4QS1P4G2_18` | P10 | `passed_with_review` | Match | Differ | 1.4882% |
| `AD4QS1P4G2_18` | P50 | `passed` | Match | Match | 4.9837% |
| `AD4QS1P4G2_18` | P90 | `passed` | Match | Match | 4.6590% |
| `CD4QS2P2G1_15` | P10 | `passed_with_review` | Phenix 8--16; pipeline 7--16 | Differ | 1.3524% |
| `CD4QS2P2G1_15` | P50 | `passed_with_review` | Match | Differ | 5.0436% |
| `CD4QS2P2G1_15` | P90 | `passed_with_review` | Match | Differ | 4.6976% |
| `CD6QS2P2G1_5` | P10 | `passed_with_review` | Match | Differ | 1.4123% |
| `CD6QS2P2G1_5` | P50 | `passed` | Match | Match | 4.7040% |
| `CD6QS2P2G1_5` | P90 | `passed` | Match | Match | 4.3665% |

All nine commands completed, all printed Phenix rows satisfied the Matthews
coefficient/solvent relation within declared rounding tolerance, and every
pipeline row satisfied the exact-mass formula. Four comparisons passed all
method checks. Five retained review differences: empirical Phenix probability
ordering differed from the intentionally uncalibrated broad pipeline prior;
the small `CD4QS2P2G1_15` probe placed one boundary copy differently and its
Phenix best guess of 36 copies was outside the configured pipeline cap of 16;
and its P50 mass-model difference was 5.0436%, slightly beyond the fixed 5%
engineering bound. None of these observations was tuned away.

The first matrix run also exposed a real parser error. Phenix printed identical
maximum probabilities of 0.055 for 35 and 36 copies while reporting 36 from its
unrounded internal values. The parser now accepts the reported best guess when
it is among the maximum printed-probability ties, but still rejects a genuinely
lower printed probability. Reference plausibility is compared only after
applying the same configured solvent-fraction bounds as the pipeline; raw
Phenix tables may intentionally include physically extreme rows.

This locally satisfies the M0.5 software-method comparison without calibrating
the current prior. It does not close M0 overall: the selected groups are method
probes, not asserted crystal identities, and the true positive-control sequence
and ASU copy count remain blocked on operator-held M0.2 evidence. Site parity
also depends on completion of the Marmic Phenix qualification in M0.3. No
scientific identity or copy-count conclusion may be inferred from this matrix.

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
starts. The fixed Marmic driver requires a unique job-owned mode-0700 directory
below compute-node `/dev/shm`, on a filesystem distinct from the durable database
root.
It also requires operator-reviewed capacities for both filesystems, pinned
Foldseek/MMseqs2/aria2 tooling. Without a staged source bundle it also requires
bounded one-byte HTTPS reachability of the exact Foldseek PDB/ProstT5 and RCSB
SEQRES/1UBQ URLs; with the fixed source bundle it instead verifies every local
object by full SHA-256 and performs no compute-node network request. The
resulting JSON records pass or failure, device and byte measurements, tool
versions, fixed routes, redirect targets, representation sizes, validators, and
`large_payload_started: false`. It sends no biological input or credentials.
Generic login-node connectivity is not qualifying evidence.

Foldseek download targets, the downloader's tmp argument, inherited `TMPDIR`,
MMseqs2 databases, and index workspace remain inside a resource build directory
below that job-owned `/dev/shm` tree. The command watchdog measures durable and
scratch roots, counts both towards the same project cap, logs usage and free
space, and terminates the complete process group on either headroom violation.
After a scratch resource is inventoried, one progress-logged copy is written to
empty durable staging and fully rehashed there before atomic publication. A
failed copy retains durable staging for review; only the exact job-owned scratch
tree is removed automatically.

The public-resource transport boundary is also fail-safe. A partial download is
resumable only when its atomically recorded URL, effective redirect URL,
validator, completed byte count, and prefix SHA-256 all match. Resumed responses
must return the exact requested `Content-Range` and unchanged representation;
otherwise the transfer restarts or fails without promotion. Storage monitoring
uses only explicit active write roots between full start/end reconciliations,
checks durable and scratch filesystem headroom continuously, and terminates the
command process group rather than only its parent. This reduces metadata
pressure on Marmic NFS without weakening the configured project cap.

Foldseek's retained PDB version file is now parsed fail-loudly rather than being
treated as an opaque inventory member. The database resource records its PDB
snapshot date, provider archive MD5, exact Foldseek database-generation commit,
and version-file SHA-256. The provider MD5 is provenance, not the repository's
trust anchor; immutable identity still comes from the full deployed-file
inventory and its SHA-256.

Every anchored verification sidecar now distinguishes
`inventory_metadata_and_functional_smoke` from
`full_checksums_and_functional_smoke` and records the Boolean checksum mode.
The fixed 45-minute P0 job uses only the bounded level. Full-checksum database
qualification now has distinct `database-stage`/`database-submit` commands, a
fingerprinted external configuration, and a fixed 48-hour Slurm allocation. It
remains a long administration gate and does not inherit the routine
`stage`/`submit` approvals.

These are implementation tests, not site qualification. Real M0.4 evidence
still requires one immutable Marmic preparation, the frozen manifest/checksum,
real command logs, full inventory verification, and measured I/O/runtime. The
fixed 45-minute P0 allocation is not yet justified for a bytewise audit on the
observed slow NFS; database qualification and Task 05 should not be conflated
until that timing is measured. Marmic compute nodes have now been shown not to
reach the first pinned Foldseek HTTPS route, so real preparation must use the
login-node source bundle described below rather than assuming compute-node
internet access.

On 9 August 2026, the deployed fixed `database-readiness` operation reached
Marmic and verified PATH-installed Pixi 0.74.0. It reported the protected
seven-line database-administration configuration as absent or unsafe. This
operation created no run, submitted no job, and returned no site paths. A
separate bounded read-only filesystem observation found
`1,132,247,285,760` bytes free on the proposed durable filesystem and no
existing project database-administration root. The site does not provide the
standard `quota` command, so no user-specific 2 TB quota was independently
observable. With the reviewed first-run values of 1.6 TB required build
capacity and a 0.2 TB durable reserve, only `932,247,285,760` bytes would be
available to the preflight. At that observation the configuration therefore
remained absent pending either increased capacity or an operator-approved
smaller measurement gate. The gate was not weakened merely to make readiness
pass.

The same day, capped one-byte ranged GET probes verified that the three fixed
public payload routes were live without downloading database content. The
Foldseek worker redirected PDB100 and ProstT5 to its S3 store and advertised
compressed representation sizes of `2,326,827,389` and `2,224,976,412` bytes,
respectively; the RCSB SEQRES representation was `66,084,235` bytes. The pinned
PDB version record was 121 bytes. The Foldseek worker returned 404 for HEAD but
206 for ranged GET, so HEAD is not a valid reachability test for these routes.
An exact aria2 1.37.0 `--dry-run=true` reproduction failed on the same HEAD-like
behaviour even though normal GET redirected successfully. The implementation
therefore requires the pinned aria2 executable but uses a strictly bounded
one-byte GET for route preflight. The small 1UBQ coordinate route currently
ignores Range and does not declare a body length; the client accepts that route
only by reading one byte and immediately closing the streaming response. Its
representation size is therefore recorded as unknown rather than inferred.
These compressed sizes do not bound extracted databases, MMseqs2 indices,
simultaneous staging, retained failed staging, or scratch use, and therefore do
not by themselves justify reducing the capacity gate. Compute-node reachability
still requires the fixed preflight.

After operator review, the first measurement build used an 800 GB project cap,
a 200 GB durable reserve, a 600 GB pre-download capacity gate, and a 200 GB
scratch reserve on the filesystem with approximately 1.13 TB free. Login-node
readiness passed and immutable commit `d41cbcf658a8e29d184d44cc50c7a7171a62feb1`
was staged. Slurm job `625468` reached a compute node but failed during the
environment phase because Marmic did not export `SLURM_TMPDIR`. No compute-node
preflight or database payload started, no durable database resource staging was
created, and scratch cleanup succeeded.

The pinned `nf-helper` Marmic profile and the checked copies used by
`nf-annotation`, `nf-busco_phylogenomics`, and `nf-sra_screen` consistently set
Nextflow scratch to `/scratch/$USER`. Their Marmic profile content has SHA-256
`943b4ea330073c073f8518ff940ae0c8b21bc749f26f2360fadc3675ef6e6a90`.
The fixed database job at that revision therefore used a job-owned mode-0700
child below that site root when `SLURM_TMPDIR` was absent, while preserving its
then-current distinct-device, ownership, symlink, `/dev/shm`, and capacity
checks.

Retry job `625471` then selected the job-owned scratch path successfully and
reached Pixi setup. It failed before preflight because the compute node could
not connect to the locked Conda package route after three retries (`Address not
available`). Again, no database payload or durable resource staging started and
scratch cleanup succeeded. The fixed staging operation now materialises the
per-run frozen `hpc` environment on the network-capable login node; the compute
job performs an offline Pixi verification before using its executables. This
preserves the exact commit/lock binding without assuming compute-node internet
access.

Revision `5b2c9f9ef75bfa5831c0abab153a17d34d3db04e` and Slurm job `625515`
confirmed that hand-off: `/scratch/$USER` selection and offline Pixi
verification passed, and the capped durable root reported
`1,043,877,462,016` filesystem-free bytes with no project content yet. Preflight
then failed before route probes or payload creation because the generic
`foldseek --version` probe did not terminate within 30 seconds. Foldseek and
MMseqs2 document `foldseek version` and `mmseqs version`; the implementation now
uses those explicit subcommands while retaining `aria2c --version`. Timeout and
execution errors are converted to actionable database errors. Scratch cleanup
succeeded, and no durable resource staging was created.

The corrected Python probe subsequently completed against all five fixed routes
from the local development environment. It recorded the two Foldseek archives,
PDB version file, and SEQRES file as ranged responses with their effective URLs,
sizes, validators, and one-byte sample SHA-256 values; 1UBQ was the bounded
unknown-size HTTP-200 case. This qualified the adapter but did not establish
Marmic compute-node egress.

Revision `4f7017b9f6b38bd3055cb4bc82524760549b9324` and Slurm job `625516`
then passed scratch selection, offline Pixi verification, the Foldseek/MMseqs2/
aria2 version probes, and both capacity gates. The durable filesystem reported
`1,043,691,012,096` free bytes before project content. The first pinned PDB100
HTTPS request failed with `Errno 99` (`Cannot assign requested address`). No
database payload or durable resource staging was created, and scratch cleanup
succeeded. This is direct evidence that the database compute job must not depend
on outbound HTTPS.

The fixed driver now materialises five immutable inputs on the login node:
PDB100, its version record, ProstT5 weights, RCSB PDB SEQRES, and the 1UBQ
coordinate positive control. Downloads go sequentially and directly to the
durable database root, are resumable with strong validators, and are recorded by
full SHA-256 in a content-addressed bundle. The Slurm preflight fully verifies
that bundle without network access. Foldseek receives only local bundle files
through an exact-URL allow-listing adapter. The current driver builds extraction,
database, and indexing output in job-owned `/dev/shm`, then performs one verified
copy to durable staging. Interrupted source transfer resumes automatically. A
failed durable copy/extraction staging directory is retained and requires
operator review before another build.

The first complete login-node stage for revision
`61bbb2cf69ba678588e8167eb23df094699aade6` ran from 11:12:23 to 11:42:25 UTC.
It wrote and fully checksummed `4,617,920,618` bytes under the 800 GB project
cap. PDB100 was the slow route: its first and second GiB milestones took about
704 and 817 seconds; ProstT5 reached its first GiB in about 67 seconds. Slurm
job `625517` then verified the offline Pixi environment and measured
`795,382,079,382` bytes available under the cap with `1,038,909,472,768`
filesystem-free bytes. It failed before source checksum verification or
extraction because NFS-cold `foldseek version` startup exceeded the generic
30-second tool probe limit. The job recorded `environment_failure`, created no
database resource staging, and removed its job-owned scratch successfully.
Because the same corrected command passed in job `625516`, this is treated as
an intermittent NFS-startup limit rather than a command mismatch. Database tool
version probes now have a fixed 180-second bound and log start/completion plus
elapsed time; the immutable source bundle is reused rather than downloaded
again.

Revision `b0e86cb8e9e32dcce218666f7e3831c480fa0eda` and Slurm job `625518`
passed offline Pixi verification, all three version probes, both capacity gates,
and full checksums for the `4,617,920,618`-byte source bundle. Foldseek then
failed while preparing ProstT5. Its command log showed that the first adapter
rewrote the fixed URL to `file://`; Foldseek's aria2 backend rejected that
protocol and its fallback chain invoked real `curl` and `wget`, which could not
reach the public host from the compute node. The incomplete ProstT5 staging was
retained and scratch cleanup succeeded. The replacement adapter now provides
strict local-copy shims for all three downloader names, accepts only the three
fixed source URLs, validates each output below the active resource staging
directory, and does not execute a network client. This adapter has passed local
fixed-source, path-escape, and unknown-URL tests; a new Marmic build has not yet
qualified it.

Revision `38cd0920fbeca5998ca29ddaf262ff419263255b` and Slurm job `625527`
then passed offline Pixi verification, every tool probe, both capacity gates,
both multi-gigabyte source checksums, and the complete database preflight. The
replacement downloader chain copied the 2,224,976,412-byte ProstT5 source into
the resource staging without a recorded network fallback. Review of the exact
resolved command exposed a separate scheduler-contract error before large
extraction was allowed to continue: `foldseek databases` had no explicit
`--threads`, while this Foldseek release's prior command evidence reported its
24-thread default and Slurm had allocated eight CPUs. The owner-bound controller
therefore cancelled only job `625527`; Slurm accounting reported terminal
`CANCELLED`, and the run evidence was collected.

Because scheduler termination occurred before Python could apply the normal
`.failed` rename, the active staging name remained outside the run directory.
The exact-confirmation recovery boundary now accepts such a case only after
collection, unchanged external configuration, an empty live queue result, and
independent `CANCELLED` accounting. It derived the sole active write root from
the structured command record, rejected arbitrary or multiple roots, and
atomically archived 6 regular files, 1 staging-confined symbolic link, and
4,642,458,543 regular-file bytes under a run-qualified `.reviewed-*` name. No
evidence was deleted. Revision
`06efd8e3c1c05896339c9566f5307796bbbd17a4` now passes `--threads 8` to both
Foldseek database commands and records that value in resource provenance. Its
replacement Marmic build is Slurm job `625528`; qualification remains open
until preparation, full verification, and all fixed smoke queries pass.

Job `625528` subsequently published a fully inventoried ProstT5 resource and
entered the PDB Foldseek build with its historical eight-CPU/64-GB allocation.
The reviewed controller cancelled that NFS-bound build by its recorded job ID,
collected the run, and archived rather than deleted its 32 files, 8 confined
links, and `4,530,919,251` regular-file bytes. Revision
`9e02e3c9cf041deef4638751565f5d9d11f270b4` then requested 100 CPUs and
2,000 GB, selected the large-memory node, and built in job-owned `/dev/shm`.
Two terabytes is intentionally less than the node's 4 TB because the configured
800 GB payload cap plus temporary overhead fits, while extra memory cannot
accelerate serial checksumming or NFS copy-back.

Slurm job `625530` passed offline Pixi and database preflight, reused the
published ProstT5 resource, and ran the PDB Foldseek build with exactly 100
threads. Foldseek produced 40 files totalling `4,530,919,251` bytes in
`/dev/shm`; their inventory digest was
`0a4fd637a7bc9765fcc2ddaab9dd2f7748be39dfea83a38bfe4f31e2c72f199e`.
The controller copied that resource once to empty durable staging, logged GiB
progress, recomputed every destination checksum, and published it. The tool
build and scratch inventory completed in under one minute; the NFS copy and
full destination verification took approximately ten minutes and remained the
I/O-bound phase.

The next PDB SEQRES step failed loudly on apparent duplicate target `10eg_a`.
Review of the exact frozen RCSB source (SHA-256
`d086a5500abc5e429eac16a6675f7b910a00c7a372f8439ba94feb8aae0bbfb6`)
showed two valid records, `10eg_A` and `10eg_a`, with identical 755-residue
sequences. Their PDB entry component is case-insensitive, but their chain tokens
are distinct: current wwPDB policy permits upper- and lower-case chain IDs. The
parser had incorrectly case-folded the compound target. It now canonicalises
only the entry ID, preserves chain-token case, still rejects a true duplicate,
and selects the fixed `1ubq_A` positive-control chain without conflating
`1ubq_a`. The complete frozen snapshot now normalises locally to `1,081,537`
protein records while explicitly skipping `64,793` non-protein records. Real
M0.4 remains open until a corrected retry completes all resources, fixed
functional smokes, and anchored full verification.

The identifier and command assumptions follow the
[RCSB file-download conventions](https://www.rcsb.org/docs/programmatic-access/file-download-services)
[RCSB identifier conventions](https://www.rcsb.org/docs/general-help/identifiers-in-pdb),
[wwPDB chain-ID policy](https://wwpdb-beta.rcsb.org/documentation/procedure),
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

On 3 August 2026, the local immutable controller was rebuilt to include the
fixed `readiness p0` interface. The first query exposed an unbounded SSH wait in
the local transport. After adding fixed connection, operation, and collection
timeouts, the same read-only query terminated after 60 seconds as
`transfer_failure`. It created no run, submitted no job, cancelled nothing, and
did not reveal any configured path. This is evidence only that the Marmic SSH
transaction was unavailable or unresponsive at that observation; it does not
supersede the earlier configuration finding or establish the current state of
Phenix, databases, or `p0.paths`.

On 9 August 2026, the checksum-verified Marmic dispatcher was refreshed from
immutable revision `aa113770fb661a22b22310335edfdad4e52df0cc`. Its dispatcher
and fixed job SHA-256 values are
`fb193ca94a22d6975fef3daddbeb73fbcd0dc9597764899bb0d7b41ba556488c`
and
`9956a03f1d720bacf6ce81879ea7575ca2596d805fd696ec19411ecfb3cb8585`.
Both bounded readiness operations then completed: Pixi 0.74.0 was ready, while
the protected P0 and database-administration configurations were absent or
unsafe. This supersedes the earlier transport observation. It does not satisfy
P0 staging readiness, database qualification, compute-node scratch/network
qualification, or scheduled real-MTZ execution.

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
