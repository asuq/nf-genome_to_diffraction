# Phase III finding ledger

Status: baseline prepared from `main` after the P6-v2 correction. This ledger is
updated only with a named regression and immutable evidence pointer. `Fixed`
means current main contains the correction; it does not by itself establish the
later Phase III release gate.

## Original 2026-08-17 review

Baseline disposition: 12 fixed, one superseded/deleted, five partial, and 16
open among the original 34 findings.

| Finding | Baseline disposition | Phase III gate / required evidence |
| --- | --- | --- |
| `PIPE-P1-01` | Open | Mutate FAA, MTZ, database inventory, adapter, lock, and Phenix identity independently; only dependent tasks rerun. |
| `PIPE-P1-02` | Partial | Exact fan-out for three hypotheses, two seeds, and two finalists plus cached resume. |
| `PIPE-P1-03` | Partial | Enabled-provider no-hit and disabled/no-model bundles compose without abort or network call. |
| `PIPE-P1-04` | Open | Network work resolves to approved staging; compute workers fail closed with sockets blocked. |
| `PIPE-P1-05` | Fixed | Dataset-qualified duplicate-label tests reject conflicts and retain deterministic equivalent selection. |
| `PIPE-P1-06` | Open | Space-group/resolution overrides reach and are verified in every Phaser/refinement command. |
| `PIPE-P1-07` | Open | Free-R identity changes with selection; malformed flags fail; exact HKL membership survives refinement. |
| `PIPE-P1-08` | Open | Parent uncertainty is preserved; placed/packed does not become scientific support. |
| `PIPE-P1-09` | Open | Pre-existing T12 files cannot be published when the current attempt writes nothing. |
| `PIPE-P1-10` | Fixed | Duplicate JSON/YAML keys fail through every loader. |
| `PIPE-P1-11` | Fixed | Strict wire types and non-finite rejection cover every runtime loader. |
| `PIPE-P1-12` | Fixed | Duplicate Matthews/preflight/group/source identities fail. |
| `PIPE-P2-01` | Open | Zero-exit refinement without parsed final Rwork/Rfree becomes `failed_parse`. |
| `PIPE-P2-02` | Open | Malformed sequence-map outputs are typed per candidate and siblings continue. |
| `PIPE-P2-03` | Fixed | Runtime, tracked, and packaged schemas are byte/semantic parity checked. |
| `PIPE-P2-04` | Fixed | Duplicate headers and ragged TSV rows produce typed diagnostics. |
| `PIPE-P2-05` | Fixed | All executed Phenix binaries are digest-bound and replacement is refused. |
| `PIPE-P2-06` | Open | Two catalogues and three crystals fan out independently; one malformed item does not erase siblings. |
| `PIPE-P2-07` | Open | One classified transient failure retries once; scientific/parser failures execute once. |
| `PIPE-P2-08` | Fixed | Declaration-only toggles/caps are removed; every retained cap has one runtime consumer. |
| `PIPE-P3-01` | Open | Locked offline wheel build, isolated install, both entry points, schemas, and version parity. |
| `DEV-P0-01` | Fixed | Frozen family snapshots and private truth classify retained PDB/entity attempts. |
| `DEV-P0-02` | Fixed | Typed identity decisions make wrong open-set reports hold. |
| `DEV-P0-03` | Fixed | Edge outcomes derive from observed evidence, not descriptors. |
| `DEV-P1-01` | Fixed | Every catalogue receives complete shared batch/result values. |
| `DEV-P1-02` | Open | Ordinary M6 MTZs retain only HKL, observations/sigma, and validated Free-R. |
| `DEV-P1-03` | Open | Leakage filtering precedes accepted-hit truncation and retains a fourth safe hit. |
| `DEV-P1-04` | Open | One bounded staging task obtains coordinates; case workers never perform HTTPS. |
| `DEV-P1-05` | Superseded/deleted | Unsafe shared-store consumer path was removed in favour of standard Nextflow resume. |
| `DEV-P1-06` | Open | Advancement does not silently prefer the largest copy hypothesis per model. |
| `DEV-P1-07` | Partial | Real cache-key mutations and deleted-child probes must drive observed rerun/HOLD evidence. |
| `DEV-P2-01` | Partial | Permutations at every aggregation boundary produce byte-identical trees. |
| `DEV-P2-02` | Partial | M6, M4, and T12 use site/run-owned caches with no account literal. |
| `DEV-P2-03` | Open | Remove/migrate nested scientific thread-pool CLIs and provide migration diagnostics. |

## Findings added after the original review

| Finding | Baseline disposition | Phase III gate / required evidence |
| --- | --- | --- |
| `PH3-P0-01` P6 composition claims self-asserted | Fixed in P6-v2; real replay pending | Missing/wrong B and 9ECN consume typed assessments; a packed wrong B remains search evidence only. |
| `PH3-P0-02` P6 control identities under-bound | Fixed in P6-v2; real replay pending | Exact parents, MTZ/models, source preparations, catalogue-minus-A universe, and checksums all match. |
| `PH3-P0-03` Empty partner channel unexecuted | Fixed locally; real replay pending | Real Nextflow graph schedules zero partner tasks, one summary, and caches byte-identically. |
| `PH3-P1-01` Control-only heteromer bridge | Open | A non-6RTZ application uses no fixed-control bundle or process. |
| `PH3-P1-02` B registry restricted by A cap | Open | A valid B model outside the A execution cap remains searchable in the all-model registry. |
| `PH3-P1-03` Parent uncertainty dropped in fixed composition | Open; overlaps `PIPE-P1-08` | A 35%-identity parent remains 35% and incremental LLG uses compatible likelihood models. |
| `PH3-P1-04` Credible status lacks final evidence/crystal binding | Open | Missing final metrics, unsupported copies, or mismatched crystal ID cannot produce a credible report. |
| `PH3-P1-05` General component depth unvalidated | Planned | 9ECN validates depth three; depths four to six remain explicitly provisional. |

## Closure rule

Before `v0.3.0`, rerun an independent adverse review against the exact release
candidate. Every row above must be `Fixed`, `Superseded`, or `Deleted`, with a
focused regression, commit/CI evidence, and any required fixed-HPC evidence.
