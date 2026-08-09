# Local-Marmic fixed-profile feedback loop

## Purpose and boundary

The interface has two routine closed profiles plus one separately gated
database-administration profile. Local Git remains the sole source of truth.
Marmic fetches an exact pushed commit, creates an isolated read-only checkout,
runs only the selected reviewed job body, and returns bounded diagnostics. It
never edits or pushes source.

| Profile | Fixed operation | Scientific meaning |
| --- | --- | --- |
| `smoke` | Locked `pixi run check` | Software/environment foundation only |
| `p0` | Real Phenix verification, bounded anchored database revalidation, all-three-crystal Task 05 run, and cached resume | M0 execution evidence only; downstream identity search remains deferred |
| `database` | Fixed route/capacity preflight, all-resource preparation, and anchored full verification | Shared database administration only; no pipeline or protein-identification claim |

The reviewed local application is the routine approval boundary. Persistent
rules may cover only `deploy-tools`, `readiness`, `stage`, `submit`, `status`,
`wait`, `logs`, `collect`, or `cancel`. The distinct `database-stage` and
`database-submit` start commands deliberately remain approval-gated. Raw SSH,
file-transfer tools, scheduler commands, and `clean` must not receive persistent
automatic approval.

The routine drivers use partition `slurm`, 2 CPUs, 8 GB memory, and a 45-minute
walltime. The database driver uses the same partition with 8 CPUs, 64 GB, and a
48-hour walltime. Only one managed job may be active across all profiles. Queue
waiting stops after 30 minutes. Local execution waiting is capped at 45 minutes
for routine jobs and 48 hours for database administration; neither timeout
silently cancels a job. The caller must inspect status and cancel the recorded
job when appropriate.

Every SSH invocation is also independently bounded: connection setup allows one
attempt with a 15-second connect timeout, routine dispatcher operations have a
60-second hard client timeout, and fixed artefact collection has a 10-minute
hard client timeout. Server-alive probes detect an unresponsive established
connection. A timeout is reported as `transfer_failure`; the controller does not
fall back to raw SSH, infer that a remote job failed, or cancel it implicitly.

## Filesystem and execution model

The remote dispatcher is installed under an approved run root with this layout:

```text
RUN_ROOT/
|-- _cache/git/nf-genome_to_diffraction.git/
|-- _cache/pixi/
|-- _config/database.paths
|-- _config/p0.paths
|-- _locks/
|-- _tooling/
|   |-- deployed-tools.json
|   |-- nf-gtd-hpc-remote
|   |-- nf-gtd-hpc-smoke-job
|   `-- pixi.path
`-- runs/RUN_ID/
    |-- source/
    |-- environment/.pixi/
    |-- cache/
    |-- execution/
    |-- state/
    |-- logs/
    |-- artifacts/
    |-- manifest.json
    `-- events.jsonl
```

Each staged source tree is detached at one full commit SHA, includes the pinned
`nf-helper` submodule, and is made read-only. A per-run locked Pixi environment
is attached outside that source tree.

The foundation smoke copies source to `SLURM_TMPDIR` or `/dev/shm`. P0 keeps the
source, Pixi environment, Nextflow cache/work directory, logs, and results on
shared durable storage because child Slurm nodes cannot see the driver's
`/dev/shm`. Only P0 driver temporaries use `/dev/shm`; `nf-helper` stages each
Nextflow process through compute-node `/scratch`. Disposable driver scratch is
removed by the job, while the durable run is retained until explicitly cleaned.

Database administration is stricter: the compute node must expose an explicit,
canonical, non-symlink `SLURM_TMPDIR` on a filesystem distinct from the durable
database root. The job rejects a missing value, `/dev/shm`, an overlapping path,
or a shared device before its fixed preflight can start a large payload. All
database command scratch lives below one job-owned child, and the finaliser
removes only that child. Failed durable resource staging is intentionally
retained and blocks an automatic second database-sized attempt.

## Build and reviewed installation

Run the local checks before building:

```bash
pixi run check
pixi run build-hpc-test
```

The build command writes the ignored `dist/nf-gtd-hpc-test` zipapp and prints its
Python interpreter and SHA-256. ZIP members use canonical order, timestamps,
permissions, and compression, so repeated builds from the same source and
locked interpreter path are byte-identical. Review the tracked controller and
remote scripts, then install immutable copies outside the writable checkout:

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
nf-gtd-hpc-test readiness p0
nf-gtd-hpc-test stage smoke --revision HEAD
nf-gtd-hpc-test submit smoke --run-id RUN_ID
nf-gtd-hpc-test status --run-id RUN_ID
nf-gtd-hpc-test wait --run-id RUN_ID
nf-gtd-hpc-test logs --run-id RUN_ID --tail 200
nf-gtd-hpc-test collect --run-id RUN_ID
nf-gtd-hpc-test cancel --run-id RUN_ID
```

