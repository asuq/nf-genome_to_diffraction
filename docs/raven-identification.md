# Raven identification execution

This case-specific operator route uses the same identification input archive,
model preparation, Phaser adapter, Nextflow graph and terminal assessment as
the Marmic screen. It does not add a new candidate generator or identity rule.

## Execution and storage

The maintained nf-helper `raven` profile launches from an explicit Raven login
node. A small detached login controller schedules independent preparation/MR
tasks through Slurm. It is not represented as a Slurm job and does not consume
one of the account's running-job slots. The controller's PID, kernel start time
and boot identity distinguish it from a later process reusing the same PID.

All project-managed software, source snapshots, inputs, temporary files, caches,
work and outputs live under `/ptmp/USER/nf-genome_to_diffraction`. `/ptmp` is an
official site alias for `/raven/ptmp`; both resolve to the same approved storage.
It is not backed up and has a site retention policy, so terminal evidence must
also be collected to the operator's durable local state.

The profile retains its 250-outstanding-task guard below Raven's default
300-submission account limit. The inspected account permits eight running jobs.
These are site constraints, not the temporary five-job Marmic ceiling. CPU and
memory requests retain the existing MR policy, while Raven's 24-hour job limit
applies to both attempts. Records distinguish the planned resource allowance
from the actual resolved walltime passed by Nextflow. This changes scheduling,
not initial copy count, Matthews hypotheses, scientific outcomes or review gates.

See the [MPCDF Raven user guide](https://docs.mpcdf.mpg.de/doc/computing/raven-user-guide.html)
and the pinned `external/nf-helper/conf/sites/raven.config` for site policy.

## Bootstrap and immutable launch records

Bootstrap is explicit operator work: install checksum-pinned Pixi and the locked
HPC environment, install the user-provided licensed Phenix package under the
approved root, and transfer the original diffraction files and candidate archive.
Do not download Phenix automatically or put its installer in Git. Set Pixi,
Conda, Nextflow, Apptainer, Python and temporary/cache locations under `/ptmp`;
disable Conda environment registration in the home directory.

One private `RavenLaunch` JSON record binds the run/owner, exact source checkout,
CPU account, input content ID, original MTZ root, Phenix manifest/checksum and
`smoke` or `screen` mode. Keep an identical local `run.json` and remote
`runs/RUN_ID/launch.json`. The source is an immutable snapshot under
`sources/COMMIT`; no remote code editing or automatic source updates are allowed.
The common `build_identification_archive` and `unpack` operations preserve the
same bounded archive checks at both sites. Rebase only site paths in a fresh
input plan, never scientific identities or original Free-R-bearing data.

Qualify the new site with a small explicit execution before the full screen.
Do not duplicate a currently active Marmic candidate. A completed pilot case
may be explicitly repeated as an operational portability check; it is not new
identity evidence. Retain and classify the owned Marmic run before retirement;
failed/cancelled scientific caches remain non-reusable.

## Controller interface

### Read-only setup inspection

The same client has a separate read-only `readiness` operation for binding the
existing Raven setup before a new M6 route is qualified. It accepts no run ID
and cannot start, resume, cancel or change the identification programme:

```text
pixi run --locked nf-gtd-raven --config CONFIG readiness --revision FULL_COMMIT --runtime-source-commit EXISTING_RUNTIME_COMMIT --phenix-manifest-sha256 FROZEN_PHENIX_SHA256
```

The local worktree must be clean and the inspection source published on `main`.
The client sends only the committed standard-library inspection program to the
existing locked Python. The remote check requires an explicit Raven login node,
the authenticated account's fixed `/ptmp` root, the exact runtime source commit,
matching Pixi lock and frozen Phenix-manifest bytes. It records package versions
and at most 128 immediate entries in each fixed manifest/resource directory.
Symlinked inventory directories are reported but not followed; metadata limits,
ownership and scope failures are explicit. No biological data is read, no
software is installed, and no job or persistent remote state is created.

This produces timestamped setup-inspection evidence, not a scientific cache.
Both `database_binding_verified` and `native_qualification_verified` remain
false. A matching runtime does not supply a missing database binding, qualify
native M6 or authorise AF01 GPU work. Focused checks cover unchanged files,
source/lock/Phenix/Python drift, symlink handling, inventory bounds and the
source-bound transport response.

### Owned identification runs

The internal Pixi task reads a private mode-0600 client config containing
`schema_version`, fixed `ssh_alias: raven`, `remote_root`, and an absolute
`local_state_root`. Run ownership comes from the exact local run record, not
directory recency or an implicit latest run.
Keep these login-controller records in a separate local state directory from
the legacy Slurm-controller store; the record formats are intentionally distinct.

```text
pixi run --locked nf-gtd-raven --config CONFIG start --run-id RUN_ID
pixi run --locked nf-gtd-raven --config CONFIG status --run-id RUN_ID
pixi run --locked nf-gtd-raven --config CONFIG logs --run-id RUN_ID --tail 200
pixi run --locked nf-gtd-raven --config CONFIG collect --run-id RUN_ID
```

`start` refuses an existing controller/state record. `status` is read-only and
distinguishes `STARTING`, `RUNNING`, `COMPLETED`, `FAILED` and `CANCELLED`.
Missing terminal evidence after process death is an operational failure, never
a scientific no-hit. A completed controller still requires all task/candidate
evidence to be classified. `logs` is bounded to the owned controller log.

`cancel` requires explicit operator authority. It authenticates process identity
and uses a Linux PID descriptor so it cannot signal a replacement process after
PID reuse. The controller asks Nextflow to stop its own children; cancellation
is not complete until terminal state and child evidence have been checked.
There is no implicit cancellation, retry, resume or cleanup.

Terminal collection authenticates the complete launch record before extraction
and uses the existing bounded archive extractor. The common assessment retains
all candidate dispositions, native logs, PDBs, trace/resources and checksums;
large native MTZ assets remain explicitly indexed on Raven for selected review.
Collection never accepts identity or makes a failed scientific cache reusable.

## Verification

The shared adapter checks cover command/copy preservation, native result and
failure classification, input/archive bounds and actual resource recording.
Focused controller checks protect ownership, duplicate start, PID reuse,
login/storage confinement and the exact shared-graph/run-owned-work command.
Configuration rendering checks the maintained Raven profile and resolved MR
limits; live Raven qualification verifies the installed runtime and Slurm path.
Neither unit tests nor a green controller exit establish protein identity.
