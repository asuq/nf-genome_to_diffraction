# Adversarial code review — 2026-08-17

## Executive verdict

Reviewed revision: `aa334b47db419d9cb6fbe3eed0ffea6fd950f20d`
(`feat(m6): fan out validation through Nextflow`).

The repository has a strong amount of defensive validation and its complete
locked local gate passes. It is nevertheless **not ready for an M6 acceptance
decision or a general production release**.

Three defects make central M6 release gates structurally incapable of measuring
what they claim to measure:

1. any accepted structural hit is counted as a correct-family model;
2. exact false assignments are hard-coded to be absent during collection; and
3. several edge outcomes are copied from the injected fault descriptor rather
   than derived from observed behaviour.

The enduring pipeline also has high-priority defects. In particular, the
integrated Nextflow route runs only the first item of several scientific
fan-outs, `-resume` can reuse results after indirect raw inputs or adapter code
change, provider configuration is ignored, Free-R and crystallographic
overrides are not propagated, and packing alone is labelled as copy support.

Recommended decision: **hold M6 and the internal-release gate**. A passing
two-case M6 smoke would establish only basic Slurm orchestration; it cannot
clear the findings below.

## Scope and classification

The review used two requested scopes.

### A. Enduring actual pipeline

This includes the main Nextflow route and shared catalogue, diffraction,
database, search, model-preparation, ranking, molecular-replacement,
refinement, review, schema, and Phenix-runtime code.

### B. Temporary HPC development and validation apparatus

This includes the repository-specific HPC controller and wrappers, M0–M6
benchmark execution/acceptance machinery, M6-specific Nextflow graph,
validation-only profiles, fixtures, and operational evidence collectors. This
section is intended to support correction before validation and safe removal
after immutable evidence has been retained.

Some findings are cross-cutting because temporary validation code calls shared
pipeline adapters. They are filed under the enduring pipeline when the shared
adapter itself must be corrected.

## Severity

- **P0 — stop gate:** an acceptance or release decision can be scientifically
  invalid. Do not accept M6 while open.
- **P1 — high:** silent scientific error, stale evidence, major workflow
  incompleteness, or a routine operational blocker.
- **P2 — medium:** important reliability, failure-taxonomy, portability, or
  maintainability defect.
- **P3 — low:** reproducibility or packaging debt without an immediate
  scientific result error.

| Scope | P0 | P1 | P2 | P3 | Total |
|---|---:|---:|---:|---:|---:|
| Enduring actual pipeline | 0 | 12 | 8 | 1 | 21 |
| Temporary HPC/validation apparatus | 3 | 7 | 3 | 0 | 13 |
| **Overall** | **3** | **19** | **11** | **1** | **34** |

## Current codebase status

### Milestone state

- Repository policy states that M0–M5 are accepted.
- Prototype 0.2 is accepted with the recorded limitation that 7L6G supports
  three rather than its declared six copies.
- The M6 protocol and predeclared criteria are approved, but acceptance evidence
  is pending.
- The newest local journal entry says the superseded monolithic M6 run was
  cancelled and the two-case Nextflow/Slurm smoke was submitted as job
  `10938045`; its last recorded state was the initial non-terminal snapshot.
  No live HPC query was made during this review.
- The journal records a green GitHub Actions run for the reviewed revision.
  This review did not independently query GitHub.

### Repository statistics at reviewed `HEAD`

Line counts use `wc -l` and include comments and blank lines.

| Measure | Value |
|---|---:|
| Version | `0.1.0.dev0` |
| Branch | `main` |
| Commits reachable from `HEAD` | 243 |
| Tracked files | 391 |
| Tracked bytes | 4,084,070 |
| Tracked Python files | 140 |
| Package Python files / lines | 87 / 46,170 |
| Enduring package Python lines, excluding `benchmarks/` and `hpc/` | 30,796 |
| Benchmark Python lines | 10,126 |
| HPC-controller Python lines | 5,248 |
| Test Python files / lines | 52 / 21,699 |
| Nextflow files / lines | 43 / 2,940 |
| M6-specific Nextflow lines | 945 |
| Nextflow process definitions under `modules/` and `workflows/` | 41 |
| Reusable workflow definitions | 9 |
| Managed HPC wrapper lines (`nf-gtd-hpc-*`) | 6,605 |
| All reviewed shell/helper lines | 7,608 |
| JSON Schemas | 7 |
| Defined test functions across test suites | 457 |
| Frozen fixture files | 123 |
| M6 cases | 63 |

The package is large for a `0.1.0.dev0` prototype: approximately one third of
package Python is benchmark/HPC code. That makes the requested removal boundary
material rather than cosmetic.

### Working tree at review start

`main` matched `origin/main`. The only pre-existing change was an uncommitted
69-line append to `docs/development-loop-journal.md`. It was preserved. The
review findings file is intentionally not committed because the working tree
contains that pre-existing user change.

### Fresh local validation

`pixi run --locked check` passed during this review:

- Ruff format and lint;
- `ty` type checking;
- 439 unit tests;
- 59 contract tests;
- 51 integration tests;
- schema and fixture validation;
- the 12-entry public control panel check;
- Markdown link checks;
- GitHub Actions workflow lint;
- Nextflow syntax and the complete stub suite; and
- syntax checks for the three managed HPC wrappers.

Total executed pytest cases: **549 passed**.

The green gate is a baseline, not a rebuttal to the findings. Several stubs have
exactly one catalogue, hypothesis, seed, or finalist and therefore cannot reveal
channel-cardinality defects. No coverage percentage is available.

---

# A. Findings in the enduring actual pipeline

## PIPE-P1-01 — Nextflow cache identities omit real scientific and software inputs

Locations:

- `conf/base.config:2-14`
- `modules/local/import_catalogues.nf:8-24`
- `modules/local/mtz_preflight.nf:8-27`
- `modules/local/search_pdb_sequences.nf:8-32`
- `src/genome_to_diffraction/schemas/manifests.py:19-36,69-85`
- `src/genome_to_diffraction/catalogue/importer.py:464-475`
- `src/genome_to_diffraction/diffraction/preflight.py:727-733`
- `src/genome_to_diffraction/structure_search/pdb_sequence.py:470-522,633-643`
- `src/genome_to_diffraction/structure_search/prostt5_foldseek.py:614-702`
- `src/genome_to_diffraction/databases/common.py:529-612`

