# Local-Marmic fixed-profile feedback loop

## Purpose and boundary

The interface has six routine closed profiles plus one separately gated
database-administration profile. Local Git remains the sole source of truth.
Marmic fetches an exact pushed commit, creates an isolated read-only checkout,
runs only the selected reviewed job body, and returns bounded diagnostics. It
never edits or pushes source.

| Profile | Fixed operation | Scientific meaning |
| --- | --- | --- |
| `smoke` | Locked `pixi run check` | Software/environment foundation only |
| `p0` | Real Phenix verification, bounded anchored database revalidation, all-three-crystal Task 05 run, and cached resume | M0 execution evidence only; downstream identity search remains deferred |
| `p1` | Frozen catalogue import, login-node exact-AFDB pilot retrieval, catalogue-wide direct PDB search, deterministic 128-query ProstT5/Foldseek slice, Phenix predicted-model preparation, cached resumes, and tracked 8OOX qualification | M1 plus the first M2 vertical slice only; deferred ProstT5 queries remain uninterpreted and no crystal identity or MR is claimed |
| `p2` | Replay the checksum-frozen P0/P1 evidence, build the exact-predicted bounded funnel, and run one CD6 first-copy Phaser hypothesis plus cached resume | Smallest M3 real-feedback slice only; a hit remains provisional and a no-hit is a completed scientific result |
| `p2-diverse` | Stage a bounded direct-PDB search and coordinate set on the login node, replay P0/P1, prepare cleaned PDB models offline, and run at most 25 multi-source CD6 first-copy hypotheses plus cached resumes | First real-candidate M2/M3 feedback slice; it does not identify a protein or authorise additional-copy placement |
| `p2-control` | Prepare checksum-frozen 8OOX inputs, build the exact 8OOW positive and unrelated 1UBQ negative, and run both through the production first-copy Phaser adapter plus cached resume | M3 score/packing/control separation only; it does not calibrate a universal success threshold or validate the full ASU |
| `database` | Login-node source staging, offline capacity preflight, all-resource preparation, and anchored full verification | Shared database administration only; no pipeline or protein-identification claim |

The reviewed local application is the routine approval boundary. Persistent
rules may cover only `deploy-tools`, `readiness`, `stage`, `submit`, `status`,
`wait`, `logs`, `collect`, `review-collect`, or `cancel`. The distinct `database-stage` and
`database-submit` start commands deliberately remain approval-gated. Raw SSH,
file-transfer tools, scheduler commands, and `clean` must not receive persistent
automatic approval.

The routine drivers use partition `slurm`, 2 CPUs, and 8 GB memory. Foundation
smoke has a 45-minute walltime; P0 has a 24-hour scheduler margin, while P1,
P2, P2-diverse, and P2-control use
the Marmic site's 1,000-hour maximum margin because NFS-cold executable and
database access are not predictably bounded. The direct PDB
`process_search` child requests 16 CPUs, 64 GB, and 24 hours. The distinct
`process_prostt5_search` child requests 100 CPUs, 2,000 GB, and the same
1,000-hour site margin because catalogue-scale sequence-to-3Di inference is the
memory-intensive step. The small outer allocation only coordinates those children. The database driver
uses the same partition with 100 CPUs, 2,000 GB, and a 48-hour walltime. The
large memory request supplies `/dev/shm` build space;
the node's full 4 TB is not requested because it would not accelerate serial
network, checksum, or copy-back I/O. Only one managed job may be active across
all profiles. Queue
waiting stops after 30 minutes. Local execution waiting uses 45-minute,
24-hour, 1,000-hour, 1,000-hour, 1,000-hour, 1,000-hour, and 48-hour margins for
smoke, P0, P1, P2, P2-diverse, P2-control, and database jobs; none of these
limits silently cancels a job. The caller must inspect status and cancel the
recorded job when appropriate.

Every SSH invocation is also independently bounded: connection setup allows one
attempt with a 15-second connect timeout, routine dispatcher operations have a
45-minute conservative client margin for NFS-cold login-node commands, and
fixed artefact collection has a 10-minute hard client timeout. The larger,
checksum-gated review-asset collection has a 30-minute transport margin.
Server-alive
probes detect an unresponsive established connection. A timeout is reported as
`transfer_failure`; the controller does not fall back to raw SSH, infer that a
remote job failed, or cancel it implicitly. The 45-minute margin replaced the
original 60-second bound after a healthy alternate login node accepted SSH but
could not complete fixed P1 readiness before that short deadline.

