"""Build the fixed 23-case prokaryotic homomer benchmark archive.

The archive contains the 11 checksum-frozen positive MTZ/catalogue pairs and
one operational same-structure chain-A search model per positive.  Seven
wrong-model cases reuse those independently derived model assets.  The two
target-absent, two wrong-catalogue, and one heteromeric assumption-violation
cases are typed identity/assumption boundaries and do not fabricate Phaser
searches.  All coordinates are operational controls, not leakage-controlled
generalisation evidence.

Inputs are the tracked public panel/suite and the fixed ignored public-source
cache.  Outputs are one regular-file-only tar archive and checksum manifest.
Source coordinate, MTZ, and proteome checksums fail loudly.  The cache identity
is the panel, suite, input, and deterministic chain-derivation checksums.
"""

import hashlib
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import gemmi

from genome_to_diffraction.benchmarks.panel import (
    HomomerWorkflowCaseSpec,
    PublicPanelEntrySpec,
    load_homomer_workflow_suite,
    load_public_control_panel,
)
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.hpc.control_slice import (
    _verified,
    _write_bundle_archive,
)
from genome_to_diffraction.hpc.models import ValidationError

_LOGGER = logging.getLogger("genome_to_diffraction.hpc.control_matrix")

SUITE_ID = "prokaryote_homomer_workflow_v1"
EXPECTED_CASE_COUNT = 23
EXPECTED_CASE_KIND_COUNTS = {
    "positive": 11,
    "wrong_model_negative": 7,
    "target_absent_negative": 2,
    "wrong_catalogue_negative": 2,
    "assumption_violation": 1,
}
EXPECTED_POSITIVE_COPY_COUNTS = {1, 2, 3, 4, 6}
MAX_CONTROL_MATRIX_ARCHIVE_BYTES = 128 * 1024 * 1024
_MODIFIED_RESIDUE_ONE_LETTER = {"KYN": "W"}


@dataclass(frozen=True, slots=True)
class ControlMatrixBundle:
    """One immutable archive for the complete fixed benchmark matrix."""

    archive: Path
    archive_sha256: str
    archive_size_bytes: int
    manifest_sha256: str
    case_count: int
    positive_count: int
    real_search_count: int


def _one_letter(residue_name: str) -> str:
    letter = _MODIFIED_RESIDUE_ONE_LETTER.get(residue_name)
    if letter is None:
        letter = gemmi.find_tabulated_residue(residue_name).one_letter_code.upper()
    if letter not in "ACDEFGHIKLMNPQRSTVWY":
        raise ValidationError(
            f"unsupported polymer residue in fixed control model: {residue_name}"
        )
    return letter


def _chain_model(
    source: Path,
    *,
    chain_name: str,
    expected_entity_sequence_sha256: str,
) -> tuple[bytes, str, str, tuple[str, ...], int]:
    """Validate the full polymer entity and derive one observed-chain model."""

    try:
        structure = gemmi.read_structure(str(source))
        structure.setup_entities()
    except (OSError, RuntimeError, ValueError) as error:
        raise ValidationError(
            f"cannot parse fixed control coordinate: {source}"
        ) from error
    if len(structure) != 1:
        raise ValidationError("fixed control coordinate must contain one model")
    chains = [chain for chain in structure[0] if chain.name == chain_name]
    if len(chains) != 1:
        raise ValidationError("fixed control chain did not resolve exactly once")
    polymer = chains[0].get_polymer()
    residues = list(polymer)
    if not residues:
        raise ValidationError("fixed control chain has no observed polymer residues")
    entity = structure.get_entity_of(polymer)
    entity_sequence = "".join(_one_letter(str(name)) for name in entity.full_sequence)
    entity_sha256 = hashlib.sha256(entity_sequence.encode("ascii")).hexdigest()
    if entity_sha256 != expected_entity_sequence_sha256:
        raise ValidationError(
            "fixed control entity sequence differs from panel mapping"
        )
    observed_sequence = "".join(_one_letter(residue.name) for residue in residues)
    selected = gemmi.Selection(f"/1/{chain_name};polymer").copy_structure_selection(
        structure
    )
    if len(selected) != 1 or len(selected[0]) != 1:
        raise ValidationError("fixed control selection did not yield one polymer chain")
    selected.remove_hydrogens()
    selected[0][0].name = "A"
    payload = selected.make_pdb_string().encode("ascii")
    first = residues[0].seqid
    last = residues[-1].seqid
    atom_count = sum(len(residue) for residue in selected[0][0].get_polymer())
    return (
        payload,
        observed_sequence,
        hashlib.sha256(observed_sequence.encode("ascii")).hexdigest(),
        (f"{chain_name}:{first}-{last}",),
        atom_count,
    )


