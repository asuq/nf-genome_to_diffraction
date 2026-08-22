# Changelog

All notable changes to this project are documented here.

## Unreleased

### Changed

- Started the `0.2.0.dev0` development line for the bounded two-component
  heteromer prototype. The immutable `v0.1.0` archival release remains
  unchanged.

### Added

- A minimal checksum-bound `1A + 1B` Phaser adapter that fixes one placed A
  coordinate, searches only B, retains the combined PDB/MTZ and raw evidence,
  and reports B-specific TFZ plus incremental LLG without treating a failed
  search as proof that B is absent.
- A fixed 6RTZ input preparer that verifies the public deposition against the
  frozen protocol, maps HisF/entity 1/chain A and HisH/entity 2/chain B, and
  writes only the exact-model A-first-copy and B-partner inputs needed by the
  adapter-isolation control.
- A path-closed Marmic `heteromer-smoke` profile. It prepares the two frozen
  public files on the login node and runs one sequential 8-CPU/16-GB Slurm job:
  real Xtriage, exact HisF first-copy, then fixed-HisF/HisH partner search.

## 0.1.0 - 2026-08-19

This is an archival, incomplete research-prototype release. It preserves the
single-component baseline before prototype-first heteromer development; it is
not a production or M6-validated release.

### Known limitations

- M6 scientific acceptance is held. The successful Marmic M6 Nextflow smoke is
  orchestration evidence only.
- The main implementation is single-component and has no heteromer
  reconstruction.
- The 7L6G control placed three copies rather than its declared six.
- Same-component copy placement retains legacy sequential behaviour in the
  released path.
- Crystallographic-context propagation, Free-R identity, cache/network/retry
  hardening, and the full M6 measurement apparatus remain incomplete.
- Outputs are research candidates and do not constitute an automatically
  validated structure or protein identity.

### Changed

- M6 acceptance now uses checksum-bound runner identity decisions, verified
  private 30%/70% family truth, and observation-derived edge evidence rather
  than accepted-hit counts, manufactured null identities, or fault-control
  descriptors. Fresh acceptance requires identity-bearing Nextflow-v2 tracks.
- M6 discovery partitioning now reuses complete batch/result value channels for
  every catalogue and deterministically sorts batch outputs before publication.
- The user-approved provisional first-copy acceptance score gate is now the
  strict disjunction `LLG > 50` or `TFZ > 5`. The adapter records the operator
  and thresholds, review packages recompute the policy from raw scores, and
  legacy `LLG > 100` plus `TFZ > 10` results can be reclassified without
  altering their preserved raw evidence. Packing and placed-copy agreement
  remain additional independent requirements.

### Added

- Multi-catalogue/multi-batch Nextflow regression coverage, real open-set false-
  assignment `HOLD` coverage, family/off-family classification evidence, and
  typed measured/contradicted/unavailable records for all nine M6 edge cases.
- Initial repository foundation for Task 00 / Epic 0.
- Bounded direct-PDB coordinate registration with sequence-group-first
  diversity, exact PDB entity/chain and searched-snapshot verification,
  content-addressed cache reuse, typed hit-to-coordinate mappings, and a
  resumable `register_coordinates.nf` stub boundary.
- One non-combinatorial experimental-model variant that verifies each registered
  PDB mapping, removes non-polymer residues and hydrogens, retains alternate
  conformations, writes a content-addressed single-chain PDB, and exposes a
  resumable `prepare_pdb_models.nf` boundary.
- A multi-source first-copy funnel that verifies paired model bundles and PDB
  mappings, round-robins across sequence/provider/variant buckets, enforces a
  hard 25-job-per-crystal smoke ceiling, publishes a relocatable aggregate model
  registry, and exposes a resumable `screen_diverse_first_copy.nf` Phaser route.
- Locked Pixi development environment for Python 3.14.6 and Nextflow 26.04.6.
- Typed, fail-loud Nextflow entry-point stubs.
- Python logging, status, checksum, atomic-write, and schema-checking utilities.
- Unit, contract, integration-scaffold, documentation, and CI checks.
- GitHub Actions checkout v6 for the current Node 24 hosted-runner runtime.
- Strict typed models for approved manifests and downstream result contracts.
- RFC 8785 canonical serialisation, content-derived IDs, and JSON/YAML/TSV
  contract commands with structured logging and optional progress reporting.
