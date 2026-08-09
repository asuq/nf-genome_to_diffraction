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
| `database` | Login-node source staging, offline capacity preflight, all-resource preparation, and anchored full verification | Shared database administration only; no pipeline or protein-identification claim |

The reviewed local application is the routine approval boundary. Persistent
rules may cover only `deploy-tools`, `readiness`, `stage`, `submit`, `status`,
`wait`, `logs`, `collect`, or `cancel`. The distinct `database-stage` and
`database-submit` start commands deliberately remain approval-gated. Raw SSH,
file-transfer tools, scheduler commands, and `clean` must not receive persistent
automatic approval.

The routine drivers use partition `slurm`, 2 CPUs, 8 GB memory, and a 45-minute
walltime. The database driver uses the same partition with 100 CPUs, 2,000 GB,
and a 48-hour walltime. The large memory request supplies `/dev/shm` build space;
the node's full 4 TB is not requested because it would not accelerate serial
network, checksum, or copy-back I/O. Only one managed job may be active across
all profiles. Queue
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

Database administration has two deliberately separate phases. The login-node
`database-stage` operation installs the frozen environment and sequentially
downloads only the five fixed public inputs directly into immutable durable
storage. This work is network/I/O-bound, uses no Slurm allocation, and retains
validator-bound partial state plus structured progress logs. While it runs,
`status` reports non-terminal `STAGING` rather than inventing a scheduler state,
and `logs` tails `database-source-stage.log`; after submission the same commands
switch to the recorded Slurm state and compute log. If a database command fails,
`logs` also includes a bounded tail from the exact command log cited by that
compute log. This diagnostic path is derived remotely rather than accepted from
the caller, and must be an owned regular file directly below the configured
database log directory with a fixed generated filename. The combined response
never exceeds the requested `--tail` line count. The compute phase creates a
unique mode-0700 parent directly below `/dev/shm`, requires that child to be
owned and on a filesystem distinct from the durable database root, and removes
it at finalisation. All database execution state lives below that job-owned
parent. The compute job verifies the
source bundle byte-for-byte and maps Foldseek's three fixed URLs to local
objects by shadowing its aria2/curl/wget fallback chain with staging-confined,
allow-listed local-copy shims; any other HTTP(S) request fails without invoking
a network client.
Foldseek and MMseqs2 output, extraction files, and indexing workspace stay in
the job-owned `/dev/shm` tree while a resource is built. Scratch and durable
bytes jointly count towards the configured project cap. Each completed resource
is inventoried in memory-backed scratch, copied once to empty durable staging
with byte progress, fully rehashed on the destination, and atomically published.
Failed copy-back staging is intentionally retained and blocks an automatic
second extraction/index attempt.

This root matches the Marmic site profile in the pinned `nf-helper` submodule:
Slurm processes use `/scratch/$USER`, copy declared outputs back to shared work,
and export the submitting environment. The checked Marmic profiles in
`nf-annotation`, `nf-busco_phylogenomics`, and `nf-sra_screen` use the same
configuration. Database administration does not rely on Nextflow's `/scratch`
setting: its fixed job creates and validates its own narrower `/dev/shm` child.

## Build and reviewed installation

Run the local checks before building:

```bash
pixi run check
pixi run build-hpc-test
```

The build command writes the ignored `dist/nf-gtd-hpc-test` zipapp and prints its
Python interpreter and SHA-256. It embeds the authoritative JSON Schemas needed
to validate private typed manifests, so the installed controller does not rely
on files beside the executable. ZIP members use canonical order, timestamps,
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

If a collected database run retains extraction or indexing staging after a
software failure or explicit cancellation, review its main and cited command
logs first. The separately approval-gated recovery operation accepts no path and
requires the exact owned run ID twice:

```bash
nf-gtd-hpc-test database-archive-failed \
  --run-id RUN_ID \
  --confirm RUN_ID
```

