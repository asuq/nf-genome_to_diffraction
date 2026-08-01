# nf-genome_to_diffraction

Foundation repository for a reproducible Nextflow and Python pipeline that will
narrow an unidentified prokaryotic crystal to reviewable protein candidates.

## Current status

This repository contains the completed foundation, typed data contracts, and an
external Phenix bootstrap/runtime boundary. Scientific catalogue and diffraction
processing are not yet implemented. Running either Nextflow entry point without
`-stub-run` fails deliberately instead of producing a misleading scientific
result. The Phenix integration is tested with a synthetic installer; real-site
validation remains required before it can be described as operational.

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

The safe foundation smoke test is:

```bash
pixi run nextflow-stub
```

Stub execution publishes schema-valid fixture manifests and standard Nextflow
report, timeline, trace, and DAG files under a disposable `/tmp/...` directory.
Normal runs fail with an explicit `foundation_only_not_implemented` message.

## Repository layout

- `src/genome_to_diffraction/`: Python infrastructure, contracts, and Phenix
  boundary; later scientific subsystems remain reserved.
- `schemas/`: stable draft scientific contracts from the approved handoff.
- `examples/`: schema and operator-contract examples.
- `workflows/`, `modules/local/`: typed foundation-only Nextflow wiring.
- `conf/`: base, local, Slurm, test, and site-example configuration.
- `tests/`: unit, contract, integration-scaffold, and workflow checks.

Generated workflow work directories, results, local environments, logs, and the
untracked documentation tree are intentionally excluded from Git.