### Real-data monitoring cadence

Real biological-data profiles may run for hours. After submission, confirm the
owned job ID, structured `RUNNING` state, and current fixed phase once. If the
job is then expected to remain quiet, stop only the local `wait` client and
schedule this development task to reactivate after 30 minutes. On reactivation:

1. run the approved structured `status` operation;
2. if the job remains non-terminal, record any meaningful phase change and
   reactivate again after 30 minutes;
3. if the job is terminal, inspect bounded `logs`, run `collect`, and classify
   the retained result before changing source; and
4. never infer failure from silence, issue implicit `cancel`, or run `clean`.

Before each pause or hand-off, update the tracked development-loop journal with
the current immutable commit, job state, accomplished checkpoints, unresolved
work, and exact reactivation action. Run IDs and machine-specific paths remain
in ignored local evidence rather than the tracked journal.

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
is attached outside that source tree. For P0, P1, P2, P2-diverse, P2-control,
and database
profiles, staging materialises that environment on the network-enabled login
node; compute jobs only verify and use it and therefore do not contact package
channels.

The foundation smoke copies source to `SLURM_TMPDIR` or `/dev/shm`. P0, P1, P2,
P2-diverse, and P2-control keep the
source, Pixi environment, Nextflow cache/work directory, logs, and results on
shared durable storage because child Slurm nodes cannot see the driver's
`/dev/shm`. Only driver temporaries use memory-backed local storage; `nf-helper` stages each
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
nf-gtd-hpc-test review-collect --run-id RUN_ID
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

After a terminal successful `p2-diverse` run has been collected, the separate
`review-collect` operation closes the M3-to-M4 human-review boundary without
accepting a caller-supplied path or candidate ID:

```bash
nf-gtd-hpc-test review-collect --run-id RUN_ID
```

The local wrapper reads the collected version-2 review manifest, verifies its
checksum and the current strict `LLG > 50` **or** `TFZ > 5` policy, and sends
only the run ID, owner token, and manifest checksum to the dispatcher. The
dispatcher independently revalidates the terminal job result, manifest,
summary, automatic eligibility, final packing, and requested placed-copy count.
For each manifest-eligible solution it returns exactly the normalised result,
resolved command, Phaser log, PDB, and MTZ named by their recorded SHA-256
digests. The manifest, run summary, and outer job result accompany those files.
No other remote files are admitted. Limits are 25 eligible candidates, 128 MiB
per file, and 512 MiB total. Local extraction rejects links, unexpected paths,
duplicates, checksum mismatches, and partial publication, and writes the verified
bundle atomically below `.untracked/hpc-test/RUN_ID/review-assets/`.

This is an evidence-transfer operation, not an approval operation. Marginal
TFZ-only candidates remain review candidates. Their raw scores, packing,
placed-copy evidence, maps, and deliberate controls must be inspected before a
reviewer creates an approval record or M4 searches additional copies.

P1 reuses that same reviewed, read-only site configuration and database
manifest. It accepts no new path or scientific parameter:

```bash
nf-gtd-hpc-test readiness p1
nf-gtd-hpc-test stage p1 --revision HEAD
nf-gtd-hpc-test submit p1 --run-id RUN_ID
nf-gtd-hpc-test wait --run-id RUN_ID
nf-gtd-hpc-test logs --run-id RUN_ID --tail 200
nf-gtd-hpc-test collect --run-id RUN_ID
```

P2 accepts no new path, crystal identifier, model, score threshold, or Phaser
argument. It is fixed to the checksum-frozen CD6 MTZ in the approved P0 bundle,
the exact predicted model produced by P1, and the tracked strict provisional
gate:

```bash
nf-gtd-hpc-test readiness p2
nf-gtd-hpc-test stage p2 --revision HEAD
nf-gtd-hpc-test submit p2 --run-id RUN_ID
nf-gtd-hpc-test wait --run-id RUN_ID
nf-gtd-hpc-test logs --run-id RUN_ID --tail 200
nf-gtd-hpc-test collect --run-id RUN_ID
```

