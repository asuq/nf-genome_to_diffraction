# Failed MR child evidence

This page defines the private diagnostic contract for an `unknown-screen`
controller that terminates after one or more first-copy Phaser tasks have been
submitted. The package closes an operational evidence gap. It does not convert
a failed controller into a successful screen and does not establish a hit,
no-hit, or protein identity.

## Boundary

The collector is an internal repository tool invoked by the reviewed HPC job
wrapper. It is not part of the installed research package or the public
`genome-to-diffraction` CLI. It reads only the exact run's Nextflow log and
run-local work tree after the controller has failed.

The source module is
`genome_to_diffraction.hpc.mr_failure_evidence`. Both first execution and
resume failure paths invoke it before the wrapper publishes the terminal job
result. A collection failure is itself a test failure; the wrapper never
silently substitutes a partial package.

## Retained inventory

For every funnel hypothesis, the manifest records:

- crystal and hypothesis identifiers;
- Matthews-derived expected copy count and the searched copy count;
- whether it was unsubmitted, completed, or unfinished when the controller
  aborted;
- every observed native scheduler job ID and attempt number;
- terminal exit and timing evidence when Nextflow observed completion;
- Slurm CPU, memory, and time directives parsed from `.command.run`;
- whether a normalised MR result is absent, valid, invalid, or belongs to a
  different hypothesis; and
- the normalised execution status only when that record validates against the
  active schema and exact hypothesis.

The package copies bounded task command files, Phaser result assets, each
hypothesis, and its resource plan. This includes the available Phaser logs and
Nextflow trace data needed to assess wall-time and resource behaviour without
depending on the failed scientific cache.

## Integrity and limits

The contract permits at most 75 funnel hypotheses and 150 submitted attempts.
Each retained file is limited to 128 MiB and the package to 2 GiB. Symlinks,
path escapes, cross-funnel submissions, contradictory completion records, and
unsafe collection paths fail closed.

`checksums.sha256` authenticates every package file other than itself and
`file-count`. Remote collection validates every row, checksum, owner, link
count, file-size bound, total-size bound, and declared count before adding the
file to the returned archive.

## Scientific semantics

Every manifest has both of these fixed values:

```json
{
  "cache_reusable": false,
  "scientific_evidence_accepted": false
}
```

A completed child from a failed controller remains an execution observation.
It may explain a defect or resource limit, but it cannot be promoted as a
scientific hit or no-hit. Only a successful, exact-source screen with its full
75-hypothesis inventory, cached replay, provenance, and checksums may reach the
A-seed review gate.

## Validation

Focused tests exercise completed, unfinished, and unsubmitted hypotheses;
valid normalised results; Slurm resource extraction; cross-funnel rejection;
checksum conservation; authenticated remote collection; and tamper rejection.
Repository-policy tests ensure both failure paths retain the collector and that
the remote wrapper continues to enforce checksum and count validation.
