# Phase III locked offline wheel gate

## Purpose and boundary

`PIPE-P3-01` requires one reproducible distribution check before the Phase III
release. The `offline-wheel-check` Pixi task builds the project wheel with the
exact Hatchling version present in `pixi.lock`, installs it without resolving
dependencies into a fresh temporary virtual environment, and tests the wheel
rather than the editable checkout.

Run the gate only after the locked Pixi environment is present:

```console
pixi run --locked --offline offline-wheel-check
```

The command uses no package index, PEP 517 build isolation, build-time
dependency resolution, or persistent output directory. It directly invokes
the already installed `hatchling==1.32.0` backend with `PIP_NO_INDEX=1` and
`UV_OFFLINE=1`. Temporary files are removed when the checker exits.

This is a repository distribution regression, not a claim that the project is
ready for general PyPI publication or arbitrary production installation.

## Inputs and checks

The exact inputs are `pyproject.toml`, `pixi.toml`, `pixi.lock`,
`nextflow.config`, the public Python package below
`src/genome_to_diffraction`, and every tracked `schemas/*.schema.json` file.
The repository-only `src/genome_to_diffraction/hpc/` client is deliberately
outside the wheel. The gate requires:

- one exact `hatchling==1.32.0` build-system requirement and the same installed
  backend version from the locked runtime;
- one pure-Python wheel with the public source package and no internal HPC
  client files;
- every tracked JSON Schema under `genome_to_diffraction/_schemas`, with bytes
  identical to the authoritative tracked schema;
- exactly one declared console entry point, `genome-to-diffraction`, with its
  expected callable target;
- identical versions in `pyproject.toml`, the Pixi workspace, package source,
  Nextflow manifest, wheel metadata, installed package metadata, and installed
  CLI `--version` output; and
- successful `--help` execution for the public console entry point after the
  wheel is installed.

The wheel is required to be `Root-Is-Purelib: true` and to contain no wheel
`.data` scheme. After validating every archive path, the checker installs this
project-specific purelib wheel by extracting it into a fresh
`--system-site-packages` virtual environment. The new environment can read the
already locked runtime dependencies, but its project import must resolve from
the wheel-owned site-packages directory. Entry points are loaded from that
installed wheel's `entry_points.txt`; the editable checkout is not accepted as
the tested package.

## Outputs and failure semantics

Success writes one JSON summary to standard output with the common release
version, exact build backend, public entry-point name, and packaged-schema
count.
There are no scientific statuses or workflow outputs. Any missing or changed
source module/schema, unexpected or missing entry point, divergent version,
non-pure wheel, unsafe archive path, failed isolated import, or non-zero help
command exits the gate with status 1.

No Nextflow cache is involved. The effective distribution identity is the
locked build backend plus every byte and metadata surface inspected above; a
change to any of them requires a new wheel and checker result.

## Focused regression coverage

`tests/unit/test_offline_wheel_gate.py` covers missing packaged schemas,
missing public entry points, accidental inclusion of the internal HPC client,
wheel/source version mismatch, and empty or divergent release-version
surfaces. The real Pixi task supplies the positive build, install, import,
entry-point, schema-byte, and version-parity evidence. Exact-source acceptance
is recorded in the Phase III finding ledger and must be refreshed for the
release candidate.