The dispatcher resolves the MTZ directly from the P0 bundle's fixed
`manifests/` plus `inputs/` layout. It does not recursively search the qualified
site root, which avoids broad NFS metadata scans and rejects stale or ambiguous
copies.

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

`readiness p0` and `readiness p1` are fixed, read-only prerequisite inspections.
They accept no path, revision, run ID, or shell fragment, create no run, and
submit no job.
Their JSON reports the exact Pixi-version status and a sanitised P0 configuration
status plus checksum, but never returns configured site paths. `ready: true`
means only that staging prerequisites exist. The staged job independently
revalidates the configuration and still must verify real Phenix and databases.

`deploy-tools` first requires a clean local worktree. It resolves the exact Git
commit, reads only `bootstrap/nf-gtd-hpc-remote` and
`bootstrap/nf-gtd-hpc-smoke-job`, and calculates their SHA-256 values without
accepting a payload or remote path from the caller. The tracked
`bootstrap/nf-gtd-hpc-recover-tools` script is also checksum-reviewed locally.
The remote side fetches the
private bare mirror, requires the commit to be reachable from `origin/main`,
extracts only those two fixed paths, rechecks both digests, runs `bash -n`, and
refuses a dispatcher that would remove `deploy-tools`. It preserves the old
copies until both mode-`0555` replacements and the atomic
`_tooling/deployed-tools.json` record have been verified. A failure before that
point leaves the installed pair unchanged or restores it from the preserved
copies.

If and only if the installed dispatcher fails before dispatch with the exact
`environment_failure` message `base64 is unavailable`, the same local
`deploy-tools` operation passes the exact committed recovery script as the
fixed Bash program. Before transmission, the local controller requires a clean
worktree, resolves the exact 40-character commit, requires it to be contained in
the local `origin/main` tracking reference, and reads only the three fixed
committed tool paths. The two replacement scripts are streamed as one bounded
payload because Marmic's Git executable itself attempts to open the unavailable
`/dev/null`, even when its standard descriptors are regular files. The recovery
script accepts only the configured fixed dispatcher path, commit, two locally
calculated checksums, and two payload sizes of at most 2 MiB each. It reads those
exact byte counts, rejects truncation and trailing data, validates ownership,
checksums and Bash syntax, and performs the same preserved-copy rollback. Other
failure classes or messages never activate the recovery path. This avoids a
recurring raw-SSH approval while keeping the repair operation commit-, checksum-
and path-gated; normal upgrades continue through the installed dispatcher after
recovery.

The remote tools do not redirect to `/dev/null`. Marmic has returned
`Permission denied` for that device in non-interactive SSH sessions, which can
turn a successful command into a false preflight failure. The dispatcher instead
creates and validates an owned mode-`0600` `_tooling/.discard` regular file
before dispatch and uses it only for intentionally discarded command output.
Compute-job cleanup diagnostics go to the retained run log directory. The
discard file is operational state outside Git; removing the whole installed
`_tooling` directory during the documented local/HPC teardown removes it too,
and a later dispatcher call recreates it safely.

The local transport preserves the authenticated remote account's PATH so the
Marmic site-provided Git and Slurm clients remain available. It does not source
interactive startup files: `BASH_ENV` and `ENV` are cleared and the fixed
dispatcher runs through absolute `/bin/bash --noprofile --norc -p`. Pixi and
Phenix continue to use separately validated absolute paths rather than PATH.

`stage` refuses a dirty worktree, a non-full revision other than `HEAD`, a commit
unavailable from local `origin/main`, a changed Pixi lock, or a submodule
mismatch. Under normal conditions, the fixed remote dispatcher still fetches
the private mirror and creates a detached read-only clone. Marmic's current Git
binary opens `/dev/null` unconditionally at startup, and the site's device is
not accessible from non-interactive login-node sessions. If and only if normal
staging returns the exact preflight error `configured Git mirror is not bare`,
the controller creates a detached local clone from the already clean, pushed
commit, initialises the recorded `nf-helper` Gitlink, removes temporary local
repository URLs, and streams the complete checkout through fixed
`stage-archive`. The tar stream is limited to 64 MiB and bound to exact archive,
commit, Pixi-lock, and `nf-helper` checksums. The dispatcher rejects unsafe
member paths, truncation, checksum mismatches, and missing detached Git
provenance before installing the locked environment. Other stage errors never
activate this fallback. Compute-node jobs retain their independent Git commit
and clean-tree checks.

