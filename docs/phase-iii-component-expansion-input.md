# Phase III component-expansion execution input

## Scientific boundary

`ComponentExpansionExecutionInput` is the checksum-addressed hand-off required
before one selected `B`--`F` component can be searched against a retained
composition parent. It is intentionally **not** a Phaser command or result
record.

The repository has exercised one fixed `solution_at_origin = True` ensemble
plus one independent search ensemble with the installed Phenix 2.1-6048 / Phaser
2.8.4 runtime. It does not retain official or real-runtime evidence proving how
several independently uncertain, already placed component ensembles should be
expressed in one fixed-partial command. Reusing the combined parent PDB as one
100%-identity ensemble would erase component-specific error models and repeat
the defect tracked as `PIPE-P1-08`. The contract therefore carries the literal
boundary
`input_complete_multi_fixed_partial_phaser_syntax_not_qualified`; no execution
adapter, parser, Nextflow process, or runtime-success claim is included.

## Exact inputs and invariants

One record binds:

- the authoritative depth-plan identity and exactly one content-addressed,
  selected, parent-bound depth candidate;
- one packed-or-higher `CompositionState` at depth one through five, with its
  exact parent combined-coordinate checksum and combined LLG evidence;
- one ordered `FixedComponentExecutionEvidence` per existing component,
  containing every requested/observed copy in a component-only PDB that retains
  the parent coordinate frame;
- each fixed component's sequence, component, placement and model identities
  through the parent state, plus its source combined coordinate, derivation,
  and original Phaser identity/error-source evidence;
- one available registry resolution and one explicit model/error record for the
  selected candidate and its requested copy count (maximum four);
- the exact `DiffractionSelection`; and
- the dataset-matched `FreeRIdentity`, including its unresolved or explicit
  convention and raw HKL-to-flag membership digest.

Validation requires ordered `A`--`F` prefixes, the next component label, one
available candidate model resolution, content-addressed plan/candidate
identities, complete cross-record identity agreement, and exact
diffraction/Free-R agreement. A multi-component parent cannot pass its combined
coordinate as one component-only file, and two fixed components cannot share
one collapsed coordinate checksum. Different parent identity fractions remain
different content-addressed evidence rather than being averaged or reset to
one.

Paths are deliberately absent from this portable record. A future qualified
adapter must accept explicit local file paths, verify each file against the
recorded checksum before command construction, and use only syntax supported by
official Phaser documentation and the retained installed runtime.

## Outputs, failure semantics, and cache identity

This boundary emits only the immutable input record. Missing, reordered,
collapsed, unavailable, non-finite, or cross-dataset evidence is an input
contract failure and no external process may start. Scientific hit/no-hit,
component TFZ, incremental LLG, requested/observed copies, final packing,
component markers, output checksums, and mandatory `search_evidence_only`
interpretation remain outputs of the future command/parser adapter; this
contract does not fabricate them.

`execution_input_id` is the cache key. It covers the complete parent state,
depth-plan identity, selected candidate, every fixed component coordinate/error
record, candidate model resolution/error record, parent LLG evidence,
diffraction selection, and Free-R identity.

## Focused test coverage

`tests/unit/test_component_expansion_execution_input.py` covers a depth-two
`A+B` parent expanding to `C`, distinct 35% and 82% fixed-parent uncertainty,
candidate identity/copy binding, content mutation, stale identifiers, missing
or reordered fixed components, combined/duplicate coordinate collapse,
non-candidate resolution substitution, model mutation, and Free-R selection
mismatch. No Phaser, Nextflow, HPC, or control run is performed.
