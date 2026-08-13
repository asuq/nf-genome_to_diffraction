# Viper-CPU prototype runbook

## Active site and boundary

Viper-CPU is the active execution site for the single-component prototype.
Marmic runs remain immutable historical evidence; do not cancel, clean, or
modify them during this cut-over. Local Git remains the only source tree.

The reviewed controller accepts only fixed operations and a user-owned
configuration. It never accepts arbitrary remote paths or shell fragments.
Run records contain `site_id`; legacy records without it are Marmic-only and
cannot be queried through a Viper controller configuration.

Tracked paths use `USERNAME` placeholders. The deployment resolves these to the
operator's account outside Git:

- runs, work, and caches: `/ptmp/USERNAME/nf-genome_to_diffraction/`;
- databases: `/ptmp/USERNAME/nf-genome_to_diffraction/databases`;
- Apptainer cache: `/ptmp/USERNAME/apptainer-cache`;
- Phenix runtime: `/ptmp/USERNAME/nf-genome_to_diffraction/software/phenix_v2.1-6048`;
- Phenix manifest: `/viper/u1/USERNAME/Softwares/manifests/phenix-2.1-6048.json`;
- reviewed tools: `/viper/u1/USERNAME/.local/libexec/nf-gtd/`.

`/ptmp` is shared, high-performance, unbacked storage. It has no user quota,
but reproducible inputs and manifests must remain recoverable elsewhere.

## Resource policy

Use Viper's small compute queue only. The hard project ceiling is **64 CPUs and
192 GB RAM** with Viper's 24-hour scheduler maximum. M4 uses seven concurrent
Phaser tasks at 8 CPUs and 16 GB each, for at most 56 CPUs. The database build
and verification job uses 64 CPUs and 192 GB. Increase neither without a new
explicit decision supported by measured resource evidence.

Database downloads are the user-approved exception to the original two-job
proposal: the fixed `database-stage` operation downloads and checksums sources
on the Viper login node. It does not use a `datatransfer` job. The subsequent
compute job is offline and builds in a job-owned directory on `/ptmp`, then
publishes each completed resource by same-filesystem atomic rename. Database
staging and M4 use separate locks so
the CPU-light download track can coexist with one managed M4 job.

## Environment

Use the existing Pixi executable directly; do not activate Mamba:

```text
/viper/u1/USERNAME/miniforge3/envs/pixi/bin/pixi
```

The Mamba `pixi` environment is only a launch location. `pixi.lock` governs
Python 3.14.6, Nextflow 26.04.6, Java 21, MMseqs2, Foldseek, and development
tools. CI qualifies Pixi 0.74.0 and Viper's 0.76.2. Separate Mamba `nextflow`
and `core` environments are not production dependencies.

## Secure bootstrap

1. Generate a Viper-only Ed25519 deploy key without printing the private key.
   Add only the public key to the private GitHub repository as read-only.
2. Verify GitHub's host key against GitHub's published fingerprints, then add it
   to the account's `known_hosts`. Configure a dedicated SSH alias that uses
   only this deploy key.
3. Create the fixed `/ptmp` root, database staging directory, caches, and bare
   mirror. Clone/fetch through the dedicated GitHub alias.
4. Copy [`hpc-viper-site.paths.example`](../conf/hpc-viper-site.paths.example)
   outside Git, replace placeholders, install it as `site.paths` next to the
   dispatcher with mode `0600`, and verify every path is canonical.
5. Install checksum-reviewed copies of the dispatcher and job script with mode
   `0555`. Record their Git revision and SHA-256 values.
6. Copy the licensed installer to `/ptmp`, require SHA-256
   `a2455e281f11241debdb25d9788ada8337420b9ff4c92935f97157f0cc9b9795`,
   and install Phenix through one scheduled 4-CPU/32-GB job. Keep the stable
   prefix `software/phenix_v2.1-6048` below the fixed `/ptmp` project root; do
   not create `phenix-current`. Phenix 2.1-6048 creates more files than Viper's
   default `/u` file quota allows. Keep its small manifest and logs under `/u`.
   Because `/ptmp` is unbacked and files may age out after 12 weeks, retain the
   licensed installer and checksums and refresh access or reinstall when needed.
7. Qualify all command probes and real `CD6QS2P2G1_5` MTZ execution. Preserve
   installer checksum, command versions, logs, and the installation manifest.

Private keys, exact user paths, and capability tokens remain outside Git.

## Controller configuration

Preserve the former Marmic configuration as `config.marmic.json`. Install a
schema-1.1 Viper configuration as the active `config.json`, using
[`hpc-test.example.json`](../conf/hpc-test.example.json). The dispatcher path is
the reviewed tool under the user software tree and `site_id` is `viper-cpu`.

The routine cycle is:

```bash
nf-gtd-hpc-test --no-progress deploy-tools --revision HEAD
nf-gtd-hpc-test --no-progress m4-import-stage --revision HEAD
nf-gtd-hpc-test --no-progress submit m4-copy --run-id RUN_ID
nf-gtd-hpc-test --no-progress status --run-id RUN_ID
nf-gtd-hpc-test --no-progress logs --run-id RUN_ID --tail 200
nf-gtd-hpc-test --no-progress collect --run-id RUN_ID
```

Use a separate command for every operation. Never persist approval for raw SSH,
raw Slurm commands, or `clean`.

## Cross-site M4 continuation

`m4-import-stage` accepts no source or destination path. It builds one fixed
checksum-gated archive from the collected successful Marmic P2-diverse evidence:
11 retained first-copy solutions, approved decisions, hypotheses, sequence
groups, MTZ preflight, the frozen CD6 MTZ, and immutable run/job provenance.

Each first-copy solution coordinate becomes the next-copy search model because
Phaser placement is a rigid-body transformation. The stage manifest records its
new checksum and separately preserves the original processed-model checksum;
they are not claimed to be identical. All 11 candidates advance, independent of
the preliminary `LLG > 50 OR TFZ > 5` ranking annotation.

Acceptance requires exactly 11 typed candidate series, retained parent/child
states, raw LLG/TFZ/delta, packing and placed-copy evidence, candidate-level
failure states, full source/nf-helper/Pixi/lock/site provenance, a typed copy
report, and a fully cached resume. A failed addition is not evidence of absence.
After inspection, proceed directly to T12 brief refinement, maps, and
sequence-from-map narrowing for all scientifically viable alternatives.

## Database track

```bash
nf-gtd-hpc-test --no-progress database-readiness
nf-gtd-hpc-test --no-progress database-stage --revision HEAD
nf-gtd-hpc-test --no-progress database-submit --run-id RUN_ID
nf-gtd-hpc-test --no-progress status --run-id RUN_ID
```

Staging records source URLs, release metadata, checksums, licences, and a frozen
source-bundle checksum. The build records tool versions, inventory, CPU/wall
time, MaxRSS where Slurm provides it, and storage. Completion is independent of
M4 and must not delay the real prototype result.

## Rollback

Stop submitting new Viper runs and restore the saved Marmic controller
configuration if historical access is needed. Do not reinterpret legacy records
as Viper records. Move, rather than delete, the active controller configuration,
tool copies, and site config into a dated user-owned rollback directory.

Do not delete `/ptmp` runs, the bare mirror, databases, Phenix, deploy keys, or
Marmic evidence as part of a configuration rollback. Each requires a separate,
explicitly reviewed retirement operation. Removing the Viper deploy key from
GitHub revokes future fetches without erasing local evidence.
