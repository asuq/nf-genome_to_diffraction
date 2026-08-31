# nf-genome_to_diffraction

Foundation repository for a reproducible Nextflow and Python pipeline that will
narrow an unidentified prokaryotic crystal to reviewable protein candidates.

## Documentation

Open the [workflow documentation](docs/atlas/current/documentation.html). Its
upper-right Scientist | Developer toggle switches between the scientific
workflow and implementation architecture while keeping one canonical
documentation entrypoint.

## Current status

Version `0.2.0` is the experimental bounded two-component heteromer prototype.
It fixes one reviewed first-component structure and searches explicit copy counts for a second component.
Real Phenix controls cover 6RTZ `1A + 1B`, 3U7Q `2A + 2B`, and the full
1,846-protein Thermotoga catalogue search. The small P6 control slice adds
missing-B, wrong-B, homomer-route non-regression, and explicit 9ECN
`unsupported_component_count` behaviour. Packing and scores remain search
evidence, not proof of identity or composition. The release is experimental,
M6 scientific acceptance remains held, and deferred hardening is documented in
the [prototype-first roadmap](docs/v0.2-roadmap.md).

This repository contains the completed foundation, typed data contracts, an
external Phenix bootstrap/runtime boundary, explicit reference-database
preparation, and trusted protein-catalogue normalisation. Diffraction processing
implements independent MTZ preflight and candidate-specific Matthews/SDS-PAGE
hypotheses. M0 real-site qualification passed on all three pilot MTZ datasets,
including real Phenix and database probes. M1 structural discovery is active:
the local MMseqs2-to-PDB sequence-search route passed its real catalogue P1
qualification. A bounded real ProstT5/Foldseek retry identified that its
`prob` output field incorrectly required unavailable query Cα coordinates;
adapter v2 corrected that call and completed the 128-sequence external search.
The result then exposed RCSB biological-assembly copy suffixes such as `A-2`
at the SEQRES crosswalk. Adapter v3 applies the source-derived chain mapping and
passed the fixed 128-sequence Marmic run with 292 retained hits across 102
sequence groups, 26 completed no-hits, explicit deferral of the other 1,492
eligible groups, and a fully cached resume. The uncapped real catalogue gate
remains open.
Exact-accession AlphaFold DB retrieval
is implemented with API/mmCIF sequence verification and immutable coordinate
caching, and the exact pilot-derived `WP_042685700.1` to `A0A832VZP6` retrieval
is qualified. The first M2 vertical slice now converts that exact pilot model
into a residue-mapped, confidence-pruned, content-addressed Molecular Replacement model through
verified Phenix 2.1-6048. The checksum-bound fixed Marmic path passed on commit
`c901dafe585d1b68b117d7d216e5053ef4985230`: login-node staging retrieved one
sequence-exact AFDB model, the Slurm task retained 429 of 442 residues, and the
model process was cached on resume. PDB coordinate registration, one cleaned
experimental source-chain variant, and a diversity-aware first-copy funnel are
now implemented with typed Nextflow boundaries. The funnel preserves predicted
and experimental evidence separately and enforces no more than 25 first-copy
jobs per crystal in smoke mode. These new boundaries pass local unit/stub/resume
acceptance but are not yet qualified on the real Marmic direct-PDB candidates.
Domain and sequence-adapted variants and the provider evidence union remain
incomplete. Optional ESM Atlas remains disabled. First-copy molecular
replacement, all-candidate same-component placement, brief refinement, maps,
sequence-from-map narrowing, cached resume, and review/status/resource reporting
have been qualified on the retained real CD6 evidence. These outputs remain
review candidates: high preliminary `R_free` values and absent human sequence
decisions prohibit claiming a validated structure or identity.

The default `main.nf` stage remains the accepted Task 05 boundary and writes
`task05_preflight_complete_downstream_deferred`. Setting
`--analysis_stage discovery` now connects that boundary to the qualified P1
PDB/ProstT5/AFDB searches, bounded direct-PDB coordinate registration, and
predicted/experimental model preparation. `--analysis_stage first_copy`
requires a one-crystal manifest, verifies its manifest-owned MTZ against the
completed preflight, runs the retain-all diverse Phaser fan-out, and publishes
a Molecular Replacement seed-review package with an empty approval template. It deliberately
stops at that file-based human checkpoint. `--analysis_stage additional_copy`
requires an explicitly edited `--approved_mr_seeds` file, validates it against
the exact regenerated package, and advances every approved seed one
same-component copy at a time to its expected count or first unsupported
addition. Seeds already expected to contain one copy remain recorded without an
unnecessary Phaser job. `--analysis_stage heteromer` instead uses the reviewed
approved seed and complete-catalogue partner plan without requiring public
control data; an optional `--heteromer_control_preparation` additionally runs
the fixed control when explicitly supplied. `--analysis_stage t12` extends the
same-component path by selecting each approved seed's last
checksum-authenticated supported state and running the qualified
brief-refinement/map/sequence adapter on every retained alternative. It refines
against the original FreeR-bearing diffraction MTZ;
the corresponding Phaser solution MTZ is preserved as a source record only. The
normal path then builds the T12.5 top-10, top-25, full-results, HTML, asset,
and header-only second-decision package directly from the typed finalist
outputs. Preliminary ranks never create an approval, and typed failed/no-hit
outcomes remain retained evidence rather than disappearing from the package
manifest. The standalone entry points remain available for focused
qualification and do not identify a protein by themselves.

