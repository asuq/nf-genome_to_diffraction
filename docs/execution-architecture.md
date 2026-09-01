# Nextflow and Slurm execution architecture

## Architectural invariant

Nextflow owns scientific fan-out, scheduling, retries, resume, and publication.
Every independent catalogue, sample, hypothesis, seed, or finalist is a channel
item and an executor task. Python processes one task or aggregates completed
typed records; Bash establishes an environment and invokes one reviewed command.
Neither may implement multi-sample scheduling with loops, threads, processes, or
nested scheduler calls.

Scientifically dependent work remains sequential only within its dependency
chain. Iterative placement of copy `n + 1`, for example, must wait for the
retained result at copy `n`; independent seeds and samples still run as separate
Nextflow tasks.

Shared single-emission sequence catalogues, model registries, reviews,
diffraction records, and Phenix manifests must be converted to reusable value
channels before they accompany a multi-item hypothesis, approved-seed, or
finalist queue. A singleton queue is consumed by its first sibling and silently
prevents later candidates from scheduling. The production first-copy,
additional-copy, and refinement workflows explicitly broadcast these inputs.
One real local stub supplies three hypotheses, two approved seeds, and two
finalists through independent singleton queues and requires all seven exact
tasks followed by a fully cached equivalent resume.

## Retired direct benchmark drivers

Historical direct control and M6 benchmark commands are not registered. Their
former Python drivers scheduled independent hypotheses, seeds, and refinements
outside Nextflow, so both the obsolete commands and their fail-only compatibility
functions were removed. Immutable prior evidence remains readable, and shared
preparation/classification helpers remain available to Nextflow-owned graphs.

Any future replay of those suites must use a reviewed DSL2 entry point that
emits one complete channel item per independent hypothesis, seed, and finalist.
The configured executor, not Python or Bash, must own concurrency, retry,
resume, and resource evidence.

## Driver and workers

The reviewed HPC wrapper submits one small Slurm driver. The driver verifies
immutable inputs and launches a typed DSL2 workflow. It performs no catalogue
search, model preparation, molecular replacement, refinement, or sequence
assessment itself. The Nextflow Slurm executor submits worker jobs and records
their native job IDs, requested resources, timing, status, and work hashes.

For M6, catalogue import fans out by unique catalogue/configuration digest.
The imported catalogues are then deduplicated globally by exact sequence-group
identity. MMseqs2 and ProstT5/Foldseek fork independently over deterministic
query batches, not one process per sample. Their results are partitioned back
to every catalogue before cases pass through the isolated trusted model-policy
transition and fan out through case preparation, first-copy hypotheses,
copy-series seeds, and refinement/sequence finalists.

MMseqs2 receives up to 100,000 unique sequences or 30 million residues per
batch. ProstT5/Foldseek receives up to 10,000 unique sequences or 3 million
residues per batch. These content limits amortise target-database and model
initialisation while keeping heterogeneous proteome sizes from creating
unbounded jobs. The fixed M6 runner contains 29 catalogues, 141,937 catalogue
records, and 70,864 unique sequences (23,020,184 residues), producing one
MMseqs2 batch and approximately eight Foldseek batches.

This boundary follows the official
[MMseqs2 user guide](https://www.mmseqs.com/latest/userguide.pdf), which defines
search as a batch query workflow and documents target-index loading overhead,
and the official [Foldseek documentation](https://github.com/steineggerlab/foldseek),
which supports multi-sequence FASTA queries for ProstT5/Foldseek search.

## Resource and cache policy

The approved M6 execution policy is
`benchmarks/m6/execution-nextflow-v1.yaml`. Its CPU and memory ceilings apply to
each submitted Slurm job, not the aggregate workflow. All ready jobs may be
submitted; Slurm owns admission and total concurrency. Aggregate peak
allocations and simultaneous Phenix jobs remain measured evidence rather than
hard gates. Batched MMseqs2 and Foldseek workers may use 32 CPUs and 16 GB;
all case and Phenix workers retain their smaller task-specific allocations.

Only truthless catalogue import, PDB-sequence search, and ProstT5/Foldseek
bundles may use the shared discovery store. Cache keys include input checksums,
database manifest, exact parameters, the Pixi-lock checksum that pins tool
versions, the execution-policy checksum, and adapter versions. A bundle is
reusable only after its complete checksum manifest validates. Trusted policy
and downstream case work are always track-specific.

## Evidence and failure semantics

Scientific no-hit, no-model, ambiguity, and abstention outcomes are typed
successful tasks. Contract, checksum, software, scheduler, and infrastructure
failures remain loud. Every candidate and every attempted or rejected model is
retained. LLG and TFZ order advancement only.

The final evidence includes the Nextflow trace, report, timeline, DAG, native
Slurm job inventory, per-job requested and observed resources, aggregate peak
concurrency, observed CPU percentage and peak RSS, cache/replay proof, and
deterministic per-case and per-track outputs. Contract tests prevent the M6
driver from returning to a monolithic Python execution path.
