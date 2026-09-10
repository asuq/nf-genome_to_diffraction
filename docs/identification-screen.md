# Case-specific all-candidate identification screen

The [historical Raven route](raven-identification.md) reused this scientific
graph. The operator-crystal programme is cancelled and its accepted assessments
remain read-only; this page does not authorise restarting it.

This internal, experimental Marmic profile runs explicit catalogue-derived
protein hypotheses without the ordinary discovery route's global 25-coordinate
acquisition boundary. It does not replace or scientifically validate the general
mass-blind candidate generator. An apparent polypeptide-mass interval is an
experimental prior, not protein identity, ASU total mass, or a hard biological
exclusion outside that interval.

## Inputs and accounting

The operator prepares one private input directory containing:

- `plan.json`, validated as `IdentificationPlan` by
  `src/genome_to_diffraction/hpc/identification_inputs.py`;
- complete canonical `sequence_groups.jsonl` and `source_records.jsonl` from one
  trusted catalogue and annotation source; and
- the public coordinate files named by ready candidates.

New input plans use `identification-screen-v2`. Ready cases accept the existing
PDB sequence/Foldseek providers or `afdb_exact`. An exact AFDB case must include
`coordinate_source` with its real AFDB accession, release, sequence/coordinate
checksums, retrieval and confidence provenance. Its `coordinate_path` is the
same safe input-relative path as `coordinate_file`; the preparation task binds
that record to the staged absolute path. Provider, version, sequence, model key
and checksum contradictions fail closed. An AFDB model must not use a fabricated
PDB identifier. Historical version-1 runs retain their original immutable source;
they are not silently interpreted using version-2 preparation or cache semantics.

The plan contains original diffraction paths/checksums and reviewed observation
labels, explicit retained Free-R test values, symmetry, resolution, ASU volume,
reflection count and experimental mass intervals. Diffraction paths must remain
under the already approved P0 input root. No new Free-R flags are generated.

Every interval-matching sequence group must appear exactly once per crystal.
Missing, duplicate, incorrectly mapped or silently omitted groups fail
validation. Candidate dispositions are:

| Disposition | Meaning |
| --- | --- |
| `ready` | An eligible model is explicitly bound to this catalogue sequence. |
| `model_unavailable` | No usable model is supplied; no MR or no-hit claim is made. |
| `existing_work` | An explicit evidence reference reserves or records another attempt; no scientific cache is imported. |

Template identity and coverage describe model suitability, not the probability
of protein identity. The full sequence mass determines all configured Matthews
copy alternatives and their existing prior. Initial MR still searches one copy
while composition retains its expected total. A coupled tNCS placement must be
reported with its observed copy count; it is not strict one-copy evidence.
Staged bytes remain checksum-exact. Independent ARM/x86 NumPy re-evaluation of
the pinned prior permits only relative round-off of `1e-12` (absolute `1e-15`);
copy inventories and the selected expected count must still agree exactly.

The fixed safety boundaries are at most three crystals, 5,000 inventory rows,
12,000 input files, 128 MiB per file and a 1 GiB input archive. These protect
staging resources; they do not truncate the input list. Exceeding a bound fails
explicitly and requires a reviewed execution plan.

## Execution and source ownership

The private mode-0600 spec `.untracked/identification-marmic/input-root.json`
contains exactly `schema_version: "1.0"` and an absolute `input_root`. The
ordinary internal HPC client stages a clean commit already on `origin/main`:

```text
pixi run --locked nf-gtd-hpc-test --config CONFIG --no-progress stage identification-screen --revision COMMIT --source-branch main
pixi run --locked nf-gtd-hpc-test --config CONFIG --no-progress submit identification-screen --run-id RUN_ID
```

Use the exact returned run ID, never a recent directory. Raw SSH and direct
Slurm commands are not part of this interface. The tar stream is bound to the
source commit and all input-file hashes. Links, duplicate members, traversal,
oversized members and mismatched content are rejected before extraction. The
job revalidates the staged input identity before emitting tasks.

Identification input transfer and validation have a bounded 60-minute client
timeout. This does not change scheduler or MR task time limits. Retain a timed-out
attempt and verify that it has no scheduler submission before an explicitly
authorised fresh staging attempt; do not overwrite partial inputs.

`run_mode: "smoke"` runs one deterministic ready representative per crystal.
All other rows remain visibly outside that run's execution subset. After a
successful representative execution, a fresh `screen` plan includes all
remaining ready candidates and explicitly reserves completed smoke work. There
is no automatic cross-run scientific resume.

