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
`p0` profile verifies configured real Phenix/database resources and runs the
three-crystal Task 05 preflight twice to prove cache reuse. Both use one
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
ranking heuristic, not an empirical probability. Real Phenix/Xtriage comparison
must be completed before treating it as calibrated. SDS-PAGE uses the nearest of
multiple supplied apparent monomer-mass bands, respects reducing/non-reducing
context and band roles, and remains a soft label only; it never excludes a
candidate by itself.

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

An intended full preparation run is:

```bash
pixi install -e hpc --frozen
pixi run -e hpc nextflow run prepare_databases.nf -profile slurm \
  --database_root /absolute/shared/nf-genome-to-diffraction/databases \
  --outdir /absolute/shared/nf-genome-to-diffraction/database-results \
  --prepare_pdb_foldseek true \
  --prepare_pdb_sequences true \
  --prepare_prostt5 true \
  --initialise_coordinate_cache true
```

This explicit operation contacts Foldseek's documented PDB/ProstT5 sources and
the public RCSB PDB SEQRES URL. It sends no catalogue sequences or credentials.
The optional `--verify_esm_atlas_connectivity true` probe fetches one documented
public MGYP sequence by accession and never submits a user sequence. ESM Atlas
sequence submission remains disabled by default, and no local ESMAtlas30 is
prepared. Resource metadata records PDB data as CC0-1.0, ProstT5 weights as MIT,
and the optional ESM Atlas response as CC-BY-4.0.

Every immutable resource records the locked tool version, parameters, retrieval
metadata, full file inventory, byte count, SHA-256 identity, and smoke-test
status. Existing valid resources are reused; incomplete resources fail loudly;
forced builds are side-by-side. The coordinate cache uses provider namespaces,
atomic sidecars, content hashes, and POSIX advisory locks. Revalidation never
downloads or repairs resources:

```bash
pixi run -e hpc nextflow run prepare_databases.nf -profile slurm \
  --database_root /absolute/shared/nf-genome-to-diffraction/databases \
  --outdir /absolute/shared/nf-genome-to-diffraction/database-verify \
  --prepare_pdb_foldseek true \
  --prepare_pdb_sequences true \
  --prepare_prostt5 true \
  --initialise_coordinate_cache true \
  --verify_only true \
  --full_verify true
```

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
