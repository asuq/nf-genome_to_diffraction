# Phase III offline localisation runtime

## Purpose and scientific boundary

Phase III uses catalogue-wide PSORTb and DeepTMHMM evidence only to order the
first molecular-replacement wave. It never treats a localisation prediction as
protein identity, composition proof, or a reason to discard a catalogue
sequence. Explicit membrane, cell-wall/surface, extracellular, or
transmembrane predictions are retained but deferred from the first wave.
Unknown, signal-peptide-only, conflicting, or failed evidence remains neutral.

The fixed implementation uses local containers with Docker networking set to
`none`. Catalogue sequences are not sent to either project or to any public
service. Container images are pulled before the scientific run; the images and
their model data are not redistributed by this repository.

## Immutable runtimes

PSORTb uses the Brinkman Lab command-line image and its archaeal model:

- tool: PSORTb 3.0.6;
- image: `brinkmanlab/psortb_commandline`;
- manifest digest:
  `sha256:5fd2243b7ed4470e2d5ad521c6f32fcd254d1579600bb1537cbe6322a2181040`;
- licence: GNU GPL v3 for PSORTb; retain the image's bundled notices;
- upstream: [PSORTb documentation](https://psort.org/documentation/) and
  [PSORTb downloads](https://psort.org/downloads/).

DeepTMHMM uses the project container:

- tool: DeepTMHMM 1.0;
- image: `deeptmhmm/deeptmhmm`;
- manifest digest:
  `sha256:e527883fd2114007c6208c3d764fece40016cc95e209eab93016644c3e7ccb16`;
- use boundary: local academic use under the upstream terms; do not
  redistribute the image or model data;
- upstream: [DeepTMHMM 1.0](https://services.healthtech.dtu.dk/services/DeepTMHMM-1.0/).

The importer binds the image manifest, platform (`linux/amd64`), container
engine version, effective command, usage statement, and mandatory
`network_mode=none` in each runtime identity. A changed image, command,
network policy, engine version, or adapter changes the content identity.

## Reviewed execution shape

The catalogue FASTA is copied into each created container so Docker Desktop
does not need access to a host project directory. These are separate commands;
they must not be joined into one shell expression.

```text
docker create --name <psortb-run> --platform linux/amd64 --network none <pinned-psortb-image> -a -o terse -i /input.faa
docker cp <catalogue.faa> <psortb-run>:/input.faa
docker start -a <psortb-run>
```

```text
docker create --name <deeptmhmm-run> --platform linux/amd64 --network none --workdir /openprotein --entrypoint python3 <pinned-deeptmhmm-image> predict.py --fasta /input.faa
docker cp <catalogue.faa> <deeptmhmm-run>:/input.faa
docker start -a <deeptmhmm-run>
```

PSORTb must emit complete terse TSV output. DeepTMHMM must emit complete
three-line topology output. The importer accepts no partial per-tool coverage.
PSORTb records are joined by the exact original FASTA header; DeepTMHMM records
are joined by the original protein identifier. Repeated annotation/locus rows
for one FASTA record are permitted only when they map to the same header,
sequence-equivalence group, and prediction.

## Portable input and outputs

`genome-to-diffraction localisation import-batch` requires:

- the frozen `sequence_groups.jsonl`;
- the frozen `source_records.jsonl`;
- complete PSORTb terse TSV;
- complete DeepTMHMM three-line topologies;
- one schema-v2 gel-evidence manifest, which may honestly contain zero
  observations;
- the exact container-engine version; and
- a new output directory.

It publishes exactly:

- `localisation_batch_manifest.json`;
- `first_wave_policy.json`;
- `group_localisation_evidence.jsonl`;
- `first_wave_sequence_group_ids.txt`;
- `excluded_sequence_group_ids.txt`;
- `gel-evidence.json`;
- `raw/psortb-terse.tsv`; and
- `raw/deeptmhmm-topologies.3line`.

`localisation validate-batch` independently validates layout, identities,
counts, tool coverage, group coverage, raw checksums, gel checksum, and every
derived first-wave list. `localisation stage-batch` performs that validation,
copies the complete bundle, and validates the staged copy again.

The live `provider_discovery` and `first_copy` operations require this complete
bundle. The Phase III A funnel binds the policy and group-evidence identities
into hypothesis/cache identities, ranks active groups before neutral groups,
and omits retained exclusions from the first wave. The current unknown input
has no gel observations, so gel evidence is explicitly neutral rather than
fabricated.

## Failure semantics and test coverage

Missing or duplicate coverage, malformed bytes, changed raw evidence, unsafe
bundle members, inconsistent duplicate-locus mappings, different predictions
for one exact sequence, an unbound gel manifest, a network mode other than
`none`, or a catalogue mismatch is an input-contract failure before molecular
replacement. A valid empty gel manifest is not a failure.

Focused tests cover active/excluded/conflicting outcomes, duplicate-locus
mapping, incomplete coverage, changed raw bytes, first-wave filtering,
mandatory live-route authority, deterministic archive/stage validation,
reviewed-wrapper collection, and three-crystal cached Nextflow replay. The
full locked repository gate is reserved for the completed pre-unknown
integration milestone.