Local ownership records live under `.untracked/hpc-test/RUN_ID/`; another run
ID cannot be guessed through path syntax or substituted for the recorded Slurm
job.

For an evidence-backed source fix, commit and push the clean change, then use the
prior run as the bounded feedback parent:

```bash
nf-gtd-hpc-test stage smoke --revision HEAD --parent-run PREVIOUS_RUN_ID
```

The initial run plus five fixes are allowed per feedback chain. A failure
signature combines the fixed class, exit status, scheduler state, and a SHA-256
of the bounded approved application-log tail after normalising run IDs,
timestamps, commit hashes, job IDs, and hostnames. This distinguishes different
root causes without exposing logs or treating routine provenance changes as a
new error. A third attempt after two identical signatures is refused pending
manual diagnosis.

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

`stage p0` records the file's SHA-256 and installs the exact frozen Linux `hpc`
Pixi environment on the login node under a fixed 45-minute transport timeout.
The timeout accommodates cold shared-filesystem materialisation while remaining
bounded. Staging records `hpc-environment-status=ready` only after the project
CLI, Nextflow, and Java executables are present. The job refuses execution if
the configuration changes or this environment-ready record is absent.
Every configured child must be a canonical non-symlink path below the
first-line root. The input-staging operation obtains that root from the already
reviewed dispatcher and database roots rather than from `$HOME`: it walks only
to their nearest canonical, owner-controlled common ancestor. This supports
sites where login-shell, workflow, and database storage use different lexical
paths without granting a caller path authority. Because these inputs are
read-only and no cleanup target is derived from this root, it may be the
operator-owned durable site directory; `/`, a foreign-owned directory, or a
symlink remains invalid. The job then:

1. verifies and reuses the pre-staged frozen Linux `hpc` Pixi environment
   without resolving or downloading packages;
2. re-verifies every required Phenix command without a per-command timeout and
   preserves its diagnostics in the verification log; the 24-hour job margin,
   structured logs, and owner-bound cancellation provide the outer controls;
3. fingerprints the frozen database manifest during staging, then runs database
   `verify-only` for PDB Foldseek, ProstT5, PDB sequences, and the coordinate
   cache, checking inventory metadata and comparing the exact resource records
   with that trust anchor; bounded MMseqs2/ProstT5/Foldseek smokes rerun locally.
   The strongest MMseqs2 hit must be significant and exactly query-equivalent,
   while the fixed `1ubq_A` SEQRES mapping and cached `1UBQ` coordinate are
   required independently. Foldseek likewise validates its strongest
   query-equivalent biological-assembly hit and the separate fixed `1UBQ`
   coordinate-cache control; external-tool version probes also have no default
   deadline. The full result and first ten hits remain audit evidence, while hit
   ordering, tied target identity, bounded result count, and full-result checksum
   are deliberately not compared because equally scoring ubiquitin targets can
   vary within the capped result set. A structured
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
during the P0 allocation.

## P1 direct-PDB discovery profile

The fixed P1 job reuses the frozen catalogue and qualified database manifest
already protected by the P0 configuration. It verifies their staging-time
checksums, imports the catalogue once, and runs `discover_structures.nf -profile
marmic` against the local PDB sequence resource. The checked `nf-helper` Marmic
configuration gives the MMseqs2 process compute-node `/scratch` and copies its
declared output to durable storage. The job repeats the identical workflow with
`-resume` and fails unless every discovery process is cached.

The final qualifier rechecks every declared result checksum, requires exactly
one result per catalogue sequence group, verifies that all retained hits carry
retrievable PDB model keys, and requires the exact 8OOX/8OOW positive-control
family for the tracked `GCF_000711905.1` sequence. It retains Nextflow CPU,
memory, process-I/O, result-size, and cache evidence. `collect` returns only the
qualification JSON, first/resume report files, catalogue manifest, search
manifest, and bounded MMseqs2 log; the full result tree remains on Marmic.
Passing the direct-search qualifier establishes that provider route. The
expanded fixed profile additionally qualifies one exact predicted-model
preparation, but it still does not perform molecular replacement or identify
any blind pilot crystal.

