# nf-genome_to_diffraction

Foundation repository for a reproducible Nextflow and Python pipeline that will
narrow an unidentified prokaryotic crystal to reviewable protein candidates.

## Current status

This repository contains **Task 00 / Epic 0 only**: environment locking,
repository structure, Python infrastructure, JSON Schema checks, typed Nextflow
entry points, stub execution, tests, and CI. Scientific processing is not yet
implemented. Running either Nextflow entry point without `-stub-run` fails
deliberately instead of producing a misleading scientific result.

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

- `src/genome_to_diffraction/`: Python infrastructure and reserved subsystems.
- `schemas/`: stable draft scientific contracts from the approved handoff.
- `examples/`: schema and operator-contract examples.
- `workflows/`, `modules/local/`: typed foundation-only Nextflow wiring.
- `conf/`: base, local, Slurm, test, and site-example configuration.
- `tests/`: unit, contract, integration-scaffold, and workflow checks.

Generated workflow work directories, results, local environments, logs, and the
untracked documentation tree are intentionally excluded from Git.