Trigger:

- change an FAA, annotation, or MTZ in place while its manifest bytes remain
  unchanged;
- mutate a database under an unchanged database manifest/database ID; or
- change Python adapter code or an executable while the `.nf` script text and
  declared inputs remain unchanged, then use `-resume`.

Mechanism and impact:

Raw scientific paths are strings inside manifests rather than declared
Nextflow `path` inputs. The adapters verify those bytes only after the process
starts; a cached process never executes the verification. Scientific processes
also do not receive a source/adapter identity or `pixi.lock`.

Database searches make the same problem stronger. Their cache keys contain
`database_id`, not each resource's inventory digest, and fresh search execution
does not call `verify_inventory()`. A mutated database can therefore be used or
reused while retaining the old identity and provenance.

This permits a successful workflow to return outputs generated from different
raw bytes, code, database contents, or licensed runtime than the current run.

Recommended fix:

1. Resolve manifests into typed, per-object planning records.
2. Declare every raw FAA, annotation, MTZ, and small inventory file as a
   Nextflow input with its expected checksum.
3. Pass a versioned software identity containing relevant adapter versions,
   source revision, and Pixi-lock digest to every scientific process.
4. Verify external database inventories before fresh execution and include the
   inventory digest in batch and per-record cache keys.
5. Use deep hashing where practical, but do not treat it as a substitute for
   materialising manifest-indirected inputs.

Regression test:

Run once, change only a referenced FAA, MTZ, database inventory, or adapter
identity, and rerun with `-resume`. The dependent process must execute again,
verify the new bytes, and emit a changed output identity.

## PIPE-P1-02 — The integrated fan-out consumes only one hypothesis, seed, or finalist

Locations:

- `workflows/main_workflow.nf:81-168,176-240`
- `workflows/diverse_first_copy_mr_workflow.nf:36-50`
- `modules/local/run_first_copy_phaser.nf:8-17`
- `workflows/additional_copy_workflow.nf:17-35`
- `modules/local/run_additional_copy_phaser.nf:9-20`
- `workflows/brief_refinement_workflow.nf:13-33`
- `modules/local/run_brief_refinement.nf:9-16`

Trigger:

Run `main.nf` with more than one first-copy hypothesis, approved seed, or T12
finalist.

Mechanism and impact:

Each multi-item fan-out channel is supplied to a process together with shared
inputs produced by `.map` from one-emission process outputs. Those shared
channels are one-shot queue channels, not reusable values. The first task
consumes the singleton items; later fan-out items cannot run.

A minimal Nextflow 26.04.6 probe with a three-item queue and a one-item queue
submitted only:

```text
PAIR_QUEUE_INPUTS (a:only)
```

The dedicated stage entry points avoid this because shared `params.*` objects
are value inputs. The integrated stub fixture has one hypothesis, so the locked
gate does not expose the bug.

Impact ranges from a later loud count mismatch to a partial downstream result.
It defeats the main workflow's intended scientific fan-out.

Recommended fix:

Convert every shared singleton to an explicit reusable value with `.first()`,
or, preferably, construct one complete tuple for each hypothesis/seed/finalist
and give the process a single tuple input.

Regression test:

An integrated stub must contain at least three hypotheses, two approved seeds,
and two finalists. Require exact matching task counts and ID sets in
`trace.tsv`, followed by a fully cached equivalent resume.

## PIPE-P1-03 — Provider configuration is ignored and valid provider no-hits abort composition

Locations:

- `src/genome_to_diffraction/schemas/manifests.py:150-170`
- `workflows/main_workflow.nf:87-132`
- `workflows/pdb_sequence_discovery_workflow.nf:27-52`
- `src/genome_to_diffraction/structure_search/pdb_coordinates.py:470-472`
- `src/genome_to_diffraction/model_registry/predicted.py:148-149,261-262`
- `src/genome_to_diffraction/model_registry/experimental.py:120-121`

Mechanism and impact:

No runtime code reads `PipelineConfig.providers`. PDB sequence, ProstT5/Foldseek,
and AFDB exact retrieval run unconditionally, with hit limits supplied through
separate Nextflow parameters. Consequently:

- `enabled: false` has no effect;
- `max_hits` can disagree with actual execution;
- `afdb_exact.enabled: false` does not prevent a network task; and
- `esm_atlas.enabled: true` is silently ignored.

The branches are also not composable under scientific no-hit. Empty PDB hits
cause coordinate registration to fail, while an empty AFDB coordinate-source
file is rejected by predicted-model preparation. Because the global strategy is
`terminate`, one valid provider no-hit can abort other viable model routes.

This contradicts the explicit policy that scientific no-hit is a completed
analysis, distinct from execution failure.

Recommended fix:

Build a provider execution plan from the validated pipeline configuration.
Disabled and no-hit providers must emit schema-valid typed empty bundles.
Model preparation must accept zero models from one provider, and only exhaustion
of all enabled routes should produce `completed_no_model`.

Regression test:

Test each provider disabled and no-hit independently, then all providers
disabled. No disabled executable/network request may occur, and each case must
complete with the appropriate typed status.

## PIPE-P1-04 — Network-labelled processes remain on network-isolated compute nodes

Locations:

- `modules/local/retrieve_afdb_exact.nf:3-6`
- `modules/local/register_pdb_coordinates.nf:3-6`
- `conf/base.config:61-65`
- `external/nf-helper/conf/sites/viper-cpu.config:60-71`
- `external/nf-helper/conf/sites/marmic.config:44-47`

Mechanism and impact:

The project labels remote tasks `process_network`, but that label only changes
resources. Viper maps `needs_internet` to its local executor; Marmic maps
`run_local`. Neither site maps `process_network`, so the HTTPS tasks remain
Slurm jobs. On a cache miss, compute nodes attempt AFDB or RCSB access despite
the policy that remote work needs a dedicated network profile.

Recommended fix:

Use one canonical network label and map it explicitly at every supported site,
or split bounded login-node staging from offline compute. Refuse submission
when the selected profile has no approved route.

Regression test:

Resolve both site profiles and assert the two network processes use the intended
executor. With compute-node sockets disabled and an empty coordinate cache,
staging must still work through only the approved process.

