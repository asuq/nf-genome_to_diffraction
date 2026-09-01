"""Add a typed non-scientific import manifest to a catalogue stub bundle."""

import argparse
import sys
from pathlib import Path

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    CatalogueImportManifest,
    CatalogueInputRecord,
    CatalogueManifest,
    OutputArtifactRecord,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalogues", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--catalogue-directory", type=Path, required=True)
    return parser


def _nonblank_count(path: Path) -> int:
    return sum(
        1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    )


def main() -> int:
    args = _parser().parse_args()
    catalogues_path = args.catalogues.resolve(strict=True)
    config_path = args.config.resolve(strict=True)
    output = args.catalogue_directory.resolve(strict=True)
    manifest = load_contract(
        catalogues_path,
        "catalogue-manifest",
        progress=False,
    )
    if not isinstance(manifest, CatalogueManifest) or len(manifest.catalogues) != 1:
        raise ValueError("catalogue stub requires exactly one catalogue")
    catalogue_id = manifest.catalogues[0].catalogue_id
    output_paths = (
        ("exact_sequences", output / "exact_sequences.faa"),
        ("sequence_groups", output / "sequence_groups.jsonl"),
        ("source_records", output / "source_records.jsonl"),
    )
    outputs = tuple(
        OutputArtifactRecord(
            role=role,
            path=path.name,
            size_bytes=path.stat().st_size,
            sha256=sha256_file(path, progress=False),
        )
        for role, path in output_paths
    )
    identity = {
        "adapter_version": "catalogue-import-stub-v1",
        "catalogue_manifest_sha256": sha256_file(
            catalogues_path,
            progress=False,
        ),
        "pipeline_config_sha256": sha256_file(config_path, progress=False),
        "outputs": [item.model_dump(mode="json") for item in outputs],
    }
    record = CatalogueImportManifest(
        schema_version="1.0",
        import_id=content_id("catimport_", identity),
        created_at="2026-01-01T00:00:00Z",
        software_version="stub",
        catalogue_ids=(catalogue_id,),
        catalogue_manifest_sha256=identity["catalogue_manifest_sha256"],
        pipeline_config_sha256=identity["pipeline_config_sha256"],
        inputs=(
            CatalogueInputRecord(
                catalogue_id=catalogue_id,
                role="catalogue_manifest",
                path=catalogues_path.name,
                sha256=identity["catalogue_manifest_sha256"],
            ),
        ),
        outputs=outputs,
        source_record_count=_nonblank_count(output / "source_records.jsonl"),
        sequence_group_count=_nonblank_count(output / "sequence_groups.jsonl"),
        warning_count=1,
        warnings=("stub_mode_no_catalogue_import",),
    )
    atomic_write_json(
        output / "catalogue_import_manifest.json",
        record.model_dump(mode="json"),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