Use the same routine operations with `p0` only after its fixed site
configuration has been reviewed:

```bash
nf-gtd-hpc-test stage p0 --revision HEAD
nf-gtd-hpc-test submit p0 --run-id RUN_ID
nf-gtd-hpc-test wait --run-id RUN_ID
nf-gtd-hpc-test logs --run-id RUN_ID --tail 200
nf-gtd-hpc-test collect --run-id RUN_ID
```

`readiness p0` is a fixed, read-only prerequisite inspection. It accepts no
path, revision, run ID, or shell fragment; creates no run; and submits no job.
Its JSON reports the exact Pixi-version status and a sanitised P0 configuration
status plus checksum, but never returns configured site paths. `ready: true`
means only that staging prerequisites exist. The staged job independently
revalidates the configuration and still must verify real Phenix and databases.

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

The initial run plus five fixes are allowed per feedback chain. A third attempt
after two identical failure signatures is refused pending manual diagnosis.

## P0 real-site profile

Create `_config/p0.paths` below the configured remote run root from the tracked
[example](../conf/hpc-p0.paths.example). The file has exactly seven non-empty
lines and no comments: allowed site root, catalogue manifest, crystal manifest,
pipeline configuration, database root, frozen database manifest, and Phenix
manifest. It is user-owned, mode `0600`, untracked, and contains the real site
paths.

P0 accepts none of those paths on the local command line. `stage p0` records the
file's SHA-256; the job refuses execution if it changes. Every configured child
must be a canonical non-symlink path below the first-line root. The job then:

1. installs the frozen Linux `hpc` Pixi environment;
2. re-verifies every required Phenix command and preserves the verification log;
3. fingerprints the frozen database manifest during staging, then runs database
   `verify-only` for PDB Foldseek, ProstT5, PDB sequences, and the coordinate
   cache, checking inventory metadata and comparing the exact resource records
   with that trust anchor; bounded MMseqs2/ProstT5/Foldseek smokes rerun locally,
   deterministic result evidence is compared, a structured
   `database_manifest.p0-revalidated.verification.json` record explicitly marks
   `inventory_metadata_and_functional_smoke`, and the previously cached public
   PDB coordinate is revalidated without a download;
4. runs `main.nf -profile marmic` with real Xtriage for the configured crystals;
5. repeats the identical command with `-resume`; and
6. fails unless all deterministic processes in the second trace are `CACHED`.

It retains complete P0 results on Marmic but collects only fixed small reports,
manifests, traces, and logs. A successful P0 means
`task05_preflight_complete_downstream_deferred`; it never claims a protein
identity or clean crystallographic acceptance merely because the job exited 0.
It also does not claim that every byte of a terabyte-scale database was rehashed
during the 45-minute allocation.

## Database administration boundary

Full preparation and `verify-only --full-verify` use separate, long-running
database-administration start commands. They may contact fixed public
Foldseek/RCSB routes and mutate a large shared root, so routine `stage` and
`submit` explicitly reject the `database` profile. Do not add the two start
commands to persistent Codex rules.

Create `_config/database.paths` below the configured remote run root from the
tracked [example](../conf/hpc-database.paths.example). It is user-owned, mode
`0600`, outside Git, and has exactly seven lines with no comments:

1. canonical user-owned allowed administration root;
2. existing user-owned durable database root below line 1;
3. new immutable manifest output path in a user-owned directory below line 1;
4. total project storage cap in bytes, at most `2000000000000`;
5. durable free-space reserve in bytes;
6. free build capacity required before downloading; and
7. compute scratch free-space reserve in bytes.

Byte counts must be canonical decimal integers without leading zeroes. The
tracked example deliberately uses a 1.8 TB project cap and 200 GB reserves on a
2 TB allocation; these remain conservative first-run assumptions, not evidence
of the real active/failed/immutable-copy size. The
manifest path must not exist when readiness and staging run. Use a new dated
path for a later intentional rebuild; the fixed driver never overwrites an
existing trust anchor. Actual site paths remain only in this external file.

