# Public prokaryotic X-ray control panel

## Purpose and current status

The version-2 panel freezes twelve public prokaryotic X-ray structures for
prototype testing.
It is intended to test catalogue-to-construct mapping, MTZ ingestion, Matthews
copy-number hypotheses, model selection, and eventually molecular replacement.
It does **not** validate raw-image integration: all reflections are deposited,
merged structure factors that are converted deterministically to MTZ with Gemmi
0.7.5.

The source of truth is
[`benchmarks/public-controls/panel.yaml`](../benchmarks/public-controls/panel.yaml).
The panel currently contains:

- three `runnable_control` entries with full catalogue, exact-model, homolog-model,
  source, and MTZ preparation specifications;
- eight `source_qualified` single-component entries with verified public sources,
  deterministic MTZ ground truth, and exact catalogue/construct mappings; and
- one `assumption_violation` entry that the current `ASU = nA` prototype must not
  report as a successful single-component solution.

Here, `runnable_control` means that input preparation is implemented and locally
verified. It does **not** mean that Phaser has already passed the provisional
`LLG > 50` or `TFZ > 5` gate. Those score results must be recorded separately
after execution with the licensed Phenix runtime.

## Panel composition

| PDB | Group | System | ASU protein content | Catalogue mapping | State |
|---|---|---|---:|---|---|
| [8OOX](https://www.rcsb.org/structure/8OOX) | Methanogen | *Methermicoccus shengliensis* glutamine synthetase | `2A` | Full `WP_042685700.1` | Runnable |
| [7P50](https://www.rcsb.org/structure/7P50) | Methanogen | *Methanothermococcus thermolithotrophicus* GlnK2 | `3A` | Full `WP_018153776.1` after a 20-aa tag | Runnable |
| [8Q5T](https://www.rcsb.org/structure/8Q5T) | Methanogen | *M. thermolithotrophicus* nitrogenase Fe protein 1 | `4A` | Full `WP_018154785.1` | Source-qualified |
| [6HF7](https://www.rcsb.org/structure/6HF7) | Methanogen | *M. thermolithotrophicus* adenylate kinase | `3A` | Full `WP_018154177.1` | Source-qualified |
| [6P1F](https://www.rcsb.org/structure/6P1F) | Methanotroph | *Methylosinus trichosporium* PmoF2 PCuAC domain | `A` | `WP_003612864.1` residues 29–159 | Runnable |
| [5FJE](https://www.rcsb.org/structure/5FJE) | Methanotroph | *M. trichosporium* copper storage protein 1 | `2A` | `WP_003609243.1` residues 25–146 | Source-qualified |
| [7L6G](https://www.rcsb.org/structure/7L6G) | Methanotroph | *M. trichosporium* MbnP | `6A` | `WP_003614734.1` residues 26–324 | Source-qualified |
| [8JPV](https://www.rcsb.org/structure/8JPV) | Methanotroph | *Methylacidiphilum fumariolicum* GluRS | `A` | Full GenBank `CCG91288.1` | Source-qualified |
| [2Q7E](https://www.rcsb.org/structure/2Q7E) | Methanogen | *Methanosarcina mazei* PylRS catalytic domain | `A` | `WP_011033391.1` residues 185–454 after a 21-aa prefix | Source-qualified |
| [1JCF](https://www.rcsb.org/structure/1JCF) | Bacterium | *Thermotoga maritima* MreB | `A` | Full `WP_010865154.1` followed by an 8-aa tag | Runnable |
| [3W45](https://www.rcsb.org/structure/3W45) | Bacterium | *Bacillus subtilis* RsbX | `2A` | Full `NP_388355.1` | Runnable |
| [6CXH](https://www.rcsb.org/structure/6CXH) | Methanotroph | *Methylotuvimicrobium alcaliphilum* pMMO | `ABC` | Three exact full-length RefSeq proteins | Assumption violation |

This is a twelve-structure panel, not twelve independent biological replicates. Public
entries can share study-specific preparation, model, beamline, and deposition
effects. The panel is therefore a feasibility and regression suite rather than a
statistically representative performance benchmark.

## Why these cases were retained

- The eleven positives contain one protein species in the crystallographic ASU,
  with copy counts from one to six. They therefore exercise the approved
  `ASU = nA` model without implying that the biological assembly equals the ASU.
- 8OOX, 7P50, and 8Q5T were reduced with autoPROC, which matches the expected
  operator input provenance most closely. Other entries intentionally test
  whether the MTZ interface is independent of the upstream reduction package.
- 6P1F, 5FJE, and 7L6G expose a common genome-to-structure problem: the deposited
  protein is a mature or soluble fragment of a longer catalogue precursor.
  Catalogue coordinates and non-catalogue prefixes are explicit, never inferred
  from equal-looking lengths.
- 7L6G includes a kynurenine modification. The catalogue sequence remains the
  identity source, while the coordinate model records the experimental chemical
  state.
- 1JCF and 3W45 add non-methanotroph bacterial controls with exact RefSeq
  mappings. They test a tagged single-copy target and an exact full-length
  two-copy target, respectively.
- The fixed first real-execution slice contains those two positives, one matched
  wrong-model control, one target-absent control, one wrong-catalogue control,
  and the 6CXH assumption violation. The same execution boundary expands to the
  tracked 23-case matrix only after this six-case slice works.
- 6CXH is an `A3B3C3` membrane complex and its deposited structure-factor CIF has
  two reflection blocks. It is a negative contract test for both the current
  single-component scope and unsafe silent reflection-block selection.

## Validation and preparation

Validate the tracked panel and its active control specifications without network
access:

```bash
pixi run public-panel-check
```

Prepare or resume all public coordinate/structure-factor sources and deterministic
MTZ files under the ignored `.untracked/` tree:

```bash
pixi run prepare-public-panel
```

The command uses structured logging and a `tqdm` structure-level progress bar.
For non-interactive automation, place the global option before the subcommand:

```bash
pixi run genome-to-diffraction --no-progress \
  benchmark prepare-public-panel \
  --panel benchmarks/public-controls/panel.yaml \
  --outdir .untracked/public-controls/panel-v2
```

To prohibit network access and revalidate an existing cache, add `--offline`.
Every source is accepted only if its exact byte count and SHA-256 match the panel.
Writes are atomic, each entry receives a preparation record, and the aggregate
record is `.untracked/public-controls/panel-v2/preparation.json`.

The preparation command contacts `files.rcsb.org` only for missing public PDB IDs.
No biological sample, private MTZ, credential, or catalogue sequence is submitted.
PDB archive data files are distributed under the
[CC0 1.0 public-domain dedication](https://www.rcsb.org/pages/policies), but the
original structures and associated publications should still be cited.

## Runnable-control order

Run the three active controls in this order:

1. 8OOX: large full-length protein, two ASU copies, autoPROC/STARANISO data.
2. 7P50: small affinity-tagged trimer, autoPROC data, exact alternate crystal
   form 7P4Y, and same-organism GlnK1 paralogue 7P4V.
3. 6P1F: monomeric internal domain, XDS data, near-exact alternate 6P1G, and the
   more distant PmoF1-domain model 6P16.

For one active control, supply the matching frozen catalogue and use its tracked
specification. For example:

```bash
pixi run genome-to-diffraction --no-progress \
  benchmark prepare-public-control \
  --specification benchmarks/public-controls/pdb_7p50.yaml \
  --proteome-faa /path/to/GCF_000376965.1/protein.faa \
  --outdir .untracked/public-controls/PDB_7P50
```

Preparation writes a full target FASTA, a derived MTZ, exact and homolog model
chains, catalogue/crystal manifests, and checksum-rich provenance. It fails if a
construct is incorrectly equated with a full protein, if an exact-sequence
catalogue group changes, or if Gemmi conversion output drifts.

## Positive and negative execution matrix

[`homomer_workflow_cases.yaml`](../benchmarks/public-controls/homomer_workflow_cases.yaml)
turns the source panel into a truth-labelled workflow suite:

- eleven positive cases require the correct catalogue sequence and known ASU
  copy count to remain available for review;
- seven wrong-model controls use unrelated prokaryotic proteins matched within
  25% of the target construct length;
- two target-absent cases remove the exact target from the otherwise correct
  catalogue;
- two wrong-catalogue cases pair diffraction data with an independently frozen
  prokaryotic proteome; and
- 6CXH remains a known heteromeric assumption-violation control.

The negatives do not impose a hidden score cutoff. A wrong model may remain in
the review package or even cross the provisional score annotation, but it must
not displace the truth-labelled positive. Target-absent and wrong-catalogue
cases must produce no reportable catalogue identity. This distinction tests
safe interpretation rather than rewarding aggressive candidate deletion.

## Interpretation and deferred work

- The public positives establish that a known `ASU = nA` answer is present. They
  do not reveal the identity of any operator pilot crystal.
- The user-defined Phaser thresholds are strict comparisons combined with
  `or`: top `LLG > 50` or top `TFZ > 5`. Equality does not pass either branch.
- Exact alternate structures are operational controls and are intentionally not
  leakage-controlled. Homolog-only runs must exclude all exact target structures
  named in the active control specification.
- `source_qualified` entries require independent exact/homolog model selection and
  a real Phenix run before promotion to `runnable_control`.
- 6CXH belongs to future heteromer development. A current single-component run
  should record a supported assumption violation or abstention, never fabricate a
  monomeric success.
- Deposited reflections do not test autoPROC integration, indexing choices, or raw
  image quality. The unknown operator MTZs remain useful post-M6 exploratory
  integration inputs, but they do not gate M5, validate M6, or calibrate scientific
  heuristics.

## Evidence sources

Catalogue sequences and annotation snapshots were frozen from the relevant NCBI
assembly packages: [GCF_000711905.1](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000711905.1/),
[GCF_000376965.1](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000376965.1/),
[GCF_000178815.2](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000178815.2/),
[GCF_000007065.1](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000007065.1/),
[GCA_000297415.1](https://www.ncbi.nlm.nih.gov/datasets/genome/GCA_000297415.1/),
[GCF_000968535.2](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000968535.2/),
[GCF_000008545.1](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000008545.1/),
and [GCF_000009045.1](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000009045.1/).
The exact release identifiers and proteome SHA-256 values are recorded in the
panel rather than inferred from organism names.

Key method papers include Müller and Wagner, “The Oxoglutarate Binding Site and
Regulatory Mechanism Are Conserved in Ammonium Transporter Inhibitors GlnKs from
Methanococcales”, *International Journal of Molecular Sciences* (2021),
[DOI 10.3390/ijms22168631](https://doi.org/10.3390/ijms22168631); Fisher et al.,
“PCuAC domains from methane-oxidizing bacteria use a histidine brace to bind
copper”, *Journal of Biological Chemistry* (2019),
[DOI 10.1074/jbc.RA119.010093](https://doi.org/10.1074/jbc.RA119.010093); Manesis
et al., “Copper binding by a unique family of metalloproteins is dependent on
kynurenine formation”, *PNAS* (2021),
[DOI 10.1073/pnas.2100680118](https://doi.org/10.1073/pnas.2100680118); and Ro
et al., “From micelles to bicelles: Effect of the membrane on particulate methane
monooxygenase activity”, *Journal of Biological Chemistry* (2018),
[DOI 10.1074/jbc.RA118.003348](https://doi.org/10.1074/jbc.RA118.003348).