## PIPE-P1-05 — Duplicate observation labels across MTZ datasets are silently misclassified as equivalent

Locations:

- `src/genome_to_diffraction/diffraction/preflight.py:83-90,158-209`
- `src/genome_to_diffraction/diffraction/preflight.py:213-246,249-307`

Mechanism and impact:

The observation candidate stores labels but not `dataset_id`. Gemmi permits two
datasets to contain the same labels. Candidate discovery correctly pairs within
a dataset, but equivalence testing later calls `column_with_label(label)`,
which returns the first matching column for both candidates.

A focused in-memory probe built two datasets with conflicting `I,SIGI` arrays.
The selector returned:

```text
selected: I,SIGI
candidates: ('I,SIGI', 'I,SIGI')
warnings: ('equivalent_observation_arrays',
           'observation_selection_deterministic')
```

The conflicting second dataset was never compared. Explicit `obs_labels` is
also unable to distinguish the two datasets. Downstream Phenix may therefore
use data different from the preflight interpretation.

Recommended fix:

Carry dataset identity with every selected column. Reject duplicate rendered
labels across datasets unless the input contract can specify a dataset
unambiguously, or materialise a derived MTZ containing exactly one selected
dataset with unique labels.

Regression test:

Create equal-label/equal-array and equal-label/conflicting-array multi-dataset
MTZs. The former may be deterministically materialised with recorded dataset
identity; the latter must fail as ambiguous.

## PIPE-P1-06 — Space-group and resolution overrides are recorded but ignored downstream

Locations:

- `src/genome_to_diffraction/diffraction/preflight.py:740-768,846-876`
- `src/genome_to_diffraction/schemas/results.py:489-505`
- `src/genome_to_diffraction/mr/phaser.py:407-421,541-556`
- `src/genome_to_diffraction/mr/add_copy.py:396-440`
- `src/genome_to_diffraction/refinement/brief.py:370-447,552-560`

Mechanism and impact:

Preflight substitutes its in-memory space group and resolution range and uses
them for ASU volume, Matthews hypotheses, and Xtriage. It does not rewrite the
MTZ. First-copy Phaser, additional-copy Phaser, and `phenix.refine` receive the
unchanged MTZ and no explicit approved space group/range. Refinement resolution
is used only by `sequence_from_map`.

The recorded hypothesis and Matthews prior can therefore describe one
crystallographic problem while the external tools solve another.

Recommended fix:

Carry the selected group and both cut-offs in the immutable diffraction and
hypothesis contracts. Either materialise a checksum-bound approved MTZ or pass
explicit supported parameters to every Phenix command and verify the resulting
log/output metadata.

Regression test:

An approved compatible override must appear in every resolved command and
output. An override that is not propagated must fail before tool execution.

## PIPE-P1-07 — Free-R selection is neither scientifically validated, identity-bound, nor propagated

Locations:

- `src/genome_to_diffraction/diffraction/preflight.py:770-781,846-856`
- `src/genome_to_diffraction/diffraction/free_r.py:67-76,121-165`
- `src/genome_to_diffraction/refinement/stage.py:508-520,883-901`
- `src/genome_to_diffraction/refinement/brief.py:78-97,441-504`
- `src/genome_to_diffraction/schemas/results.py:390-467,631-681`
- `src/genome_to_diffraction/benchmarks/m6_nextflow.py:1854-1878,1935-1971`

Mechanism and impact:

Preflight accepts any chosen integer column as Free-R. It does not verify that
flags are finite/integer-like, contain a usable test set and work set, or have a
defensible distribution. Free-R generation similarly checks only the presence
and MTZ type of the generated column.

The selected label and flag semantics are omitted from `preflight_id`. A probe
with `FreeA` and `FreeB` produced the same ID for both choices. Another probe
with an all-zero `FreeR_flag` reported:

```text
present FreeR_flag pass_with_review ['xtriage_not_run']
```

T12 staging checks only `free_flag_status`; `T12RunRequest` carries no Free-R
label, and `phenix.refine` receives only observation labels. The refined MTZ is
not checked for unchanged HKL-to-flag membership. The M6 finalist path calls
T12 directly without first requiring a valid Free-R selection.

This can make two different validation sets share an immutable identity and can
allow Phenix to auto-select another column or generate flags.

Recommended fix:

Bind the selected label, convention/test value, distribution summary, and a
checksum of the HKL-to-flag mapping into the preflight identity. Pass the chosen
array explicitly to refinement and verify byte-equivalent membership after
refinement.

Regression test:

Different valid flag selections must have different IDs. Constant, non-finite,
and non-integral flags must fail. Wrong-column use or changed flag membership
after refinement must fail.

## PIPE-P1-08 — Copy “support” is packing-only and the fixed parent is modelled as exact

Locations:

- `src/genome_to_diffraction/mr/add_copy.py:396-440,560-635`
- `src/genome_to_diffraction/schemas/results.py:532-628`
- `src/genome_to_diffraction/benchmarks/control_matrix_run.py:381-392`
- `src/genome_to_diffraction/benchmarks/m6_collection.py:333-374`
- `src/genome_to_diffraction/benchmarks/m6_evaluation.py:187-207`

Mechanism and impact:

The fixed parent is assigned `identity = 1.0` even when it originated from a
low-identity homologue. The searched copy uses the recorded model identity, so
the two likelihood error models are inconsistent.

An added copy becomes `additional_copy_supported=True` solely when the solution
packs and the PDB contains the expected number of placement remarks. LLG delta
and TFZ are recorded but do not affect support. The benchmark then treats the
maximum packing-only count as true-copy recovery.

Packing is a steric filter, not evidence that an added biological component is
present. This can turn a Matthews-expected count into an “empirically
supported” count by construction.

Recommended fix:

Use the original model uncertainty/identity for fixed parent copies. Separate
`placed_and_packed` from a scientifically supported count. Retain all attempts,
but define any stronger support rule explicitly and do not use packing alone
for M6 true-copy acceptance.

Regression test:

- A 35% identity parent must remain 35% in the fixed ensemble.
- A packed addition without independently approved support must remain retained
  but must not increment a scientific supported-count field.

## PIPE-P1-09 — T12 can publish stale files as fresh Phenix results

Locations:

- `src/genome_to_diffraction/refinement/brief.py:408-410,429-430`
- `src/genome_to_diffraction/refinement/brief.py:471-504,527-535`
- `src/genome_to_diffraction/refinement/brief.py:619-624`

Mechanism and impact:

`run_t12_candidate()` permits a pre-existing non-empty output directory and
uses fixed output names. Success is exit zero plus post-command file existence.
A prior model, MTZ, maps, or `sequence_from_map.pdb` can therefore satisfy a
new invocation that writes nothing.

A focused fake-runtime probe prepopulated all fixed outputs and returned zero
without writing. The adapter emitted `completed_success`, checksummed the stale
model, and published the stale sequence model.

Nextflow's normal fresh work directories reduce exposure but do not protect the
public CLI, manual reruns, legacy drivers, or retries.

Recommended fix:

Reject an existing/non-empty output directory, or run each command in an
attempt-owned temporary directory and atomically promote only outputs created
by that attempt.

Regression test:

Prepopulate every fixed output, return zero while writing nothing, and require
an input/parse failure with no stale checksum or path published.

## PIPE-P1-10 — Duplicate JSON/YAML keys silently change scientific configuration

Locations:

- `src/genome_to_diffraction/schemas/io.py:260-276`

Mechanism and impact:

Ordinary `json.load()` and `yaml.safe_load()` silently retain one value for a
duplicate mapping key. A duplicate provider flag, threshold, path, consent
field, or resource cap acquires order-dependent meaning before schema
validation.

A duplicated `max_first_copy_jobs` with values 200 and 1 passed validation and
resolved to 1.

Recommended fix:

Use a JSON `object_pairs_hook` and a SafeLoader mapping constructor that reject
duplicate keys with path/key diagnostics.

Regression test:

Reject duplicate top-level and nested keys in JSON and YAML, including provider
enablement, remote consent, thresholds, and paths.

## PIPE-P1-11 — Runtime contracts coerce malformed types and accept non-finite metrics

Locations:

- `src/genome_to_diffraction/schemas/base.py:27-36`
- `src/genome_to_diffraction/schemas/io.py:260-318`
- `src/genome_to_diffraction/refinement/brief.py:113-124`
- `src/genome_to_diffraction/schemas/results.py:508-529`

Mechanism and impact:

The base model is described as strict but sets `strict=False`, and many JSONL
readers call Pydantic directly without authoritative wire-schema validation.
Python's JSON parser also accepts `NaN` and `Infinity`.

Focused probes showed string integers being accepted for sequence length,
source counts, and reflection counts. `contract validate` accepted non-standard
`NaN`/`Infinity` MR metrics even though later RFC 8785 canonicalisation cannot
serialise them.

This silently repairs malformed wire data and admits metrics that can corrupt
sorting, status logic, or later serialisation.

Recommended fix:

Set `allow_inf_nan=False`, reject JSON parse constants, and centralise all
JSONL/YAML runtime loading through strict wire validation. Preserve explicit
datetime/enum conversion rather than relying on global coercion.

Regression test:

String integers/booleans, integral floats for integer fields, `NaN`,
`Infinity`, and YAML `.nan/.inf` must fail at every supported entry point.

## PIPE-P1-12 — Matthews enumeration silently chooses the last duplicate record

Locations:

- `src/genome_to_diffraction/matthews/enumerate.py:420-446`

Mechanism and impact:

The loader accepts multiple valid records with the same crystal or
sequence-group ID, then direct dictionary construction silently keeps the last
one. Two preflights for one crystal with ASU volumes 250,000 and 500,000 Å³
were accepted; every hypothesis used the second volume.

Ordering can therefore change Matthews coefficients, solvent fractions,
physical status, and retained copy ranks.

Recommended fix:

Build explicit unique indexes that report the duplicated ID and line numbers.
Require one preflight per crystal, one group per immutable ID/digest, unique
source IDs, and exact expected coverage.

Regression test:

Both identical and conflicting duplicate preflight/group records must fail.

## PIPE-P2-01 — Refinement succeeds even when no R values were parsed

Locations:

- `src/genome_to_diffraction/refinement/brief.py:261-283,480-540,551-603`
- `src/genome_to_diffraction/schemas/results.py:631-681`

Mechanism and impact:

Exit zero, expected files, and coefficient labels are sufficient for
`COMPLETED_SUCCESS`. Initial and final `R_work`/`R_free` may all be `None`, and
`sequence_from_map` still runs. A Phenix log-format change can erase the primary
refinement-quality evidence while the result remains successful.

Recommended fix:

Require parsed final `R_work` and `R_free` for completed refinement, and initial
values where comparison is claimed. Otherwise emit `FAILED_PARSE`.

Regression test:

A zero-exit run with all files but an unrecognised R-value log must fail parsing
and must not invoke sequence assessment.

## PIPE-P2-02 — Malformed `sequence_from_map` output aborts instead of producing typed evidence

Locations:

- `src/genome_to_diffraction/refinement/brief.py:310-360,586-603`

Mechanism and impact:

Unknown groups, wrong lengths, duplicate groups, or result-validation failures
raise out of the adapter after an exit-zero external command. No
`SequenceMapResult(FAILED_PARSE)` is emitted, so a candidate-local parse defect
becomes a failed Nextflow task.

Recommended fix:

Introduce a specific parse exception, catch parser/model validation errors after
execution, and emit a typed failed-parse result while retaining the command and
raw log.

Regression test:

Unknown group, wrong length, duplicate group, malformed summary, and
inconsistent output model must all produce typed parse failures.

## PIPE-P2-03 — Exported contract schemas disagree with runtime-authoritative schemas

Locations:

- `src/genome_to_diffraction/schemas/io.py:287-318,369-381`
- `src/genome_to_diffraction/cli.py:1297-1308`
- `tests/contract/test_typed_contracts.py:182-186`

Mechanism and impact:

Runtime validation uses tracked/packaged authoritative JSON Schemas, while
`contract schema` regenerates a schema from Pydantic. The exported
`pipeline-config` schema accepted `reference_backend: null`; runtime validation
rejected it. Clients built from the public schema command can therefore create
invalid inputs.

Recommended fix:

Export the authoritative schema whenever a `schema_filename` exists. Add parity
tests against an accepted/rejected mutation corpus and an installed wheel.