- Checksum-gated external Phenix bootstrap, isolated runtime verifier/executor,
  atomic current-symlink promotion, progress reporting, and preserved logs.
- Idempotent Foldseek PDB, ProstT5, PDB-sequence/MMseqs2, coordinate-cache, and
  opt-in ESM Atlas connectivity preparation with a 1.8 TB storage guard.
- Case-sensitive PDB-chain crosswalking for both legacy `PDBID_CHAIN` records
  and Foldseek PDB100 `PDBID-assemblyN_CHAIN` result identifiers.
- Trusted FASTA catalogue normalisation with lossless source provenance, exact
  sequence grouping, explicit residue review policies, molecular-mass bounds,
  GFF3/GenBank/TSV locus adapters, and JSONL/TSV/Parquet registries.
- Independent Gemmi MTZ inspection, isolated Xtriage parsing, immutable one-time
  Free-R generation, soft SDS-PAGE features, bounded Matthews calculations, and
  real resumable Nextflow wiring through the Task 05 boundary.
- Tracked operational documentation for the Marmic runtime layout, prototype
  procedure, and verified `GCF_000711905.1`/`CD6QS2P2G1_5` pilot findings.
- Compound-CDS merging and lossless preservation of distinct loci that share a
  RefSeq protein accession, validated by the real Marmic Task 05 pilot.
- Repository-specific immutable-commit Marmic smoke testing with a fixed Slurm
  profile, owner-bound job control, structured failure records, bounded
  `logging`/`tqdm` feedback, and approval-gated cleanup.
- Paired single-component and full-program roadmaps that distinguish the active
  `ASU = nA` prototype from later heteromer search, advanced crystallographic and
  assembly support, calibrated automation, and final platform development.
- A fixed `p0` Marmic profile with immutable external configuration
  fingerprinting, real Phenix and database verification, all-three-crystal Task
  05 execution, mandatory cached resume, bounded artefact collection, and a
  tracked M0 qualification dashboard.
- A create-only, checksum-confirmed P0 configuration boundary that validates the
  seven external site paths without exposing them, permits a read-only
  nearest operator-owned common site root across dispatcher and database
  storage, and refuses overwrite or persistent approval.
- Checksum-gated, path-closed staging of the seven frozen three-crystal P0
  inputs with deterministic archives, immutable remote publication, structured
  progress, and a separately reviewed private configuration candidate.
- Immutable controller builds now bundle the authoritative JSON Schemas and
  exercise contract loading from the installed zipapp rather than relying on a
  neighbouring repository checkout.
- Expected-1UBQ database qualification with explicit search thresholds,
  SEQRES-to-mmCIF protein-entity sequence binding, immutable coordinate-cache
  provenance, retained query/result/log evidence, and reproducible rerun records.
- Bounded structured MMseqs2 smoke-result diagnostics that retain the hit count,
  expected-target cardinality, and first ten scored targets when qualification
  fails, without copying an unrestricted search result into controller logs.
- Ubiquitin search qualification now resolves the deterministically strongest
  hits through the SEQRES crosswalk, requires the MMseqs2 hit to have the exact
  query hash, and independently retains the fixed `1ubq_A`
  sequence-to-coordinate control instead of relying on redundant database tie
  ordering.
- Validator-bound resumable public downloads with verified prefix state,
  redirect provenance, continuous capacity/headroom checks, scoped NFS storage
  monitoring, and whole-process-group termination on watchdog failures.
- Database-preparation threads now follow the allocated Nextflow CPUs, including
  the Foldseek `databases` download/extraction commands, with an explicitly
  provisional Marmic preparation allocation for first-site timing.
- Shared database administration now uses one logged, timeout-bounded advisory
  exclusive lock per database root to prevent cooperating runs from racing.
- Retained incomplete resource staging now blocks automatic rebuilds, preventing
  repeated Foldseek failures from silently consuming another full allocation.
- Fixed database inputs are now downloaded sequentially and resumably on the
  Marmic login node into a content-addressed, full-checksum source bundle. The
  compute preflight verifies that bundle, distinct scratch, declared capacity,
  and pinned tools entirely offline before any extracted payload starts.
