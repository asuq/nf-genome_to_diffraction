# Phase III composition-attempt fan-out

Status: local stub-only execution boundary. It does not run Phaser and is not an
unknown-crystal or control profile.

## Purpose and authority

`build_composition_attempt_inventory` converts one authoritative
`CompositionExpansionDepthPlan` plus its exact ordered
`PlannedCompositionAttempt` rows into a content-addressed execution inventory.
The builder cannot select, reorder, omit, or add a hypothesis. The depth plan
remains the authority for the one shared attempt budget across the retained
parent beam: at most 25 selected attempts at one depth and at most 100
additional-component attempts globally.

The boundary introduces no Phaser flags, placement logic, score threshold, or
scientific support transition. It only proves that a future executor can
receive one complete immutable item per selected row. The separate
component-expansion execution-input contract will own fixed coordinates,
per-component uncertainty, and parent-LLG semantics; those values are not
guessed here.

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

`STUB_PLANNED_COMPOSITION_ATTEMPT` is intentionally stub-only. A non-stub run
fails before creating scientific output. Under `nextflow -stub-run`, the task
hash covers the selected row and the complete inventory bytes. The stub copies
the inventory and emits only `stub_not_executed` identity evidence; it is not an
MR result and cannot promote a composition state.

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

No Phenix runtime or version is required because no external scientific command
is implemented. Live component execution, real-Phenix qualification, controls,
unknown profiles, and HPC submission remain separate pending gates.
