"""Validate the fixed known-control reopening input before Nextflow fan-out.

Inputs are one portable JSON manifest and its retained reviewed plan, source
identity, sequences, registry, preflight, original MTZ and licensed-runtime
manifest. The output is a path-resolved dispatch document for the existing no-A
workflow. This bounded I/O task invokes no scientific executable. It reuses the
unknown-pass-2 selection validator without its later RG7 closure requirement;
only 7L6G, 3U7Q and 9ECN are admitted. Every scientific task retains its existing
content keys, one-copy request and 175-attempt bound. Malformed, stale or changed
authority fails explicitly. Tests cover the common validator and fixed scope.
"""

import argparse
import json
import sys
from pathlib import Path

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.unknown_pass2_inputs import (
    validate_no_a_reopening_authority,
)
from genome_to_diffraction.localisation.reopen_batch import (
    BatchLocalisationReopenPlan,
    BatchLocalisationReopenStatus,
)
from genome_to_diffraction.schemas.v2.execution import PhaseIIIExecutionIdentity

PATH_FIELDS = (
    "pass1_assessment",
    "no_a_expansion_plan",
    "sequence_groups",
    "model_registry",
    "preflight",
    "mtz",
    "diffraction_selection",
    "phenix_manifest",
    "execution_identity",
    "source_records",
    "matthews",
    "pipeline_config",
)


def validate_known_control_reopening(
    manifest: Path,
    *,
    source_commit: str,
    phenix_manifest: Path,
) -> dict[str, object]:
    """Reuse source/parent/package/selection authentication for one control."""

    from genome_to_diffraction.hpc.raven_qualification import confined

    manifest = manifest.resolve(strict=True)
    root = manifest.parent
    document = json.loads(manifest.read_text())
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "crystal_id", "parent_run_id", "paths"}
        or document["schema_version"] != "1.0"
        or document["crystal_id"] not in {"7L6G", "3U7Q", "9ECN"}
        or not isinstance(document["paths"], dict)
        or set(document["paths"]) != set(PATH_FIELDS)
    ):
        raise ValueError("known-control reopening manifest is invalid")
    paths = {}
    for name, value in document["paths"].items():
        if not isinstance(value, str):
            raise ValueError("known-control input path must be relative text")
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts or str(relative) != value:
            raise ValueError("known-control input path escapes its bundle")
        paths[name] = confined(root / relative, root)
    identity = PhaseIIIExecutionIdentity.model_validate_json(
        paths["execution_identity"].read_text()
    )
    crystal_id = document["crystal_id"]
    if identity.source_commit != source_commit:
        raise ValueError("known-control execution source changed")
    mtz_assets = [
        item
        for item in identity.crystal_artifacts
        if item.owner_id == crystal_id and item.role == "mtz"
    ]
    if (
        len(mtz_assets) != 1
        or mtz_assets[0].sha256 != sha256_file(paths["mtz"])
        or mtz_assets[0].size_bytes != paths["mtz"].stat().st_size
        or sha256_file(paths["phenix_manifest"]) != sha256_file(phenix_manifest)
    ):
        raise ValueError("known-control diffraction or runtime changed")
    plan = BatchLocalisationReopenPlan.model_validate_json(
        (paths["no_a_expansion_plan"] / "localisation_reopen_plan.json").read_text()
    )
    if plan.status is not BatchLocalisationReopenStatus.READY_REVIEWED:
        raise ValueError("known-control qualification requires reviewed reopening")
    validate_no_a_reopening_authority(
        paths,
        crystal_id=crystal_id,
        identity=identity,
        expected_parent_run_id=document["parent_run_id"],
    )
    return {
        "crystal_id": crystal_id,
        "parent_run_id": document["parent_run_id"],
        "paths": {name: str(path) for name, path in paths.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--phenix-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dispatch = validate_known_control_reopening(
        args.manifest,
        source_commit=args.source_commit,
        phenix_manifest=args.phenix_manifest,
    )
    atomic_write_json(args.output, dispatch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
