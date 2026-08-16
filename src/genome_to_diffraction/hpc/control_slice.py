"""Build the fixed six-case prokaryotic control archive for Viper.

The controller accepts no caller-selected cases or evidence roots. It packages
the two checksum-frozen positive controls, their exact and homolog search
models, and one size-matched unrelated model. Target-absent, wrong-catalogue,
and assumption-violation cases reuse those fixed inputs and are declared in the
tracked slice. The remote stage validates this inventory before any scheduled
execution.
"""

import logging
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from tqdm import tqdm

from genome_to_diffraction.benchmarks.mr_controls import _clean_polymer_chain
from genome_to_diffraction.benchmarks.panel import (
    load_homomer_workflow_slice,
    load_homomer_workflow_suite,
    load_public_control_panel,
)
from genome_to_diffraction.benchmarks.public_control import load_public_control_spec
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.models import ValidationError

_LOGGER = logging.getLogger("genome_to_diffraction.hpc.control_slice")

SLICE_ID = "prokaryote_homomer_smoke_v1"
EXPECTED_CASE_IDS = (
    "POS_1JCF",
    "POS_3W45",
    "NEG_MODEL_3W45_6HF7",
    "NEG_ABSENT_3W45",
    "NEG_CATALOGUE_3W45_1JCF",
    "NEG_ASSUMPTION_6CXH",
)
EXPECTED_CONTROL_IDS = ("PDB_1JCF", "PDB_3W45")
PROTEOME_FILES = {
    "PDB_1JCF": "GCF_000008545.1_ASM854v1_protein.faa",
    "PDB_3W45": "GCF_000009045.1_ASM904v1_protein.faa",
}
MODEL_SEQUENCE_IDENTITIES = {
    "pdb_1jce_chain_a_exact": 1.0,
    "pdb_8azg_chain_m_homolog": 0.56,
    "pdb_3w43_chain_a_exact": 1.0,
    "pdb_3t91_chain_a_homolog": 0.21,
}
WRONG_MODEL_SOURCE_SHA256 = (
    "14abeb9760258361183bee3505693ef5d69c366506cc08f77d2ae55ca405e109"
)
WRONG_MODEL_OBSERVED_SEQUENCE_SHA256 = (
    "01647f27a2bdd08feff355166b37a6789aadbd556e82c3e4825bad39bfdab7a7"
)
WRONG_MODEL_SHA256 = "2ef5d135307a6a54d7dfce07abe63c9cf20d04cb648fd09b12d19fb4f34e98de"
MAX_CONTROL_SLICE_ARCHIVE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ControlSliceBundle:
    """One immutable fixed-input archive for the six-case Viper run."""

    archive: Path
    archive_sha256: str
    archive_size_bytes: int
    manifest_sha256: str
    case_count: int