The complete scientific and engineering handoff is retained separately and is
intentionally not tracked here. `AGENTS.md`, the JSON Schemas, and examples
preserve the mandatory scope and data-contract constraints needed by the
foundation.

## Supported platforms

- Linux x86-64, including the intended HPC development target.
- macOS Apple Silicon for local development.

The environment pins the conventional GIL build of Python 3.14.6, Nextflow
26.04.6, Java 21 LTS, and the `ty` type checker.
Pixi 0.76.2 is the supported and tested launcher version. Phenix is
licensed external software and is never installed by Pixi or included in this
repository.

## Setup and checks

```bash
pixi install --frozen
pixi run check
```

Useful focused tasks include:

```bash
pixi run format
pixi run lint
pixi run typecheck
pixi run test-unit
pixi run test-contract
pixi run schema-check
pixi run nextflow-check
pixi run nextflow-stub
pixi run hpc-wrapper-check
pixi run public-panel-check
```

Environment resolution contacts the public Conda/Bioconda and PyPI package
indexes for dependency metadata and packages. It does not transmit biological
input data.

## Command-line interface

```bash
genome-to-diffraction --version
genome-to-diffraction schema-check
genome-to-diffraction contract validate catalogue-manifest examples/catalogues.tsv
genome-to-diffraction contract canonicalise pipeline-config examples/config.yaml
genome-to-diffraction contract schema sequence-group
genome-to-diffraction structure-search pdb-sequence --help
genome-to-diffraction structure-search register-pdb-coordinates --help
genome-to-diffraction structure-search prostt5-foldseek --help
genome-to-diffraction structure-search afdb-exact --help
genome-to-diffraction structure-search qualify-p1 --help
genome-to-diffraction model prepare-experimental --help
genome-to-diffraction model prepare-predicted --help
genome-to-diffraction ranking diverse-first-copy-funnel --help
genome-to-diffraction diffraction select-single --help
```

`schema-check` validates every tracked JSON Schema against Draft 2020-12,
validates the supplied JSON/YAML/TSV fixtures against both JSON Schema and the
typed application models, and checks cross-manifest references. Contract commands
log progress and diagnostics to standard error; use `--log-format json` for
structured logs and `--no-progress` for non-interactive execution.

The direct local structural search and its Nextflow entry point are documented
in the [structural-search interface](docs/structural-search.md). A PDB hit is
model/family evidence tied back to a supplied exact-sequence group; it never
becomes a reportable catalogue identity by itself.

## Immutable Viper-CPU test profiles

Viper-CPU is the active HPC site. Marmic runs and runbooks are retained as
immutable historical evidence. The active site uses the pinned `nf-helper`
Viper profile, `/ptmp` work/storage, Pixi 0.76.2 as a launcher for the locked
project environment, and a hard ceiling of 64 CPUs, 192 GB RAM, and 24 hours.

The repository includes a repository-specific local controller and fixed remote
dispatcher. The `smoke` profile runs `pixi run check`; the separately bounded
`p0` profile verifies real Phenix, performs anchored database metadata and
functional-smoke revalidation, and runs the three-crystal Task 05 preflight
twice to prove cache reuse. The fixed `p1` profile imports the same frozen
catalogue, runs the three implemented structural-discovery branches, repeats
them with `-resume`, and applies the tracked direct-PDB 8OOX positive-control
and model-key gate. Its current ProstT5/Foldseek pilot is capped at 128
deterministically sorted real sequences; deferred records are explicitly
uninterpreted, and the source-corrected adapter must pass before the uncapped
provider gate. P0
deliberately does not perform a terabyte-scale full-checksum audit. The
separately approval-gated `database` profile downloads and checksums its fixed
sources on the Viper login node, then runs `/ptmp` resource construction,
same-filesystem publication, and anchored full verification with 4 CPUs,
8 GB, and a 24-hour limit. All profiles use one
immutable pushed commit. Neither provides arbitrary SSH/paths, source edits on
Marmic, automatic cleanup, or downstream protein identification. Machine-readable
results are written to standard output; diagnostic `logging` and optional
`tqdm` wait/collection progress use standard error.

The fixed `m4-import-stage` boundary resumes the prototype from the collected
11-candidate Marmic P2 evidence without repeating P0-P2. It retains every
candidate and binds review, decision, MTZ, model-derivation, Git, submodule,
Pixi, lock, Phenix, and site records.

The one-time `p0-inputs-stage` boundary packages only the seven frozen pilot
files named by the private typed manifests, checks them against the frozen
inventory, rewrites workstation paths, and streams a deterministic archive to a
fixed content-addressed remote root. It accepts no destination or shell fragment
and produces a private seven-line candidate for separate checksum-confirmed
`p0-configure` review. Neither operation belongs in persistent routine approval.

The controller must be built and installed as a reviewed immutable application
outside the writable checkout before adding narrow Codex approval rules. See the
[Viper-CPU runbook](docs/viper-cpu-runbook.md) for installation,
configuration, operations, failure classes, and the clean approval boundary.
The current M0 evidence and remaining scientific prerequisites are separated in
the [M0 qualification dashboard](docs/m0-qualification.md).
The accepted direct-search evidence and its limits are recorded in the
[P1 direct-PDB qualification](docs/p1-direct-pdb-qualification.md).
The first real ProstT5/Foldseek attempt, diagnosed bounded retry, and focused
source-derived correction are recorded in the
[P1 ProstT5/Foldseek qualification](docs/p1-prostt5-qualification.md).
The first immutable predicted-model adapter and its real Phenix result are
recorded in the
[M2 predicted-model preparation report](docs/m2-predicted-model-preparation.md).

