# Phase III component-expansion execution input

## Scientific boundary

`ComponentExpansionExecutionInput` is the checksum-addressed hand-off required
before one selected `B`--`F` component can be searched against a retained
composition parent. It is not itself a Phaser command or result record; the
one-attempt executor resolves its content identities to run-owned files and
revalidates every byte before command construction.

The accepted 6RTZ/3U7Q component-coordinate controls and positive 9ECN
`2A+2B+2C` installed-runtime control now qualify one independently uncertain
fixed ensemble per placed component followed by one next-component search.
Reusing the combined parent PDB as one 100%-identity ensemble remains
prohibited. New records therefore carry the exact boundary
`installed_phaser_multi_fixed_component_v1_qualified_by_9ecn`; this does not
qualify other Phaser algorithms or establish component identity from scores.

## Retained 6RTZ/3U7Q coordinate audit

The exact `v0.2.0` Marmic release run from source
`68d216fad6dc83ca4a66de1f0bd9a37d365f2b80` retains enough evidence to prove
that the existing files cannot safely be split into component coordinates:

- 6RTZ parent result
  `ff79d6598166a4e77449a09401fc7209c0dbd2e239d1cd355a8efa3c6c845e1c`
  names coordinate
  `8c7f4570ad7c6e5d2201021b7a099026e2f9eaa9eed5bb13caad6f04bef5ed7b`
  but records `solution_file_path: null`; its A+B result
  `8384a9bd2e52da4d5e2bcc68a4ca3ed61164c4a3091e1c870a37387aafbe1817`
  names only the combined coordinate
  `5a67bf1f2a26f2f26f2a34e454042d607118adb2f011a49edffd5f554c15f2b1`.
- 3U7Q parent result
  `5e454ddafa004a79477138b54c3e85d7a33281c77709c4ea44e73fccc458991c`
  names coordinate
  `e8794d52a865e1c9c318d23d0a61027395eb36e4711053d90aebdbbbaa72f6a1`
  but records `solution_file_path: null`; its 2A+2B result
  `f8202cd33c8be8a91cdee6ba5dfd34ca3c8d999b4b2b2d04902c6c0d0ccc2eae`
  names only the combined coordinate
  `57bdad5fa946955ded678005c00dfe6e0345e5debf5eaabae4e8ca6b3b92a378`.
- The captured Phaser preprocessor input for both partner runs contains
  `XYZOUT ON`, not `XYZOUT ON ENSEMBLE ON`. The retained logs reproduce rounded
  `SOLU 6DIM` summaries, but the standalone full-precision `.sol` files and
  native per-placement PDBs were not collected.
- The combined PDBs contain chain identifiers, but neither those PDBs nor the
  result contracts bind a chain identifier to an ensemble. In 3U7Q the second
  run also represents both placed A copies as one combined `fixed_parent`
  ensemble at the origin. Assigning chains from append order would therefore be
  an undocumented inference, and the rounded log transforms cannot reproduce
  the exact combined coordinates.

`ComponentCoordinateDerivationBoundary` checksum-binds this blocked state. It
carries the combined coordinate, result, command, raw-log, artifact-inventory,
source-commit, tool-version, component, and copy-count identities. It must carry
no `.sol` checksum, placement-coordinate checksums, derived coordinates, or
command, and it cannot create `FixedComponentExecutionEvidence`.

The official Phaser keyword reference specifies that `XYZOUT ON ENSEMBLE ON`
writes one `FILEROOT.#.#.pdb` for every placed ensemble and that the second
number corresponds to a `SOLU 6DIM` entry in the `.sol` file. The official
Phenix Phaser reference separately states that each placed ensemble has its own
`SOLU 6DIM` keyword and documents the z-y-z rotation followed by translation.
Those are the required semantics; combined-PDB chain order is not a substitute.

The qualified output adapter:

1. request the documented per-placement coordinate output without changing the
   scientific search;
2. retain and checksum the exact `.sol`, combined PDB, and every
   `FILEROOT.#.#.pdb`;
3. parse exactly one selected `SOLU SET`, bind every file ordinal to its
   documented `SOLU 6DIM` ensemble label, and require the planned copy counts;
4. retain component coordinates from the stage where that component was
   introduced rather than recovering them from a later collapsed fixed parent;
5. checksum-group only entries with the same component/ensemble identity; and
6. verify that all grouped component atom records recombine exactly to the
   combined parent before emitting derivation evidence.

The installed-runtime probe, accepted 6RTZ/3U7Q controls, and accepted 9ECN
control complete all six steps. `PhaserPerPlacementInventory` content-binds the
ordinal/ensemble/component/copy mapping and exact atom recombination;
`FixedComponentExecutionEvidence` preserves each original model uncertainty.

References: [Phaser keyword reference](https://www.phaser.cimr.cam.ac.uk/index.php/Keywords)
and [Phenix automated molecular-replacement reference](https://phenix-online.org/documentation/reference/phaser.html).

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

Paths are deliberately absent from this portable record. The qualified
one-attempt executor receives explicit run-owned roots/files, resolves each
recorded checksum, verifies the execution and all-model-registry identities,
and uses only the installed-runtime-qualified multi-fixed syntax.

## Outputs, failure semantics, and cache identity

The portable boundary emits the immutable input record. Missing, reordered,
collapsed, unavailable, non-finite, or cross-dataset evidence is an input
contract failure and no external process may start. The executor separately
emits typed hit/no-hit/failure status, raw component TFZ and incremental LLG,
requested/observed copies, final packing, component markers, exact Free-R
preservation, output checksums, and mandatory `search_evidence_only`
interpretation. Only a parsed hit can create a child state; candidate-local
no-hit/tool/parse outcomes remain retained terminal attempts.

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

`tests/unit/test_component_coordinate_derivation_boundary.py` covers the
content-addressed blocked evidence, exact evidence-gap inventory, ordered
component/copy coverage, mutation invalidation, and refusal of guessed
coordinates or commands.

`tests/unit/test_composition_runtime.py` covers packed claim-free child-state
creation and completed no-hit retention. The composition-attempt Nextflow gate
requires exactly 25 distinct complete task identities, a typed no-model empty
path, and byte-identical cached replay using the same real process boundary in
stub mode.
