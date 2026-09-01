# Phase III offline localisation and wave-policy boundary

> This document preserves the original per-sequence-group adapter and reopen
> policy. The active Phase III unknown-pass route uses the checksum-pinned,
> catalogue-batch PSORTb and DeepTMHMM runtime described in
> [Phase III offline localisation runtime](phase-iii-localisation-runtime.md).
> The historical blocked DeepTMHMM path below remains readable but is not the
> current application writer.

This focused slice defines offline, one-sequence-group localisation contracts and
the catalogue-wide first-wave policy. It does not download a runtime, submit
sequences to a public service, run DeepTMHMM, launch a real/HPC profile, or infer
protein identity or crystal composition.

## PSORTb 3.0.6

The standalone adapter is fixed to the archaeal model and terse output:

```text
psort -a -o terse sequence.faa
```

The command is based on the official [PSORTb 3.0 documentation](https://psort.org/documentation/),
which documents `-a` for Archaea, `-o terse`, FASTA input, and three tab-delimited
fields: sequence ID, localisation, and score. The runtime contract binds version
3.0.6 and the executable SHA-256; the [official downloads page](https://psort.org/downloads/)
identifies Bio-Tools-PSort 3.0.6 as the current standalone package.

One attempt retains the input FASTA, version probe, command record, stdout, stderr,
and result JSON. Parsed archaeal labels normalise to `membrane`, `surface`,
`extracellular`, `soluble`, or `unknown`. Non-zero execution and malformed output
become typed `failed` results while their raw files remain retained. Runtime or
checksum mismatches are input-contract failures and fail before scientific use.

## DeepTMHMM 1.0

The official [DeepTMHMM 1.0 service documentation](https://services.healthtech.dtu.dk/services/DeepTMHMM-1.0/)
documents FASTA input, alpha-helical and beta-barrel topology prediction, the
user-downloadable runtime, and its academic/commercial licence boundary. It does
not publish a stable local image entrypoint, argument list, or raw-output wire
format.

Consequently, this slice binds a user-provided image path and SHA-256, version 1.0,
academic-use context, and exactly one checksum-verified FASTA input, but emits an
empty command with `blocked_unverified_cli`. It now also emits one typed
`skipped_policy` blocked result per sequence group. That result has no localisation
outcome and cannot be merged as a prediction. The image is never redistributed. A
future slice may enable execution only after inspecting the supplied image and
freezing its exact CLI, raw-output fixture, parser, and failure test. No DeepTMHMM
result is fabricated while invocation is blocked.

## Catalogue task and first-wave policy

`LOCALISATION_WAVE_WORKFLOW` materialises one content-addressed PSORTb task for
every exact sequence-equivalence group and fans those tasks out through Nextflow.
Each item binds the full sequence-group record, canonical FASTA checksum, PSORTb
runtime identity, and blocked DeepTMHMM runtime identity. The merger refuses a
missing, duplicate, unknown, checksum-mutated, or task-mismatched result; an empty
input inventory remains a typed complete zero-task branch.

Every retained group receives one merged outcome and one explicit disposition:

- `soluble` is `active`;
- `membrane`, `surface`, `extracellular`, and `transmembrane` are `excluded` from
  the first wave; and
- `unknown`, `conflicting`, and `failed` are `neutral` and remain first-wave
  eligible.

Active groups are ordered before neutral groups, with sequence-group ID as the
deterministic within-class tie-breaker. Every excluded group remains in the full
evidence JSONL, a dedicated retained-excluded JSONL, and the policy inventory.
This policy is a scheduling boundary only; it neither makes a localisation truth
claim nor changes candidate identity.

## Reopen boundary

The reopen planner consumes an exact first-wave completion record. Every eligible
group must have a result. `packed` and `completed_no_packed_result` are terminal;
missing or failed MR results keep the wave incomplete. Excluded groups reopen only
when the wave is complete and contains zero packed results. Any packed result keeps
them closed. If the first wave is empty, it is vacuously complete and retained
excluded groups may open; when no excluded groups exist, no reopen is required.

The reopen record always preserves the complete excluded inventory, whether its
status is `activated_no_packed_result`, `not_activated_packed_result`,
`pending_active_wave`, or `not_required_no_excluded_groups`.

## Status and cache boundary

The shared outcome vocabulary is `membrane`, `surface`, `extracellular`,
`transmembrane`, `soluble`, `unknown`, `conflicting`, and `failed`. Unknown and
failed evidence do not override a successful independent observation; incompatible
informative observations resolve to `conflicting` rather than to an exclusion.

PSORTb runtime and command identities include tool version, adapter version,
executable checksum, sequence identity, input checksum, archaeal model, and output
format. DeepTMHMM runtime/input plans bind the image, version, sequence, and FASTA
checksums. Catalogue task, merged evidence, first-wave policy, active-wave
completion, and reopen plan records each have content-derived identities. Both tool
contracts state `local_offline`, no network use, no public sequence submission, and
no runtime redistribution.

Focused coverage is in `tests/unit/test_localisation_adapters.py` and
`tests/unit/test_localisation_wave_policy.py`, with a frozen PSORTb terse fixture
under `tests/fixtures/localisation/`. The dedicated Nextflow stub covers five
groups, a typed PSORTb failure, a zero-task branch, exact counts, exclusion
retention, zero-pack reopen, and byte-stable cached resume. Real PSORTb/DeepTMHMM,
composition-planner consumption, unknown profiles, and HPC execution remain
separate qualification slices.
