# nf-genome_to_diffraction

Foundation repository for a reproducible Nextflow and Python pipeline that will
narrow an unidentified prokaryotic crystal to reviewable protein candidates.

## Current status

This repository contains the completed foundation, typed data contracts, an
external Phenix bootstrap/runtime boundary, explicit reference-database
preparation, and trusted protein-catalogue normalisation. Diffraction processing
now implements independent MTZ preflight and candidate-specific Matthews/SDS-PAGE
hypotheses. Structural search, molecular replacement, refinement, map-based
sequence assessment, ranking, and final identification are not yet implemented.
`main.nf` therefore ends with an explicit
`task05_preflight_complete_downstream_deferred` scope record; its successful exit
does not mean that a protein identity was found. Phenix and full database
preparation have synthetic/local acceptance coverage. Tasks 04 and 05 have also
completed a real Slurm pilot on Marmic with Xtriage deliberately skipped; real
Phenix and reference-database validation remain required.

The complete scientific and engineering handoff is retained separately and is
intentionally not tracked here. `AGENTS.md`, the JSON Schemas, and examples
preserve the mandatory scope and data-contract constraints needed by the
foundation.

## Supported platforms

- Linux x86-64, including the intended HPC development target.
- macOS Apple Silicon for local development.

The environment pins the conventional GIL build of Python 3.14.6, Nextflow
26.04.6, and Java 21 LTS.
Pixi 0.74.0 is required. Phenix is licensed external software and is never
installed by Pixi or included in this repository.

## Setup and checks

```bash
pixi install --frozen
pixi run check
```

Useful focused tasks include:

```bash
pixi run format
pixi run lint
pixi run typecheck
pixi run test-unit
pixi run test-contract
pixi run schema-check
pixi run nextflow-check
pixi run nextflow-stub
pixi run hpc-wrapper-check
pixi run public-panel-check
```

Environment resolution contacts the public Conda/Bioconda and PyPI package
indexes for dependency metadata and packages. It does not transmit biological
input data.

## Command-line interface

```bash
genome-to-diffraction --version
genome-to-diffraction schema-check
genome-to-diffraction contract validate catalogue-manifest examples/catalogues.tsv
genome-to-diffraction contract canonicalise pipeline-config examples/config.yaml
genome-to-diffraction contract schema sequence-group
```

`schema-check` validates every tracked JSON Schema against Draft 2020-12,
validates the supplied JSON/YAML/TSV fixtures against both JSON Schema and the
typed application models, and checks cross-manifest references. Contract commands
log progress and diagnostics to standard error; use `--log-format json` for
structured logs and `--no-progress` for non-interactive execution.

## Immutable Marmic test profiles

The repository includes a repository-specific local controller and fixed remote
dispatcher. The `smoke` profile runs `pixi run check`; the separately bounded
`p0` profile verifies real Phenix, performs anchored database metadata and
functional-smoke revalidation, and runs the three-crystal Task 05 preflight
twice to prove cache reuse. It deliberately does not perform a terabyte-scale
full-checksum audit. A third, separately approval-gated `database` profile runs
fixed route/capacity preflight, full shared-resource preparation, and anchored
full verification with 8 CPUs, 64 GB, and a 48-hour limit. All profiles use one
immutable pushed commit. Neither provides arbitrary SSH/paths, source edits on
Marmic, automatic cleanup, or downstream protein identification. Machine-readable
results are written to standard output; diagnostic `logging` and optional
`tqdm` wait/collection progress use standard error.

The controller must be built and installed as a reviewed immutable application
outside the writable checkout before adding narrow Codex approval rules. See the
[local-Marmic feedback-loop runbook](docs/hpc-feedback-loop.md) for installation,
configuration, operations, failure classes, and the clean approval boundary.
The current M0 evidence and remaining scientific prerequisites are separated in
the [M0 qualification dashboard](docs/m0-qualification.md).

## Public X-ray control panel

