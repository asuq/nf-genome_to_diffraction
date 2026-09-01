# Phase III Phaser interface probe

## Purpose and boundary

Phase III needs native per-placement Phaser coordinates before a placed
`A+B` parent can be searched safely for `C`. The official Phaser keyword
reference documents `XYZOUT ON ENSEMBLE ON`, but the corresponding PHIL field
exposed by the installed Phenix build must be observed rather than guessed.

The fixed `phase3-phenix-probe` profile performs only this interface discovery.
It runs no molecular replacement and accepts no caller path, executable,
argument, crystal, model, threshold, or command.

## Inputs and execution

The local controller binds the same checksum-frozen Marmic Phenix manifest used
by the accepted controls. The compute job refreshes that manifest to bind the
exact executable checksums, then executes only:

```text
phenix.phaser --show_defaults
```

Execution goes through the isolated Phenix child environment. The profile uses
2 CPUs, 8 GB, and the default 45-minute outer limit; the fixed interface call
has a 300-second deadline. No structure, reflection, sequence, or other
scientific input is supplied.

The immutable Phase III source is published and deployed only from `main`.
The controller rejects the retired development branch and arbitrary names.

## Outputs and cache identity

The probe retains:

- the executable-hashed Phenix manifest and verification log;
- the exact combined stdout/stderr bytes from `--show_defaults`;
- a path-free `phaserinterface_<sha256>` report binding the adapter version,
  Phenix version, runtime identity, `phenix.phaser` executable checksum, exact
  command, exit status, output checksum and size, and observed interface tokens;
- a final checksum manifest over the four retained evidence files.

The report content ID is the probe cache/evidence identity. Any runtime,
executable, command, or returned-defaults change changes that identity.

## Failure semantics

An unverified or changed manifest, replaced executable, non-zero command exit,
empty output, non-empty output directory, missing retained file, or checksum
mismatch is an execution/contract failure. The probe never emits a scientific
hit, no-hit, identity, placement, or composition status.

## Validation and next use

Focused unit tests use a checksum-verified fake Phenix installation to prove
the fixed command, exact byte retention, content identity, and refusal to
overwrite an existing directory. A fake managed lifecycle proves fixed staging,
submission, terminal success, and bounded collection.

The real Marmic probe passed as Slurm job `633758` with retained defaults
SHA-256 `35eeb2a1349e47f91860b54270f4017bf97a1b10e92cb1e9d107e56531b4283b`.
Its exact installed PHIL paths include:

```text
phaser.crystal_symmetry.space_group
phaser.keywords.resolution.low
phaser.keywords.resolution.high
phaser.keywords.general.xyzout_ensemble
```

The opt-in schema-v2 first-copy command now passes the selected space group and
both resolution limits explicitly through these observed names; historical v1
commands remain unchanged. A later real known-control run demonstrated that the
installed Phenix frontend silently drops the advertised ensemble-output flag,
so component recovery instead uses exact model-bound combined-PDB chains and a
complete verified atom partition. Multi-fixed Phaser syntax remains unqualified.

## Primary documentation

- [Phaser output-control keywords](https://www.phaser.cimr.cam.ac.uk/index.php/Keywords)
- [Phenix Phaser reference](https://phenix-online.org/documentation/reference/phaser.html)