def _regular(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValidationError(f"required {label} is absent: {path}") from error
    if path.is_symlink() or not resolved.is_file():
        raise ValidationError(f"{label} must be a regular non-symlink file")
    return resolved


def _verified(path: Path, expected_sha256: str, label: str) -> Path:
    resolved = _regular(path, label)
    if sha256_file(resolved) != expected_sha256:
        raise ValidationError(f"fixed {label} checksum changed")
    return resolved


def _write_bundle_archive(
    destination: Path,
    *,
    members: dict[str, Path],
    manifest_payload: dict[str, object],
    progress: bool,
) -> tuple[str, int, str]:
    """Write a bounded regular-file-only archive plus checksum inventory."""

    inventory: dict[str, dict[str, object]] = {}
    resolved_members: dict[str, Path] = {}
    for archive_name, source in members.items():
        relative = PurePosixPath(archive_name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValidationError("control-slice archive member path is unsafe")
        resolved = _regular(source, f"control-slice asset {archive_name}")
        resolved_members[relative.as_posix()] = resolved
        inventory[relative.as_posix()] = {
            "sha256": sha256_file(resolved),
            "size_bytes": resolved.stat().st_size,
        }
    if len(resolved_members) != len(members):
        raise ValidationError("control-slice archive member names are not unique")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="nf-gtd-control-slice-", dir="/tmp"
    ) as temporary:
        manifest = Path(temporary) / "control_slice_import_manifest.json"
        atomic_write_json(manifest, {**manifest_payload, "inventory": inventory})
        manifest_sha256 = sha256_file(manifest)
        archive_members = {
            **resolved_members,
            "control_slice_import_manifest.json": manifest,
        }
        with (
            tarfile.open(
                destination, mode="w:gz", format=tarfile.PAX_FORMAT
            ) as archive,
            tqdm(
                total=len(archive_members),
                desc="Building Viper control slice",
                unit="file",
                disable=not progress,
            ) as progress_bar,
        ):
            for archive_name, source in sorted(archive_members.items()):
                archive.add(source, arcname=archive_name, recursive=False)
                progress_bar.update(1)

    archive_size = destination.stat().st_size
    if not 1 <= archive_size <= MAX_CONTROL_SLICE_ARCHIVE_BYTES:
        destination.unlink(missing_ok=True)
        raise ValidationError("control-slice archive exceeds its fixed size bound")
    return sha256_file(destination), archive_size, manifest_sha256


def build_fixed_control_slice_bundle(
    repository: Path,
    destination: Path,
    *,
    progress: bool,
) -> ControlSliceBundle:
    """Build the only accepted local evidence archive for the six-case slice."""

    control_root = repository / "benchmarks/public-controls"
    panel_path = control_root / "panel.yaml"
    panel = load_public_control_panel(panel_path)
    suite_path = control_root / panel.workflow_suite
    suite = load_homomer_workflow_suite(suite_path, panel)
    slice_path = control_root / panel.smoke_slice
    smoke_slice = load_homomer_workflow_slice(slice_path, panel=panel, suite=suite)
    if smoke_slice.slice_id != SLICE_ID or smoke_slice.case_ids != EXPECTED_CASE_IDS:
        raise ValidationError("fixed control-slice identity changed")

    evidence_root = repository / ".untracked/public-controls"
    prepared: dict[str, dict[str, object]] = {}
    members: dict[str, Path] = {}
    for control_id in EXPECTED_CONTROL_IDS:
        entry = next(item for item in panel.entries if item.control_id == control_id)
        if entry.active_control_specification is None:
            raise ValidationError(f"fixed positive is not runnable: {control_id}")
        specification_path = control_root / entry.active_control_specification
        specification = load_public_control_spec(specification_path)
        local_root = evidence_root / control_id
        proteome = _verified(
            evidence_root / "runnable-sources" / PROTEOME_FILES[control_id],
            specification.expected_proteome_sha256,
            f"{control_id} proteome",
        )
        mtz = _verified(
            local_root / "derived" / specification.derived_mtz.filename,
            specification.derived_mtz.sha256,
            f"{control_id} MTZ",
        )
        model_records: dict[str, dict[str, object]] = {}
        members[f"controls/{control_id}/proteome.faa"] = proteome
        members[f"controls/{control_id}/input.mtz"] = mtz
        for model in specification.mr_models:
            model_path = _verified(
                local_root / "models" / model.filename,
                model.expected_model_sha256,
                f"{control_id} model {model.model_id}",
            )
            archive_path = f"controls/{control_id}/models/{model.model_id}.pdb"
            members[archive_path] = model_path
            model_records[model.model_id] = {
                "archive_path": archive_path,
                "sha256": model.expected_model_sha256,
                "leakage_class": model.leakage_class,
                "sequence_identity_fraction": MODEL_SEQUENCE_IDENTITIES[model.model_id],
                "exact_sequence_mapping": (model.leakage_class == "operational_exact"),
            }
        prepared[control_id] = {
            "control_specification_sha256": sha256_file(specification_path),
            "expected_asu_copy_count": specification.expected_asu_copy_count,
            "target_protein_id": specification.target_protein_id,
            "catalogue_id": specification.catalogue_id,
            "annotation_provider": specification.annotation_provider,
            "target_sequence_sha256": specification.target_sequence_sha256,
            "proteome_sha256": specification.expected_proteome_sha256,
            "mtz_sha256": specification.derived_mtz.sha256,
            "models": model_records,
        }

    wrong_source = _verified(
        evidence_root / "panel-v2/PDB_6HF7/sources/6HF7.cif",
        WRONG_MODEL_SOURCE_SHA256,
        "6HF7 wrong-model source",
    )
    wrong_payload, _, wrong_ranges, wrong_atoms = _clean_polymer_chain(
        wrong_source,
        chain_name="A",
        expected_sequence_sha256=WRONG_MODEL_OBSERVED_SEQUENCE_SHA256,
    )
    with tempfile.TemporaryDirectory(
        prefix="nf-gtd-control-model-", dir="/tmp"
    ) as temporary:
        wrong_model = Path(temporary) / "6HF7-chain-A-polymer.pdb"
        wrong_model.write_bytes(wrong_payload)
        if sha256_file(wrong_model) != WRONG_MODEL_SHA256:
            raise ValidationError("fixed 6HF7 wrong-model derivation changed")
        members["controls/NEG_MODEL_3W45_6HF7/model.pdb"] = wrong_model
        manifest_payload: dict[str, object] = {
            "schema_version": "1.0",
            "adapter_version": "public-homomer-smoke-import-v1",
            "site_id": "viper-cpu",
            "panel_id": panel.panel_id,
            "slice_id": smoke_slice.slice_id,
            "case_ids": list(smoke_slice.case_ids),
            "panel_sha256": sha256_file(panel_path),
            "suite_sha256": sha256_file(suite_path),
            "slice_sha256": sha256_file(slice_path),
            "positive_controls": prepared,
            "wrong_model": {
                "case_id": "NEG_MODEL_3W45_6HF7",
                "source_control_id": "PDB_6HF7",
                "target_control_id": "PDB_3W45",
                "source_coordinate_sha256": WRONG_MODEL_SOURCE_SHA256,
                "observed_sequence_sha256": (WRONG_MODEL_OBSERVED_SEQUENCE_SHA256),
                "model_sha256": WRONG_MODEL_SHA256,
                "residue_ranges": list(wrong_ranges),
                "atom_count": wrong_atoms,
            },
            "target_absent_derivation": {
                "case_id": "NEG_ABSENT_3W45",
                "source_control_id": "PDB_3W45",
                "remove_all_sequence_sha256": prepared["PDB_3W45"][
                    "target_sequence_sha256"
                ],
            },
            "wrong_catalogue_derivation": {
                "case_id": "NEG_CATALOGUE_3W45_1JCF",
                "target_control_id": "PDB_3W45",
                "catalogue_control_id": "PDB_1JCF",
            },
            "assumption_violation": {
                "case_id": "NEG_ASSUMPTION_6CXH",
                "target_control_id": "PDB_6CXH",
                "expected_outcome": "assumption_violation_or_abstention",
                "asu_model": "three_distinct_protein_species",
            },
            "all_candidates_retained": True,
            "score_policy": "LLG/TFZ_are_ranking_annotations_only",
        }
        archive_sha256, archive_size, manifest_sha256 = _write_bundle_archive(
            destination,
            members=members,
            manifest_payload=manifest_payload,
            progress=progress,
        )

    _LOGGER.info(
        "built fixed prokaryotic control-slice archive",
        extra={
            "slice_id": smoke_slice.slice_id,
            "case_count": len(smoke_slice.case_ids),
            "archive_size_bytes": archive_size,
        },
    )
    return ControlSliceBundle(
        archive=destination,
        archive_sha256=archive_sha256,
        archive_size_bytes=archive_size,
        manifest_sha256=manifest_sha256,
        case_count=len(smoke_slice.case_ids),
    )
