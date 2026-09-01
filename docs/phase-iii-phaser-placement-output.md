# Phase III Phaser component-coordinate recovery

## Purpose and qualified interface

General `A+B+C+...` search needs component-only fixed coordinates in the
parent frame. Inferring them from combined PDB chain order or rounded log
transforms is prohibited. Marmic probe
`gtd-phase3-phenix-probe-20260824T100809Z-a962e97da229-c046087f`, Slurm
`633758`, qualified the installed Phenix 2.1-6048 PHIL interface without
running crystallographic data:

```text
phaser.keywords.general.xyzout = True
phaser.keywords.general.xyzout_ensemble = True
phaser.keywords.general.keywords = True
```

The exact `phenix.phaser --show_defaults` output has SHA-256
`35eeb2a1349e47f91860b54270f4017bf97a1b10e92cb1e9d107e56531b4283b`.
The probe exited zero, records `scientific_execution_performed=false`, and all
four retained qualification checksums verify. However, the first real 6RTZ
control proved that the installed Phenix wrapper silently translates the above
settings to native `XYZOUT ON`, without the required `ENSEMBLE ON`. It writes
`PHASER.sol` and the combined PDB/MTZ, but no `PHASER.1.<ordinal>.pdb` files.

## Adapter inputs and outputs

The fixed-A/joint-B adapter now writes those three PHIL values explicitly and
uses cache identity `phenix-fixed-a-joint-b-v4-native-placements`.

`collect_phaser_per_placement_outputs` consumes one completed known-control
output directory, exact command/result records, the expected
component-label/ensemble/copy mapping, and one checksum-bound source model per
component. It requires:

- `PHASER.sol`;
- combined `PHASER.1.pdb`;
- one unique exact source-model polymer sequence per component;
- exact assignment of every combined-PDB polymer chain to its source model;
- exact component copy counts and complete top-solution `SOLU 6DIM` coverage;
- one `component_<LABEL>.pdb` retaining every placed copy in the parent frame;
- a complete atom-for-atom partition back to the combined coordinate.

Chain order and rounded Euler/translation values are not used. A fixed 3U7Q
two-copy A parent correctly has one fixed-parent `SOLU 6DIM` entry and two
exact-model A chains; the searched B component has two solution entries and
two B chains.

It writes `phaser_per_placement_inventory.json`. The content-addressed record
binds the command/result, exact `.sol` lines, source-model and polymer digests,
combined coordinate, derived component coordinates, exact chain/copy/atom
counts, tool version, crystal, search, and verified atom-partition digest.

`build_fixed_component_execution_evidence` then consumes that exact inventory,
one packed schema-v2 parent state, and the original identity/error record for
each component. It rechecks the parent crystal and combined-coordinate bytes,
each source-model identity, every requested/observed copy count, and every
derived coordinate checksum before emitting the existing
`FixedComponentExecutionEvidence` records in parent-component order. Each
record binds the complete inventory digest and retains its own original Phaser
identity; a 35%-identity A model cannot silently become a perfect or shared
model. This local bridge does not construct or execute a multi-fixed command.

The CLI boundary is:

```text
genome-to-diffraction mr collect-per-placement \
  --crystal-id ID \
  --search-id ID \
  --phaser-version VERSION \
  --output-directory DIRECTORY \
  --command-record FILE \
  --result-record FILE \
  --expected-component LABEL:ENSEMBLE_ID:COPY_COUNT \
  --component-model LABEL:SOURCE_MODEL_PATH
```

Repeat both component options for every known component.

The fixed Marmic `heteromer-smoke` profile now applies this collector to both
known positive controls immediately after the successful partner search:

- 6RTZ requires `1 x fixed_parent` and `1 x search_partner`;
- 3U7Q requires two model-matched A chains and two model-matched B chains.

The wrapper fails if either component inventory is incomplete or its atom
partition differs. It publishes a separate 46-file
`phase3-placement-control-checksums.sha256` manifest covering
the exact inputs, parent and partner command/results, `.sol`, combined
coordinates/MTZ, the four grouped component PDBs, both inventories, and
summaries. The
immutable 47-file v0.2 P6 checksum manifest is not changed or reinterpreted.

## Failure and scientific boundary

The parser runs no external command. Missing or symlinked files, malformed
solution blocks, unknown ensembles, duplicate fixed-parent entries, unmatched
or indistinguishable source-model sequences, unassigned non-protein content,
copy-count disagreement, and incomplete atom partitions fail as input-contract
errors. Input mutation changes the inventory ID.

The corrected adapter records
`recombination_status=verified_exact_combined_atom_partition` only after its
complete coordinate comparison passes. A local replay of the retained real
6RTZ result recovered all 3,543 atoms without native per-ensemble files. Both
fixed 6RTZ and 3U7Q must still pass a fresh exact-source Marmic run before the
locally verified fixed-evidence bridge can support a live
`ComponentExpansionExecutionInput` or 9ECN search.

## Tests and references

Focused tests cover `1A+1B`, `2A+2B`, out-of-order combined chains, the single
fixed-parent/two-copy distinction, deterministic output, combined-coordinate
mutation, missing `.sol` or source models, unknown/ambiguous ensembles,
indistinguishable source sequences, unknown chains, copy mismatch, and exact
real 6RTZ atom reconstruction. The fixed-evidence bridge additionally rejects
mutated grouped or combined coordinates, incomplete/incorrect original
uncertainty, invalid identity fractions, and mutated inventory contracts.

- [Official Phaser output keywords](https://www.phaser.cimr.cam.ac.uk/index.php/Keywords)
- [Phenix Phaser reference](https://phenix-online.org/documentation/reference/phaser.html)
