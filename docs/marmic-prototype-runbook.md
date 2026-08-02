# Marmic prototype runbook

## Purpose

This runbook reproduces the implemented Task 05 boundary on Marmic: trusted
catalogue import, MTZ preflight, and Matthews enumeration. Scientific stages
after Task 05 are deferred. Use absolute paths and keep raw inputs, generated
results, environments, caches, and logs outside Git.

The initial verified run is summarised in the
[prototype test report](prototype-test-report-2026-08-02.md).

## Runtime layout

Create one isolated run root per pilot:

```text
RUN_ROOT/
|-- input/
|   |-- genome/
|   `-- diffraction/
|-- manifests/
|-- software/manifests/
|-- databases/
|-- cache/
|   |-- nextflow-home/
|   `-- work/
|-- logs/
`-- results/
```

The tracked [layout helper](../bootstrap/prepare_project_layout.sh) creates this
structure idempotently and never removes or overwrites files:

```bash
export REPOSITORY=/absolute/path/to/nf-genome_to_diffraction
export RUN_ROOT=/absolute/path/to/pilot_run

"$REPOSITORY/bootstrap/prepare_project_layout.sh" --root "$RUN_ROOT"
```

## Verify the pinned Pixi runtime

Pixi is installed independently on Marmic and registered on `PATH`. Do not create
another Mamba environment for Pixi. Resolve its executable once so scheduled
commands do not depend on interactive shell initialisation:

```bash
pixi --version
export PIXI_BIN="$(type -P pixi)"
test -n "$PIXI_BIN"
test -x "$PIXI_BIN"
"$PIXI_BIN" --version
"$PIXI_BIN" install -e hpc --frozen
```

Both version checks must report Pixi 0.74.0. Pixi contacts Conda channels and
PyPI for dependency metadata and packages; it does not need to transmit
biological inputs. Confirm the pinned tools before launch:

```bash
"$REPOSITORY/.pixi/envs/hpc/bin/python" --version
"$REPOSITORY/.pixi/envs/hpc/bin/nextflow" -version
"$REPOSITORY/.pixi/envs/hpc/bin/genome-to-diffraction" --version
```

Expected foundation versions are Python 3.14.6, Nextflow 26.04.6, Java 21, Pixi
0.74.0, and project version `0.1.0.dev0`.

## Stage and validate inputs

Place immutable genome/annotation files under `input/genome/` and the MTZ under
`input/diffraction/`. Record source releases and SHA-256 checksums. Do not copy
large inputs into the repository.

Create these run-specific contracts under `manifests/`:

- `catalogues.tsv`, with the trusted proteome and one coherent provider
  annotation set;
- `crystals.tsv`, with the MTZ, catalogue ID, optional SDS-PAGE evidence, and
  explicit remote-submission policy; and
- `config.yaml`, with residue policy, copy-count range, retention count, and
  other intentional settings.

Validate them before scheduling:

```bash
export RUNTIME_BIN="$REPOSITORY/.pixi/envs/hpc/bin"

"$RUNTIME_BIN/genome-to-diffraction" --no-progress contract validate \
  catalogue-manifest "$RUN_ROOT/manifests/catalogues.tsv"
"$RUNTIME_BIN/genome-to-diffraction" --no-progress contract validate \
  crystal-manifest "$RUN_ROOT/manifests/crystals.tsv"
"$RUNTIME_BIN/genome-to-diffraction" --no-progress contract validate \
  pipeline-config "$RUN_ROOT/manifests/config.yaml"
```

Use explicit observation and Free-R labels when the MTZ contains more than one
reasonable array. Keep `allow_remote_sequence_submission=false` unless sequence
submission has been reviewed and explicitly authorised.

## Marmic profile and scratch

Use only `-profile marmic`. Do not combine `slurm,marmic`: the generic project
Slurm configuration can override site settings supplied by `nf-helper`.

The tracked [Marmic wrapper](../conf/marmic.config) imports the pinned
`nf-helper` site profile and puts the project `hpc` environment on each process
`PATH`. The site profile supplies the Slurm executor, conservative submission
limits, `--export=ALL`, and compute-node scratch staging.

The Nextflow driver may use `/dev/shm` for its small temporary files when the
login filesystem is slow. Keep `cache/work` and the output directory unchanged
between resume runs. Do not place irreplaceable inputs only in `/dev/shm` or
compute-node scratch.

## Submit the workflow

A minimal non-interactive driver is:

```bash
#!/usr/bin/env bash
#SBATCH --job-name=nf-gtd-task05
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=12:00:00
#SBATCH --export=ALL
#SBATCH --output=/absolute/run/root/logs/task05-driver-%j.log