- Database tool-version probes now log start/completion and elapsed time and use
  a fixed 180-second bound to tolerate measured NFS-cold executable startup.
- Failed database command logs are now available through the existing bounded
  `logs` operation after owner, configured-root, file-type, and filename checks;
  callers still cannot supply remote paths.
- Offline Foldseek extraction now shadows its aria2/curl/wget fallback chain
  with fixed-URL, staging-confined local-copy shims, preventing a fallback from
  attempting compute-node network access.
- A collected, terminal database software failure or scheduler-confirmed
  cancellation can now release its retained build guard through an
  exact-confirmation operation that archives rather than deletes the log-derived
  staging tree and rejects active jobs, configuration drift, or unsafe entries;
  fail-closed path checks report the rejected safety condition without exposing
  caller-controlled paths, and only staging-confined symbolic links are
  preserved.
- Large Foldseek and MMseqs2 resources now build entirely in explicit distinct
  compute-node scratch. Scratch bytes count towards the project cap; publication
  uses one progress-logged copy-back, full destination checksums, atomic
  promotion, retained failed staging, and exact-child scratch cleanup.
- PDB SEQRES target identity now canonicalises the case-insensitive entry ID
  while preserving the case-sensitive chain token, accepting valid pairs such
  as `10eg_A`/`10eg_a` without weakening exact-duplicate rejection or the fixed
  `1ubq_A` qualification target.
- P0 database checks are explicitly bounded metadata/functional revalidation;
  verification evidence records whether full checksums were computed, while
  long database administration stays outside routine HPC start approvals.
- A separately approval-gated Marmic database profile now fingerprints a fixed
  external capacity/path contract, uses 100 CPUs/2,000 GB/48 hours, creates one
  owned `/dev/shm` build tree, uses an exact-URL local Foldseek source adapter,
  and accepts no arbitrary paths or shell fragments on its start commands.
- A tracked local-settings inventory documents recoverable removal and
  restoration of the installed HPC controller, its configuration/capabilities,
  Codex approval boundary, and the verified local Phenix selection/evidence.
- A fixed local Phenix Matthews method-reference check now validates frozen MTZ
  provenance, preserves the licensed-tool log outside Git, compares copy sets
  and ordering, and keeps method compatibility distinct from identity or
  positive-control evidence.
- A predeclared three-MTZ/three-protein reference matrix now retains copy-bound,
  mass-model, and uncalibrated-ordering differences as review outcomes; rounded
  Phenix probability ties and common solvent-bound comparisons are handled
  explicitly without tuning the prior.
- Fixed SSH connect, operation, and collection timeouts now prevent the reviewed
  HPC controller from hanging indefinitely and classify unreachable or
  unresponsive transport as `transfer_failure` without implicit cancellation.
- The immutable HPC controller builder now canonicalises archive order,
  timestamps, permissions, and compression, producing the same SHA-256 for
  repeated builds from identical source and the same locked interpreter path.
- A twelve-structure public prokaryotic X-ray panel now freezes exact RCSB and
  NCBI provenance, catalogue-to-construct mappings, deterministic MTZ
  derivation, three fully preparable controls, eleven truth-labelled positives,
  a negative execution matrix, and one deliberate heteromer assumption
  violation, with structured logging and bounded progress reporting.
- The pilot Matthews retention cap is now four rather than three. Real 8OOX
  Task 05 and Phenix 2.1-6048 reference runs independently place its known
  two-copy, high-solvent ASU hypothesis fourth, so this is a bounded execution
  correction without fitting or changing the uncalibrated ranking heuristic.
- P0 staging now materialises and verifies its frozen Pixi environment on the
  network-enabled login node under a fixed transport timeout; the Slurm job
  reuses that exact environment without attempting package resolution on an
  offline compute node.
- P0 Phenix verification now runs without a per-command deadline under a fixed
  24-hour Slurm/controller margin, retains clean timeout evidence for callers
  that choose a bound, and uses normalised application-log evidence to
  distinguish feedback-loop failure signatures with different root causes.
- External database-tool version probes are likewise unbounded by default;
  callers may still request an explicit deadline outside the NFS-sensitive P0
  path.
