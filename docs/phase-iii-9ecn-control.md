# Phase III 9ECN three-component control preparation

## Purpose and fixed scientific identity

The Phase III depth-three validation control is public structure 9ECN, a
`2A+2B+2C` methyl-coenzyme M reductase assembly from *Methanosarcina
acetivorans*. Frozen M6 protocol entry `A04` fixes all source, catalogue,
protein, entity, chain, and copy-count identities:

| Component | Protein | Catalogue accession | Source entity | ASU chains | Model chain | Copies |
| --- | --- | --- | --- | --- | --- | --- |
| A | McrA | `WP_011024419.1` | 1 | A,B | A | 2 |
| B | McrB | `WP_011024423.1` | 2 | C,D | C | 2 |
| C | McrG | `WP_011024420.1` | 3 | E,F | E | 2 |

The deposited coordinate and structure-factor SHA-256 values remain exactly the
protocol-frozen `75beb77879508fc3158cd7045d27076997ef976453c45e0b9fe77764ef6f90b3`
and `3eecec037ca00c3f5ebdb3c3adf8b53932b169538bfa4c2b299f942b05d871c7`.

## Construct and modification safeguards

McrG source entity 3 is a 321-residue construct with a 73-residue N-terminal
expression tag. The deposited reference alignment maps source positions
74--321 to the exact 248-residue catalogue sequence. Model chain E contains
247 observed aligned residues and no observed expression-tag residues. Both
the complete construct digest and catalogue-sequence digest are retained.

McrA contains the deposited modified polymer residues `MGN` and `DYA` at
catalogue positions 420 and 470. They are retained as modified coordinate
residues while being validated against the corresponding catalogue glutamine
and aspartate. Unknown modifications, changed reference alignments, reordered
entities, altered chains, mismatched source files, and ambiguous polymer
records fail closed.

## Inputs, outputs, and execution boundary

The preparation command is:

```text
genome-to-diffraction benchmark prepare-9ecn-phase3-control \
  --protocol benchmarks/m6/protocol.yaml \
  --coordinates FIXED_9ECN_CIF \
  --structure-factors FIXED_9ECN_SF_CIF \
  --outdir EMPTY_OUTPUT
```

Alternatively, the fixed `--download` option may retrieve only the two exact
public protocol resources during an approved login-staging operation. It
cannot accept arbitrary PDB identifiers, URLs, chains, thresholds, or
composition values.

Outputs are a converted MTZ, the fixed crystal manifest, three exact catalogue
sequence groups, three processed experimental models, their checksum-bound
model-preparation manifest, one joint two-copy McrA MR hypothesis, and a
content-addressed preparation manifest with every file checksum and size.

Real frozen public inputs produced 147,424 reflection rows, models with 568,
432, and 247 observed residues, and the exact `2A+2B+2C` manifest. This is
input preparation only: it runs no Phaser search and makes no scientific
identity or composition claim. Real 6RTZ/3U7Q native-placement recombination
must pass before 9ECN scientific execution.

## Tests and primary source

Focused regressions cover the frozen protocol identity, expression-tag and
reference-alignment mutation, all three checksum-bound model records, and the
joint two-copy parent hypothesis. The existing 6RTZ/3U7Q preparation tests
remain green.

- [RCSB PDB entry 9ECN](https://www.rcsb.org/structure/9ECN)
