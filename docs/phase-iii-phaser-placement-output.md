# Phase III native Phaser placement output

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
four retained qualification checksums verify.

## Adapter inputs and outputs

The fixed-A/joint-B adapter now writes those three PHIL values explicitly and
uses cache identity `phenix-fixed-a-joint-b-v4-native-placements`.

`collect_phaser_per_placement_outputs` consumes one completed known-control
output directory, exact command/result records, and the expected
component-label/ensemble/copy mapping. It requires:

- `PHASER.sol`;
- combined `PHASER.1.pdb`;
- one `PHASER.1.<ordinal>.pdb` for every top-solution `SOLU 6DIM` line; and
- no missing, extra, unexpected, duplicated, or count-mismatched placement.

It writes `phaser_per_placement_inventory.json`. The content-addressed record
binds the command/result, exact `.sol` lines, native placement files, combined
coordinate, component groups, copy counts, tool version, crystal, and search.
The CLI boundary is:

```text
genome-to-diffraction mr collect-per-placement \
  --crystal-id ID \
  --search-id ID \
  --phaser-version VERSION \
  --output-directory DIRECTORY \
  --command-record FILE \
  --result-record FILE \
  --expected-component LABEL:ENSEMBLE_ID:COPY_COUNT
```

Repeat `--expected-component` for every known component.

## Failure and scientific boundary

The parser runs no external command. Missing or symlinked files, malformed
solution blocks, unknown ensembles, ordinal gaps, extra placement PDBs, and
copy-count disagreement fail as input-contract errors. Input mutation changes
the inventory ID.

The first adapter version proves only exact `.sol`-to-native-PDB ordinal
mapping. It deliberately records
`recombination_status=not_assessed_pending_real_control` and
`can_create_fixed_component_evidence=false`. A real 6RTZ/3U7Q control must
demonstrate exact component grouping/recombination before these files can
populate `ComponentExpansionExecutionInput` or be used to search 9ECN for C.

## Tests and references

Focused tests cover `1A+1B`, `2A+2B`, deterministic output, coordinate
mutation, missing `.sol`/placement files, extra files, unknown ensembles, and
copy mismatch. The fixed partner command regression asserts every qualified
PHIL value.

- [Official Phaser output keywords](https://www.phaser.cimr.cam.ac.uk/index.php/Keywords)
- [Phenix Phaser reference](https://phenix-online.org/documentation/reference/phaser.html)
