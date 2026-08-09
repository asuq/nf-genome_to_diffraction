# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

- Initial repository foundation for Task 00 / Epic 0.
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
  operator-owned home root, and refuses overwrite or persistent approval.
- Checksum-gated, path-closed staging of the seven frozen three-crystal P0
  inputs with deterministic archives, immutable remote publication, structured
  progress, and a separately reviewed private configuration candidate.
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
- A ten-structure public methanogen/methanotroph X-ray panel now freezes exact
  RCSB and NCBI provenance, catalogue-to-construct mappings, deterministic MTZ
  derivation, three fully preparable controls, and one deliberate heteromer
  assumption violation, with structured logging and bounded progress reporting.
- The pilot Matthews retention cap is now four rather than three. Real 8OOX
  Task 05 and Phenix 2.1-6048 reference runs independently place its known
  two-copy, high-solvent ASU hypothesis fourth, so this is a bounded execution
  correction without fitting or changing the uncalibrated ranking heuristic.

### Not implemented

- Structural search, model preparation, molecular replacement, refinement,
  map-based sequence assessment, final ranking, and final scientific reporting.
- Real-site Phenix/database validation, structural search, and MR.

## 1.0 - 31 July 2026

Initial approved developer handoff. The complete handoff is retained outside this
Git repository.