## Public X-ray control panel

The tracked [public-control panel](docs/public-control-panel.md) freezes ten
methanogen and methanotroph structures for prototype regression testing. Three
controls have complete catalogue, construct, model, and MTZ preparation
specifications; six more have qualified public sources and exact construct
mappings; one heteromeric membrane complex deliberately violates the current
single-component assumption. `runnable_control` describes reproducible input
preparation, not a completed molecular-replacement result.

```bash
pixi run public-panel-check
pixi run prepare-public-panel
```

Public coordinate and structure-factor files, derived MTZs, logs, and preparation
records are written below ignored `.untracked/public-controls/`; no public binary
data are committed. Real Phenix runs and the provisional strict Phaser gates
(`LLG > 50` or `TFZ > 5`) remain separate qualification steps. Equality does
not pass either comparison; packing, placed-copy agreement, maps, and human
review remain independent evidence.

## Trusted catalogue import

Catalogue import accepts one or more already trusted protein FASTA catalogues;
it does not predict genes, combine competing annotations, or infer taxonomy.
Relative input paths are resolved against the catalogue manifest. Every declared
input is checksummed, and every original FASTA record is retained even when its
amino-acid sequence is an exact duplicate of another record.

```bash
pixi run genome-to-diffraction catalogue import \
  --catalogues /absolute/input/catalogue_manifest.json \
  --config /absolute/input/config.yaml \
  --outdir /absolute/results/catalogue
```

The output contains canonical exact-sequence FASTA, sequence-group and
source-record registries in JSONL/TSV/Parquet, a group-to-source mapping, and a
checksummed import manifest. Optional locus metadata can come from a provider's
GFF3, GenBank flat file, or explicit TSV mapping; conflicting mappings fail.
Duplicate protein identifiers are flagged rather than overwritten.

Sequences are uppercased and whitespace is removed. A terminal stop is removed
only when configured and the transformation is recorded; internal stops remain
visible, have no molecular mass, and are excluded from the search FASTA. Exact
sequence groups use full SHA-256 identities. Average neutral polypeptide mass,
including terminal water, is calculated by the locked Biopython version.
`B/Z/J/X` produce defensible IUPAC mass bounds rather than an invented exact
mass. Chemically defined `U/O` retain exact masses but are marked for downstream
review because tool support varies. The configured `warn`, `exclude`, or `error`
policy controls all such review residues.

Python modules emit contextual logging at file, catalogue, and completion
boundaries and use `tqdm` for checksumming and protein-level progress. Use
`--log-format json` for machine-readable debugging or `--no-progress` when a
scheduler captures non-interactive logs.

## MTZ preflight and Free-R policy

Gemmi independently reads MTZ unit-cell, space-group, resolution, reflection, and
column metadata. Observation selection prefers an explicit override, then an
unambiguous intensity/sigma array, then amplitude/sigma. When several arrays are
present, a documented deterministic label priority may select one with a warning;
an unresolved tie fails. Map coefficients such as `FWT/PHWT` are never accepted as
observations.

Normal preflight runs verified `phenix.xtriage` once per crystal through the
isolated Phenix boundary and preserves its complete log:

```bash
pixi run genome-to-diffraction diffraction preflight \
  --crystals /absolute/input/crystal_manifest.json \
  --phenix-manifest /absolute/software/manifests/phenix.json \
  --outdir /absolute/results/preflight
```

`--skip-xtriage` exists for preparation and automated tests only. It always adds
`xtriage_not_run` and yields `pass_with_review`, never a clean pass. Xtriage
anisotropy, translational-NCS, twinning, and symmetry concerns are normalised but
the raw log remains the source record. A map-only MTZ, ambiguous observation arrays,
an invalid Free-R override, or incompatible cell/symmetry yields `fail` and stops
the workflow.

Existing Free-R flags are preserved. Missing flags are reported and are not
silently generated during preflight. A separate one-time command creates a new
immutable MTZ derivative through `phenix.reflection_file_converter`, using lattice
symmetry, an explicit fraction/cap, CNS convention, and a recorded random seed:

```bash
pixi run genome-to-diffraction diffraction generate-free-r \
  --source-mtz /absolute/input/without_free_r.mtz \
  --output-mtz /absolute/input/derived/with_free_r.mtz \
  --phenix-manifest /absolute/software/manifests/phenix.json \
  --command-log /absolute/input/derived/free_r.log \
  --record /absolute/input/derived/free_r_generation.json
```

The command refuses a source that already has flags, refuses an existing output,
checks that the source did not change, validates the generated Free-R column, and
records both MTZ checksums.

## Matthews and SDS-PAGE hypotheses

For candidate mass `M`, copy count `n`, and independently calculated ASU volume
`V_ASU`, the implementation records `V_M = V_ASU / (n M)` and solvent fraction
`1 - 1.23 / V_M`. Every configured copy count is retained in JSONL/TSV/Parquet;
the top configured number (four in the pilot configuration) is marked for
downstream use. Four is the smallest predeclared cap that preserves the known
two-copy 8OOX control: both Phenix and the transparent broad prior rank that
high-solvent hypothesis fourth. This changes only the execution cap, not the
ranking heuristic or its interpretation. Mass
bounds produce corresponding Matthews and solvent bounds rather than a fabricated
midpoint.

