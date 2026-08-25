# Phase III provider-empty graph

## Purpose and fixed scope

The local `PROVIDER_EMPTY_GRAPH_WORKFLOW` closes the Phase III provider-routing
edge case without inventing another provider interface. It resolves the existing
authoritative `ProviderExecutionPlan`, routes one enabled local PDB-sequence
scientific no-hit, two configured-disabled providers, and the unsupported ESM
Atlas provider, then emits one typed `completed_no_model` terminal.

This is scheduling evidence, not a provider qualification or scientific search.
The enabled branch exists only under `nextflow -stub-run`. A normal execution
fails with exit 64 before an executable or network route can run. The graph has
no network-labelled process and makes no network request.

## Inputs, outputs, and status

Inputs are the exact pipeline config, resolved aggregate plan and entries,
database manifest, complete sequence-group catalogue, and four provider bundle
directories. The completion verifier requires:

- the config checksum recorded by the plan;
- exactly one branch for every fixed provider;
- exactly one typed result per sequence group in every branch;
- `completed_no_hit`/`no_hit` for the enabled local branch;
- `skipped_policy`/`not_interpretable` for disabled and unsupported branches;
- checksum-valid empty hit and coordinate-source files.

The output contains `provider_empty_graph_completion.json` and the existing
all-eligible-model registry. Every catalogue sequence group remains present as
`no_eligible_model`. The completion ID covers the exact plan, config, catalogue,
branch/result digests, and registry; this is the cache identity. A plan/config
mismatch, missing/duplicate branch, non-empty hit/model output, malformed result,
or enabled network route is a contract failure and publishes no terminal.

## Application propagation

The ordinary application now carries the same typed evidence beyond discovery.
An empty combined PDB hit file is accepted only when both complete PDB and
Foldseek result inventories independently record `completed_no_hit`,
`skipped_policy`, or `skipped_ineligible` for every catalogue sequence group.
Coordinate registration then publishes zero checksum-bound sources and
mappings without a network request.

Experimental model preparation accepts those empty files only with their exact
zero-count registration manifest and matching output checksums. Predicted model
preparation likewise requires complete AFDB/Atlas no-hit or disabled-result
evidence before publishing zero models; it never invokes Phenix for that empty
batch. Missing evidence, missing catalogue rows, contradictory hits, and
unpaired source/mapping files remain contract failures.

The first-copy funnel accepts independently checksum-bound empty preparation
batches. A populated provider continues normally when another provider is empty;
when every provider is empty, the existing complete model registry retains
every sequence group as `no_eligible_model` and no Phaser hypothesis is emitted.
The file-based MR-seed checkpoint still publishes an honest zero-candidate
review package without inventing an approval or identity claim.

## Focused tests

`tests/unit/test_provider_empty_graph.py` covers the complete mixed graph,
deterministic bytes, plan/config mismatch, missing coverage, and duplicate
coverage. `pixi run --locked provider-empty-graph-stub` schedules all three
empty-path classes together, requires six exact completed tasks, verifies the
typed no-model registry, requires byte-identical cached resume, and checks the
non-stub fail-closed boundary. Focused PDB registration, experimental and
predicted model preparation, first-copy funnel, and MR-seed-review regressions
exercise the real local adapter chain and reject unexplained empty files. The
normal control-independent Nextflow application still retains its existing
positive and explicit-control paths. No real provider, remote service, operator
input, or HPC profile is used.
