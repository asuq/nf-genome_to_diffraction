# Phase III offline localisation adapter boundary

This focused slice defines offline, one-sequence-group localisation contracts. It
does not schedule Nextflow processes, exclude or rank candidates, download a
runtime, or submit sequences to a public service.

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
empty command with `blocked_unverified_cli`. The image is never redistributed. A
future slice may enable execution only after inspecting the supplied image and
freezing its exact CLI, raw-output fixture, parser, and failure test. No DeepTMHMM
result is fabricated while invocation is blocked.

## Status and cache boundary

The shared outcome vocabulary is `membrane`, `surface`, `extracellular`,
`transmembrane`, `soluble`, `unknown`, `conflicting`, and `failed`. Unknown and
failed evidence do not override a successful independent observation; incompatible
informative observations resolve to `conflicting` rather than to an exclusion.

PSORTb runtime and command identities include tool version, adapter version,
executable checksum, sequence identity, input checksum, archaeal model, and output
format. DeepTMHMM runtime/input plans bind the image, version, sequence, and FASTA
checksums. Both contracts state `local_offline`, no network use, no public sequence
submission, and no runtime redistribution.

Focused coverage is in `tests/unit/test_localisation_adapters.py`, with a frozen
PSORTb terse fixture under `tests/fixtures/localisation/`. Nextflow integration,
catalogue-wide fan-out, first-wave policy, and candidate ranking are intentionally
deferred.
