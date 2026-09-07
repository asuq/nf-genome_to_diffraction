"""Register the complete leakage-filtered M6 model inventory offline.

Inputs are validated catalogue groups, accepted structural hits and the qualified
database manifest. Outputs are one portable coordinate registry and exact mapping
inventory. Registration reads existing cache objects; it runs no external tool and
has no network authority. Batches bound registration I/O to 1,000 hits without
imposing an admission limit. Duplicate, missing or changed mappings fail closed.
The parent M6 stage binds input/output checksums and this adapter version. Focused
tests cover batching, conservation, duplicate detection and portable object paths.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.schemas.results import (
    CoordinateHitMappingRecord,
    CoordinateSourceRecord,
    StructuralSearchHit,
)
from genome_to_diffraction.structure_search import (
    PdbCoordinateRegistrationRequest,
    register_pdb_coordinates,
)

M6_REGISTRATION_ADAPTER = "m6-complete-offline-registration-v1"
M6_REGISTRATION_BATCH_SIZE = 1000


def registration_batches(
    hits: tuple[StructuralSearchHit, ...],
) -> tuple[tuple[StructuralSearchHit, ...], ...]:
    """Partition every accepted hit once, independently of provider rank."""

    identifiers = [hit.hit_id for hit in hits]
    if len(identifiers) != len(set(identifiers)):
        raise PublicControlError("M6 accepted model inventory contains duplicate hits")
    ordered = sorted(
        hits, key=lambda hit: (hit.sequence_group_id, hit.provider, hit.hit_id)
    )
    return tuple(
        tuple(ordered[start : start + M6_REGISTRATION_BATCH_SIZE])
        for start in range(0, len(ordered), M6_REGISTRATION_BATCH_SIZE)
    )


def register_m6_models(
    *,
    hits: tuple[StructuralSearchHit, ...],
    sequence_groups: Path,
    database_manifest: Path,
    output_directory: Path,
) -> None:
    """Materialise all accepted mappings through bounded offline registration."""

    batches = registration_batches(hits)
    if not batches:
        raise PublicControlError("M6 active coordinate registry has no accepted hits")
    output_directory.mkdir(parents=True, exist_ok=False)
    sources: dict[str, CoordinateSourceRecord] = {}
    mappings: dict[str, CoordinateHitMappingRecord] = {}
    batch_checksums: dict[str, str] = {}
    for index, batch in enumerate(batches, start=1):
        batch_root = output_directory / "batches" / f"{index:04d}"
        batch_root.mkdir(parents=True)
        batch_hits = batch_root / "accepted_hits.jsonl"
        atomic_write_text(
            batch_hits, "".join(f"{canonical_json_text(hit)}\n" for hit in batch)
        )
        registration = batch_root / "registration"
        register_pdb_coordinates(
            PdbCoordinateRegistrationRequest(
                structural_hits_jsonl=batch_hits,
                sequence_groups_jsonl=sequence_groups,
                database_manifest=database_manifest,
                output_directory=registration,
                hit_ids=tuple(hit.hit_id for hit in batch),
                maximum_hits_per_sequence_group=max(
                    Counter(hit.sequence_group_id for hit in batch).values()
                ),
                maximum_mappings=len(batch),
                materialise_coordinate_objects=True,
                allow_network_acquisition=False,
                progress=False,
            )
        )
        batch_checksums[str(index)] = sha256_file(
            registration / "registration_manifest.json"
        )
        for line in (
            (registration / "coordinate_sources.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ):
            source = CoordinateSourceRecord.model_validate_json(line)
            local_path = Path(source.coordinate_path)
            if local_path.is_absolute() or ".." in local_path.parts:
                raise PublicControlError(
                    "M6 registration returned a non-portable coordinate"
                )
            coordinate = registration / local_path
            if (
                coordinate.is_symlink()
                or sha256_file(coordinate) != source.coordinate_sha256
            ):
                raise PublicControlError("M6 registered coordinate checksum differs")
            previous = sources.get(source.coordinate_id)
            source = source.model_copy(
                update={
                    "coordinate_path": str(coordinate.relative_to(output_directory))
                }
            )
            if previous is not None:
                if previous.model_dump(
                    exclude={"coordinate_path"}
                ) != source.model_dump(exclude={"coordinate_path"}):
                    raise PublicControlError(
                        "M6 repeated coordinate identity has conflicting evidence"
                    )
            else:
                sources[source.coordinate_id] = source
        observed_hits: set[str] = set()
        for line in (
            (registration / "coordinate_hit_mappings.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ):
            mapping = CoordinateHitMappingRecord.model_validate_json(line)
            if mapping.mapping_id in mappings or mapping.hit_id in observed_hits:
                raise PublicControlError(
                    "M6 registration duplicated an accepted mapping"
                )
            observed_hits.add(mapping.hit_id)
            mappings[mapping.mapping_id] = mapping
        if observed_hits != {hit.hit_id for hit in batch}:
            raise PublicControlError(
                "M6 registration omitted or introduced accepted hits"
            )
    sources_path = output_directory / "coordinate_sources.jsonl"
    mappings_path = output_directory / "coordinate_hit_mappings.jsonl"
    atomic_write_text(
        sources_path,
        "".join(f"{canonical_json_text(sources[key])}\n" for key in sorted(sources)),
    )
    atomic_write_text(
        mappings_path,
        "".join(f"{canonical_json_text(mappings[key])}\n" for key in sorted(mappings)),
    )
    if {mapping.coordinate_id for mapping in mappings.values()} != set(sources):
        raise PublicControlError(
            "M6 coordinate registry and mapping inventories differ"
        )
    atomic_write_json(
        output_directory / "registration_manifest.json",
        {
            "schema_version": "1.0",
            "adapter_version": M6_REGISTRATION_ADAPTER,
            "status": "completed_success",
            "scope": "complete_post_leakage_accepted_model_inventory",
            "accepted_hit_count": len(hits),
            "selected_mapping_count": len(mappings),
            "coordinate_source_count": len(sources),
            "batch_size_limit": M6_REGISTRATION_BATCH_SIZE,
            "batch_manifest_sha256": batch_checksums,
            "output_sha256": {
                "coordinate_sources": sha256_file(sources_path),
                "coordinate_hit_mappings": sha256_file(mappings_path),
            },
        },
    )