## PIPE-P2-04 — Ragged TSV input escapes the CLI error taxonomy

Locations:

- `src/genome_to_diffraction/schemas/io.py:78-84,126-179,245-257`

Mechanism and impact:

`csv.DictReader` supplies `None` for missing cells, but `_optional()` calls
`.strip()` unconditionally. A short catalogue row raises an uncaught
`AttributeError` instead of `ContractLoadError`; extra cells and duplicate
headers are also unchecked.

Recommended fix:

Validate unique headers and exact row width before conversion. Reject `None`
keys/values and translate CSV, Unicode, and shape errors into row/column-aware
`ContractLoadError`.

Regression test:

Short/long rows, duplicate headers, blank required cells, invalid UTF-8, and
quoted multiline fields.

## PIPE-P2-05 — Phenix manifests do not bind the executables that are run

Locations:

- `src/genome_to_diffraction/schemas/manifests.py:310-335`
- `src/genome_to_diffraction/phenix/runtime.py:359-436,470-505,579-611`

Mechanism and impact:

Only `phenix_env.sh` is checksummed. Runtime validation constrains the resolved
executable to the installation prefix but does not compare its bytes with the
verified installation. A replaced `phenix.phaser` or `phenix.refine` can run
under an old manifest/version identity.

Recommended fix:

Record and verify a digest for every required command (and any necessary
wrapper target) before execution, then include the resolved runtime identity in
scientific cache keys.

Regression test:

Verify a fake runtime, replace one executable at the same path, and require
refusal before spawn.

## PIPE-P2-06 — Independent catalogues and crystals remain monolithic Python loops

Locations:

- `modules/local/import_catalogues.nf:3-25`
- `src/genome_to_diffraction/catalogue/importer.py:458-512`
- `modules/local/mtz_preflight.nf:3-28`
- `src/genome_to_diffraction/diffraction/preflight.py:1061-1089`

Mechanism and impact:

One Nextflow task loops over every catalogue or crystal. A malformed object
aborts the batch; one changed object invalidates everything; retry, resource,
and provenance isolation are lost. This directly conflicts with the repository
invariant that independent scientific objects are channel items.

Recommended fix:

Plan one validated tuple per catalogue/crystal, execute each item separately,
then aggregate deterministic typed results.

Regression test:

Two catalogues and two crystals, with one typed no-hit/failure case, must show
separate trace tasks and preserve unaffected outputs.

## PIPE-P2-07 — Transient scheduler/infrastructure failures have no bounded retry path

Locations:

- `conf/base.config:11-14`
- `external/nf-helper/conf/sites/marmic.config:38-41`
- `modules/local/run_additional_copy_phaser.nf:6`
- `modules/local/run_brief_refinement.nf:6`

Mechanism and impact:

Global `maxRetries=0` makes attempt-scaled site resources dead and provides no
recovery for preemption, node loss, or transient staging/NFS failures. Long
search/Phenix tasks require manual restart or resume.

Recommended fix:

Retry only classified infrastructure exits with a small bound and backoff.
Input, parser, and deterministic tool failures must remain non-retriable.

Regression test:

A recognised transient fixture fails once and succeeds on attempt two; an input
contract failure executes exactly once.

## PIPE-P2-08 — Several declared resource/retention limits have no runtime consumer

Locations:

- `src/genome_to_diffraction/schemas/manifests.py:194-226`
- `workflows/main_workflow.nf:135-240`
- `conf/base.config:46-55,96-109`
- `conf/viper-cpu.config:25-39,78-93`

Mechanism and impact:

Repository search found no enduring runtime use of
`max_refinement_finalists`, `max_sequence_map_finalists`, or
`max_concurrent_mr_jobs`. Refinement and sequence-map fan-out follow the
approved TSV contents, while concurrency is fixed by site config. Other review
and retention booleans are enforced unconditionally rather than from config.

An operator can therefore change a validated setting with no behavioural
effect.

Recommended fix:

Either enforce each field at a single documented boundary and record its
resolved value, or remove unsupported settings from the authoritative schema.

Regression test:

Set each supported cap to one and prove task/retention counts; unsupported
fields must fail validation rather than be ignored.

## PIPE-P3-01 — The wheel is not reproducibly buildable from the locked environment

Locations:

- `pyproject.toml:1-3,27-33`
- `pixi.toml`
- `pixi.lock`

Mechanism and impact:

The build backend is unbounded `hatchling>=1.27`, but Hatchling/build tooling is
absent from the Pixi environment and lock. There is no locked wheel-build or
clean-wheel test. `pixi run --locked python -m hatchling build` fails because
the module is absent; a networked PEP 517 build may work but is not reproducible
offline.

Recommended fix:

Pin build tooling, add a locked wheel task, install the wheel into an isolated
environment, and test both entry points plus packaged `_schemas`.

---

# B. Findings in temporary HPC development and validation apparatus

## DEV-P0-01 — M6 “correct-family” recovery has no family-truth check

Locations:

- `src/genome_to_diffraction/benchmarks/m6_prepare.py:52-59`
- `src/genome_to_diffraction/benchmarks/m6_protocol.py:354-370`
- `src/genome_to_diffraction/benchmarks/m6_model_policy.py:366-380`
- `src/genome_to_diffraction/benchmarks/m6_collection.py:367-371`
- `src/genome_to_diffraction/benchmarks/m6_evaluation.py:194-226`
- `benchmarks/m6/protocol.yaml:147-149,419-428,520-531`
- `tests/unit/test_m6_benchmark.py:270-286`

Mechanism and impact:

The protocol freezes 30%/70% cluster evidence and allowed-family counts, but
preparation has no cluster-snapshot input and no code verifies the frozen lines
or counts. Collection defines `correct_family_model_retained` as
`accepted_model_hit_count > 0`.

Any accepted hit—including an off-family or domain-only hit—satisfies the
operational 10/12 or leakage 7/11 correct-family gate. The existing unit test
passes with only a count and no accepted PDB/entity/family identity.

Recommended fix:

Verify the frozen snapshots and line hashes at trusted preparation, retain
accepted PDB/entity IDs through collection, and classify each hit against the
predeclared family on the truth side.

Regression test:

An off-family accepted hit must remain false; a verified family member must be
true; snapshot/count tampering must abort.

