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
and verification job deliberately uses only 4 CPUs and 8 GB because it unpacks
prebuilt Foldseek resources and constructs the smaller PDB-SEQRES MMseqs index.
A complete 8-CPU/32-GB qualification build finished in 2m45s with 3.27 GB
MaxRSS and 1.7% CPU utilisation; the reduced allocation retains memory margin.
Its 24-hour request provides margin for shared-filesystem I/O. Increase these
database resources only when new terminal evidence shows they are insufficient.

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
tools. CI qualifies Viper's Pixi 0.76.2. Separate Mamba `nextflow`
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

## Fixed T12 continuation

The active T12 boundary binds one retained successful Viper M4 run and accepts
no caller-supplied input root. It selects the checksum-authenticated supported
copy-two PDB/MTZ parent for each of the 11 retained seeds inside that run. The
controller transfers only the fixed authoritative catalogue
`source_records.jsonl` crosswalk, because the accepted M4 import already holds
the sequence groups, MTZ preflight, and Phenix manifest.

```bash
nf-gtd-hpc-test --no-progress deploy-tools --revision HEAD
nf-gtd-hpc-test --no-progress t12-stage --revision HEAD --parent-run M4_RUN_ID
nf-gtd-hpc-test --no-progress submit t12 --run-id T12_RUN_ID
nf-gtd-hpc-test --no-progress status --run-id T12_RUN_ID
nf-gtd-hpc-test --no-progress logs --run-id T12_RUN_ID --tail 200
nf-gtd-hpc-test --no-progress collect --run-id T12_RUN_ID
nf-gtd-hpc-test --no-progress t12-review-collect --run-id T12_RUN_ID
```

Each candidate receives four CPUs and 16 GB, with at most four concurrent
refinement tasks and the Viper 24-hour scheduler ceiling. There is no adapter
timeout. Acceptance requires exactly 11 typed refinement and sequence results,
all candidates retained, full parent/catalogue/MTZ/Phenix/source/Pixi/lock
provenance, and an 11/11 cached resume pass. Candidate-level scientific or tool
failure remains reviewable evidence and does not abort or remove other
candidates.

Run `t12-review-collect` only after the normal bounded collection is present.
It accepts only the owned run ID, revalidates the typed terminal summary and
11/11 cached resume, and transfers only PDB/MTZ/both CCP4 maps/sequence-
assignment files plus the checksum-bound catalogue, annotation crosswalk, and
MTZ preflight whose checksums are already recorded in the collected evidence.
The local destination
contains `sequence_candidates_top10.tsv`, `sequence_candidates_top25.tsv`,
`sequence_candidates_full.tsv`, `sequence_candidates.html`,
`sequence_approval_candidates.tsv`, `sequence_gene_annotations.tsv`,
`sequence_matthews_context.tsv`, `approved_sequence_groups.tsv`, a package
manifest, and all finalist assets. Each finalist includes separate `2mFo-DFc`
and `mFo-DFc` maps; the sequence-from-map PDB is explicitly a map-derived
assignment hypothesis, not an independently refined structure. The approval
template is deliberately empty;
reviewing in Coot and recording decisions remains a human checkpoint.

For CD6, keep the prototype-assumption status `unknown` unless the maps and
other evidence justify a stronger call. CD6 is an unknown crystal and may be
heteromeric or otherwise violate `ASU = nA`; Matthews copy-number context is a
physical prior and cannot establish single-component composition.

After collection, build the T13.1 status locally from the accepted T12 summary,
job result, refinement records, checkpoint manifest, candidate table, and human
decision TSV:

```bash
pixi run --locked genome-to-diffraction --no-progress review build-status \
  --crystal-id CRYSTAL_ID \
  --t12-summary T12_SUMMARY_JSON \
  --job-result JOB_RESULT_JSON \
  --refinement-results T12_REFINEMENT_RESULTS_JSONL \
  --checkpoint-manifest SEQUENCE_CHECKPOINT_MANIFEST_JSON \
  --approval-candidates SEQUENCE_APPROVAL_CANDIDATES_TSV \
  --decisions APPROVED_SEQUENCE_GROUPS_TSV \
  --out SCIENTIFIC_STATUS_JSON
```

The default assumption status is `unknown`. An empty decision file preserves
`completed_success` execution while reporting `insufficient_evidence`; it never
promotes a ranked candidate. Set the assumption-status option only after that
assumption has been reviewed, and use `--residual-content-suspected` only when
the experimental evidence supports it.

Add the T13.2 report to the already verified checkpoint package:

```bash
pixi run --locked genome-to-diffraction --no-progress review build-report \
  --status SCIENTIFIC_STATUS_JSON \
  --checkpoint-dir T12_SEQUENCE_CHECKPOINT_DIRECTORY
```

The builder first rechecks every manifest-bound table and finalist asset. It
then writes `crystal_report.html`, `scientific_status.json`, and
`crystal_report_manifest.json` inside that package, so its links remain
portable with the review assets. The HTML is a review aid, not a replacement
for Coot inspection or explicit decisions.

## Fixed 23-case homomer control matrix

The operational control matrix is a fixed Viper boundary with no caller-
supplied data root or case selection. It contains 11 prokaryotic positive
controls, seven wrong-model controls, two target-absent controls, two wrong-
catalogue controls, and one heteromeric assumption-violation control. Positive
ground truth spans expected ASU counts 1, 2, 3, 4, and 6. All candidates and
candidate-level failures are retained; LLG/TFZ remain ranking annotations.

```bash
nf-gtd-hpc-test --no-progress deploy-tools --revision HEAD
nf-gtd-hpc-test --no-progress control-matrix-stage --revision HEAD
nf-gtd-hpc-test --no-progress submit control-matrix --run-id RUN_ID
nf-gtd-hpc-test --no-progress status --run-id RUN_ID
nf-gtd-hpc-test --no-progress logs --run-id RUN_ID --tail 200
nf-gtd-hpc-test --no-progress collect --run-id RUN_ID
```

The scheduled job uses 64 CPUs, 192 GB, and the 24-hour Viper ceiling. It runs
at most seven concurrent Phaser searches, advances every packed positive
sequentially to its expected count, and applies T12 to every packed positive.
The package is an operational same-structure test and makes no leakage-
controlled generalisation claim.

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
