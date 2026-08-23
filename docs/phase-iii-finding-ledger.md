# Phase III finding ledger

Status: branch baseline prepared from `main` at `24f733c` while the corrected
P6-v2 Marmic replay remains non-terminal. Update a row only with a named
regression and an immutable evidence pointer. `Fixed` means the source contains
the correction; it does not by itself establish the later Phase III release
gate.

## Original 2026-08-17 review

Baseline disposition: 12 fixed, one superseded/deleted, five partial, and 16
open among the original 34 findings.

| Finding | Baseline disposition | Phase III gate / required evidence |
| --- | --- | --- |
| `PIPE-P1-01` | Open | Independently mutate FAA, MTZ, database inventory, adapter, lock, and Phenix identity; only dependent tasks rerun. |
| `PIPE-P1-02` | Partial; three-crystal boundary fixed | Exact complete-item fan-out now covers three crystals with cached resume; hypotheses, seeds, and finalists remain to be integrated. |
| `PIPE-P1-03` | Partial | Enabled-provider no-hit and disabled/no-model bundles compose without abort or network call. |
| `PIPE-P1-04` | Open | Network work resolves only to approved staging; compute workers fail closed with sockets blocked. |
| `PIPE-P1-05` | Fixed | Dataset-qualified duplicate-label tests reject conflicts and retain deterministic equivalent selection. |
| `PIPE-P1-06` | Partial | Schema-v2 binds a dataset-qualified MTZ selection, every override source, and selection-derived first-copy/refinement command identities. Known observation-label parameters and sequence-from-map high resolution are explicit; qualified Phaser/refinement space-group and resolution-limit parameters remain pending and are typed as preflight-verified boundaries. |
| `PIPE-P1-07` | Open | Free-R identity changes with selection; malformed flags fail; exact HKL membership survives refinement. |
| `PIPE-P1-08` | Open | Parent uncertainty is preserved; placed/packed does not become scientific support. |
| `PIPE-P1-09` | Fixed on `dev/phase3`; integration evidence pending | T12 accepts only a new or empty attempt-owned directory; stale files fail before tool execution and cannot be published. |
| `PIPE-P1-10` | Fixed | Duplicate JSON/YAML keys fail through every loader. |
| `PIPE-P1-11` | Fixed | Strict wire types and non-finite rejection cover every runtime loader. |
| `PIPE-P1-12` | Fixed | Duplicate Matthews/preflight/group/source identities fail. |
| `PIPE-P2-01` | Fixed on `dev/phase3`; integration evidence pending | Zero-exit refinement without parsed final Rwork/Rfree becomes `failed_parse`; completed result contracts require both final values. |
| `PIPE-P2-02` | Fixed on `dev/phase3`; integration evidence pending | Unknown or inconsistent sequence-map catalogue identities emit candidate-level `failed_parse` records instead of aborting sibling finalists. |
| `PIPE-P2-03` | Fixed | Runtime, tracked, and packaged schemas are byte/semantic parity checked. |
| `PIPE-P2-04` | Fixed | Duplicate headers and ragged TSV rows produce typed diagnostics. |
| `PIPE-P2-05` | Fixed | All executed Phenix binaries are digest-bound and replacement is refused. |
| `PIPE-P2-06` | Partial; three-crystal boundary fixed | Three crystal items retain complete shared context; two-catalogue and malformed-sibling isolation remain open. |
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
| `DEV-P1-07` | Partial | Real cache-key mutations and deleted-child probes drive observed rerun/HOLD evidence. |
| `DEV-P2-01` | Partial | Permutations at every aggregation boundary produce byte-identical trees. |
| `DEV-P2-02` | Partial | M6, M4, and T12 use site/run-owned caches with no account literal. |
| `DEV-P2-03` | Open | Remove/migrate nested scientific thread-pool CLIs and provide migration diagnostics. |

## Findings added after the original review

| Finding | Baseline disposition | Phase III gate / required evidence |
| --- | --- | --- |
| `PH3-P0-01` P6 composition claims self-asserted | Fixed in P6-v2; real replay pending | Missing/wrong B and 9ECN consume typed assessments; packed wrong B remains search evidence only. |
| `PH3-P0-02` P6 control identities under-bound | Fixed in P6-v2; real replay pending | Exact parents, MTZ/models, source preparations, catalogue-minus-A universe, and checksums match. |
| `PH3-P0-03` Empty partner channel unexecuted | Fixed locally; real replay pending | Real Nextflow schedules zero partner tasks, one summary, and caches byte-identically. |
| `PH3-P1-01` Control-only heteromer bridge | Open | A non-control application uses no 6RTZ preparation or fixed-control process. |
| `PH3-P1-02` B registry restricted by A cap | Open | A valid B model outside the A execution cap remains searchable in the all-model registry. |
| `PH3-P1-03` Parent uncertainty dropped | Open; overlaps `PIPE-P1-08` | A lower-identity parent retains its model-error evidence and incremental LLG uses compatible likelihood models. |
| `PH3-P1-04` Credible status lacks final evidence/crystal binding | Open | Missing final metrics, unsupported copies, or mismatched crystal ID cannot produce a credible report. |
| `PH3-P1-05` General component depth unvalidated | Contract fixed; control validation pending | Schema-v2 enforces provisional depths above three; 9ECN must still validate depth three. |
| `PH3-P1-06` Selected crystal status promoted globally | Open | Every result and report stays bound to one crystal item; sibling success cannot promote a held/failed crystal. |
| `PH3-P1-07` Provider empty channels untested end to end | Open | Enabled no-hit, disabled, and no-model providers each reach a typed complete terminal record through Nextflow. |
| `PH3-P1-08` Unknown-panel mixed outcomes cannot finalise | Open | One success, one no-hit, and one typed tool/parse failure produce three honest terminal reports. |
| `PH3-P1-09` Component-specific scores obscured by parent | Open | Every expansion records component TFZ and incremental LLG separately from combined/parent LLG. |
| `PH3-P1-10` Deeper component claims lack validation boundary | Planned | Depth three is control-validated; depths four to six are forcibly provisional regardless score/packing/refinement. |
| `PH3-P1-11` Per-parent plans multiply the depth budget | Fixed on `dev/phase3`; execution evidence pending | One parent-bound depth plan proves a shared maximum of 25 attempts across the complete three-parent beam and a 100-attempt global bound. |
| `PH3-P1-12` Unverified DeepTMHMM image command could be guessed | Fixed contract; runtime integration blocked | User image/input checksums are bound, but command and parser remain empty with `blocked_unverified_cli` until the supplied image is inspected. |
| `PH3-P1-13` Conflicting localisation could become a hard exclusion | Fixed contract; ranking evidence pending | Conflicting informative tool outcomes resolve to `conflicting`; unknown and failed observations remain neutral rather than excluded. |

## Closure rule

Before `v0.3.0`, rerun an independent adverse review against the exact release
candidate. Every row must be `Fixed`, `Superseded`, or `Deleted`, with a focused
regression, commit/CI evidence, and any required fixed-HPC evidence.
