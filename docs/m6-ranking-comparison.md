# Frozen M6 ranking comparison

The approved [recipe](../benchmarks/m6/ranking-comparison-v1.yaml) fixes cases
M6C001, M6C009, M6C010, M6C012, M6C013, M6C022, M6C025, M6C034, M6C037,
M6C042, M6C055 and M6C056. Each case keeps its original operational or leakage
track, catalogue, model eligibility, physical rules and native parameters.
The recipe checksum is enforced in code; changing a budget or case is a new
scientific-policy decision. Unknown-crystal results cannot tune this experiment.

| Arm | Admission prior | Review order |
| --- | --- | --- |
| A | Solvent density | Prior first, diagnostic reference |
| B | Solvent density times copy frequency | Prior first, diagnostic reference |
| C | Solvent density | Production MR review |
| D | Solvent density times copy frequency | Production MR review |

All arms retain the separate density, frequency and product values. Both
admission cohorts use production's diversity buckets and task limits over the
complete acquired-model inventory. The weighted cohort must reproduce the
source production admission exactly. The solvent-only cohort changes the
per-model copy ordering and admission prior while retaining the same coordinates
and physical classifications. Every initial hypothesis searches one copy.

The two review orders use the same production eligibility checks for inspectable,
packed, interpreted copy states. Prior-first order changes only which eligible
states receive the five available advancement positions. Original production,
MR and Matthews ranks remain diagnostic fields. Benchmark authority is explicit
and bound to the arm, case, native cohort and selected moving models.

## Two separate execution stages

1. Prepare the comparison from twelve retained current M6 case bundles using
   `genome-to-diffraction benchmark prepare-m6-comparison`. Supply the frozen
   recipe and protocol, exact source commit, software lock and verified Phenix
   manifest. This bounded file operation reuses completed M6 preparation and
   emits 24 checksum-bound cohorts. It runs no scientific tools.
2. Use `qualification.nf --qualification_stage m6_comparison_initial` with the
   prepared `--comparison_root`, `--software_lock` and `--phenix_manifest`.
   Nextflow schedules at most 25 initial hypotheses per cohort, at most 600 in
   total. A/C consume the same native result files; B/D consume the same native
   result files. Each pair's complete native-file checksums must agree.
3. The initial stage publishes `comparison_advancement/comparison_advancement.json`
   only after all 48 case/arm reviews are present. It records at most 240 chains
   and the exact planned additional-copy budget:
   `sum(max(expected copies - observed copies, 0))` over selected seeds. Native
   first-copy failures hold continuation; a completed no-hit remains an explicit
   empty outcome. Early chain stops and classified resource retries are recorded
   separately from logical hypothesis budgets.
4. Use `qualification.nf --qualification_stage m6_comparison_continuation` with
   that frozen advancement directory. Its validation task rechecks the native
   evidence, environment, selected seeds and exact budgets before any copy task.
   The existing M6 copy, finalist, refinement and case-assembly processes perform
   the work. Missing outputs or changed scope cannot silently remove a case.
5. `comparison_results/comparison_results.json` fixes every terminal case/arm
   checksum. Only then run `genome-to-diffraction benchmark evaluate-m6-comparison`
   with the private truth map. The existing M6 truth assessment produces raw
   case assessments and diagnostic gains/losses against D. Failed recovery
   stages remain unassessed in those comparisons.

Execution uses the locked Python 3.14/Nextflow environment and the same externally
licensed Phenix runtime as M6. Raven qualification must precede native execution;
the reviewed wrapper keeps project state under `/ptmp`, enforces its 24-hour
limit and records allocations. Local graph tests make no native Phenix claim.

## Acceptance, identity and tests

The initial plan binds the source commit, recipe, protocol, lock, Phenix manifest,
original case contents and both acquired-model cohorts. Each frozen advancement
binds all seed bundles and paired native outputs. Collected results bind every
case bundle before truth joining. These identities enter the existing Nextflow
task inputs; independent native hypotheses and chains remain channel items.

Reference arms have no new recovery cutoff. Full M6 collection and acceptance
reject comparison-arm records, including D. Production still requires the
unchanged complete 63-case operational/leakage criteria in
[M6 validation](m6-validation.md). The comparison cannot qualify RG7 or unknown
pass 2 by itself.

Focused tests cover production admission replay, alternate prior ordering,
unchanged registry bytes, paired evidence, stale workloads, scope rejection and
separation from full M6 acceptance. The real two-stage Nextflow metadata check
retains 48 empty case/arm outcomes, verifies cached replay and rejects changed
native records before opening a truth map. The main M6 tests cover the reused
native command, result, retry and failure boundaries. List inputs use explicit
distinct staging directories, following the
[Nextflow typed-process staging contract](https://docs.seqera.io/nextflow/process-typed#custom-file-staging).