- P0 verifies pinned MMseqs2 and Foldseek during staging and prepends the locked
  environment to `PATH`, so offline database revalidation resolves those exact
  tools while retaining the batch system utilities.
- PDB search revalidation requires the strongest MMseqs sequence-search hit to
  be significant and exactly query-equivalent, while independently verifying
  the fixed `1ubq_A` SEQRES mapping and cached `1UBQ` coordinate. Foldseek uses
  the same separation with its strongest biological-assembly hit. Revalidation
  does not treat ordering, tied target identity, bounded hit count, or the
  complete result checksum as reproducible scientific invariants.
- A shared structural-search result contract and the first M1 provider now run
  catalogue-wide local MMseqs2 searches against the qualified PDB sequence
  resource, preserve exact PDB/chain mappings and raw evidence, distinguish
  hit, no-hit, and ineligible outcomes, and expose a resumable typed Nextflow
  entry point.
- A fixed path-closed Marmic P1 operation now reuses the frozen P0 catalogue and
  qualified database manifest, runs catalogue-wide direct PDB discovery through
  the checked `nf-helper` Marmic profile, requires a fully cached resume, and
  emits checksum-validated 8OOX/model-key/resource qualification evidence.
- The first real P1 run evaluated all 1,621 exact-sequence groups (1,620 search
  eligible), retained the exact 8OOX/8OOW family, measured the direct-search
  process, and passed cached resume; the sanitised qualification dossier records
  counts and limitations.
- A CPU-default ProstT5/Foldseek-to-PDB provider now searches the qualified
  immutable PDB100 and ProstT5 resources, preserves raw candidate output,
  requests no unavailable query-coordinate metrics, crosswalks assembly-chain
  targets to reusable PDB model keys, and exposes explicit GPU opt-in through
  the typed discovery workflow.
- An exact AlphaFold DB provider now accepts strict UniProt accessions or an
  explicit source-record mapping, rejects RefSeq identifiers as implicit
  mappings, verifies both API and mmCIF polymer sequences against the catalogue
  digest, excludes complex/fragment models, and caches the selected coordinate
  plus provenance atomically. Its dedicated Nextflow network branch sends no
  biological sequence and emits explicit ineligible/no-hit/error states. A live
  public `P69905` control passed the current API, exact mmCIF-polymer check, and
  cache-publication boundary.
- The exact pilot RefSeq-to-UniProt mapping
  `WP_042685700.1` to `A0A832VZP6` now has a tracked narrow input and passed a
  live accession/API/mmCIF sequence-equality retrieval with immutable hashes.
- After the first full-catalogue ProstT5/Foldseek attempt exited without a
  durable native scratch log, failures now retain a bounded 16-KiB/40-line log
  tail. The fixed real retry uses a deterministic 128-sequence pilot cap with
  explicit `skipped_policy` results and Marmic's 100-CPU/2,000-GB process
  allocation; the uncapped catalogue gate remains open.
- A deterministic predicted-model adapter now verifies immutable AFDB/Atlas
  source coordinates against exact catalogue sequences, invokes verified
  `phenix.process_predicted_model` in an isolated shell, validates retained
  residue positions, recalculates processed-model mass, and publishes
  content-addressed mmCIF/record/manifest/log outputs. The real pilot-derived
  `A0A832VZP6` model passed Phenix 2.1-6048 with 429 of 442 residues retained.
- The bounded real ProstT5 retry showed that Foldseek `prob` requires unavailable
  query Cα coordinates for FASTA/ProstT5 searches. Adapter v2 follows the exact
  `10-941cd33` source by omitting only that field, retaining identity, coverage,
  E-value, and bit score, recording nullable probability provenance, and
  invalidating the former cache identity.
- Fixed routine Marmic dispatcher operations now use a 45-minute transport
  margin instead of 60 seconds, retaining connection liveness checks and
  fail-closed command/path validation while tolerating NFS-cold alternate login
  nodes. The local rollback guide records how the stable SSH alias selects and
  restores an operator-chosen login node.
- The source-corrected real 128-sequence ProstT5/Foldseek run completed its
  external search, then exposed RCSB biological-assembly copy chains such as
  `A-2` at the SEQRES crosswalk. Adapter v3 strips only documented numeric
  operator suffixes for assembly-qualified lookup while retaining the complete
  Foldseek target, assembly number, and operator indices in hit provenance.