The tracked [public-control panel](docs/public-control-panel.md) freezes ten
methanogen and methanotroph structures for prototype regression testing. Three
controls have complete catalogue, construct, model, and MTZ preparation
specifications; six more have qualified public sources and exact construct
mappings; one heteromeric membrane complex deliberately violates the current
single-component assumption. `runnable_control` describes reproducible input
preparation, not a completed molecular-replacement result.

```bash
pixi run public-panel-check
pixi run prepare-public-panel
```

Public coordinate and structure-factor files, derived MTZs, logs, and preparation
records are written below ignored `.untracked/public-controls/`; no public binary
data are committed. Real Phenix runs and the provisional strict Phaser gates
(`LLG > 100` and `TFZ > 10`) remain separate qualification steps.

## Trusted catalogue import

Catalogue import accepts one or more already trusted protein FASTA catalogues;
it does not predict genes, combine competing annotations, or infer taxonomy.
Relative input paths are resolved against the catalogue manifest. Every declared
input is checksummed, and every original FASTA record is retained even when its
amino-acid sequence is an exact duplicate of another record.

```bash
pixi run genome-to-diffraction catalogue import \
  --catalogues /absolute/input/catalogue_manifest.json \
  --config /absolute/input/config.yaml \
  --outdir /absolute/results/catalogue
```

The output contains canonical exact-sequence FASTA, sequence-group and
source-record registries in JSONL/TSV/Parquet, a group-to-source mapping, and a
checksummed import manifest. Optional locus metadata can come from a provider's
GFF3, GenBank flat file, or explicit TSV mapping; conflicting mappings fail.
Duplicate protein identifiers are flagged rather than overwritten.

Sequences are uppercased and whitespace is removed. A terminal stop is removed
only when configured and the transformation is recorded; internal stops remain
visible, have no molecular mass, and are excluded from the search FASTA. Exact
sequence groups use full SHA-256 identities. Average neutral polypeptide mass,
including terminal water, is calculated by the locked Biopython version.
`B/Z/J/X` produce defensible IUPAC mass bounds rather than an invented exact
mass. Chemically defined `U/O` retain exact masses but are marked for downstream
review because tool support varies. The configured `warn`, `exclude`, or `error`
policy controls all such review residues.

Python modules emit contextual logging at file, catalogue, and completion
boundaries and use `tqdm` for checksumming and protein-level progress. Use
`--log-format json` for machine-readable debugging or `--no-progress` when a
scheduler captures non-interactive logs.

## MTZ preflight and Free-R policy

Gemmi independently reads MTZ unit-cell, space-group, resolution, reflection, and
column metadata. Observation selection prefers an explicit override, then an
unambiguous intensity/sigma array, then amplitude/sigma. When several arrays are
present, a documented deterministic label priority may select one with a warning;
an unresolved tie fails. Map coefficients such as `FWT/PHWT` are never accepted as
observations.

Normal preflight runs verified `phenix.xtriage` once per crystal through the
isolated Phenix boundary and preserves its complete log:

```bash
pixi run genome-to-diffraction diffraction preflight \
  --crystals /absolute/input/crystal_manifest.json \
  --phenix-manifest /absolute/software/manifests/phenix.json \
  --outdir /absolute/results/preflight
```

`--skip-xtriage` exists for preparation and automated tests only. It always adds
`xtriage_not_run` and yields `pass_with_review`, never a clean pass. Xtriage
anisotropy, translational-NCS, twinning, and symmetry concerns are normalised but
the raw log remains authoritative. A map-only MTZ, ambiguous observation arrays,
an invalid Free-R override, or incompatible cell/symmetry yields `fail` and stops
the workflow.

Existing Free-R flags are preserved. Missing flags are reported and are not
silently generated during preflight. A separate one-time command creates a new
immutable MTZ derivative through `phenix.reflection_file_converter`, using lattice
symmetry, an explicit fraction/cap, CNS convention, and a recorded random seed:

