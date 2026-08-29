# Phase III complete-catalogue ProstT5/Foldseek batching

The ordinary prototype originally submitted one complete sequence catalogue to
ProstT5/Foldseek. Its fixed 128-query pilot could defer later proteins while
still publishing a superficially completed search. Phase III therefore opts in
to complete, Nextflow-owned catalogue batching without changing historical
single-batch provider runs.

## Inputs and execution

One strict sequence-group JSONL file is sorted by its immutable sequence-group
identity. The complete inventory is divided into deterministic content-addressed
batches containing no more than 128 groups. The frozen 1,621-group application
catalogue therefore produces exactly 13 independent batch items; no group is
silently omitted because of eligibility, rank, or its location in the input.

The existing resolved provider plan, Foldseek provider entry, database manifest,
sequence bytes, and configured search parameters cross every process boundary.
Each Nextflow `SEARCH_PHASE3_FOLDSEEK_BATCH` task invokes the existing
`structure-search prostt5-foldseek` adapter once with its own complete,
already-bounded catalogue and without an additional within-batch pilot cap.
The existing `process_prostt5_search` label retains site resource policy. Each
batch is an independent Nextflow item; no process-local `maxForks` cap is set,
so the site scheduler owns placement, fairness, and concurrent execution.

Exact-source Marmic job `636570` qualified this policy with all 13 children
submitted together at 32 CPUs and 192 GB. Every child completed in under five
minutes at 21.1--22.2 GB peak RSS and was recovered as `CACHED` on resume.

Direct PDB search, disabled providers, existing search thresholds, and
non-Phase-III application modes retain their previous behaviour. No Python
thread pool or nested scheduler performs scientific work.

## Outputs, failures, and cache identity

The plan records the complete source SHA-256, exact batch count, maximum group
count, and every ordered group identity. The merger independently requires
every expected batch exactly once, complete typed query coverage, zero deferred
queries, consistent result/hit inventories, and matching result, raw-tool, and
command-log checksums. A missing, duplicated, changed, or incomplete batch is
an input-contract failure, not a scientific no-hit.

Each per-batch raw Foldseek result and command log remains under the merged
provider bundle, and typed result pointers are rebased to their retained
location. The historical provider output files remain
`search_results.jsonl`, `structural_hits.jsonl`, and `search_manifest.json`;
the aggregate manifest additionally records exact batch count and source batch
manifest checksums. Sequence/provider inputs and immutable batch identities
form task cache keys, and sorted batch/result inventories make merged output
independent of scheduler completion order.

Focused public synthetic regressions cover exact 13-by-128 planning,
byte-identical reverse-order merges, missing/duplicate/deferred/mutated batch
refusal, and changed raw evidence. The dedicated
`pixi run --locked phase3-foldseek-batch-stub` gate executes real Nextflow
scheduling with typed synthetic no-hit outputs and validates fully cached
resume; it never runs Foldseek, downloads a database, or submits a sequence to
an external service. Real installed-tool and fixed-HPC qualification remain
separate required gates.
