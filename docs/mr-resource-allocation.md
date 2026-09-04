# Dynamic Phaser resource allocation

## Purpose and scope

Phase III assigns each active molecular-replacement task a deterministic
first-attempt resource plan before Nextflow submits it. The plan is operational
evidence only. It never changes candidate rank, identity, scientific status,
LLG/TFZ interpretation, or the fixed hypothesis budgets.

The policy applies to Phase III first-copy, no-A expansion, additional-copy,
and B--F composition attempts. Dedicated M6 labels remain fixed so the M6
operational/leakage comparison retains a controlled resource contract.
Historical runs and releases remain immutable.
Their still-readable fixed routes use the separate internal
`process_mr_fixed` label and retain their original site allocations; they do
not enter the new retry policy.

## Inputs, formula, and tiers

Each `MrResourcePlan` binds:

- the selected MTZ reflection count;
- moving-model polymer atom count;
- the number of copies searched jointly;
- fixed-parent polymer atom count; and
- the crystallographic general-position multiplicity.

It is a schema-v2 public file contract. Operators and tests can validate a
retained plan with
`genome-to-diffraction contract validate mr-resource-plan PLAN.json`.

Missing, non-positive, malformed, or contradictory measurements fail before
Phaser execution. Version 2 retains the same formula:

```text
reflection_count
  * (moving_atoms * searched_copies + fixed_atoms)
  * min(general_position_multiplicity, 8)
```

The symmetry factor is capped at eight so a high-symmetry space group affects
the operational estimate without dominating all coordinate and reflection
evidence.

| First-attempt tier | Workload score | CPUs | Memory | Time |
| --- | ---: | ---: | ---: | ---: |
| Standard | up to 1,000,000,000 | 8 | 32 GB | 24 h |
| Heavy | over 1,000,000,000 through 10,000,000,000 | 12 | 48 GB | 36 h |
| Very heavy | over 10,000,000,000 | 16 | 64 GB | 48 h |

The fixed public controls anchor the initial operational bands. Representative
scores are approximately 0.056 billion for 3W45, 0.139 billion for 6P1F,
0.399 billion for 1JCF, 2.090 billion for the two-copy 8OOX search, and
16.952 billion for the first two-copy 3U7Q component. Unknown outcomes were not
used to choose scientific thresholds. After the first full unknown screen
demonstrated that Phaser receives `phaser.keywords.general.jobs=task.cpus` and
uses its assigned CPUs, the operator explicitly chose to overprovision the
successor screen to reduce elapsed time. The workload boundaries remain
unchanged; only first-attempt resources and the cache identity advance.

## Retry contract

For now, one retry is permitted. Nextflow applies the nf-core-style linear
rule `first_attempt_resource * task.attempt`, bounded at 16 CPUs, 64 GB, and
48 hours:

| Tier | Attempt 1 | Attempt 2 |
| --- | --- | --- |
| Standard | 8 CPU / 32 GB / 24 h | 16 CPU / 64 GB / 48 h |
| Heavy | 12 CPU / 48 GB / 36 h | 16 CPU / 64 GB / 48 h |
| Very heavy | 16 CPU / 64 GB / 48 h | 16 CPU / 64 GB / 48 h |

A retry is allowed only for exit 75 transient infrastructure failure or the
nf-core scheduler/resource interruption ranges 104, 130--145, and 175--177.
Scientific no-hit, packing rejection, invalid input, and parse/contract failure
do not receive a larger attempt. The same scientific hypothesis is retried;
the retry does not consume another scientific hypothesis budget.

This follows the [Nextflow dynamic resource mechanism](https://www.nextflow.io/docs/latest/process.html#dynamic-task-resources)
and the current [nf-core pipeline template](https://github.com/nf-core/tools/blob/main/nf_core/pipeline-template/conf/base.config).

## Execution, provenance, and cache identity

The resource plan is content-addressed and linked to, but kept separate from,
each scientific hypothesis; composition execution tasks bind the same plan
type directly. Resource-policy changes therefore do not change a scientific
hypothesis ID. The Phaser adapter independently
requires `task.cpus` to equal the planned CPU count for the recorded
`task.attempt`. The plan, resource attempt, executed thread count, and command
identity are retained together; the Nextflow trace retains allocated CPU,
memory, time, attempt, wall time, CPU utilisation, and peak RSS.

Changing the formula, thresholds, tier resources, retry policy, or caps changes
the adapter/resource-plan identity and invalidates affected active task caches.
There is no automatic learning or outcome-driven self-tuning. A later policy
change requires reviewed trace evidence, focused regressions, and a new adapter
version.

## Controller bounds and failure semantics

The fixed Marmic controllers allow the maximum 48-hour child retry to finish:

- unknown screen: 120 hours;
- reviewed single-component continuation: 120 hours; and
- five-depth pass 2: 528 hours, comprising five possible 96-hour
  first-attempt-plus-retry depth paths and two days for orchestration/replay.

Slurm owns aggregate admission. No `maxForks` or executor queue cap limits the
number of emitted scientific hypotheses. Historical Marmic runs predating this
policy remain unchanged and cannot reuse these successor task caches.

## Validation

Focused coverage checks formula derivation, tier boundaries, symmetry capping,
content-address mutation rejection, retry multiplication, CPU caps, invalid
attempts, and thread-plan mismatches. Repository policy checks require dynamic
directives on every active Phase III MR process, the fixed resource limits,
retry classification, and absence of Phase III `maxForks`. Cached Nextflow
stubs preserve task identities. A focused live local fixture proves that an
exit-75 first attempt is retried at doubled CPU/memory/time and that the
successful second attempt is reused as `CACHED` on canonical resume.
Exact-source Marmic qualification must still confirm the emitted 8/12/16-CPU
first attempts and any observed scheduler/resource retry before release.
