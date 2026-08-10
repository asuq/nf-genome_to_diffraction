# P1 ProstT5/Foldseek qualification

## Current result

The first real full-catalogue ProstT5/Foldseek attempt reached the external
search but failed with Foldseek exit status 1. It therefore provides execution
evidence, not a completed search and not a scientific no-hit. The direct PDB
branch in the same immutable run completed normally.

This report records the failure before the retry so that later success cannot
erase the original operational evidence. The immediate priority is a
representative real-data result, followed by the full-catalogue gate; additional
synthetic polishing is not a prerequisite.

## Immutable attempt and retained evidence

| Item | Observed value |
| --- | --- |
| Fixed run | `gtd-p1-20260809T231907Z-24020981eff0-312edb08` |
| Source revision | `24020981eff0c6ef4e1280426cfd93f0cef8e0e5` |
| nf-helper revision | `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a` |
| Coordinator Slurm job | `625581` |
| Direct-search child job | `625582`, completed |
| ProstT5/Foldseek child job | `625583`, exit status 1 |
| Catalogue | 1,625 source records, 1,621 exact sequence groups |
| ProstT5 input | 1,620 eligible exact sequences, CPU mode, 16 threads |
| Search resources | Qualified Foldseek 10.941cd33 PDB100 and ProstT5 resources |
| External-command interval | 9 August 2026 23:37:15 UTC to 10 August 2026 00:04:41 UTC |
| Fixed failure class | `test_failure` |
| Failure signature | `f5af2fc0c6a55b8ca021b41dcd0a56c373b23fe17e79bd9b4c79f9a4d949fb9d` |

The direct branch retained 15,405 normalised hits for 944 sequence groups;
676 completed with no direct hit and one was ineligible. That branch is
consistent with the separately accepted direct-PDB qualification. The failed
run did not reach the P1 resume or qualification phases, so it does not supersede
the earlier accepted direct-provider evidence.

Foldseek wrote its detailed native log below the compute-node `/scratch` task
directory. Nextflow reported only the adapter's exit-status message, and the
outer coordinator then removed its job-owned scratch as designed. No retained
evidence identifies out-of-memory, malformed input, database corruption, or a
specific Foldseek defect. Treating any one of those as the root cause would be
speculation.

## Focused correction and pilot slice

The retry changes only the demonstrated operational boundaries:

1. an external-tool failure includes at most the final 16 KiB and 40 lines of
   the native Foldseek log in durable structured error output;
2. ProstT5/Foldseek has a distinct process label on Marmic and requests the
   qualified large node: 100 CPUs, 2,000 GB RAM, compute-node `/scratch`, and
   the site's 1,000-hour scheduler margin;
3. the fixed first retry searches the first 128 otherwise eligible records in
   lexicographic `sequence_group_id` order; and
4. all other eligible records are emitted as `skipped_policy` /
   `not_interpretable` with the pilot-cap reason. They are never converted to
   `completed_no_hit`.

The cap is deterministic and enters the search/cache identity. In the frozen
pilot catalogue, the exact 442-residue `WP_042685700.1` glutamine-synthetase
sequence group is sorted rank 118, so it is included. Its sequence-group ID is
`seq_102e653b2ce68310033502e10e60f54e7cb143dc71acd0e964d0cad47f961964`.
This provides a known real catalogue control without inventing a separate toy
sequence.

## Acceptance boundary

The 128-query run qualifies command construction, real ProstT5 inference,
Foldseek/PDB search, result parsing, target crosswalking, explicit deferred
states, publication, and cached resume on the actual Marmic resources. It does
not close catalogue-wide P1 and cannot be described as complete evidence for
the 1,492 deferred eligible sequences.

After the pilot slice passes, proceed directly to coordinate/model preparation
for the known positive-control path while running the uncapped catalogue search
as the remaining T7.2 gate. A second identical full-catalogue failure will now
carry the bounded native diagnostic required to decide whether batching,
Foldseek parameters, resource selection, or database repair is warranted.