First perform the path-free readiness check. It reports sanitised Pixi and
configuration statuses and the configuration SHA-256, but no site paths and no
compute-node claim:

```bash
nf-gtd-hpc-test database-readiness
```

Review the exact commit and external configuration, then explicitly approve the
two start commands individually:

```bash
nf-gtd-hpc-test database-stage --revision HEAD
nf-gtd-hpc-test database-submit --run-id RUN_ID
nf-gtd-hpc-test wait --run-id RUN_ID
nf-gtd-hpc-test logs --run-id RUN_ID --tail 200
nf-gtd-hpc-test collect --run-id RUN_ID
```

`database-stage` fingerprints the external configuration. Execution refuses a
post-stage edit. `database-submit` has fixed Slurm resources and accepts no URL,
path, resource, or shell argument. On the compute node the job requires explicit
distinct scratch, installs the frozen `hpc` Pixi environment, and runs the fixed
preflight. That preflight checks available capacity, scratch headroom,
Foldseek/MMseqs2/aria2 versions, and only the pinned PDB, ProstT5, SEQRES, and
1UBQ routes. Route checks are one-byte HTTPS range requests because the
Foldseek worker serves GET redirects but returns 404 to HEAD-style aria2 dry
runs. The preflight rejects an unsupported status, malformed range metadata,
invalid length, oversized ranged body, or non-HTTPS redirect and records
`large_payload_started: false`. The bounded exception is an HTTP-200 streaming
response: the client reads exactly one byte, closes immediately, and records an
unknown representation size when the server supplies no length.

Only after preflight passes does the job prepare PDB Foldseek, PDB sequence,
ProstT5, and coordinate-cache resources under the durable root. `aria2c` is
wrapped with `--no-conf=true`, so a user configuration cannot silently change
the reviewed transfer behaviour. Success requires a frozen manifest checksum
and a second anchored `--verify-only --full-verify` pass. Fixed small manifests,
preflight evidence, and logs are collectable; database payloads stay on Marmic.
There is no automatic retry or cleanup of retained failed durable staging.

## Results and failure interpretation

Each remote run records the Git and `nf-helper` commits, Pixi executable/version,
Pixi-lock checksum, timestamps, scheduler job ID/state, exit status, logs, and a
structured job result. `collect` accepts regular files from a fixed whitelist,
rejects traversal and symlinks, limits each file to 20 MiB and the total to 100
MiB, and writes locally below the owned run directory.

Failure classes are:

- `success`: the selected fixed profile completed its explicit gate checks;
- `software_failure`: the job detected unexpected source mutation or application
  behaviour outside a test assertion;
- `test_failure`: the foundation checks or fixed P0 workflow/cache gate failed;
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
rules only for its absolute path followed by `deploy-tools`, `readiness`, `stage`,
`submit`, `status`, `wait`, `logs`, `collect`, or `cancel`. Keep raw SSH, transfer tools,
Slurm commands, and the wrapper's `clean` operation approval-gated.

Resolve the installed path literally; shell variables and `~` are not valid rule
substitutes. The intended Codex rule shape is:

```python
prefix_rule(
    pattern = [
        "/absolute/path/to/installed/nf-gtd-hpc-test",
        ["deploy-tools", "readiness", "stage", "submit", "status", "wait", "logs", "collect", "cancel"],
    ],
    decision = "allow",
    justification = "Allow only the reviewed nf-genome_to_diffraction HPC interface.",
    match = [
        "/absolute/path/to/installed/nf-gtd-hpc-test deploy-tools --revision HEAD",
        "/absolute/path/to/installed/nf-gtd-hpc-test readiness p0",
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

For a recoverable inventory of every local file and approval changed by this
integration, plus disable and restoration commands, use the
[local settings and rollback guide](local-settings-and-rollback.md). Removing
local settings does not authorise deletion of shared Marmic state.

## Deferred scope

P0 consumes already prepared real Phenix and database resources; it does not
install licensed software, download databases, accept arbitrary Nextflow
parameters, or expose raw SSH. Structural discovery, MR, refinement, map-based
sequence work, full pilots, and benchmarks require their later roadmap gates.