```bash
pixi run genome-to-diffraction matthews enumerate \
  --crystals /absolute/input/crystal_manifest.json \
  --config /absolute/input/config.yaml \
  --preflight /absolute/results/preflight/mtz_preflight.jsonl \
  --sequence-groups /absolute/results/catalogue/sequence_groups.jsonl \
  --source-records /absolute/results/catalogue/source_records.jsonl \
  --outdir /absolute/results/matthews
```

The current fast backend is explicitly named
`broad_solvent_centrality_v1_uncalibrated`: it is a transparent broad physical
ranking heuristic, not an empirical probability. One selected hypothesis can be
checked against the fixed local Phenix Matthews implementation without widening
the generic Phenix executor:

```bash
pixi run genome-to-diffraction --no-progress matthews reference-check \
  --crystals /absolute/input/crystal_manifest.json \
  --config /absolute/input/config.yaml \
  --preflight /absolute/results/preflight/mtz_preflight.jsonl \
  --sequence-groups /absolute/results/catalogue/sequence_groups.jsonl \
  --source-records /absolute/results/catalogue/source_records.jsonl \
  --phenix-manifest /absolute/software/manifests/phenix.json \
  --crystal-id CRYSTAL_ID \
  --sequence-group-id SEQUENCE_GROUP_ID \
  --outdir /absolute/results/matthews-reference
```

The command validates the frozen MTZ checksum, resolves only
`mmtbx.matthews` inside the verified Phenix prefix, runs the fixed
`MTZ n_residues=N` interface, preserves the log, and compares plausible copy
sets and ordering. Its report explicitly separates Phenix's residue-count mass
model from the pipeline's exact sequence-composition mass. `passed_with_review`
is a successful execution with retained mass-model, copy-boundary, copy-cap, or
uncalibrated-ordering differences; it is not silently converted to `passed`.
Either status is method evidence only: it does not prove identity, copy number,
calibration, or a positive control. SDS-PAGE uses the nearest of multiple
supplied apparent monomer-mass bands, respects reducing/non-reducing context and
band roles, and remains a soft label only; it never excludes a candidate by
itself.

## External Phenix runtime

Phenix is user-supplied licensed software. The bootstrap does not download it,
redistribute it, add it to Pixi, or send the installer anywhere. It verifies the
full SHA-256 before installation, refuses existing or unsafe targets, uses the
official non-interactive installer form, and writes separate installation and
verification logs plus a schema-valid manifest.

Use a new absolute, versioned prefix. Replace `BUILD`, paths, and the digest with
values for the installer obtained directly from Phenix:

```bash
pixi run bootstrap/install_phenix.sh \
  --installer /absolute/path/phenix-installer.sh \
  --installer-sha256 FULL_64_CHARACTER_SHA256 \
  --prefix /absolute/software/phenix-2.1-BUILD \
  --expected-release 2.1 \
  --expected-build 2.1-BUILD \
  --temp-dir /absolute/executable/tmp \
  --manifest /absolute/software/manifests/phenix-2.1-BUILD.json \
  --current-link /absolute/software/current
```

The verifier checks `PHENIX`, `PHENIX_PREFIX`, `PHENIX_VERSION`, and help-mode
execution of Xtriage, Phaser, predicted-model processing, refinement,
sequence-from-map, `phenix.maps`, and `phenix.reflection_file_converter`.
Revalidate or run one exact argument array without changing the parent Pixi
environment:

```bash
pixi run genome-to-diffraction --no-progress phenix verify \
  --manifest /absolute/software/manifests/phenix-2.1-BUILD.json
pixi run bin/phenix_exec.sh \
  --manifest /absolute/software/manifests/phenix-2.1-BUILD.json \
  -- phenix.xtriage --help
```

On Linux, the bootstrap enforces x86-64 and glibc 2.17 or newer. Default storage
preflight thresholds follow the official guidance: 15 GiB for the installed
runtime and 25 GiB for temporary extraction. A failed new target is moved aside
for debugging; an existing versioned installation is never overwritten.

## Nextflow entry points

- `main.nf` preserves the archival v0.2 application shape.
- `phase3_application.nf` is the only current reviewed Phase III application
  owner. Its compute-only `provider_discovery` operation stops before every
  network acquisition. The fixed login controller uses
  `structure-search stage-phase3-provider-coordinates` on the resulting owned
  package; both operations require the complete checksum-pinned offline
  localisation/molecular-weight bundle. `first_copy` then requires all three exact
  input records and executes model preparation plus Molecular Replacement without network access.

The reviewed `unknown-discovery` wrapper exposes no input paths. It reads one
owned mode-0600 untracked specification at
`.untracked/phase3-unknown-pass1/unknown-discovery-inputs.json`; the tracked
shape is [examples/unknown_discovery_inputs.example.json](examples/unknown_discovery_inputs.example.json).
The controller validates the exact review/execution identity, AFDB map, and
PSORTb/DeepTMHMM localisation/molecular-weight runtime evidence, streams a path-free
immutable archive, and requests a fixed 8-CPU, 32-GB, 24-hour Slurm allocation.
Staging and submitting remain separate operations.
After that run completes successfully, `stage unknown-screen --parent-run ...`
accepts only the owned discovery parent, performs bounded provider acquisition
on the login node, and records the preparation checksum in the child run. The
screen cannot submit until that step succeeds; its Slurm job runs only the
offline application and requires a fully cached replay.

