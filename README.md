# genome-to-diffraction

[![CI: main](https://github.com/asuq/nf-genome_to_diffraction/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/asuq/nf-genome_to_diffraction/actions/workflows/ci.yml?query=branch%3Amain)
[![Release: v0.2.0](https://img.shields.io/badge/release-v0.2.0-blue)](docs/releases/v0.2.0.md)
[![License: BSD--3--Clause](https://img.shields.io/badge/license-BSD--3--Clause-green)](LICENSE)

`genome-to-diffraction` is a reproducible research application for narrowing an
unidentified protein crystal to reviewable candidates from a trusted protein
catalogue. It joins catalogue identity, structural-reference evidence,
crystallographic constraints, molecular replacement, refinement, maps, and
file-based human decisions without treating any single score as proof.

> **Experimental research software.** The current release is `v0.2.0`. It
> supports the bounded two-component form `ASU = nA + mB`. Unreleased
> candidate-confidence and general-composition development now continues on
> `main` toward `v0.3.0`; it is not part of the `v0.2.0` release contract.

## Documentation

Open the deterministic offline [technical atlas](docs/atlas/current/index.html)
for scientist and developer views of the workflow, executable inventory,
contracts, module relationships, and validation evidence. The
[documentation index](docs/README.md) remains the canonical text entry point.
Contributors continuing unreleased work should also read the sanitised
[v0.3 development handoff](docs/v0.3-development-handoff.md).

## What the application does

```text
trusted protein catalogue + diffraction MTZ + reviewed configuration
                              |
                              v
 catalogue normalisation -> MTZ preflight -> Matthews/copy hypotheses
                              |
                              v
 structural models -> bounded molecular replacement -> human checkpoint
                              |
                              v
 refinement + maps + sequence-equivalence evidence -> candidate report
```

The application is designed to:

- preserve exact sequence, source-record, model, crystal, and hypothesis
  identities;
- retain all tested, deferred, failed, and no-hit outcomes;
- separate scientific no-hit from execution failure;
- preserve raw metrics and checksums alongside human-readable reports;
- stop at explicit crystallographic, MR-seed, composition, and sequence review
  boundaries; and
- run deterministically through Python and Nextflow with pinned environments.

It does **not** predict genes, infer taxonomy, merge competing genome
annotations, or prove an identity from LLG, TFZ, packing, or a structural hit
alone. Exact sequence or locus claims require independently reviewed map and
sequence evidence. An unresolved sequence-equivalence group is a valid result.

## Requirements

| Requirement | Purpose |
| --- | --- |
| Pixi `0.76.2` | Reproduces the locked Python, Java, and Nextflow environment. |
| Linux x86-64 | Required for the complete workflow and local MMseqs2/Foldseek routes. |
| macOS Apple Silicon | Supported for contract work, catalogue processing, and development checks. |
| Phenix | Required for Xtriage, Phaser, refinement, and map-based stages. It is licensed separately and is never installed by Pixi. |
| Prepared reference databases | Required for structural search. Database construction is a separate administrative operation. |

The locked environment currently uses Python `3.14.6`, Nextflow `26.04.6`, and
Java 21. See [Phenix policy](#phenix) and
[reference databases](#reference-databases) before attempting crystallographic
execution.

## Quick start

Clone the private repository using an authorised Git identity, then install the
locked environment:

```bash
git clone git@github.com:asuq/nf-genome_to_diffraction.git
cd nf-genome_to_diffraction
pixi install --locked
```

Verify the public application and packaged contracts:

```bash
pixi run --locked genome-to-diffraction --version
pixi run --locked genome-to-diffraction schema-check
```

Validate the shipped examples:

```bash
pixi run --locked genome-to-diffraction contract validate \
  catalogue-manifest examples/catalogue_manifest.json

pixi run --locked genome-to-diffraction contract validate \
  crystal-manifest examples/crystal_manifest.json

pixi run --locked genome-to-diffraction contract validate \
  pipeline-config examples/config.yaml
```

These commands validate interfaces only; they do not contact scientific
services or execute Phenix.

## Prepare an analysis

Start from copies of these versioned examples:

| Input | Example | Meaning |
| --- | --- | --- |
| Catalogue manifest | [`examples/catalogue_manifest.json`](examples/catalogue_manifest.json) | One trusted annotation source and its protein FASTA catalogue. |
| Crystal manifest | [`examples/crystal_manifest.json`](examples/crystal_manifest.json) | Manifest-owned MTZ inputs and optional explicit column choices. |
| Pipeline configuration | [`examples/config.yaml`](examples/config.yaml) | Provider, Matthews, shortlist, and retention policy. |
| Gel evidence | [`examples/gel_evidence_manifest.json`](examples/gel_evidence_manifest.json) | Optional apparent monomer-mass evidence; never ASU mass. |
| Provider plan | [`examples/provider_plan.json`](examples/provider_plan.json) | Explicitly enabled structural-evidence providers and limits. |

Replace all example paths and identifiers with your own reviewed values. Keep
catalogue, crystal, and result directories separate and immutable during a
run.

### 1. Import the trusted catalogue

```bash
pixi run --locked genome-to-diffraction catalogue import \
  --catalogues /absolute/input/catalogue_manifest.json \
  --config /absolute/input/config.yaml \
  --outdir /absolute/results/catalogue
```

The import retains every original source record and creates exact-sequence
groups, source mappings, molecular masses, checksums, and JSONL/TSV/Parquet
registries. It does not call a gene predictor or alter the supplied annotation.

### 2. Inspect the diffraction data

```bash
pixi run --locked genome-to-diffraction diffraction preflight \
  --crystals /absolute/input/crystal_manifest.json \
  --phenix-manifest /absolute/software/phenix-install-manifest.json \
  --outdir /absolute/results/preflight
```

Preflight independently records unit cells, space groups, resolution,
reflection columns, selected observations, Free-R evidence, and Xtriage
warnings. Ambiguous observations, map-only MTZ files, or incompatible
crystallographic metadata fail closed.

### 3. Enumerate candidate copy hypotheses

```bash
pixi run --locked genome-to-diffraction matthews enumerate \
  --crystals /absolute/input/crystal_manifest.json \
  --config /absolute/input/config.yaml \
  --preflight /absolute/results/preflight/mtz_preflight.jsonl \
  --sequence-groups /absolute/results/catalogue/sequence_groups.jsonl \
  --source-records /absolute/results/catalogue/source_records.jsonl \
  --outdir /absolute/results/matthews
```

Matthews estimates are physical priors, not identity evidence. The active
development line derives each candidate's complete copy range from ASU volume,
sequence mass, and solvent bounds; it has no configured copy ceiling. Its
checksum-pinned empirical prior combines resolution-conditioned solvent density
with a soft observed-copy-frequency weight, while retaining even zero-weight
states for review. See the [Matthews method and limits](docs/matthews-probability.md).

### 4. Continue to structural search and MR

The remaining stages require prepared reference databases, immutable model
coordinates, a verified Phenix installation, and file-based review decisions.
Begin with:

- [structural-search interface](docs/structural-search.md);
- [experimental model preparation](docs/m2-experimental-model-preparation.md);
- [predicted model preparation](docs/m2-predicted-model-preparation.md);
- [first-copy molecular replacement](docs/m3-first-copy-phaser.md); and
- [brief refinement and sequence narrowing](docs/t12-brief-refinement.md).

Use `genome-to-diffraction <group> --help` before constructing a command. Do
not bypass a review package by calling a later scientific adapter directly.

## Public command-line interface

The installed research package exposes exactly one application:

```bash
genome-to-diffraction --help
```

Its command groups are:

| Group | Responsibility |
| --- | --- |
| `contract`, `schema-check` | Validate and canonicalise versioned file contracts. |
| `catalogue` | Normalise trusted protein catalogues. |
| `diffraction`, `matthews` | Inspect MTZ evidence and enumerate ASU copy hypotheses. |
| `structure-search`, `model`, `ranking` | Gather structural evidence, prepare models, and build bounded candidate funnels. |
| `mr`, `refinement`, `composition` | Execute bounded crystallographic hypotheses. |
| `localisation` | Apply checksum-bound offline localisation evidence. |
| `review` | Build and validate human checkpoint packages. |
| `phenix`, `databases`, `benchmark` | Manage explicit external-runtime, reference-data, and public-control boundaries. |

Global options include structured JSON logs and non-interactive progress:

```bash
genome-to-diffraction --log-format json --no-progress <group> <command> ...
```

## Outputs and interpretation

An analysis may publish:

- exact-sequence and source-record catalogues;
- diffraction preflight and Xtriage evidence;
- Matthews and localisation candidate inventories;
- structural-hit and processed-model registries;
- per-hypothesis commands, raw logs, normalised results, and resource plans;
- MR-seed, composition, and sequence review packages;
- coordinates, maps, refinement statistics, and checksums; and
- portable HTML reports.

Every report should be read together with its manifest and raw evidence.
`completed_no_hit` is a valid scientific outcome. `failed_*` and scheduler
failure states are not no-hits and must never be promoted into a biological
claim.

## Phenix

Phenix is external licensed software. The repository neither downloads nor
redistributes it. A user supplies an installer and checksum to the bootstrap
boundary, then the scientific workflow verifies the resulting installation
manifest. Phenix environment changes are confined to dedicated subprocesses so
they cannot replace the Pixi Python runtime.

Never source `phenix_env.sh` globally before running this application.

## Reference databases

Database preparation is intentionally separate from analysis. Normal runs do
not download, rebuild, or repair PDB, MMseqs2, Foldseek, ProstT5, or coordinate
cache resources. Each prepared resource records its release, tool version,
parameters, inventory, and checksum authority.

The Linux-only environment adds database tools:

```bash
pixi install -e hpc --locked
```

See the [database and execution documentation](docs/README.md) before allocating
storage or running a preparation workflow.

## Reproducibility and data policy

- Commit `pixi.toml` and `pixi.lock` define the software environment.
- Scientific identifiers and file contracts are content-addressed and
  checksum-validated.
- Remote ESM Atlas sequence submission is disabled by default and requires an
  explicit reviewed opt-in.
- AlphaFold DB lookup uses mapped public accessions; it does not silently submit
  catalogue sequences.
- Phenix, biological inputs, generated results, caches, logs, and local
  environments are not committed.
- Record the exact Git commit, database manifests, Phenix manifest, inputs,
  non-default parameters, and review decisions for every reported analysis.

Environment installation contacts configured Conda/Bioconda and PyPI indexes
for package metadata and packages. It does not transmit biological inputs.

## Validation and evidence

Run the focused checks while developing:

```bash
pixi run --locked format-check
pixi run --locked lint
pixi run --locked typecheck
pixi run --locked test-unit
pixi run --locked test-contract
pixi run --locked docs-check
```

`test-unit` and `test-integration` use all locally visible CPUs. Embedded
Nextflow unit tests share one lock-safe group; integration fixtures use isolated
per-test roots. Use `test-unit-serial` or `test-integration-serial` when
reproducing an order-sensitive failure. A convenient pre-review gate omits the
slow stateful workflow stubs:

```bash
pixi run --locked check-fast
```

The complete repository gate includes Python, schemas, docs, Nextflow syntax,
stub/resume workflows, offline wheel inspection, and wrapper syntax:

```bash
pixi run --locked check
```

Run the complete gate once at a scientific integration, deployment, or release
boundary rather than after every edit. GitHub Actions runs quality, unit,
integration, core Nextflow, and two scientific-stub lanes in parallel; one CI
run is required for the exact commit selected for Marmic deployment.

The repository-specific HPC wrapper is an **internal validation tool**, not a
public research-package command. From a source checkout, invoke it only through
its Pixi task:

```bash
pixi run --locked nf-gtd-hpc-test --help
```

Its fixed profiles, installation boundary, immutable-source policy, and failure
classes are documented in the [HPC validation runbook](docs/hpc-feedback-loop.md).
It does not provide an arbitrary remote shell or a general user-facing
scheduler interface.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/genome_to_diffraction/` | Public scientific application and internal source-checkout tooling. |
| `schemas/` | Packaged Draft 2020-12 file contracts. |
| `examples/` | Validated contract examples and empty review decisions. |
| `modules/local/`, `workflows/` | Typed Nextflow processes and workflows. |
| `conf/` | Local, test, Slurm, and site profiles. |
| `tests/` | Unit, contract, integration, workflow, and packaging gates. |
| `docs/` | User guides, methods, validation evidence, release snapshots, and isolated development history. |
| `bootstrap/` | Explicit Phenix, database, and internal HPC bootstrap boundaries. |

Start with the [documentation index](docs/README.md). Historical development
records are useful for audit but are not the user guide and do not supersede
schemas or examples.

## Release and support status

| Surface | Status | Evidence |
| --- | --- | --- |
| `v0.2.0` | Experimental bounded two-component prototype | [Release notes](docs/releases/v0.2.0.md) |
| `main` after `v0.2.0` | Unreleased v0.3 development; not yet a stable release contract | [Canonical v0.3 roadmap](docs/v0.3-roadmap.md) |
| Exact protein identity | Never inferred from MR scores alone | [Scientific safeguards](AGENTS.md#3-mandatory-scientific-safeguards) |
| CI | Locked repository gate on the named branch/commit | [GitHub Actions](https://github.com/asuq/nf-genome_to_diffraction/actions/workflows/ci.yml) |

For a report or publication, record the tagged version when available and the
exact Git commit. Also cite the external databases and scientific tools used by
that analysis.

## Licence

The source code is available under the [BSD 3-Clause licence](LICENSE).
External databases, models, and Phenix retain their own licences and citation
requirements.