## DEV-P0-02 — M6 exact-false-assignment gates are structurally vacuous

Locations:

- `src/genome_to_diffraction/benchmarks/m6_nextflow.py:222-245,2204-2232`
- `src/genome_to_diffraction/benchmarks/m6_collection.py:317-375,394-404`
- `src/genome_to_diffraction/benchmarks/m6_evaluation.py:288-324,353-361`
- `tests/unit/test_m6_benchmark.py:656-674`

Mechanism and impact:

`M6CaseEvidence` has no reportable identity/assigned sequence field.
Collection hard-codes `exact_identity_sequence_sha256=None` for every positive
and open-set case and relabels all target-absent/wrong-catalogue cases as
`completed_no_exact_assignment`, regardless of raw candidate evidence.
Evaluation counts only non-null values from that hard-coded field.

A direct probe supplied M6C025 with raw `candidate_evidence` and a selected
wrong-sequence seed. Collection still returned:

```text
M6C025 no_exact_assignment completed_no_exact_assignment None
```

The advertised zero-false-assignment gate cannot fail through the real
collect→evaluate path.

Recommended fix:

Add a checksum-bound runner-side identity decision:
`abstained`, `ambiguous`, or `reported`, with optional sequence digest(s) and
evidence pointers. Derive truth-side results from that record, never case kind.

Regression test:

A complete synthetic collect→evaluate run with a reportable wrong open-set
identity must produce a non-zero false-assignment count and `hold`.

## DEV-P0-03 — M6 edge controls certify their descriptor rather than observed behaviour

Locations:

- `src/genome_to_diffraction/benchmarks/m6_prepare.py:403-421`
- `src/genome_to_diffraction/benchmarks/m6_nextflow.py:1152-1202`
- `src/genome_to_diffraction/benchmarks/m6_nextflow.py:1987-2020,2160-2185`
- `src/genome_to_diffraction/benchmarks/m6_evaluation.py:230-257,325-367`

Mechanism and impact:

Wrong-SDS, non-top-Matthews, equivalent-column, remote-disabled,
remote-rate-limited, and missing-Phenix outcomes can be produced solely from
the injected `fault_control.json`.

Direct calls with no scientific evidence returned successful expected outcomes
for wrong SDS, non-top Matthews, and rate limiting. Missing Phenix is returned
while a valid real manifest is still supplied and Xtriage is skipped.

The all-edge-outcomes gate can therefore certify test labels rather than the
adapters under test.

Recommended fix:

Derive every outcome from typed evidence: actual SDS and Matthews rows, actual
array equivalence/warnings, a deterministic rate-limit response, and a truly
invalid isolated Phenix runtime.

Regression test:

Keep the descriptor but delete or contradict the observed evidence; evaluation
must hold.

## DEV-P1-01 — The 29-catalogue M6 graph partitions only the first catalogue

Locations:

- `workflows/m6_validation_workflow.nf:65-72,103-118`
- `modules/local/m6_nextflow_tasks.nf:147-181`
- `src/genome_to_diffraction/benchmarks/m6_nextflow.py:2297-2298`

Mechanism and impact:

`imported` is multi-item, but `batch_plan` and collected result lists are
one-emission queue channels. `M6_PARTITION_DISCOVERY(imported, batch_plan, ...)`
consumes the singleton channels on the first catalogue. Remaining catalogue
cases disappear at the join and aggregation later fails after costly work.

The real runner has 29 catalogues and approximately eight Foldseek batches. The
local and Slurm smoke fixtures have one catalogue and cannot reveal this.

Recommended fix:

Convert the shared plan/lists to reusable values, or explicitly combine every
catalogue with the complete shared tuple.

Regression test:

Use at least two distinct catalogues with cases on both; require one partition
task per catalogue and the complete expected case set.

## DEV-P1-02 — Ordinary M6 MTZs retain target-model-derived phase/map columns

Locations:

- `src/genome_to_diffraction/benchmarks/m6_prepare.py:223-242,328-365`
- `tests/unit/test_m6_benchmark.py:1525-1586`

Mechanism and impact:

The complete deposited reflection block is converted and the ordinary variant
only sanitises metadata. Deposited `FWT/PHWT`, calculated structure factors,
HL coefficients, or other target-model-derived arrays remain in the supposedly
truth-isolated runner.

A focused ordinary-path probe produced:

```text
H K L FreeR_flag FP SIGFP FWT PHWT
```

Current commands select observations explicitly, which limits immediate use,
but truth-derived phases remain accessible to tools and future code. The
byte-level token scan does not detect crystallographic information leakage.

Recommended fix:

Publish an allow-listed minimal MTZ containing H/K/L, exactly one selected
observation/sigma pair or quartet, and the validated Free-R array.

Regression test:

An input with `FWT/PHWT/FC/PHIC` must produce an ordinary runner MTZ without
those arrays while preserving observed data and Free-R membership exactly.

## DEV-P1-03 — Leakage filtering occurs after top-three hit truncation

Locations:

- `src/genome_to_diffraction/benchmarks/m6_nextflow.py:716-733,857-866,919-930`
- `src/genome_to_diffraction/structure_search/pdb_sequence.py:523-555`
- `src/genome_to_diffraction/structure_search/prostt5_foldseek.py:468-480,703-737`
- `src/genome_to_diffraction/benchmarks/m6_model_policy.py:313-339`
- `benchmarks/m6/protocol.yaml:147-337`

Mechanism and impact:

Only three hits per query survive normalisation. Exact-deposition and
≥70%-identity/≥80%-coverage exclusions occur later. If the first three are
excluded, a valid fourth leakage-safe homologue is invisible. Frozen
`allowed_30_to_70_model_count` values as large as 375 are not otherwise used.

This creates artificial model scarcity and biases leakage-controlled recovery.

Recommended fix:

Use a bounded deeper raw cap, apply all truth-side exclusions, then cap accepted
hits. Bind both caps into cache identity.

Regression test:

Three disallowed leading hits plus a fourth safe family hit must retain the
fourth hit.

## DEV-P1-04 — M6 case preparation performs hidden HTTPS inside Slurm workers

Locations:

- `modules/local/m6_nextflow_tasks.nf:242-267`
- `src/genome_to_diffraction/benchmarks/m6_nextflow.py:1415-1424`
- `src/genome_to_diffraction/structure_search/pdb_coordinates.py:393-432`
- `src/genome_to_diffraction/databases/sources.py:69-79`