The fixed P1 route additionally supplies the tracked one-row exact AFDB mapping.
Immutable staging imports the catalogue and retrieves the public model
on the login node, where outbound HTTPS is available. It requires one exact hit
and coordinate, records fixed-file checksums, and leaves all heavy work to
Slurm. The compute job verifies that record, runs discovery without remote
accessions, then runs `prepare_models.nf` with the P0-verified Phenix manifest
and a separate Nextflow cache. It requires exactly one processed pilot model
and a fully cached model-preparation resume. The collected allow-list adds only
the prefetch/model manifests, records, traces, and bounded logs; coordinates,
licensed software, and the full run tree remain on Marmic. This extends the real
vertical slice but still does not claim a final candidate identity or an MR
solution.

The first attempt at this slice, immutable run
`gtd-p1-20260811T075356Z-0741c79d7723-75d0e6bd` (Slurm job `625736`), failed
before scientific search or Phenix execution. Compute host `slurm-302` refused
all three HTTPS attempts to the official AlphaFold prediction API. The collected
failure signature is
`751f993436611721ef26cf3b8fcfededc770c6688339a59a0101ca71498210cc`.
This evidence is why the fixed route now performs only the bounded public
retrieval on the login node and verifies its checksum-bound hand-off on the
compute node. It is an infrastructure failure, not a no-hit result.

The corrected route passed on immutable commit
`c901dafe585d1b68b117d7d216e5053ef4985230` as run
`gtd-p1-20260811T080728Z-c901dafe585d-d0e103c7`, coordinator job `625744`.
All seven staged hand-off files passed compute-node checksum verification. The
three discovery processes completed and cached on resume; the single Phenix
2.1-6048 model task completed in 54.7 seconds realtime with 334.4 MB peak RSS,
retained 429 of 442 residues, and cached on resume. The overall recorded job
ran from 08:09:17Z to 08:17:31Z. This qualifies the first real predicted-model
vertical slice only, not the candidate funnel or molecular replacement.

The first real P1 run passed on immutable commit
`f198884a5d7e6c66c0f6a94f1a28cadb0004fe37` as coordinator job `625575`.
It evaluated 1,621 exact-sequence groups (1,620 search eligible), retained
15,401 hits, recovered the exact 8OOX/8OOW family, and cached the sole search
process on resume. Detailed sanitised evidence and limitations are recorded in the
[P1 direct-PDB qualification](p1-direct-pdb-qualification.md).

The first P1 run containing the full-catalogue ProstT5/Foldseek provider reached
Foldseek but exited 1 before publication. Its native log was on task scratch and
did not survive outer cleanup. The bounded retry retained its native-log tail,
used the large-node resource label, and searched the first 128 sorted eligible
real sequences. It demonstrated that requesting Foldseek `prob` makes a
ProstT5 sequence query require a missing query Cα database. Adapter v2 removes
that field based on the exact Foldseek source. The next identical slice
completed Foldseek, then exposed RCSB biological-assembly copy suffixes such as
`A-2` at the SEQRES crosswalk. Adapter v3 maps those copies back to the original
case-sensitive chain while preserving copy provenance. Its next identical slice
passed as coordinator job `625655`: 292 hits were retained for 102 groups, 26
groups completed with no hit, and all three processes were cached on resume.
Deferred sequences are `skipped_policy`, never no-hits.
See the
[P1 ProstT5/Foldseek qualification](p1-prostt5-qualification.md).

## P2 fixed CD6 first-copy profile

The fixed P2 route deliberately replays P0 and P1 inside the same immutable
run before entering molecular replacement. This preserves the exact catalogue,
preflight, Matthews, coordinate, processed-model, database, and Phenix anchors
instead of accepting a caller-selected intermediate. After replay it:

1. verifies the single CD6 MTZ from the checksum-frozen P0 bundle layout;
2. builds the inspectable exact-predicted funnel and requires exactly one
   physically possible, bounded hypothesis for this pilot slice;
3. runs `screen_first_copy.nf -profile marmic`, with each Phenix process using
   two CPUs, 8 GB, compute-node `/scratch`, and the 1,000-hour site margin;
4. validates and preserves the normalised MR result, then requires its execution
   status to be `completed_hit` or `completed_no_hit`;
5. repeats the identical route with `-resume` and requires both deterministic
   processes to report `CACHED`; and
6. rechecks the source commit and tracked worktree before reporting success.

