# P1 ProstT5/Foldseek qualification

## Current result

The first real full-catalogue ProstT5/Foldseek attempt and first bounded
128-sequence retry reached the external search but failed with Foldseek exit
status 1. The retry retained the native log tail and identified a specific
adapter incompatibility: requesting `prob` from a ProstT5 sequence query makes
Foldseek `convertalis` require a query Cα database that does not exist. Adapter
v2 removed that field, and the next real 128-sequence run completed Foldseek
successfully in 6 minutes 39 seconds. It then failed loudly at target
crosswalking because PDB100 contains RCSB biological-assembly symmetry-copy
chains such as `A-2`, whereas the SEQRES resource is keyed by the original
chain `A`. These runs provide execution evidence, not completed searches and
not scientific no-hits. The direct PDB and exact AFDB branches produced
retained artefacts where the workflow reached them.

This report retains all three failed runs so that later success cannot erase the
operational evidence. The immediate priority remains a representative real-data
result, followed by the full-catalogue gate; additional synthetic polishing is
not a prerequisite.

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

## Bounded retry and diagnosed root cause

| Item | Observed value |
| --- | --- |
| Fixed run | `gtd-p1-20260810T004207Z-b0a33315a57c-c924c5fa` |
| Source revision | `b0a33315a57c02ab0bcb14e22e818e6e124d08bc` |
| nf-helper revision | `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a` |
| Coordinator Slurm job | `625585` |
| Catalogue | 1,625 source records, 1,621 exact sequence groups |
| ProstT5 input | first 128 of 1,620 eligible exact sequences, CPU mode, 100 threads |
| Run interval | 10 August 2026 00:43:10–00:59:43 UTC |
| Fixed failure class | `test_failure` |
| Failure signature | `eb60cf9bf626f8c3f7f8055c3cb5605a01c000fba56f583d6ad0a03847ce5571` |

ProstT5 inference, prefiltering, and structural alignment completed for all 128
selected queries. Foldseek then warned that the query Cα database was absent,
disabled structure-bit sorting, and failed in `convertalis` with `No datafile
could be found for .../query_ca`. The fixed output list ended in `prob`.

The exact installed Foldseek tag is `10-941cd33` at source commit
`941cd33ff0771cd2e3f144e3293e22a2b87e9fda`. Its output-field parser leaves
`qcov` and `tcov` coordinate-independent, while `prob` sets `needQCa`,
`needTCa`, `needLDDT`, `needBacktrace`, and `needTMaligner`; see
[`LocalParameters.cpp` lines 383–403](https://github.com/steineggerlab/foldseek/blob/941cd33ff0771cd2e3f144e3293e22a2b87e9fda/src/commons/LocalParameters.cpp#L383-L403).
The software failure is therefore in adapter output construction, not evidence
of insufficient CPUs or RAM, slow NFS, database corruption, catalogue defects,
or a scientific no-hit.

## Focused corrections and next pilot slice

The first retry changed only the demonstrated operational boundaries:

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

Adapter v2 now removes only `prob` from `--format-output`, keeps identity,
coordinates, lengths, coverage, E-value, and bit score, and reports probability
as unavailable with the source-derived reason. Hit ordering is E-value, then
descending bit score, query coverage, target coverage, and target identifier.
The adapter version and cache identity changed so failed v1 output cannot be
mistaken for v2 evidence. A focused command-construction regression test rejects
reintroduction of `prob` or the other query-coordinate fields.

## Source-corrected search and assembly-copy finding

| Item | Observed value |
| --- | --- |
| Fixed run | `gtd-p1-20260810T094507Z-0411a521d725-d1eb9519` |
| Source revision | `0411a521d7250ada74ae57657789902fdc37dcd5` |
| nf-helper revision | `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a` |
| Coordinator Slurm job | `625649` |
| Compute host | `slurm-302.mpi-bremen.de` |
| Catalogue | 1,625 source records, 1,621 exact sequence groups |
| ProstT5 input | first 128 of 1,620 eligible exact sequences, CPU mode, 100 threads |
| Foldseek interval | 10 August 2026 10:01:00–10:07:40 UTC |
| Foldseek exit status | `0` |
| Fixed failure class | `test_failure` |
| Failure signature | `f8d8aa06c5b658abdabc461429ea32bf0ace8e95b336598b4be45f0dd7ab4f0c` |

This run proves that removing `prob` was sufficient for the exact pinned
Foldseek command to complete on the intended real inputs and database. Parsing
then reported unmapped identifiers including `1IOM-assembly1_A-2`,
`2BB3-assembly1_B-3`, and `3CTA-assembly1_A-2`. The suffix is not a SEQRES chain:
RCSB appends a numeric transformation-operator ID to copies in generated
biological assemblies. Foldseek's pinned PDB100 build uses assembly mmCIF input
with `--chain-name-mode 1`, and its `createdb` implementation writes the parsed
chain name to the database header unchanged.

Adapter v3 strips only trailing positive numeric operator components from an
assembly-qualified target for crosswalk lookup. It retains the unmodified
Foldseek target, raw assembly chain, biological-assembly number, and parsed
operator indices in output provenance. Targets without `-assemblyN` are not
normalised this way. The behaviour follows the exact
[Foldseek PDB100 build command](https://github.com/steineggerlab/foldseek/blob/941cd33ff0771cd2e3f144e3293e22a2b87e9fda/util/update_webserver_pdb/single-script.sh#L41),
[Foldseek header construction](https://github.com/steineggerlab/foldseek/blob/941cd33ff0771cd2e3f144e3293e22a2b87e9fda/src/strucclustutils/structcreatedb.cpp#L417-L421),
and the official
[RCSB biological-assembly chain convention](https://www.rcsb.org/news/62559153c8eabd0c4864f208).

## Acceptance boundary

The next passing 128-query run will qualify command construction, real ProstT5
inference, Foldseek/PDB search, result parsing, target crosswalking, explicit
deferred states, publication, and cached resume on the actual Marmic resources.
It does not close catalogue-wide P1 and cannot be described as complete evidence
for the 1,492 deferred eligible sequences.

After the corrected pilot slice passes, proceed directly to the next real
prototype stage while running the uncapped catalogue search as the remaining
T7.2 gate. The known positive-control AFDB coordinate/model-preparation path has
already passed independently; it does not substitute for the local
ProstT5/Foldseek gate.