The dispatcher requires either a completed `software_failure` or a
`cancel_requested` run whose recorded Slurm job is absent from the live queue
and independently reported `CANCELLED` by accounting. It also requires the
unchanged external configuration fingerprint, fixed database profile, and an
owner-controlled regular directory cited by the structured run log directly
below one recognised resource root. Failed runs supply the emitted
`staging_path`; cancelled runs use the last fixed command's sole `write_roots`
entry. Existing symbolic links are preserved only when their resolved targets
remain inside that same staging tree. It rejects active jobs, broken or escaping
links, other non-file entries, foreign ownership, and escaped paths. Success
atomically renames the directory to a run-qualified `.reviewed-*` archive and
records its original path, destination, regular-file count, symbolic-link
count, and regular-file bytes. It deletes no evidence but releases the
resource's `.failed` or orphaned active build guard. Never run this before
collection and diagnosis, and do not include it in automatic feedback or a
persistent approval rule.

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

First prepare the fixed pilot inputs through the reviewed transfer boundary.
Copy [the two-checksum example](../conf/hpc-p0-inputs.example.json) to
`.untracked/m0-qualification/p0-inputs.json`, replace the zero placeholders with
the exact qualified database-manifest and Phenix-manifest SHA-256 values, and
review the file. The catalogue, crystal, pipeline configuration, and frozen
input inventory remain at their fixed `.untracked/m0-qualification/` locations;
scientific data must remain below the project `data/` directory.

Compute the specification checksum, then stage it. The second command builds a
deterministic archive in `/tmp`, validates all seven scientific-file sizes and
SHA-256 values against the frozen inventory, rewrites workstation paths, and
streams the archive through the fixed dispatcher. It accepts no remote path.

```bash
shasum -a 256 .untracked/m0-qualification/p0-inputs.json
nf-gtd-hpc-test p0-inputs-stage \
  --confirm-spec-sha256 SPEC_SHA256
```

The remote operation writes only below its fixed content-addressed
`_p0_inputs/` root. It verifies the archive checksum, exact 12-file payload
layout, regular-file ownership, hard-link count, per-file inventory, qualified
database anchor, and exactly one Phenix manifest with the approved checksum.
The received archive and four identity sidecars are retained with that payload,
giving 17 regular files in the published tree. Files become mode `0444` and
directories mode `0555`. Repeating the same operation rehashes the retained
archive, the archived inventory, and every extracted payload before reusing the
tree; a fixed dispatcher lock serialises concurrent publication attempts, and a
changed object cannot replace or silently reuse an existing identity.
Machine JSON on stdout reports only identities and the local candidate location.
Progress and diagnostics use `tqdm` and structured logging on stderr.

Success creates the private local candidate
`.untracked/m0-qualification/hpc-p0.paths`. Review its exactly seven non-empty
LF-terminated lines: owner-controlled site root, rewritten catalogue manifest,
rewritten crystal manifest, pipeline configuration, database root, frozen
database manifest, and Phenix manifest. This file contains real site paths and
must never be committed. The operation refuses to overwrite a different local
candidate.

Compute the candidate checksum separately, review the seven paths, and install
it through the create-only configuration boundary:

```bash
shasum -a 256 .untracked/m0-qualification/hpc-p0.paths
nf-gtd-hpc-test p0-configure \
  --paths-file .untracked/m0-qualification/hpc-p0.paths \
  --confirm-sha256 SHA256
nf-gtd-hpc-test readiness p0
```

The local controller requires an owned mode-`0600` regular file and rejects
symlinks, non-ASCII or non-canonical text, unsafe path characters, and a
confirmation that differs from the exact payload checksum. The dispatcher
decodes at most 4 KiB into an owner-controlled
temporary file, independently verifies its checksum, mode, line count, path
containment, and live inputs, then atomically creates `_config/p0.paths` with
mode `0600`. It refuses to overwrite an existing configuration and returns no
configured paths. This operation is a one-time external setting change and is
not suitable for persistent command approval.

`p0-inputs-stage` is likewise a separately approved data-transfer operation,
not a routine persistent approval. It cannot read arbitrary local files: the
controller fixes the private manifest/inventory paths, requires the seven
referenced files to resolve below the project `data/` directory, and rejects
symlinks or inventory drift. It never uploads SSH material, Git configuration,
credentials, other project files, or biological sequences not named by the
frozen manifests. No remote service receives the biological inputs; bytes travel
only over the configured private SSH endpoint.