The adapter itself has no default Phaser timeout. The scheduler and local wait
margins are conservative observation boundaries; neither silently cancels a
job. Collection is limited to fixed small provenance, funnel, result, Phaser
log/command, optional solution files, and first/resume trace artefacts. A
successful P2 run means the CD6 first-copy attempt executed reproducibly. A
tool, parser, or infrastructure failure remains collectable but makes the outer
run a `test_failure`; it is never converted into a successful no-hit. It does
not by itself identify a protein, validate the full P2 gate, or authorise
same-component additional-copy searches.

The reviewed fake Git/Slurm/Nextflow/Phenix lifecycle covers fixed staging,
submission resources, immutable input reuse, first run, cached resume,
normalised no-hit handling, adapter-failure rejection, collection allow-lists,
and job-result provenance.

The first real attempt at corrected database validation failed before Phaser
because a bounded MMseqs tie set omitted literal `1ubq_A`; the correction now
uses the strongest sequence-equivalent hit while retaining the independent
fixed 1UBQ mapping and coordinate anchors. The next immutable run replayed P0
and P1 successfully and cached both P2 processes, but its normalised result was
`failed_tool_execution`: Phaser 2.8.4 reported no scattering in the processed
mmCIF. That run established route reproducibility, not P2 scientific
completion. Predicted-model preparation now publishes the Phenix-generated PDB
validated by a real positive control. The next PDB-model run completed Phaser
but exposed an unrecognised terminal no-solution phrase. Immutable commit
`4e64ce5bc10c518276a86f2c0870e4c18899f86d` corrected that parser boundary;
its replay completed successfully as `completed_no_hit`, with zero
accepted/packed solutions, no output solution files, and both P2 processes
cached on resume. This qualifies the fixed route, not the full P2 gate or a
protein identification.

## P2-diverse bounded multi-source profile

`p2-diverse` is a separate fixed operation so the qualified one-model `p2`
route remains unchanged. It accepts no path, crystal, accession, hit ID,
threshold, model variant, or shell fragment. Staging on the network-capable
login node:

1. performs the same immutable P1 catalogue import and exact-AFDB prefetch;
2. runs the local PDB sequence search with two threads, at most 25 hits per
   query, E-value at most `1e-5`, query coverage at least `0.5`, and query
   length at most 10,000 residues;
3. registers at most three hits per sequence group and 25 mappings overall,
   downloading or reusing official PDB mmCIF objects through the verified
   shared coordinate cache; and
4. requires 1–25 mappings, records every fixed output checksum atomically, and
   binds the checksum-list digest into the run manifest.

The scheduled phase is offline. It replays P0/P1, verifies the login-stage
checksum list, and requires the normalised login-node PDB hit file to have the
same SHA-256 as the scheduled P1 search. It then runs
`prepare_pdb_models.nf` and `screen_diverse_first_copy.nf`, each once normally
and once with `-resume`. The funnel receives an explicit additional cap of 25
jobs even though the underlying pilot configuration permits more. It must
retain at least one exact predicted and one mapped experimental hypothesis,
must publish no more than 25 hypotheses, and must produce one validated
Phaser result for each. Only `completed_hit` and `completed_no_hit` are accepted
as scientific completions; the strict provisional hit gate is `LLG > 50` or
`TFZ > 5`. Final packing and the requested placed-copy count remain independent
requirements.

Full model/result directories and native Phaser logs remain in the retained
remote run. Collection is bounded to login-stage manifests/mappings, model and
funnel manifests, hypotheses, first/resume traces, normalised result and
command JSONL, 200-line log tails, summary counts, and a SHA-256 inventory.
Neither the wrapper nor the adapter imposes a Phaser deadline.

```bash
nf-gtd-hpc-test readiness p2-diverse
nf-gtd-hpc-test stage p2-diverse --revision HEAD
nf-gtd-hpc-test submit p2-diverse --run-id RUN_ID
nf-gtd-hpc-test status --run-id RUN_ID
nf-gtd-hpc-test logs --run-id RUN_ID --tail 200
nf-gtd-hpc-test collect --run-id RUN_ID
```

The fake Git/Slurm/Nextflow lifecycle covers login-node registration failure,
offline checksum hand-off, the 25-job command cap, predicted/experimental
retention, result cardinality, scientific status validation, both cached
resumes, and bounded collection. This software route has not yet run against
the real Marmic direct-PDB candidates; do not treat local acceptance as M2/M3
scientific qualification.

