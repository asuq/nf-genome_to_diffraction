# Local-Marmic smoke-test feedback loop

## Purpose and boundary

Version 1 runs the repository's complete foundation check on Marmic through one
fixed Slurm profile. Local Git remains the sole source of truth. The HPC fetches
an exact pushed commit, creates an isolated read-only checkout, runs tests, and
returns diagnostics. It never edits or pushes source.

The reviewed local application is the routine approval boundary. It may request
only `deploy-tools`, `stage`, `submit`, `status`, `wait`, `logs`, `collect`, or
`cancel` from the fixed remote dispatcher. Raw SSH, file-transfer tools,
scheduler commands, and `clean` must not receive persistent automatic approval.

The smoke job uses partition `slurm`, 2 CPUs, 8 GB memory, and a 45-minute
walltime. Only one managed smoke job may be active. Queue waiting stops after 30
minutes, execution waiting stops after 45 minutes, and neither timeout silently
cancels a job. The caller must inspect status and cancel the recorded job when
appropriate.

## Filesystem and execution model

The remote dispatcher is installed under an approved run root with this layout:

```text
RUN_ROOT/
|-- _cache/git/nf-genome_to_diffraction.git/
|-- _cache/pixi/
|-- _locks/
|-- _tooling/
|   |-- deployed-tools.json
|   |-- nf-gtd-hpc-remote
|   |-- nf-gtd-hpc-smoke-job
|   `-- pixi.path
`-- runs/RUN_ID/
    |-- source/
    |-- state/
    |-- logs/
    |-- artifacts/
    |-- manifest.json
    `-- events.jsonl