Mechanism and impact:

`M6_PREPARE_ACTIVE_CASE`, labelled only `m6_case_prepare`, calls PDB coordinate
registration. A coordinate-cache miss downloads from RCSB. Arbitrary M6 hits
are not guaranteed to have been cached by the 1UBQ database smoke.

Network-isolated workers fail; network-enabled parallel workers mutate a shared
cache outside declared Nextflow outputs.

Recommended fix:

Resolve the bounded PDB ID set first, stage coordinates through a dedicated
network/login process, checksum them, and run case preparation offline.

Regression test:

With an empty cache and compute sockets disabled, a dedicated staging task must
obtain all objects and no case worker may invoke HTTP.

## DEV-P1-05 — Shared-store search bundles are consumed without checksum verification

Locations:

- `modules/local/m6_nextflow_tasks.nf:87-145`
- `src/genome_to_diffraction/benchmarks/m6_nextflow.py:510-533`
- `src/genome_to_diffraction/benchmarks/m6_nextflow.py:871-888,936-977`
- `benchmarks/m6/execution-nextflow-v1.yaml:29-36`

Mechanism and impact:

`storeDir` can skip the producer. `_batch_search_records()` then parses result
and hit JSONL without comparing them with `bundle_manifest.output_sha256` or
the nested search-manifest inventory. A schema-valid altered hit can change
model policy while provenance retains the old manifest digest.

Recommended fix:

Validate adapter, task/cache identity, every declared output, and nested raw
result/log checksums whenever a stored bundle is loaded.

Regression test:

Modify a valid stored hit without updating either manifest. Cross-track reuse
must fail before partition or model policy.

## DEV-P1-06 — M6 seed selection silently prefers the largest copy count per model

Location:

- `src/genome_to_diffraction/benchmarks/m6_nextflow.py:1540-1607`

Mechanism and impact:

Before score ranking, `best_by_model` replaces a lower-copy hypothesis whenever
another hypothesis for the same sequence/model has a larger
`copy_count_expected`, regardless of Matthews rank, LLG, or TFZ. Only the
largest-count representative can enter the five advancing seeds.

Raw attempts remain archived, but plausible lower-copy parents are not advanced
or refined. This violates the requirement to keep multiple plausible copy
counts live and biases the packing-only true-copy procedure upward.

Recommended fix:

Reserve advancement diversity across copy hypotheses, or select representatives
by the declared ranking key without a hard preference for larger count.

Regression test:

A strong two-copy result and weaker four-copy result for one model must leave
the two-copy hypothesis advancement-eligible.

## DEV-P1-07 — M6 verification self-asserts cache-invalidation and partial-output gates

Locations:

- `src/genome_to_diffraction/benchmarks/m6_scientific.py:166-209`
- `src/genome_to_diffraction/benchmarks/m6_scientific.py:213-226`
- `src/genome_to_diffraction/benchmarks/m6_collection.py:202-216`
- `tests/unit/test_m6_benchmark.py:423-425`

Mechanism and impact:

`cache_invalidation_verified` is established by changing a checksum string and
confirming that a canonical digest changes; no cached stage is perturbed.
`no_silent_partial_output` and `resume_load_verified` are literal `True`.
Collection requires those booleans but does not independently reconstruct
child-output completeness. The wrapper separately compares aggregate outputs on
resume, but that does not test invalidation or every retained raw child.

Acceptance can therefore claim cache invalidation and no silent partial output
without exercising those failure modes.

Recommended fix:

Use mutation tests against each shared cache-key component and a complete
declared child-output inventory. Treat resume equivalence, cache invalidation,
and partial-output detection as separate observed records.

Regression test:

Change one input component at a time and require only dependent stages to run.
Delete one child/raw output while leaving aggregates and require verification to
fail.

## DEV-P2-01 — Slurm completion order can change M6 output bytes

Locations:

- `workflows/m6_validation_workflow.nf:105-118,209-215,253-264,302-313`
- `src/genome_to_diffraction/benchmarks/m6_nextflow.py:965-977,1025-1035`
- `src/genome_to_diffraction/benchmarks/m6_nextflow.py:1566-1574,1669-1674`
- `src/genome_to_diffraction/benchmarks/m6_nextflow.py:2097-2112,2225-2249`

Mechanism and impact:

Collected batch/child lists are not sorted by stable IDs before concatenation,
enumerated manifest fields, or serialisation. Equivalent clean runs with
different task completion order can produce different partition JSONL, input
identities, case records, and digests. A cached resume preserves first-run order
and cannot reveal this.

Recommended fix:

Sort bundles by validated batch ID and child results by stable scientific ID
before every aggregation or identity construction.

Regression test:

Permute every aggregator's input order and require byte-identical complete
output trees.

## DEV-P2-02 — A personal Apptainer cache path is hard-coded and test-enforced

Locations:

- `bootstrap/nf-gtd-hpc-smoke-job:1851,2086,2342,2516`
- `tests/contract/test_repository_policy.py:200-205`

Mechanism and impact:

M6, M4, and T12 export `/ptmp/ashima/apptainer-cache`. Another user or changed
site layout can fail permissions or cross account boundaries even though the
site config already computes a user-specific cache location.

Recommended fix:

Persist the validated cache path in run state or derive
`/ptmp/${USER}/apptainer-cache` after validating `USER`. Remove the account
literal and its assertion.

Regression test:

Generate jobs for two safe usernames and require their own configured paths.

## DEV-P2-03 — Legacy benchmark CLIs still run nested Python thread pools

Locations:

- `AGENTS.md:80-89`
- `docs/execution-architecture.md:3-15`
- `src/genome_to_diffraction/benchmarks/control_slice_run.py:19,537-538`
- `src/genome_to_diffraction/benchmarks/control_matrix_run.py:20,495-496`
- `src/genome_to_diffraction/benchmarks/control_matrix_run.py:551-554,617-620`
- `src/genome_to_diffraction/cli.py:493-508,1513-1545`

Mechanism and impact:

Packaged public commands still schedule independent scientific work through
`ThreadPoolExecutor`, contrary to the current invariant that Nextflow owns
scientific fan-out. These paths have weaker executor provenance, resume, and
resource isolation.

