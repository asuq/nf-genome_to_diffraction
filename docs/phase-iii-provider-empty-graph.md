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

## Focused tests

`tests/unit/test_provider_empty_graph.py` covers the complete mixed graph,
deterministic bytes, plan/config mismatch, missing coverage, and duplicate
coverage. `pixi run --locked provider-empty-graph-stub` schedules all three
empty-path classes together, requires six exact completed tasks, verifies the
typed no-model registry, requires byte-identical cached resume, and checks the
non-stub fail-closed boundary. No real provider, model preparation, remote
service, operator input, or HPC profile is used.