```bash
pixi run genome-to-diffraction diffraction generate-free-r \
  --source-mtz /absolute/input/without_free_r.mtz \
  --output-mtz /absolute/input/derived/with_free_r.mtz \
  --phenix-manifest /absolute/software/manifests/phenix.json \
  --command-log /absolute/input/derived/free_r.log \
  --record /absolute/input/derived/free_r_generation.json
```

The command refuses a source that already has flags, refuses an existing output,
checks that the source did not change, validates the generated Free-R column, and
records both MTZ checksums.

## Matthews and SDS-PAGE hypotheses

For candidate mass `M`, copy count `n`, and independently calculated ASU volume
`V_ASU`, the implementation records `V_M = V_ASU / (n M)` and solvent fraction
`1 - 1.23 / V_M`. Every configured copy count is retained in JSONL/TSV/Parquet;
the top configured number (three by default) is marked for downstream use. Mass
bounds produce corresponding Matthews and solvent bounds rather than a fabricated
midpoint.

```bash
pixi run genome-to-diffraction matthews enumerate \
  --crystals /absolute/input/crystal_manifest.json \
  --config /absolute/input/config.yaml \
  --preflight /absolute/results/preflight/mtz_preflight.jsonl \
  --sequence-groups /absolute/results/catalogue/sequence_groups.jsonl \
  --source-records /absolute/results/catalogue/source_records.jsonl \
  --outdir /absolute/results/matthews
```

The current fast backend is explicitly named
`broad_solvent_centrality_v1_uncalibrated`: it is a transparent broad physical
ranking heuristic, not an empirical probability. One selected hypothesis can be
checked against the fixed local Phenix Matthews implementation without widening
the generic Phenix executor:

```bash
pixi run genome-to-diffraction --no-progress matthews reference-check \
  --crystals /absolute/input/crystal_manifest.json \
  --config /absolute/input/config.yaml \
  --preflight /absolute/results/preflight/mtz_preflight.jsonl \
  --sequence-groups /absolute/results/catalogue/sequence_groups.jsonl \
  --source-records /absolute/results/catalogue/source_records.jsonl \
  --phenix-manifest /absolute/software/manifests/phenix.json \
  --crystal-id CRYSTAL_ID \
  --sequence-group-id SEQUENCE_GROUP_ID \
  --outdir /absolute/results/matthews-reference
```

The command validates the frozen MTZ checksum, resolves only
`mmtbx.matthews` inside the verified Phenix prefix, runs the fixed
`MTZ n_residues=N` interface, preserves the log, and compares plausible copy
sets and ordering. Its report explicitly separates Phenix's residue-count mass
model from the pipeline's exact sequence-composition mass. `passed_with_review`
is a successful execution with retained mass-model, copy-boundary, copy-cap, or
uncalibrated-ordering differences; it is not silently converted to `passed`.
Either status is method evidence only: it does not prove identity, copy number,
calibration, or a positive control. SDS-PAGE uses the nearest of multiple
supplied apparent monomer-mass bands, respects reducing/non-reducing context and
band roles, and remains a soft label only; it never excludes a candidate by
itself.

## External Phenix runtime

Phenix is user-supplied licensed software. The bootstrap does not download it,
redistribute it, add it to Pixi, or send the installer anywhere. It verifies the
full SHA-256 before installation, refuses existing or unsafe targets, uses the
official non-interactive installer form, and writes separate installation and
verification logs plus a schema-valid manifest.

Use a new absolute, versioned prefix. Replace `BUILD`, paths, and the digest with
values for the installer obtained directly from Phenix:

```bash
pixi run bootstrap/install_phenix.sh \
  --installer /absolute/path/phenix-installer.sh \
  --installer-sha256 FULL_64_CHARACTER_SHA256 \
  --prefix /absolute/software/phenix-2.1-BUILD \
  --expected-release 2.1 \
  --expected-build 2.1-BUILD \
  --temp-dir /absolute/executable/tmp \
  --manifest /absolute/software/manifests/phenix-2.1-BUILD.json \
  --current-link /absolute/software/current
```

