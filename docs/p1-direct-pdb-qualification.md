# P1 direct-PDB qualification

## Scope

This report records the first real catalogue-wide direct PDB sequence-search
run on Marmic. It qualifies the T7.1 MMseqs2 provider and the fixed P1 execution
boundary. It does not close the full M1 gate: ProstT5/Foldseek, exact AFDB
retrieval, optional policy-gated ESM Atlas search, and provider evidence union
remain to be implemented.

The search supplies structural-family and model evidence for catalogue sequence
groups. It does not identify any blind crystal and does not perform molecular
replacement.

## Gate summary

| Check | Result | Evidence |
| --- | --- | --- |
| Immutable software revision | Passed | Git commit `f198884a5d7e6c66c0f6a94f1a28cadb0004fe37`; `nf-helper` commit `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a` |
| Local/CI software gate | Passed | 228 unit, 51 contract, and 33 integration tests; GitHub Actions run `31339483112` succeeded |
| Fixed Marmic operation | Passed | P1 run `gtd-p1-20260809T223232Z-f198884a5d7e-2f8e104c`, Slurm coordinator job `625575` |
| Catalogue coverage | Passed | 1,625 source records normalised to 1,621 exact-sequence groups; 1,620 groups were eligible for search |
| Direct PDB execution | Passed | MMseqs2 18.8cc5c searched immutable database `db_485ff3f74924baf9e9a5e15d52da221da678c8add3ddf328d4d4a606b3c7552c` |
| Positive-control family | Passed | Exact 8OOW chains occupied ranks 1–12 and 8OOX chains A/B ranks 13–14 for the tracked 8OOX sequence group |
| Retrievable model keys | Passed | Every retained hit passed the namespaced PDB model-key check |
| Resume | Passed | The sole scientific process was `COMPLETED` first and `CACHED` on `-resume` |
| Resource evidence | Passed | Process time, CPU, memory, process-I/O counters, result size, and cache state were retained |

## Catalogue and search outcome

The frozen `GCF_000711905.1` catalogue produced 1,621 exact-sequence groups from
1,625 source protein records. Catalogue import retained 12 explicit review
flags: two compound-CDS merge flags, two below-minimum-length exclusions, and
eight multiple-compatible-locus flags. These are review states, not silent
record loss.

The direct PDB provider reported:

- 944 sequence groups with one or more retained hits;
- 676 completed scientific no-hit results;
- one explicitly ineligible group;
- 15,401 retained normalised hits in total; and
- 31,304,315 bytes in the validated search result tree.

A completed no-hit remains a scientific outcome of this provider and is not
negative evidence that the catalogue sequence cannot explain a crystal.

## Positive-control result

The predeclared control group was
`seq_102e653b2ce68310033502e10e60f54e7cb143dc71acd0e964d0cad47f961964`,
the exact 442-residue `WP_042685700.1` sequence used by PDB 8OOX. Fourteen exact
family hits were retained, all with E-value `2.585e-298`, bit score 910, query
coverage 1.0, and sequence identity 1.0:

- PDB 8OOW chains A–L at provider ranks 1–12; and
- PDB 8OOX chains A/B at provider ranks 13–14.

The result proves that the bounded top-25 direct-search route retains the known
operational exact model family and a retrievable model key. The control is
intentionally not leakage-controlled and therefore does not estimate
generalisation performance.

## Runtime and cache evidence

The outer fixed job ran from `2026-08-09T22:34:09Z` to
`2026-08-09T22:47:59Z`. This includes NFS-cold Python/Nextflow startup,
catalogue import, scheduling, search, cached resume, qualification, and scratch
finalisation.

The scientific search child, Slurm job `625578`, recorded:

- Nextflow duration 1 minute 29 seconds and process realtime 54.6 seconds;
- 72.7% reported CPU utilisation;
- 151.4 MB peak RSS and 2.9 GB peak virtual memory;
- 223.7 MB `rchar` and 34.3 MB `wchar`; and
- exit status 0.

The `rchar`/`wchar` fields are process-I/O counters and are not assumed to equal
physical database-device traffic. The cached trace preserves the original
process measurements and changes only the execution status to `CACHED`.

## Observed warning and limitations

Nextflow accepted the configured E-value and coverage values but warned that
DSL numeric parameters arrived as `BigDecimal` at module ports typed `Float`.
The follow-up source explicitly converts those two values before the typed
module call; local syntax and stub execution no longer emit the mismatch. The
real scientific result was not rerun solely for this non-fatal typing warning.

The run qualifies only the direct sequence-to-PDB provider. It does not yet:

- provide structure-similarity evidence for remote homologues;
- retrieve or process coordinates;
- deduplicate equivalent chains into processed model identities;
- construct the bounded MR hypothesis funnel; or
- make a protein-identity or crystallographic-solution claim.

The next real-data priority is T7.2 ProstT5/Foldseek-to-PDB, followed by exact
model retrieval and provider-aware evidence union.