- The fixed adapter-v3 Marmic pilot passed on 128 real sequence groups, retaining
  292 hits for 102 groups, 26 completed no-hits, 18 assembly-copy hits, explicit
  policy deferral of the other 1,492 eligible groups, and a fully cached resume.
- A typed predicted-model Nextflow entry point now passes exact coordinate and
  sequence records to the verified Phenix adapter. The fixed P1 operation
  supplies only the tracked pilot AFDB mapping, requires one processed model,
  verifies cached discovery/model resumes, and collects only small provenance.
- After Marmic compute nodes rejected outbound AFDB HTTPS, the fixed P1 route
  was split at the network boundary: immutable login-node staging now retrieves
  and sequence-verifies the one public pilot model, records hand-off checksums,
  and scheduled discovery/model work verifies and consumes it offline.
- The corrected fixed route passed as Slurm job `625744` on immutable commit
  `c901dafe585d1b68b117d7d216e5053ef4985230`. Phenix 2.1-6048 retained 429 of
  442 residues in the exact pilot model and the model process cached on resume.
- An exact-predicted-model funnel now verifies coordinate/model/sequence
  identity and checksums, excludes physically impossible copy counts, preserves
  inspectable priority fields, applies deterministic hard caps, and emits one
  immutable record per first-copy MR job.
- The first-copy Phaser adapter now runs through the isolated licensed runtime,
  preserves commands/logs/output checksums, uses final packing evidence,
  separates scientific no-hits from execution failures, and enforces the
  provisional strict `LLG > 100` and `TFZ > 10` gate without a default timeout.
- The first-copy Phaser adapter now accepts the bounded cleaned-PDB policy only
  when its mapping ID and candidate-to-source identity match the processed-model
  provenance, and passes that verified identity instead of an unjustified 100%.
- A typed `screen_first_copy.nf` route and fixed checksum-gated Marmic P2
  operation now execute the bounded CD6 exact-model hypothesis and require a
  fully cached resume. The fixed fake Git/Slurm/Nextflow/Phenix lifecycle passes;
  real P2 qualification remains pending.
- The first immutable CD6 P2 replay completed the real database, P0, P1, funnel,
  and cached-resume path but exposed a Phenix 2.1-6048 interoperability failure:
  Phaser 2.8.4 found no scatterers in the processed mmCIF. Predicted-model
  preparation now requests Phenix's PDB output for this single-chain slice; the
  exact 429-residue model passed the public 8OOX control with final LLG 1149.2,
  TFZ 46.0, and accepted packing.
- The fixed P2 harness now treats `failed_tool_execution`, `failed_parse`, and
  `failed_infrastructure` normalised results as qualification failures while
  preserving their bounded result, command, and logs. Only completed hit or
  completed no-hit outcomes can make the outer P2 feedback run successful.
- The real PDB-model retry reached a successful Phaser no-solution termination:
  76 translations entered packing, none were accepted, no solution files were
  written, and the top translation TFZ was 5.11. The parser now recognises
  Phaser's terminal `Sorry - No solution` form as a valid completed no-hit
  while continuing to reject logs without terminal solution evidence.
- The immutable parser-correction replay now qualifies the fixed Marmic P2
  route as `completed_no_hit`: outer execution succeeds, the result contract
  validates, both P2 processes cache on resume, and no tool/parse failure is
  mistaken for a scientific result.
- The tracked development-loop journal is now a mandatory read-first and
  write-before-handoff record so scientific discoveries, completed evidence,
  unresolved work, and the exact restart point survive task boundaries.

### Not implemented

- Uncapped real-catalogue ProstT5/Foldseek qualification, optional ESM Atlas
  search, provider hit union, real Marmic PDB coordinate qualification,
  sequence-adapted/domain model variants, real multi-source funnel qualification,
  same-component copy placement, refinement, map-based sequence assessment,
  final ranking, and final scientific reporting.
- The remaining multi-provider P1 gate, real diverse P2 run, broader P2
  qualification/review package, and downstream MR gates.

## 1.0 - 31 July 2026

Initial approved developer handoff. The complete handoff is retained outside this
Git repository.