## P2-control same-MTZ separation profile

`p2-control` is the closed M3 calibration run. It accepts no caller-selected
MTZ, model, identity value, score threshold, copy count, path, or Phaser
argument. Login-node staging resolves the checksum-frozen Methermicoccus
proteome from the reviewed P0 catalogue manifest, prepares the tracked public
8OOX control, imports its catalogue, and binds all generated inputs by SHA-256.
The scheduled phase uses the same 8OOX MTZ for both hypotheses:

1. the operational positive is exact 8OOW chain A and is expected to produce a
   packed one-copy `completed_hit`;
2. the deliberate negative is the independently qualified 1UBQ ubiquitin chain
   from the shared coordinate cache and is expected to produce
   `completed_no_hit`;
3. the negative's fixed 1% Phaser identity is a conservative control-only error
   model input, not measured sequence homology; typed model and hypothesis roles
   must both declare this interpretation;
4. both jobs use the production `RUN_FIRST_COPY_PHASER` process with four CPUs,
   8 GB, `/scratch`, no adapter or Xtriage command deadline, and the site's long
   scheduler margin; and
5. the identical two-process run is resumed and both processes must be cached.

The terminal separation requirement is strict `LLG > 50` **or** `TFZ > 5`, a
packed positive top solution, exactly one placed positive copy, and no score-gate
pass for the negative. The run preserves both normalised results, resolved
commands, bounded Phaser log tails, preflight, model/hypothesis manifests,
first/resume traces, input checksums, and a bounded artefact checksum inventory
even when separation fails. A separation failure is `test_failure`, not an
infrastructure failure and not evidence that the raw run disappeared.

```bash
nf-gtd-hpc-test readiness p2-control
nf-gtd-hpc-test stage p2-control --revision HEAD
nf-gtd-hpc-test submit p2-control --run-id RUN_ID
nf-gtd-hpc-test status --run-id RUN_ID
nf-gtd-hpc-test logs --run-id RUN_ID --tail 200
nf-gtd-hpc-test collect --run-id RUN_ID
```

Passing this pair shows that the current operational positive and one unrelated
negative separate under one first-copy screen. It does not estimate false
positive rates, validate the current gate generally, prove a full two-copy ASU,
or approve any marginal CD6 candidate.

## Database administration boundary

Full preparation and `verify-only --full-verify` use separate, long-running
database-administration start commands. `database-stage` contacts only the
fixed public Foldseek/RCSB routes from the login node and writes directly to a
large shared root; the Slurm job is network-free. Routine `stage` and `submit`
explicitly reject the `database` profile. Keep these mutating start operations
separate from the routine smoke-test operations.

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
- `test_failure`: the foundation checks or a fixed P0/P1/P2 workflow gate failed;
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
`submit`, `status`, `wait`, `logs`, `collect`, `review-collect`, or `cancel`. Keep raw SSH, transfer tools,
Slurm commands, `p0-inputs-stage`, `p0-configure`, and the wrapper's `clean`
operation approval-gated.

Resolve the installed path literally; shell variables and `~` are not valid rule
substitutes. The intended Codex rule shape is:

```python
prefix_rule(
    pattern = [
        "/absolute/path/to/installed/nf-gtd-hpc-test",
        ["deploy-tools", "readiness", "stage", "submit", "status", "wait", "logs", "collect", "review-collect", "cancel"],
    ],
    decision = "allow",
    justification = "Allow only the reviewed nf-genome_to_diffraction HPC interface.",
    match = [
        "/absolute/path/to/installed/nf-gtd-hpc-test deploy-tools --revision HEAD",
        "/absolute/path/to/installed/nf-gtd-hpc-test readiness p0",
        "/absolute/path/to/installed/nf-gtd-hpc-test status --run-id RUN_ID",
        "/absolute/path/to/installed/nf-gtd-hpc-test review-collect --run-id RUN_ID",
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

P0, P1, and P2 consume already prepared real Phenix and database resources; they do not
install licensed software, download databases, accept arbitrary Nextflow
parameters, or expose raw SSH. Broader structural providers, MR variants,
same-component copy placement, refinement, map-based sequence work, full pilots,
and benchmarks require their later roadmap gates.