The internal `identification_screen` stage of `qualification.nf` emits one
preparation task and then one dependent MR
task for each ready candidate. Preparation verifies the exact PDB entity/author
chain, removes other chains, non-polymer residues and hydrogens, and writes a
single-chain model and the full catalogue sequence. No new sequence adaptation,
side-chain pruning or domain-splitting heuristic is introduced by this profile.

For an exact AFDB case, preparation instead reuses the shared
[`phenix.process_predicted_model` adapter](m2-predicted-model-preparation.md)
for one candidate per Nextflow task. The established policy removes
low-confidence residues, converts pLDDT to pseudo-B values and retains one
unsplit model. Source and retained-position sequence mappings, the full
catalogue composition, raw confidence provenance, processed-model record,
runtime digest and native processing logs remain visible. No predicted model
enters MR as an untreated PDB-chain substitute. Empty, malformed or failed
preparations remain explicit preparation failures and do not become MR no-hits.

Both processes stage and content-hash the Phenix manifest. AF-model MR checks
its prepared model/source/runtime binding and uses the established exact-model
100% sequence-mapping input with uncertainty encoded in the converted B values,
as in the shared [first-copy adapter](m3-first-copy-phaser.md). This is not a
claim of error-free predicted coordinates. Experimental models retain their
registered homologue identity and native B values.

The preparation stub bypasses licensed prediction processing and is explicitly
`stub_not_scientific`; the real MR adapter refuses that state. Collection retains
nested predicted-model manifests, models and native logs, including evidence
from failed tasks. Existing MTZ retention and collection bounds still apply.

MR uses isolated licensed Phenix `MR_AUTO`. Existing deterministic workload
plans provide overprovisioned 8/12/16-CPU, 32/48/64-GB, 24/36/48-hour first
attempts. One classified resource/interruption retry scales linearly with
`task.attempt`, bounded at 16 CPUs, 64 GB and 48 hours. At the operator's current
temporary request, this profile launches Nextflow with `-qs 4`: at most four
submitted/active preparation and MR children combined, plus one controller,
for a five-job total. This is not a per-process `maxForks` limit and does not
change other site workflows. Slurm still decides which admitted jobs can run.
Do not remove this temporary limit without explicit direction. MR children exclude
`slurm-003` under the existing site policy. The controller requests eight CPUs,
32 GB and the configured 1,000-hour site allowance so a serialized catalogue is
not cut off by the former 120-hour controller limit. This is an upper allowance,
not an expected runtime; the controller exits on completion. Individual MR
limits are unchanged. No refinement or identity decision runs automatically.

## Results and failure evidence

Each MR task preserves its exact command, candidate/model/diffraction identity,
allocated resources and attempt, byte streams, native Phaser log, and assets.
Statuses distinguish retained placements (`completed_hit`), `completed_no_hit`,
`failed_parse`, `execution_failed`, and `output_missing`. Preparation failures
remain `model_preparation_failed`. A zero scheduler exit does not establish
scientific success or protein identity.

The fixed collector preserves all inventory dispositions and trace rows,
including failed-attempt command/log/partial-asset evidence from confined work
directories when available. A missing terminal record stays incomplete or
unknown, not a no-hit. The summary keeps raw parser metrics separate from
primary-PDB-associated metrics and observed polymer-chain counts.

Bulk collection transfers metadata, logs, PDBs and checksums. Large native map
and reflection MTZ files remain unchanged on Marmic and are indexed by path,
size and checksum; their omission from bulk transfer is explicit. They must be
retrieved for selected finalist review before any map or refinement claim.
Private candidate reports, inputs and outputs do not belong in the public atlas.

Stop for explicit review of convincing exploratory seeds. Preserve unresolved
and sequence-equivalence-group endpoints; no score, runtime or mass prior alone
can establish identity.

## Checks

Focused tests cover inventories exceeding 25 ready candidates, exact catalogue
coverage, altered mappings/coordinates/copies/diffraction, source-bound archive
round trips, unsafe archive members, native chain preparation, resource/thread
binding, no-hit versus parse/resource failure, unpublished failed-task evidence,
owned staging/submission, and a real Nextflow preparation/non-scientific stub
graph. Real Phenix execution is qualified separately on Marmic. A passing stub
or orchestration test is not a scientific identification or a release claim.