Recommended fix:

Migrate retained controls to Nextflow channel items or disable execution
commands and keep only immutable-result verifiers until the validation slice is
removed.

Regression test:

Add a repository-policy test forbidding concurrency primitives in scientific
Python drivers and a CLI migration-message test.

---

# Clean removal boundary for temporary code

The temporary slice is not currently isolated behind one package or plugin.
Removal should begin only after immutable validation evidence is retained and a
core-only gate exists.

## Coherent M6 slice

Remove together:

- `m6_validation.nf`;
- `workflows/m6_validation_workflow.nf`;
- `modules/local/m6_nextflow_tasks.nf`;
- M6-specific modules under `src/genome_to_diffraction/benchmarks/`;
- `benchmarks/m6/`;
- M6 labels in `conf/base.config`, `conf/test.config`, and
  `conf/viper-cpu.config`;
- M6 parser/dispatch branches in `src/genome_to_diffraction/cli.py`;
- M6 controller and wrapper profile branches;
- M6 fixtures, tests, and operational documentation.

## Coupling that must be untangled first

- `src/genome_to_diffraction/cli.py:11-62,453-745,1478-1808` eagerly imports
  and registers benchmark code. Deleting benchmark modules first breaks the
  core CLI at import time.
- `src/genome_to_diffraction/structure_search/qualification.py:13-15` imports a
  public-control helper from the benchmark package.
- `pyproject.toml:25-28` exposes the temporary `nf-gtd-hpc-test` entry point.
- `bootstrap/nf-gtd-hpc-smoke-job` is monolithic and mixes M6, database, M4,
  T12, and other routes; deleting only M6 branches does not remove its other
  development coupling.
- Repository checks and docs currently require temporary commands and paths.

Recommended removal preparation:

1. Split core and validation CLIs/modules.
2. Define a core-only dependency graph and locked gate.
3. Move validation-only exception/helpers out of core imports.
4. Archive immutable evidence outside the code-removal change.
5. Remove profile branches, tests, and docs in the same focused change as their
   implementation.
6. Do not delete shared scientific adapters, the Phenix runtime, database/cache
   code, or `external/nf-helper` merely because M6 calls them.
7. Never delete the shared discovery cache or remote evidence as part of code
   cleanup without separate explicit approval.

---

# Recommended remediation order

## Stop gate before any M6 scientific track

1. Fix DEV-P0-01 through DEV-P0-03.
2. Fix the M6 multi-catalogue cardinality defect (DEV-P1-01).
3. Remove truth-derived MTZ columns and filter before accepted-hit truncation.
4. Make shared-store reuse verify checksums and move coordinate staging to an
   explicit network process.
5. Replace packing-only true-copy evidence or remove that criterion from M6.
6. Add a real multi-catalogue, multi-batch, permuted-order local integration
   fixture before another scientific submission.

The existing two-case smoke may be collected as orchestration evidence, but it
must not authorise an operational or leakage scientific run.

## Enduring pipeline high-priority repair

1. Correct the integrated fan-out cardinality and cache identities.
2. Make provider configuration authoritative and no-hit composable.
3. Fix the network executor mapping.
4. Correct duplicate-dataset observation selection.
5. Bind and propagate space-group, resolution, and Free-R selections.
6. Separate packing from scientific copy support.
7. Make T12 output publication fresh/transactional.
8. Harden configuration and runtime contract parsing.

## Subsequent reliability work

Address schema-export parity, TSV diagnostics, executable identity, per-object
Nextflow fan-out, classified retries, remaining dead configuration, and locked
wheel construction.

# Areas inspected without a supported finding

- Matthews formula and bound direction are correct: sequence-derived mass,
  `V_asu/(nM)`, and `1 - 1.23/Vm`.
- SDS–PAGE remains a soft monomer/polypeptide-mass annotation and is not used as
  ASU total mass or oligomer evidence.
- Physical impossibility, review status, and four-hypothesis retention are
  separated.
- Exact-sequence grouping and source/locus crosswalks preserve duplicate loci.
- Predicted-model preparation verifies exact sequence/position mapping and
  confidence-pruned output.
- Experimental PDB preparation verifies coordinate/SEQRES mappings and
  preserves homologue identity metadata.
- Single-dataset observation selection rejects map-only arrays and conflicting
  equal-priority arrays.
- Phaser tool failure, parse failure, no-hit, and hit states remain distinct.
- Foldseek proposals require a direct amino-acid alignment before M6 leakage
  decisions.
- Within a unique output directory, published process directory names do not
  collide.
- M6 `groupKey` child counts and the final exact case-set validation fail loudly
  when emitted children are lost.
- The isolated Phenix subprocess uses a clean environment, argument arrays, and
  prefix-constrained executable resolution; missing executable hashes are the
  material remaining gap.
- Archive import uses bounded size, file-only inventories, and checksums.
- Managed run IDs, ownership capabilities, locks, and destructive cleanup
  targets are narrowly validated.
- No implemented public ESM Atlas sequence-submission route was found.

# Verification performed

- Complete `pixi run --locked check`: passed.
- Focused static and synthetic probes:
  - three-item/one-item Nextflow queue cardinality;
  - duplicate-label multi-dataset MTZ selection;
  - constant Free-R flag acceptance;
  - same preflight identity for different Free-R selections;
  - stale T12 output acceptance;
  - duplicate YAML key acceptance;
  - non-finite/coerced runtime contracts;
  - duplicate Matthews record overwrite;
  - ordinary M6 retention of `FWT/PHWT`;
  - descriptor-derived M6 edge outcomes; and
  - unconditional open-set `no_exact_assignment`.
- Three independent review passes covered scientific validity, Nextflow/HPC
  execution, and Python/schema/test boundaries.

# Limitations

- No real Phenix command was executed.
- No live HPC, scheduler, remote service, private M6 input, or generated
  `.untracked` scientific result was inspected.
- The latest remote status in this report is the last journaled snapshot, not a
  live observation.
- Local Nextflow tests were stub/synthetic; real Slurm behaviour was reviewed
  from tracked code and retained reports.
- Network-socket-dependent local tests were not added; the sandbox does not
  permit binding the required loopback socket.
- Coverage tooling is not present, so no line or branch coverage percentage is
  claimed.