```

Each staged source tree is detached at one full commit SHA, includes the pinned
`nf-helper` submodule, and is made read-only. The Slurm job copies that source to
`SLURM_TMPDIR` when supplied, otherwise `/dev/shm`, and materialises the locked
Pixi `default` environment there. Only the shared Pixi package cache, logs, and
run records use durable storage. Disposable scratch is removed by the job; the
durable run is retained until explicitly cleaned.

## Build and reviewed installation

Run the local checks before building:

```bash
pixi run check
pixi run build-hpc-test
```

The build command writes the ignored `dist/nf-gtd-hpc-test` zipapp and prints its
Python interpreter and SHA-256. Review the tracked controller and remote scripts,
then install immutable copies outside the writable checkout:

```bash
mkdir -p "$HOME/.local/bin"
install -m 0555 dist/nf-gtd-hpc-test "$HOME/.local/bin/nf-gtd-hpc-test"
shasum -a 256 "$HOME/.local/bin/nf-gtd-hpc-test"
```

An existing installation that predates `deploy-tools` needs one manually
reviewed bootstrap replacement. This is the only upgrade that needs raw SSH;
do not persist an approval for that command. Once the new dispatcher is active,
all later remote-tool upgrades use the fixed operation described below.

Resolve the independent PATH-installed Pixi once and store only the absolute
executable path:

```bash
type -P pixi
pixi --version
type -P pixi > "RUN_ROOT/_tooling/pixi.path"
chmod 0600 "RUN_ROOT/_tooling/pixi.path"
```

`RUN_ROOT` above is a placeholder, not a literal path. Pixi must report 0.74.0.
The dispatcher refuses another version. Updating the installed local controller
requires another review, immutable build, checksum, and local installation.

## Local configuration

Copy [the configuration example](../conf/hpc-test.example.json) to the
user-controlled default location:

```text
~/.config/nf-gtd-hpc-test/config.json
```

Replace all placeholders with absolute paths. The local state root must be
exactly `<repository>/.untracked/hpc-test`. The remote dispatcher path must name
the installed `nf-gtd-hpc-remote` under the approved run root. The configuration
is intentionally outside Git because it contains account- and site-specific
paths.

## Operations

Every successful command prints one JSON object to standard output. Structured
or human diagnostics use standard error, so callers may parse stdout safely.
Use `--log-format json` for JSON diagnostic logs and `--no-progress` to suppress
terminal progress bars.

```bash
nf-gtd-hpc-test deploy-tools --revision HEAD
nf-gtd-hpc-test stage smoke --revision HEAD
nf-gtd-hpc-test submit smoke --run-id RUN_ID
nf-gtd-hpc-test status --run-id RUN_ID
nf-gtd-hpc-test wait --run-id RUN_ID
nf-gtd-hpc-test logs --run-id RUN_ID --tail 200
nf-gtd-hpc-test collect --run-id RUN_ID
nf-gtd-hpc-test cancel --run-id RUN_ID
```

`deploy-tools` first requires a clean local worktree. It resolves the exact Git
commit, reads only `bootstrap/nf-gtd-hpc-remote` and
`bootstrap/nf-gtd-hpc-smoke-job`, and calculates their SHA-256 values without
accepting a payload or remote path from the caller. The remote side fetches the
private bare mirror, requires the commit to be reachable from `origin/main`,
extracts only those two fixed paths, rechecks both digests, runs `bash -n`, and
refuses a dispatcher that would remove `deploy-tools`. It preserves the old
copies until both mode-`0555` replacements and the atomic
`_tooling/deployed-tools.json` record have been verified. A failure before that
point leaves the installed pair unchanged or restores it from the preserved
copies.

`stage` refuses a dirty worktree, a non-full revision other than `HEAD`, a commit
unavailable from the private mirror, a changed Pixi lock, or a submodule mismatch.
Local ownership records live under `.untracked/hpc-test/RUN_ID/`; another run ID
cannot be guessed through path syntax or substituted for the recorded Slurm job.

For an evidence-backed source fix, commit and push the clean change, then use the
prior run as the bounded feedback parent:

```bash
nf-gtd-hpc-test stage smoke --revision HEAD --parent-run PREVIOUS_RUN_ID
```

The initial run plus five fixes are allowed. A third attempt after two identical
failure signatures is refused pending manual diagnosis.

## Results and failure interpretation

Each remote run records the Git and `nf-helper` commits, Pixi executable/version,
Pixi-lock checksum, timestamps, scheduler job ID/state, exit status, logs, and a
structured job result. `collect` accepts regular files from a fixed whitelist,
rejects traversal and symlinks, limits each file to 20 MiB and the total to 100
MiB, and writes locally below the owned run directory.

Failure classes are:

- `success`: all foundation checks passed;
- `software_failure`: the job detected unexpected source mutation or application
  behaviour outside a test assertion;
- `test_failure`: `pixi run check` failed;
- `scheduler_rejection` or `queue_timeout`: scheduling did not start normally;
- `node_failure`: Slurm reported a failed node;
- `environment_failure`: Pixi, resources, walltime, or runtime preparation failed;
- `filesystem_failure` or `transfer_failure`: staging, storage, Git, submodule, or
  artefact transfer failed;
- `wrapper_failure`: an identifier, ownership, state, or safety invariant failed;
- `unknown_failure`: evidence is insufficient for a narrower classification.

Do not modify source for scheduler, node, environment, filesystem, transfer, or
ambiguous failures unless logs demonstrate a software cause.

## Cleanup and Codex approval

Cleanup is deliberately separate and destructive:

```bash
nf-gtd-hpc-test clean --run-id RUN_ID --confirm RUN_ID
```

It refuses an active job, requires the local ownership record and exact repeated
run ID, resolves the target below the run root, and deletes only that run. Never
include `clean` in a persistent Codex allow rule.

After installing and checksumming the immutable local application, add allow
rules only for its absolute path followed by `deploy-tools`, `stage`, `submit`,
`status`, `wait`, `logs`, `collect`, or `cancel`. Keep raw SSH, transfer tools,
Slurm commands, and the wrapper's `clean` operation approval-gated.

Resolve the installed path literally; shell variables and `~` are not valid rule
substitutes. The intended Codex rule shape is:

```python
prefix_rule(
    pattern = [
        "/absolute/path/to/installed/nf-gtd-hpc-test",
        ["deploy-tools", "stage", "submit", "status", "wait", "logs", "collect", "cancel"],
    ],
    decision = "allow",
    justification = "Allow only the reviewed nf-genome_to_diffraction HPC interface.",
    match = [
        "/absolute/path/to/installed/nf-gtd-hpc-test deploy-tools --revision HEAD",
        "/absolute/path/to/installed/nf-gtd-hpc-test status --run-id RUN_ID",
    ],
    not_match = [
        "/absolute/path/to/installed/nf-gtd-hpc-test clean --run-id RUN_ID --confirm RUN_ID",
        "ssh approved-hpc-alias",
    ],
)
```

Verify the active rule independently in both Codex App and Codex CLI. Routine
wrapper calls should not prompt; `clean` and raw SSH must still prompt.

## Deferred integration

This interface runs foundation checks only. The real organism/diffraction pair,
database preparation, Phenix, Task 05 pilot, full runs, and benchmarks are not
part of this profile. Add the real integration profile only after the scheduled
smoke test passes and its provenance and collected result are verified.
