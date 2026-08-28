# Phase III composition-attempt fan-out

Status: locally implemented one-attempt execution boundary. The process has a
safe stub mode; real installed-runtime and fixed-profile qualification remain.

## Purpose and authority

`build_composition_attempt_inventory` converts one authoritative
`CompositionExpansionDepthPlan` plus its exact ordered
`PlannedCompositionAttempt` rows into a content-addressed execution inventory.
The builder cannot select, reorder, omit, or add a hypothesis. The depth plan
remains the authority for the one shared attempt budget across the retained
parent beam: at most 25 selected attempts at one depth and at most 100
additional-component attempts globally.

The inventory introduces no Phaser flags, placement logic, score threshold, or
scientific support transition. The separate component-expansion input owns
fixed coordinates, per-component uncertainty, and parent-LLG semantics. The
one-attempt executor resolves those identities and uses only the
9ECN-qualified multi-fixed adapter; none of those values is guessed here.

## Python inputs and outputs

The builder requires:

- one registry-bound `CompositionExpansionDepthPlan`;
- its complete ordered `PlannedCompositionAttempt` tuple;
- every parent `CompositionState` in depth-plan rank order;
- one matching `DiffractionSelection` and `FreeRIdentity`; and
- one exact `ComponentExpansionExecutionInput` per selected candidate; and
- one opaque `execution_identity_id` produced by the separate global Phase III
  execution-identity boundary.

`CompositionAttemptInventory` embeds the plan, parent states, diffraction and
Free-R records, complete component-execution inputs, all-model-registry
identity, global execution identity, and compact `CompositionAttemptTask` rows.
Every task has an immutable
`compattempt_...` content ID binding:

- the shared depth-plan ID and allocation rank;
- the exact parent state and selected depth candidate;
- every parent model-resolution ID and the selected candidate model-resolution
  ID;
- the exact component-expansion execution-input ID, including component-only
  fixed coordinates, original uncertainties, and parent LLG evidence;
- the diffraction-selection and Free-R identity IDs;
- the all-model-registry ID; and
- the global execution-identity ID.

`write_composition_attempt_inventory` writes deterministic UTF-8 JSON.
`load_composition_attempt_inventory` revalidates every nested content identity
and exact cross-record relationship. No external command or external service is
used by these Python functions.

## Status and failure semantics

The inventory status is one of:

- `ready`: exactly one task for every selected candidate;
- `empty_no_model`: no task is schedulable because the retained physical
  hypotheses have typed unavailable model resolutions; or
- `empty_no_selected_attempts`: another valid zero-selection state, such as no
  physically possible hypothesis or an exhausted shared budget.

Scientific empty states complete normally with zero task rows. Missing,
reordered, duplicated, content-mutated, cross-crystal, cross-dataset,
selection/Free-R-mismatched, registry-unbound, or unavailable selected inputs
raise `CompositionAttemptInventoryError`. A selected task can never carry an
unavailable model resolution.

## Nextflow boundary and cache key

`COMPOSITION_ATTEMPT_WORKFLOW` reads the Python-validated inventory, expands
only `attempts`, and combines every row with the complete immutable inventory
path. `combine` broadcasts that path to all selected rows; there are no
independent consumable singleton queues. Each Nextflow item therefore carries
its attempt row plus the complete parent, candidate/model-resolution,
diffraction, Free-R, registry, and execution-identity context.

`RUN_PHASE3_COMPOSITION_ATTEMPT` receives each item plus the run-owned fixed
coordinate root, all-model registry, sequence groups, preflight, MTZ, Phenix
manifest, and complete execution identity. A real run independently validates
all identities and raw Free-R membership before Phaser. Completed hit, no-hit,
tool, parser, and infrastructure results remain distinct. Only parsed
candidate-specific placement evidence can create a child state, and every
result remains `search_evidence_only`; depths four through six carry
`provisional_unvalidated_component_depth`.

Under `nextflow -stub-run`, the same process hash covers the selected row,
complete inventory, and every runtime input. The stub copies the inventory and
emits only `stub_not_executed` identity evidence; it is not an MR result and
cannot promote a composition state.

## Test coverage

`tests/unit/test_composition_attempt_inventory.py` covers the shared 25-attempt
budget across three parents, exact selected-row preservation, deterministic
attempt identities, typed no-model and other empty paths, content mutation,
strict loading, and byte-stable writing.

`pixi run --locked composition-attempt-stub` runs the focused Nextflow fixture.
It requires exactly 25 distinct attempt tags for three parents, checks every
published identity and complete inventory copy, accepts a typed no-model
inventory with zero execution tasks, and requires a second `-resume` run to
reuse the same 25 task hashes with byte-identical retained output.

`tests/unit/test_composition_runtime.py` covers a packed claim-free child state
and a completed no-hit with no child. Real Phenix 2.1-6048/Phaser 2.8.4 was
qualified through 6RTZ, 3U7Q, and positive 9ECN; one fixed-HPC general-attempt
profile remains before this boundary is accepted for unknown pass 2.