def _case_kind_counts(cases: tuple[HomomerWorkflowCaseSpec, ...]) -> dict[str, int]:
    counts = {kind: 0 for kind in EXPECTED_CASE_KIND_COUNTS}
    for case in cases:
        counts[case.case_kind] += 1
    return counts


def _proteome_filename(entry: PublicPanelEntrySpec) -> str:
    return f"{entry.assembly_accession}_{entry.assembly_version}_protein.faa"


def build_fixed_control_matrix_bundle(
    repository: Path,
    destination: Path,
    *,
    progress: bool,
) -> ControlMatrixBundle:
    """Build the complete fixed 23-case benchmark archive."""

    control_root = repository / "benchmarks/public-controls"
    panel_path = control_root / "panel.yaml"
    panel = load_public_control_panel(panel_path)
    suite_path = control_root / panel.workflow_suite
    suite = load_homomer_workflow_suite(suite_path, panel)
    if suite.suite_id != SUITE_ID or len(suite.cases) != EXPECTED_CASE_COUNT:
        raise ValidationError("fixed homomer workflow suite identity changed")
    if _case_kind_counts(suite.cases) != EXPECTED_CASE_KIND_COUNTS:
        raise ValidationError("fixed homomer workflow case distribution changed")

    entries = {entry.control_id: entry for entry in panel.entries}
    positives = tuple(
        entries[case.target_control_id]
        for case in suite.cases
        if case.case_kind == "positive"
    )
    if {entry.asu_protein_copy_count for entry in positives} != (
        EXPECTED_POSITIVE_COPY_COUNTS
    ):
        raise ValidationError("positive controls no longer cover ASU counts 1/2/3/4/6")

    evidence_root = repository / ".untracked/public-controls"
    members: dict[str, Path] = {}
    positive_records: dict[str, dict[str, object]] = {}
    derived_models: dict[str, dict[str, object]] = {}
    with tempfile.TemporaryDirectory(
        prefix="nf-gtd-control-matrix-", dir="/tmp"
    ) as temporary:
        model_root = Path(temporary)
        for entry in positives:
            if entry.derived_mtz is None:
                raise ValidationError(
                    f"positive control lacks one MTZ: {entry.control_id}"
                )
            target = entry.catalogue_targets[0]
            proteome = _verified(
                evidence_root / "runnable-sources" / _proteome_filename(entry),
                entry.expected_proteome_sha256,
                f"{entry.control_id} proteome",
            )
            mtz = _verified(
                evidence_root
                / f"panel-v2/{entry.control_id}/derived/{entry.derived_mtz.filename}",
                entry.derived_mtz.sha256,
                f"{entry.control_id} MTZ",
            )
            coordinate = _verified(
                evidence_root
                / f"panel-v2/{entry.control_id}/sources/{entry.coordinates.filename}",
                entry.coordinates.sha256,
                f"{entry.control_id} coordinate",
            )
            payload, observed, observed_sha, ranges, atom_count = _chain_model(
                coordinate,
                chain_name="A",
                expected_entity_sequence_sha256=(
                    target.construct_mapping.coordinate_sequence_sha256
                ),
            )
            model_id = f"pdb_{entry.pdb_id.lower()}_chain_a_operational"
            model = model_root / f"{model_id}.pdb"
            model.write_bytes(payload)
            model_sha = sha256_file(model)
            model_archive_path = f"models/{model_id}.pdb"
            members[model_archive_path] = model
            derived_models[entry.control_id] = {
                "model_id": model_id,
                "archive_path": model_archive_path,
                "sha256": model_sha,
                "source_coordinate_sha256": entry.coordinates.sha256,
                "source_chain_id": "A",
                "entity_sequence_sha256": (
                    target.construct_mapping.coordinate_sequence_sha256
                ),
                "observed_sequence_sha256": observed_sha,
                "observed_sequence": observed,
                "observed_residue_ranges": list(ranges),
                "atom_count": atom_count,
                "sequence_identity_fraction": 1.0,
                "exact_sequence_mapping": True,
                "leakage_class": "operational_same_structure",
            }
            members[f"controls/{entry.control_id}/proteome.faa"] = proteome
            members[f"controls/{entry.control_id}/input.mtz"] = mtz
            positive_records[entry.control_id] = {
                "expected_asu_copy_count": entry.asu_protein_copy_count,
                "target_protein_id": target.protein_id,
                "catalogue_id": (
                    f"{entry.assembly_accession.lower().replace('.', '_')}_refseq"
                ),
                "annotation_provider": entry.annotation_provider,
                "annotation_version": entry.annotation_version,
                "target_sequence_sha256": target.sequence_sha256,
                "construct_sequence_sha256": (
                    target.construct_mapping.coordinate_sequence_sha256
                ),
                "proteome_sha256": entry.expected_proteome_sha256,
                "mtz_sha256": entry.derived_mtz.sha256,
                "model": derived_models[entry.control_id],
            }

        wrong_models: dict[str, dict[str, object]] = {}
        typed_cases: dict[str, dict[str, object]] = {}
        for case in suite.cases:
            record: dict[str, object] = {
                "case_kind": case.case_kind,
                "target_control_id": case.target_control_id,
                "expected_outcome": case.expected_outcome,
            }
            if case.case_kind == "wrong_model_negative":
                if case.model_control_id is None:
                    raise ValidationError("fixed wrong-model case lacks a model source")
                model = derived_models[case.model_control_id]
                wrong_models[case.case_id] = {
                    **record,
                    "model_control_id": case.model_control_id,
                    "model_chain_id": case.model_chain_id,
                    "model": model,
                }
            elif case.case_kind != "positive":
                if case.catalogue_control_id is not None:
                    record["catalogue_control_id"] = case.catalogue_control_id
                typed_cases[case.case_id] = record

        manifest_payload: dict[str, object] = {
            "schema_version": "1.0",
            "adapter_version": "public-homomer-matrix-import-v1",
            "site_id": "viper-cpu",
            "panel_id": panel.panel_id,
            "suite_id": suite.suite_id,
            "case_ids": [case.case_id for case in suite.cases],
            "case_kind_counts": EXPECTED_CASE_KIND_COUNTS,
            "positive_copy_counts": sorted(EXPECTED_POSITIVE_COPY_COUNTS),
            "panel_sha256": sha256_file(panel_path),
            "suite_sha256": sha256_file(suite_path),
            "positive_controls": positive_records,
            "wrong_model_controls": wrong_models,
            "typed_boundary_cases": typed_cases,
            "all_candidates_retained": True,
            "score_policy": "LLG/TFZ_are_ranking_annotations_only",
            "generalisation_claim": "none_operational_same_structure_controls",
        }
        archive_sha, archive_size, manifest_sha = _write_bundle_archive(
            destination,
            members=members,
            manifest_payload=manifest_payload,
            progress=progress,
            maximum_archive_bytes=MAX_CONTROL_MATRIX_ARCHIVE_BYTES,
            manifest_name="control_matrix_import_manifest.json",
        )

    real_search_count = (
        len(positives) + EXPECTED_CASE_KIND_COUNTS["wrong_model_negative"]
    )
    _LOGGER.info(
        "built fixed prokaryotic control matrix",
        extra={
            "case_count": len(suite.cases),
            "positive_count": len(positives),
            "real_search_count": real_search_count,
            "archive_size_bytes": archive_size,
        },
    )
    return ControlMatrixBundle(
        archive=destination,
        archive_sha256=archive_sha,
        archive_size_bytes=archive_size,
        manifest_sha256=manifest_sha,
        case_count=len(suite.cases),
        positive_count=len(positives),
        real_search_count=real_search_count,
    )