The verifier checks `PHENIX`, `PHENIX_PREFIX`, `PHENIX_VERSION`, and help-mode
execution of Xtriage, Phaser, predicted-model processing, refinement,
sequence-from-map, `phenix.maps`, and `phenix.reflection_file_converter`.
Revalidate or run one exact argument array without changing the parent Pixi
environment:

```bash
pixi run genome-to-diffraction --no-progress phenix verify \
  --manifest /absolute/software/manifests/phenix-2.1-BUILD.json
pixi run bin/phenix_exec.sh \
  --manifest /absolute/software/manifests/phenix-2.1-BUILD.json \
  -- phenix.xtriage --help
```

On Linux, the bootstrap enforces x86-64 and glibc 2.17 or newer. Default storage
preflight thresholds follow the official guidance: 15 GiB for the installed
runtime and 25 GiB for temporary extraction. A failed new target is moved aside
for debugging; an existing versioned installation is never overwritten.

## Nextflow entry points

- `main.nf` exposes catalogue, crystal, configuration, prepared-database,
  Phenix-manifest, output/cache, review, approval, and execution-profile inputs.
- `prepare_databases.nf` exposes database-root, output, preparation switches,
  coordinate-cache initialisation, and verify-only inputs.

The safe workflow smoke test is:

```bash
pixi run nextflow-stub
```

Stub execution publishes schema-valid fixture manifests, catalogue/preflight/
Matthews records, and standard Nextflow report, timeline, trace, and DAG files
under a disposable `/tmp/...` directory. A real `main.nf` run executes Tasks 04
and 05, with Xtriage enabled by default, and publishes `scope/pipeline_scope.json`
to state that all downstream scientific stages remain deferred. Non-stub database
preparation is the separate administrative workflow below.

For the implemented partial workflow:

```bash
pixi run nextflow run main.nf -profile local \
  --catalogues /absolute/input/catalogue_manifest.json \
  --crystals /absolute/input/crystal_manifest.json \
  --config /absolute/input/config.yaml \
  --database_manifest /absolute/shared/database_manifest.json \
  --phenix_manifest /absolute/software/manifests/phenix.json \
  --outdir /absolute/results/task05 \
  --cache_root /absolute/cache/nf-genome-to-diffraction
```

## Reference-database preparation

The Linux-only `hpc` environment pins Foldseek 10.941cd33 and MMseqs2 18.8cc5c.
The preparation workflow writes directly to a shared absolute database root, so
terabyte-scale resources are never staged into Nextflow work directories. Its
default hard project cap is 1.8 TB and it requires 200 GB of filesystem headroom.
The database CLI thread count is derived from the allocated Nextflow `task.cpus`,
so MMseqs2 indexing and the bounded search operations do not use the old
independent four-thread default. The internal concurrency of `foldseek databases`
still needs confirmation against the pinned Linux executable before the real
site run. The Marmic profile starts database preparation at 8 CPUs, 64 GB, and
48 hours; this is an initial measurement allocation, not a runtime or capacity
guarantee.

An intended full preparation run is:

```bash
pixi install -e hpc --frozen
pixi run -e hpc nextflow run prepare_databases.nf -profile marmic \
  --database_root /absolute/shared/nf-genome-to-diffraction/databases \
  --scratch_root /absolute/compute-node/scratch \
  --minimum_scratch_free_bytes REVIEWED_SCRATCH_BYTES \
  --outdir /absolute/shared/nf-genome-to-diffraction/database-results \
  --prepare_pdb_foldseek true \
  --prepare_pdb_sequences true \
  --prepare_prostt5 true \
  --initialise_coordinate_cache true
```