`stage p0` records the file's SHA-256; the job refuses execution if it changes.
Every configured child must be a canonical non-symlink path below the
first-line root. The input-staging operation obtains that root from the already
reviewed dispatcher and database roots rather than from `$HOME`: it walks only
to their nearest canonical, owner-controlled common ancestor. This supports
sites where login-shell, workflow, and database storage use different lexical
paths without granting a caller path authority. Because these inputs are
read-only and no cleanup target is derived from this root, it may be the
operator-owned durable site directory; `/`, a foreign-owned directory, or a
symlink remains invalid. The job then:

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
database-administration start commands. `database-stage` contacts only the
fixed public Foldseek/RCSB routes from the login node and writes directly to a
large shared root; the Slurm job is network-free. Routine `stage` and `submit`
explicitly reject the `database` profile. Keep these mutating start operations
separate from the seven routine smoke-test operations.

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
2 TB storage allocation; these remain conservative assumptions, not evidence
of the real active/failed/immutable-copy size. The five observed compressed
inputs total about 4.62 GB; extracted resources, indices, failed staging, and
temporary-copy peaks still require measurement. The reviewed Marmic first-run
configuration therefore uses an 800 GB cap, 200 GB durable reserve, 600 GB
pre-download gate, and 200 GB scratch reserve. Separately, the Slurm job requests
2,000 GB of RAM so this bounded payload and temporary overhead fit in `/dev/shm`.
The manifest path must not exist
when readiness and staging run. Use a new dated path for a later intentional
rebuild; the fixed driver never overwrites an existing trust anchor. Actual site
paths remain only in this external file.

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
post-stage edit and materialises the frozen per-run `hpc` Pixi environment on
the login node. It then downloads the five admitted inputs sequentially and
directly to a content-addressed source bundle below the durable database root,
with a bounded six-hour transport timeout and retained environment/source logs.
Every source records requested and effective URLs, validators, size, and full
SHA-256. Per-source journals reuse completed inputs and preserve a validated
partial download for an interrupted transfer.

`database-submit` has fixed 100-CPU/2,000-GB/48-hour Slurm resources and accepts
no URL, path, resource, or shell argument. On the compute node the job requires
distinct `/dev/shm` scratch,
verifies the staged environment with Pixi `--offline`, recomputes all bundle
checksums, and runs the fixed preflight. That preflight checks available
capacity, scratch headroom, and Foldseek/MMseqs2/aria2 versions without making
any network request. Version probes have a fixed three-minute limit because
Marmic NFS-cold executable startup has exceeded 30 seconds; structured start,
completion, and elapsed-time records distinguish slow startup from a hung tool.
Allow-listing `aria2c`, `curl`, and `wget` shims serve only Foldseek's exact
three admitted HTTPS URLs from the verified local files and reject all other
HTTP(S) input. They do not invoke a network client: each accepts the pinned
downloader's output-file conventions, validates that the destination remains
inside the current resource staging directory, and copies the matching bundle
object. This covers Foldseek 10.941cd33's downloader fallback chain without
depending on compute-node egress. The bundled SEQRES and 1UBQ files are consumed
directly.

Only after preflight passes does the job prepare PDB Foldseek, PDB sequence, and
ProstT5 resources in job-owned `/dev/shm`; the small coordinate cache remains a
direct durable administrative resource. No downloader user configuration is
consulted during offline extraction. Each large resource is copied once to
durable staging and must pass destination checksums before publication. Success requires a
frozen manifest checksum and a second anchored `--verify-only --full-verify`
pass. Fixed small manifests,
preflight evidence, and logs are collectable; database payloads stay on Marmic.
Source transfers are resumable. Failed extraction or index staging is retained
and blocks another build until explicit operator review; it is never deleted or
blindly retried by the fixed driver. The archive operation above is a manual,
recoverable release of that guard, not cleanup.

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
Slurm commands, `p0-inputs-stage`, `p0-configure`, and the wrapper's `clean`
operation approval-gated.

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