After the first-component review, `stage unknown-single-component --parent-run ...` reads
the second mode-0600 fixed spec at
`.untracked/phase3-unknown-pass1/unknown-single-component-inputs.json`; its
tracked shape is
[examples/unknown_single_component_inputs.example.json](examples/unknown_single_component_inputs.example.json).
Each TSV must belong to that exact screen run and match its independently
confirmed SHA-256. The wrapper builds the canonical owned registry/review
stages and will not submit the offline continuation without them.
- `prepare_databases.nf` exposes database-root, output, preparation switches,
  coordinate-cache initialisation, and verify-only inputs.
- `m6_validation.nf` owns the independently reviewable M6 graph.
- `qualification.nf` owns fixed controls and small stage tests. It is not an
  alternative Phase III application route.

The qualification operations retain the earlier focused boundaries without
publishing nine competing roots:

- `qualification.nf --qualification_stage discovery` exposes exact sequence
  groups, source records, the qualified database manifest, output/cache roots,
  bounded direct-PDB and ProstT5/Foldseek-to-PDB parameters, and optional exact
  UniProt mappings for AFDB retrieval.
- `qualification.nf --qualification_stage register_coordinates` exposes
  direct-PDB hit and sequence-group records, the qualified database manifest, a
  per-group source quota, and a hard global mapping cap for content-addressed
  PDB coordinate registration.
- `qualification.nf --qualification_stage prepare_predicted_models` exposes
  exact coordinate-source and sequence-group records, a verified Phenix
  manifest, and output/cache roots for deterministic confidence-pruned
  predicted-model preparation.
- `qualification.nf --qualification_stage prepare_experimental_models` exposes
  registered PDB coordinate sources, typed hit-to-coordinate mappings, and
  catalogue sequence groups for the one cleaned experimental source-chain
  variant.
- `qualification.nf --qualification_stage first_copy` runs the qualified
  exact-predicted first-copy route.
- `qualification.nf --qualification_stage diverse_first_copy` joins predicted
  and registered experimental model bundles, applies source/variant diversity
  and the profile-specific hard cap plus an optional stricter execution cap,
  publishes one aggregate immutable model registry, and fans the selected
  first-copy hypotheses out to Phaser. The fixed `p2-diverse` HPC operation
  sets this additional cap to 25, but has not yet been interpreted as a protein
  identification despite completing on real Marmic direct-PDB candidates.
- `qualification.nf --qualification_stage first_copy_controls` runs the fixed
  same-MTZ first-copy calibration pair: exact 8OOW chain A as the known-positive
  model and independently anchored 1UBQ ubiquitin as the deliberate unrelated
  negative. It uses the production Phaser adapter and records the strict
  `LLG > 50` or `TFZ > 5` decision without claiming that a passing first copy
  validates a complete ASU.

The safe workflow smoke test is:

```bash
pixi run nextflow-stub
```

Stub execution publishes schema-valid fixture manifests, catalogue/preflight/
Matthews records, first-copy/checkpoint fixtures, and standard Nextflow report,
timeline, trace, and DAG files under a disposable `/tmp/...` directory. A real
default `main.nf` run executes Tasks 04 and 05, with Xtriage enabled by default;
later stages run only when selected explicitly. Non-stub database preparation
is the separate administrative workflow below.

For the implemented partial workflow:

```bash
pixi run nextflow run main.nf -profile local \
  --catalogues /absolute/input/catalogue_manifest.json \
  --crystals /absolute/input/crystal_manifest.json \
  --config /absolute/input/config.yaml \
  --database_manifest /absolute/shared/database_manifest.json \
  --phenix_manifest /absolute/software/manifests/phenix.json \
  --outdir /absolute/results/task05 \
  --cache_root /absolute/cache/nf-genome-to-diffraction
```

For the implemented local structural-discovery routes:

```bash
pixi run -e hpc nextflow run qualification.nf \
  --qualification_stage discovery \
  -profile local \
  --sequence_groups /absolute/results/catalogue/sequence_groups.jsonl \
  --source_records /absolute/results/catalogue/source_records.jsonl \
  --database_manifest /absolute/shared/database_manifest.json \
  --outdir /absolute/results/structural-discovery \
  --cache_root /absolute/cache/nf-genome-to-diffraction
```

To run the normal workflow through the first human checkpoint, provide a
manifest containing exactly one crystal and add:

```bash
pixi run -e hpc nextflow run main.nf -profile local \
  --analysis_stage first_copy \
  --maximum_first_copy_jobs 25 \
  --catalogues /absolute/input/catalogue_manifest.json \
  --crystals /absolute/input/one_crystal_manifest.json \
  --config /absolute/input/config.yaml \
  --database_manifest /absolute/shared/database_manifest.json \
  --phenix_manifest /absolute/software/manifests/phenix.json \
  --outdir /absolute/results/first-copy \
  --cache_root /absolute/cache/nf-genome-to-diffraction
```

This writes `mr_seed_review/approved_mr_seeds.tsv` with only its header. A
reviewer must inspect the retained PDB/MTZ/log evidence and add explicit
decisions before same-component copy placement can begin.

To cross that checkpoint, retain the same immutable inputs and provide the
edited decision file:

```bash
pixi run -e hpc nextflow run main.nf -profile local \
  --analysis_stage additional_copy \
  --approved_mr_seeds /absolute/review/approved_mr_seeds.tsv \
  --maximum_first_copy_jobs 25 \
  --catalogues /absolute/input/catalogue_manifest.json \
  --crystals /absolute/input/one_crystal_manifest.json \
  --config /absolute/input/config.yaml \
  --database_manifest /absolute/shared/database_manifest.json \
  --phenix_manifest /absolute/software/manifests/phenix.json \
  --outdir /absolute/results/additional-copy \
  --cache_root /absolute/cache/nf-genome-to-diffraction
```

The validated stage records every approved seed, the original first-copy model
checksum, the rigid-body-derived staged-model checksum, and whether another
copy is required. No LLG/TFZ filter is applied at this boundary.

To continue through refinement, maps, and sequence narrowing, use the same
command and immutable decisions with `--analysis_stage t12` and a distinct
output directory. The live T12 stage writes `finalists.tsv`,
`copy_count_report.tsv`, `copy_count_report.md`, and
`t12_stage_manifest.json`. Expected-one seeds, candidates that reach expected
`n`, and candidates ending in a typed unsupported/tool/parse outcome all remain
present. A missing result bundle is an execution failure rather than evidence
that another copy is absent. After all T12 candidate processes finish, the
workflow publishes `t12_sequence_checkpoint/` with bounded review views, full
scores, self-contained Coot assets and source records, per-finalist typed outcomes,
and an intentionally empty `approved_sequence_groups.tsv`. A `-resume` run
caches both the candidate work and this deterministic checkpoint.

When trusted catalogue metadata does not itself contain a strict UniProt
accession, supply an optional two-column mapping with
`--afdb_accession_map /absolute/input/afdb_accessions.tsv`. Its exact header is
`source_record_id<TAB>uniprot_accession`. RefSeq `WP_...` identifiers are not
silently treated as UniProt accessions.

This entry point requires the Linux `hpc` environment because MMseqs2 and
Foldseek are not in the macOS development environment. The AFDB branch sends
only mapped public accessions to the official service; it does not submit
protein sequences. It is not a final identification workflow.

For the bounded direct-PDB coordinate-registration route:

```bash
pixi run -e hpc nextflow run qualification.nf \
  --qualification_stage register_coordinates \
  -profile local \
  --structural_hits /absolute/results/structural-discovery/pdb_sequence_search/structural_hits.jsonl \
  --sequence_groups /absolute/results/catalogue/sequence_groups.jsonl \
  --database_manifest /absolute/shared/database_manifest.json \
  --maximum_hits_per_sequence_group 3 \
  --maximum_mappings 25 \
  --outdir /absolute/results/pdb-coordinate-registration \
  --cache_root /absolute/cache/nf-genome-to-diffraction-coordinates
```

This network-labelled step submits only public four-character PDB accessions to
the official coordinate archive. On Marmic it must be executed during the
checksum-gated login-node prefetch because compute nodes have no outbound HTTPS;
the scheduled workflow consumes only the resulting immutable records and cached
objects.

For the implemented predicted-model preparation route:

```bash
pixi run -e hpc nextflow run qualification.nf \
  --qualification_stage prepare_predicted_models \
  -profile local \
  --coordinate_sources /absolute/results/structural-discovery/afdb_exact_search/coordinate_sources.jsonl \
  --sequence_groups /absolute/results/catalogue/sequence_groups.jsonl \
  --phenix_manifest /absolute/software/manifests/phenix.json \
  --outdir /absolute/results/model-preparation \
  --cache_root /absolute/cache/nf-genome-to-diffraction-models
```

The fixed Marmic P1 operation supplies only the tracked one-row pilot mapping.
Because Marmic compute nodes do not provide outbound HTTPS, immutable staging
retrieves and sequence-verifies that public model on the login node, records a
checksum manifest, and passes the frozen coordinate record to this entry point.
The compute job verifies those checksums before running discovery offline and
licensed Phenix on Slurm. A normal successful run must produce exactly one
processed pilot model and cache the model process on resume.

## Reference-database preparation

The Linux-only `hpc` environment pins Foldseek 10.941cd33 and MMseqs2 18.8cc5c.
The preparation workflow publishes final resources to a shared absolute database
root, so terabyte-scale resources are never staged into Nextflow work directories. Its
default hard project cap is 1.8 TB and it requires 200 GB of filesystem headroom.
That cap is a safety ceiling, not an estimate of this prototype's fixed inputs.
Observed compressed inputs total about 4.62 GB (approximately 2.33 GB PDB100,
2.22 GB ProstT5, and 66 MB PDB SEQRES, plus small metadata/control files); the
first real build must still measure extracted resources, indices, failed
staging, and temporary-copy peaks. The reviewed Marmic measurement profile uses
an 800 GB cap inside the available 1 TB allocation.
The database CLI thread count is derived from the allocated job CPUs,
so MMseqs2 indexing and the bounded search operations do not use the old
independent four-thread default. The fixed database administration job requests
4 CPUs, 8 GB, and 24 hours in the small queue: its large Foldseek inputs are
prebuilt archives, while its principal constructed index is PDB SEQRES. The
allocation follows a successful full build that peaked at 3.27 GB; the 24-hour
bound accommodates shared-filesystem I/O rather than a large CPU claim.
Job-owned construction and durable publication both use `/ptmp`, avoiding a
cross-filesystem copy before atomic publication.

An intended full preparation run is:

```bash
pixi install -e hpc --frozen
pixi run -e hpc nextflow run prepare_databases.nf -profile viper-cpu \
  --database_root /ptmp/USERNAME/nf-genome_to_diffraction/databases \
  --scratch_root /ptmp/USERNAME/nf-genome_to_diffraction/database-staging/JOB_ID \
  --minimum_scratch_free_bytes REVIEWED_SCRATCH_BYTES \
  --outdir /absolute/shared/nf-genome-to-diffraction/database-results \
  --prepare_pdb_foldseek true \
  --prepare_pdb_sequences true \
  --prepare_prostt5 true \
  --initialise_coordinate_cache true
```

This standalone operation can contact Foldseek's documented PDB/ProstT5 sources
and the public RCSB PDB SEQRES URL. On Marmic, the fixed `database-stage`
operation instead downloads all five admitted inputs sequentially on the login
node directly into immutable durable storage. The Slurm job consumes that
checksummed bundle without network access. The bounded qualification smoke uses
the bundled public 1UBQ mmCIF after the strongest search hit passes fixed score,
coverage, and SEQRES-mapping checks, the MMseqs2 hit is query-equivalent, and the
independent `1ubq_A` sequence/identifier control passes. No catalogue sequence,
credential, crystal input, or licensed Phenix file is transmitted.
The optional `--verify_esm_atlas_connectivity true` probe fetches one documented
public MGYP sequence by accession and never submits a user sequence. ESM Atlas
sequence submission remains disabled by default, and no local ESMAtlas30 is
prepared. Resource metadata records PDB data as CC0-1.0, ProstT5 weights as MIT,
and the optional ESM Atlas response as CC-BY-4.0.

Every immutable resource records the locked tool version, parameters, retrieval
metadata, full file inventory, byte count, SHA-256 identity, and smoke-test
status. Existing valid resources are reused; incomplete resources fail loudly;
forced builds are side-by-side. Preparation parses non-empty MMseqs2 and
Foldseek results and requires each deterministically strongest hit to resolve
through the protein-only SEQRES crosswalk. Plain `PDBID_CHAIN` and Foldseek's
assembly-qualified `PDBID-assemblyN_CHAIN` targets resolve to the same PDB entry
and case-sensitive chain key while the original search identifier remains in
the evidence. Biological-assembly symmetry copies such as
`PDBID-assemblyN_CHAIN-2` and `..._CHAIN-12-60` resolve through the original
SEQRES chain while retaining the Foldseek chain, assembly number, and operator
indices as raw source records. The MMseqs2 sequence hit must have the exact fixed
query hash;
Foldseek additionally enforces its score and coverage thresholds without
confusing structural rank with sequence identity. Preparation
separately maps `1ubq_A` through the same crosswalk. That fixed control binds the
legacy suffix to the mmCIF protein entity through its author-chain identifier.
The canonical polymer and SEQRES sequence hashes must agree before publication
into the coordinate cache by SHA-256 under a per-source POSIX lock.
Immutable metadata sidecars and the digest index are verified together. The
manifest retains query, result, and log checksums. Revalidation reruns the local
known queries, compares deterministic scores and output hashes, and writes
`database_manifest.verification.json`, but never downloads or repairs resources.
It requires the frozen manifest and its operator-recorded SHA-256, so mutable
`current` links and sidecars are not the trust anchor:

SEQRES compound targets canonicalise the case-insensitive PDB entry component
but preserve chain-token case. Thus valid chains such as `10eg_A` and `10eg_a`
remain distinct even when their sequences are identical; a true duplicate of
the same entry and case-sensitive chain token still fails loudly.

Preparation and verification take one advisory exclusive lock below the
database root before inspecting or changing shared state. Lock wait,
acquisition, and release are logged; terminal users see bounded `tqdm` progress,
and `--lock-timeout-seconds` fails loudly instead of waiting indefinitely.
This protects cooperating `genome-to-diffraction databases prepare` processes;
external programs that ignore the lock remain outside this safety boundary.

Python-managed public downloads resume only from a checksummed partial prefix bound
to the requested/effective URL and a strong ETag or Last-Modified validator.
`Range`, `If-Range`, `Content-Range`, final size, and HTTPS preservation are
validated before atomic promotion; a server-declined or unvalidated resume starts
cleanly. Each completed source is journalled, so a later fixed staging attempt
reuses verified completed files and resumes the interrupted file without
redownloading earlier inputs. Capacity and free-space headroom are checked
throughout. External tools are monitored through their declared durable and
scratch write roots, avoiding a full scan of the large shared database tree
every 20 seconds. Scratch payload bytes count towards the same project cap as
durable bytes, and the complete process group is stopped if either filesystem
loses headroom, the combined cap is crossed, or the scoped watchdog fails. The
fixed database job creates one unique mode-0700 parent directly below
the Viper `/ptmp` database staging root, requires it to share the durable
database filesystem, and removes it at finalisation. Source archives and
resumable partial-transfer state are downloaded directly below the durable
source root on the login node. Foldseek and MMseqs2 then construct each resource
in the job-owned `/ptmp` staging directory, inventory it there, recompute all
destination SHA-256 checksums, and only then
atomically publish the resource. A copy failure retains the bounded durable
staging for explicit archival and leaves no partially published `current`
resource; cleanup is never automatic.