This explicit operation contacts Foldseek's documented PDB/ProstT5 sources and
the public RCSB PDB SEQRES URL. The bounded qualification smoke also fetches the
public 1UBQ mmCIF coordinate after the expected `1ubq_A` hit passes fixed score,
coverage, SEQRES-sequence, and identifier checks. It sends no catalogue sequences
or credentials.
The optional `--verify_esm_atlas_connectivity true` probe fetches one documented
public MGYP sequence by accession and never submits a user sequence. ESM Atlas
sequence submission remains disabled by default, and no local ESMAtlas30 is
prepared. Resource metadata records PDB data as CC0-1.0, ProstT5 weights as MIT,
and the optional ESM Atlas response as CC-BY-4.0.

Every immutable resource records the locked tool version, parameters, retrieval
metadata, full file inventory, byte count, SHA-256 identity, and smoke-test
status. Existing valid resources are reused; incomplete resources fail loudly;
forced builds are side-by-side. Preparation requires the expected 1UBQ hit from
parsed non-empty MMseqs2 and Foldseek results, maps it through the validated
protein-only SEQRES crosswalk, and binds the legacy suffix to the mmCIF protein
entity through its author-chain identifier. The canonical polymer and SEQRES
sequence hashes must agree before publication into the coordinate cache by
SHA-256 under a per-source POSIX lock. Immutable metadata sidecars and the digest
index are verified together. The manifest retains query, result, and log
checksums. Revalidation reruns the local known queries, compares deterministic
scores and output hashes, and writes `database_manifest.verification.json`, but
never downloads or repairs resources. It requires the frozen manifest and its
operator-recorded SHA-256, so mutable `current` links and sidecars are not the
trust anchor:

Preparation and verification take one advisory exclusive lock below the
database root before inspecting or changing shared state. Lock wait,
acquisition, and release are logged; terminal users see bounded `tqdm` progress,
and `--lock-timeout-seconds` fails loudly instead of waiting indefinitely.
This protects cooperating `genome-to-diffraction databases prepare` processes;
external programs that ignore the lock remain outside this safety boundary.

Python-managed public downloads resume only from a checksummed partial prefix bound
to the requested/effective URL and a strong ETag or Last-Modified validator.
`Range`, `If-Range`, `Content-Range`, final size, and HTTPS preservation are
validated before atomic promotion; a server-declined or unvalidated resume starts
cleanly. Capacity and free-space headroom are checked throughout. External tools
are monitored through their declared durable and scratch write roots, avoiding
a full scan of the large shared database tree every 20 seconds, and the complete
process group is stopped if either filesystem loses headroom, the durable cap is
crossed, or the scoped watchdog fails. Explicit `SLURM_TMPDIR` scratch must be
an existing canonical owned directory on a different filesystem. When a site
does not export `SLURM_TMPDIR`, the fixed database job creates one unique
mode-0700 parent below compute-node `/scratch/$USER` and removes it at
finalisation. Both routes reject `/dev/shm`, shared-device scratch, and
insufficient headroom before a payload starts. Foldseek archives and MMseqs2
index workspace are disposable there, while immutable database content remains
under the durable database root.

The downloads performed internally by `foldseek databases` do not currently
expose equivalent checkpoint state. A failed Foldseek staging directory is
retained for diagnosis, and any retained incomplete staging blocks a new build
until an operator inspects and handles it through an approved administrative
action. The pipeline never deletes it or starts another database-sized download
automatically. Do not describe the whole database build as resumable or assume
that a 2 TB allocation is sufficient until the first retained site measurements
confirm active, failed, and immutable-copy sizes.

Before a large administration job, run the compute-node preflight with explicit
absolute paths and operator-reviewed capacity requirements:

```bash
genome-to-diffraction --log-format json --no-progress databases preflight \
  --database-root /absolute/shared/database-root \
  --scratch-root /absolute/compute-node/scratch \
  --report /absolute/shared/run/database-preflight.json \
  --storage-limit-bytes 1800000000000 \
  --minimum-free-bytes 200000000000 \
  --required-database-capacity-bytes REVIEWED_REQUIRED_BYTES \
  --minimum-scratch-free-bytes REVIEWED_SCRATCH_BYTES
```