set -euo pipefail

: "${REPOSITORY:?export the repository path before sbatch}"
: "${RUN_ROOT:?export the pilot run root before sbatch}"

export PATH="$REPOSITORY/.pixi/envs/hpc/bin:/usr/bin:/bin"
export JAVA_CMD="$REPOSITORY/.pixi/envs/hpc/lib/jvm/bin/java"
export NXF_HOME="$RUN_ROOT/cache/nextflow-home"
export NXF_ANSI_LOG=false
export TMPDIR="/dev/shm/nf-gtd-driver-${SLURM_JOB_ID}"
mkdir -p "$TMPDIR"

cd "$REPOSITORY"
printf 'driver_host=%s\n' "$(hostname -f)"
printf 'driver_job=%s\n' "$SLURM_JOB_ID"
printf 'repository_commit=%s\n' "$(git rev-parse HEAD)"
python --version
nextflow -version
genome-to-diffraction --version

nextflow run main.nf \
  -profile marmic \
  --catalogues "$RUN_ROOT/manifests/catalogues.tsv" \
  --crystals "$RUN_ROOT/manifests/crystals.tsv" \
  --config "$RUN_ROOT/manifests/config.yaml" \
  --database_manifest /absolute/path/to/verified/database_manifest.json \
  --phenix_manifest /absolute/path/to/verified/phenix_manifest.json \
  --profile_mode pilot \
  --review_mode prepare \
  --outdir "$RUN_ROOT/results/task05" \
  --cache_root "$RUN_ROOT/cache"
```

Export the two paths, check the `#SBATCH --output` path, and submit:

```bash
export REPOSITORY=/absolute/path/to/nf-genome_to_diffraction
export RUN_ROOT=/absolute/path/to/pilot_run
sbatch "$RUN_ROOT/manifests/run_task05.sbatch"
```

For a preparation-only test without a verified Phenix runtime, add
`--skip_xtriage true`. This forces `pass_with_review`, records
`xtriage_not_run`, and must not be interpreted as a clean crystallographic pass.

## Resume

After fixing an input or code failure, retain the exact cache root, work
directory, manifests, and output root, then add `-resume` immediately after
`main.nf`:

```bash
nextflow run main.nf \
  -resume \
  -profile marmic \
  ...
```

Check the driver log for `Cached process`. A second identical successful run
should cache input validation, catalogue import, MTZ preflight, and Matthews
enumeration. A changed input checksum, parameter, command, or relevant code path
should invalidate the affected process rather than silently reuse it.

## Outputs and acceptance checks

The important result areas are:

```text
results/task05/
|-- catalogue/
|-- preflight/
|-- matthews/
|-- scope/
`-- pipeline_info/
```

Confirm that `scope/pipeline_scope.json` reports
`task05_preflight_complete_downstream_deferred`. Inspect the preflight and
Matthews Markdown reports, but retain the JSONL/TSV/Parquet files as the
machine-readable evidence. Row counts must agree across formats.

For the `GCF_000711905.1`/`CD6QS2P2G1_5` pilot specifically, the accepted counts
are 1,625 source records, 1,621 sequence groups, 1,620 search FASTA records,
1 preflight record, and 25,920 Matthews hypotheses. These values are regression
expectations for this frozen input pair, not universal biological expectations.

## Logging and troubleshooting

Python commands provide contextual `logging` output and `tqdm` progress for
many-record operations. Use `--log-format json` for structured scheduler logs,
`--log-level DEBUG` for additional diagnostics, and `--no-progress` when progress
bars are unsuitable for captured logs.

When NFS is slow:

- inspect Slurm accounting and process logs before assuming the job is stuck;
- use `/dev/shm` only for disposable driver temporaries;
- allow the Marmic site profile to stage process work through compute-node
  scratch;
- avoid relocating the Nextflow cache during a run; and
- preserve failed work directories until the cause is understood and resume has
  been tested.

Fail loudly on annotation conflicts, ambiguous MTZ observation arrays, invalid
Free-R selection, missing inputs, or contract violations. A scientific no-hit is
a valid completed outcome, but an execution or input-contract failure is not.