The approval-gated database staging operation materialises the frozen per-run
`hpc` Pixi environment and the fixed source bundle on the login node. It writes
the sources directly to the configured durable database root and records the
bundle manifest/checksum in the immutable run. Its SSH transport is bounded to
six hours. Compute nodes then verify the same environment with Pixi offline and
recompute all source checksums before preflight; they need no outbound Conda,
PyPI, Foldseek, or RCSB access. The environment and source evidence remain bound
to the staged commit and `pixi.lock` checksum.

During compute preparation, an allow-listing `aria2c` adapter maps only the three
exact Foldseek HTTPS source URLs to the verified local bundle and rejects every
other HTTP(S) URL. Failed extraction or index staging is retained for diagnosis,
and a retained incomplete resource blocks a new build until an operator handles
it through a separately approved administrative action. The pipeline never
deletes retained resource staging automatically. Source transfer is resumable;
extraction and index construction are restartable only after that review.

Before a large administration job, run the compute-node preflight with explicit
absolute paths and operator-reviewed capacity requirements:

```bash
genome-to-diffraction --log-format json --no-progress databases preflight \
  --database-root /absolute/shared/database-root \
  --scratch-root /absolute/compute-node/scratch \
  --report /absolute/shared/run/database-preflight.json \
  --storage-limit-bytes 1800000000000 \
  --minimum-free-bytes 200000000000 \
  --required-database-capacity-bytes REVIEWED_REQUIRED_BYTES \
  --minimum-scratch-free-bytes REVIEWED_SCRATCH_BYTES \
  --source-bundle /absolute/shared/run/source_bundle.json
```

The preflight requires non-overlapping scratch and durable database roots. They
may share one `/ptmp` filesystem, enabling atomic rename publication. It verifies
the pinned Foldseek/MMseqs2 tools and measures both capacity
boundaries, requires pinned aria2 1.37.0 for local Foldseek extraction, and
fully verifies the supplied source bundle. It records each fixed URL, effective
URL, validator, size, and SHA-256 as `durable_source_verified`; it does not probe
the network from a compute node. Without `--source-bundle`, standalone preflight
retains the bounded one-byte route-probe mode for sites that explicitly permit
compute-node egress. These endpoints come from the pinned
[Foldseek 10-941cd33 database script](https://github.com/steineggerlab/foldseek/blob/941cd33/data/structdatabases.sh)
and this repository's fixed RCSB inputs. The probes transmit no catalogue,
crystal, sequence, credentials, or licensed data. A generic internet probe is
never accepted as evidence for the fixed inputs.

```bash
pixi run -e hpc nextflow run prepare_databases.nf -profile viper-cpu \
  --database_root /ptmp/USERNAME/nf-genome_to_diffraction/databases \
  --outdir /ptmp/USERNAME/nf-genome_to_diffraction/database-verify \
  --prepare_pdb_foldseek true \
  --prepare_pdb_sequences true \
  --prepare_prostt5 true \
  --initialise_coordinate_cache true \
  --verify_only true \
  --full_verify true \
  --expected_manifest /absolute/shared/database_manifest.json \
  --expected_manifest_sha256 EXPECTED_64_HEX_SHA256
```

`--full_verify true` recomputes the deployed inventories and is a long database
administration operation, not part of the approval-enabled `p0` job. Its
verification sidecar records either
`full_checksums_and_functional_smoke` or
`inventory_metadata_and_functional_smoke` plus an explicit Boolean checksum
flag. The fixed Viper administration driver uses `database-stage` and
`database-submit`, fingerprinted external configuration, and explicit distinct
job-owned compute staging. Those start commands remain approval-gated; the routine
`stage`/`submit` approvals remain limited to `smoke` and bounded `p0`.

## Repository layout

- `docs/`: tracked operational runbooks and verified prototype test reports.
- `src/genome_to_diffraction/`: Python infrastructure, contracts, Phenix and
  database boundaries, and trusted catalogue normalisation; later scientific
  subsystems remain reserved.
- `schemas/`: stable draft scientific contracts from the approved handoff.
- `examples/`: schema and operator-contract examples.
- `workflows/`, `modules/local/`: typed Nextflow wiring and process adapters.
- `conf/`: base, local, Slurm, test, and site-example configuration.
- `tests/`: unit, contract, integration-scaffold, and workflow checks.

Generated workflow work directories, results, local environments, logs, and the
separately retained developer handoff are intentionally excluded from Git.

The documentation index, Marmic runbook, and verified initial pilot findings are
available in [`docs/README.md`](docs/README.md).

## Method and software references

- Gemmi official documentation: [MTZ/reflection handling](https://gemmi.readthedocs.io/en/stable/hkl.html)
  and [Matthews coefficient](https://gemmi.readthedocs.io/en/stable/analysis.html).
- Phenix official documentation: [Xtriage](https://phenix-online.org/download/documentation/cci_apps/xtriage/phenix.xtriage.html)
  and [reflection-file tools](https://phenix-online.org/version_docs/dev-2486/reference/reflection_file_tools.html).
- Matthews, B. W. “Solvent content of protein crystals.” *Journal of Molecular
  Biology* (1968), DOI [10.1016/0022-2836(68)90205-2](https://doi.org/10.1016/0022-2836(68)90205-2).
- Kantardjieff, K. A. and Rupp, B. “Matthews coefficient probabilities: improved
  estimates for unit cell contents of proteins, DNA, and protein-nucleic acid
  complex crystals.” *Protein Science* (2003), DOI
  [10.1110/ps.0350503](https://doi.org/10.1110/ps.0350503).