The preflight requires scratch on a different filesystem from the durable
database root, verifies the pinned Foldseek/MMseqs2 tools, measures both capacity
boundaries, requires pinned aria2 1.37.0 for the later Foldseek transfer, and
probes only the exact PDB, ProstT5, SEQRES, and 1UBQ routes with an in-memory
HTTPS `Range: bytes=0-0` request. Each route must return status 206, an exact
one-byte body, and a valid total representation size. A status-200 response is
accepted only by reading one byte and immediately closing the streaming
response; its total size remains unknown when the server does not declare one.
An invalid length, other status, or non-HTTPS redirect fails before a payload
starts. The report records the
effective URL, validators, representation size, and
`large_payload_started: false`. These endpoints come from the pinned
[Foldseek 10-941cd33 database script](https://github.com/steineggerlab/foldseek/blob/941cd33/data/structdatabases.sh)
and this repository's fixed RCSB inputs. The probes transmit no catalogue,
crystal, sequence, credentials, or licensed data. A generic internet probe is
not accepted as evidence that the compute node can reach the required routes.

```bash
pixi run -e hpc nextflow run prepare_databases.nf -profile marmic \
  --database_root /absolute/shared/nf-genome-to-diffraction/databases \
  --outdir /absolute/shared/nf-genome-to-diffraction/database-verify \
  --prepare_pdb_foldseek true \
  --prepare_pdb_sequences true \
  --prepare_prostt5 true \
  --initialise_coordinate_cache true \
  --verify_only true \
  --full_verify true \
  --expected_manifest /absolute/shared/database_manifest.json \
  --expected_manifest_sha256 EXPECTED_64_HEX_SHA256
```

`--full_verify true` recomputes the deployed inventories and is a long database
administration operation, not part of the approval-enabled `p0` job. Its
verification sidecar records either
`full_checksums_and_functional_smoke` or
`inventory_metadata_and_functional_smoke` plus an explicit Boolean checksum
flag. The fixed Marmic administration driver uses `database-stage` and
`database-submit`, fingerprinted external configuration, and explicit distinct
compute scratch. Those start commands remain approval-gated; the routine
`stage`/`submit` approvals remain limited to `smoke` and bounded `p0`.

## Repository layout

- `docs/`: tracked operational runbooks and verified prototype test reports.
- `src/genome_to_diffraction/`: Python infrastructure, contracts, Phenix and
  database boundaries, and trusted catalogue normalisation; later scientific
  subsystems remain reserved.
- `schemas/`: stable draft scientific contracts from the approved handoff.
- `examples/`: schema and operator-contract examples.
- `workflows/`, `modules/local/`: typed Nextflow wiring and process adapters.
- `conf/`: base, local, Slurm, test, and site-example configuration.
- `tests/`: unit, contract, integration-scaffold, and workflow checks.

Generated workflow work directories, results, local environments, logs, and the
separately retained developer handoff are intentionally excluded from Git.

The documentation index, Marmic runbook, and verified initial pilot findings are
available in [`docs/README.md`](docs/README.md).

## Method and software references

- Gemmi official documentation: [MTZ/reflection handling](https://gemmi.readthedocs.io/en/stable/hkl.html)
  and [Matthews coefficient](https://gemmi.readthedocs.io/en/stable/analysis.html).
- Phenix official documentation: [Xtriage](https://phenix-online.org/download/documentation/cci_apps/xtriage/phenix.xtriage.html)
  and [reflection-file tools](https://phenix-online.org/version_docs/dev-2486/reference/reflection_file_tools.html).
- Matthews, B. W. “Solvent content of protein crystals.” *Journal of Molecular
  Biology* (1968), DOI [10.1016/0022-2836(68)90205-2](https://doi.org/10.1016/0022-2836(68)90205-2).
- Kantardjieff, K. A. and Rupp, B. “Matthews coefficient probabilities: improved
  estimates for unit cell contents of proteins, DNA, and protein-nucleic acid
  complex crystals.” *Protein Science* (2003), DOI
  [10.1110/ps.0350503](https://doi.org/10.1110/ps.0350503).
