"""Prepare the fixed public 6RTZ ``1A + 1B`` adapter-isolation inputs.

The preparer consumes the checksum-frozen 6RTZ coordinate and structure-factor
files already staged on a network-capable login node. It verifies them against
the tracked M6 protocol, maps entity 1/chain A and entity 2/chain B to the two
frozen exact sequences, converts the deposited reflections to MTZ, and writes
only the files needed for an exact-model A first-copy run followed by the
fixed-A/one-B adapter. It performs no Phenix work and no candidate search.

Outputs are sequence groups, A/B polymer PDBs, the A model/hypothesis inputs,
one crystal manifest, and a checksum-bearing preparation manifest. Failures are
input/preparation errors; no scientific no-hit is produced here. The identity
is derived from source, derived-file, sequence, model, and hypothesis checksums.
The real Phenix control remains a separate scheduled operation.
"""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import gemmi

from genome_to_diffraction.benchmarks.m6_protocol import load_m6_protocol
from genome_to_diffraction.catalogue.mass import MASS_METHOD, assess_mass
from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.diffraction.preflight import select_observations
from genome_to_diffraction.ids import (
    canonical_json_text,
    canonical_sequence,
    content_id,
)
from genome_to_diffraction.schemas.manifests import (
    CrystalEntry,
    CrystalManifest,
    PrototypeProfile,
)
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    ProcessedModelRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.time import utc_now_iso

_CONTROL_KEY = "A01"
_CRYSTAL_ID = "6RTZ"
_PARENT_CHAIN = "A"
_PARTNER_CHAIN = "B"
_ADAPTER_VERSION = "6rtz-fixed-a-one-b-inputs-v1"


class HeteromerControlPreparationError(ValueError):
    """The fixed public control cannot be prepared without changing identity."""


@dataclass(frozen=True)
class HeteromerControlPreparationRequest:
    """Inputs for the fixed 6RTZ preparation operation."""

    protocol: Path
    coordinates: Path
    structure_factors: Path
    output_directory: Path
    progress: bool = True


@dataclass(frozen=True)
class HeteromerControlPreparationResult:
    """Stable paths required by the fixed real-Phenix control."""

    preparation_manifest: Path
    crystal_manifest: Path
    sequence_groups_jsonl: Path
    processed_models_jsonl: Path
    model_preparation_manifest: Path
    hypotheses_jsonl: Path
    mtz: Path
    parent_model: Path
    partner_model: Path
    parent_sequence_group_id: str
    partner_sequence_group_id: str
    parent_hypothesis_id: str


def _regular_file(path: Path, *, label: str) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise HeteromerControlPreparationError(
            f"{label} is not a regular file: {resolved}"
        )
    return resolved


def _verify_source(path: Path, *, sha256: str, size: int, label: str) -> Path:
    resolved = _regular_file(path, label=label)
    if resolved.stat().st_size != size or sha256_file(resolved) != sha256:
        raise HeteromerControlPreparationError(
            f"{label} does not match the frozen 6RTZ source"
        )
    return resolved


def _control_spec(protocol_path: Path):
    protocol = load_m6_protocol(protocol_path)
    matches = [
        control
        for control in protocol.assumption_controls
        if control.target_key == _CONTROL_KEY
    ]
    if len(matches) != 1:
        raise HeteromerControlPreparationError("protocol does not uniquely define A01")
    control = matches[0]
    if (
        control.source.pdb_id != _CRYSTAL_ID
        or control.source.pdb_entity_ids != (1, 2)
        or control.asu_distinct_protein_species != 2
        or control.asu_protein_copy_count != 2
        or len(control.proteins) != 2
    ):
        raise HeteromerControlPreparationError(
            "A01 no longer defines the fixed 6RTZ 1A+1B control"
        )
    return control


def _entity_sequences(coordinates: Path) -> dict[int, str]:
    try:
        block = gemmi.cif.read_file(str(coordinates)).sole_block()
    except (RuntimeError, ValueError) as error:
        raise HeteromerControlPreparationError(
            f"cannot parse 6RTZ coordinates: {error}"
        ) from error
    sequences: dict[int, str] = {}
    for row in block.find(
        ["_entity_poly.entity_id", "_entity_poly.pdbx_seq_one_letter_code_can"]
    ):
        try:
            entity_id = int(str(row[0]))
            sequence = canonical_sequence(str(row[1]).strip().strip(";"))
        except (TypeError, ValueError) as error:
            raise HeteromerControlPreparationError(
                "6RTZ contains an invalid polymer entity record"
            ) from error
        if entity_id in sequences:
            raise HeteromerControlPreparationError(
                f"6RTZ polymer entity {entity_id} is duplicated"
            )
        sequences[entity_id] = sequence
    asymmetry = {
        str(row[0]): int(str(row[1]))
        for row in block.find(["_struct_asym.id", "_struct_asym.entity_id"])
        if str(row[0]) in {_PARENT_CHAIN, _PARTNER_CHAIN}
    }
    if asymmetry != {_PARENT_CHAIN: 1, _PARTNER_CHAIN: 2}:
        raise HeteromerControlPreparationError(
            "6RTZ chain A/B to entity 1/2 mapping changed"
        )
    return sequences


def _sequence_group(sequence: str) -> SequenceGroupRecord:
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    mass = assess_mass(sequence)
    if mass.exact_da is None:
        raise HeteromerControlPreparationError("6RTZ sequence mass is not exact")
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=mass.exact_da,
        molecular_mass_lower_da=mass.lower_da,
        molecular_mass_upper_da=mass.upper_da,
        mass_method=MASS_METHOD,
        residue_policy=mass.residue_policy,
        source_record_count=1,
        quality_flags=mass.quality_flags,
    )


def _extract_polymer_chain(
    coordinates: Path,
    output: Path,
    *,
    chain_name: str,
    full_sequence: str,
) -> tuple[str, tuple[str, ...]]:
    try:
        structure = gemmi.read_structure(str(coordinates))
        selected = gemmi.Selection(f"/1/{chain_name};polymer").copy_structure_selection(
            structure
        )
    except (RuntimeError, ValueError) as error:
        raise HeteromerControlPreparationError(
            f"cannot extract 6RTZ chain {chain_name}: {error}"
        ) from error
    if len(selected) != 1 or len(selected[0]) != 1:
        raise HeteromerControlPreparationError(
            f"6RTZ chain {chain_name} did not resolve exactly once"
        )
    chain = selected[0][0]
    polymer = list(chain.get_polymer())
    observed = "".join(
        gemmi.find_tabulated_residue(residue.name).one_letter_code.upper()
        for residue in polymer
    )
    if not observed or not full_sequence.startswith(observed):
        raise HeteromerControlPreparationError(
            f"6RTZ chain {chain_name} coordinates do not match its entity sequence"
        )
    selected.remove_hydrogens()
    atomic_write_bytes(output, selected.make_pdb_string().encode("ascii"))
    first, last = polymer[0].seqid, polymer[-1].seqid
    return observed, (f"{chain_name}:{first}-{last}",)


def _convert_structure_factors(structure_factors: Path, output: Path) -> gemmi.Mtz:
    try:
        blocks = gemmi.as_refln_blocks(gemmi.cif.read_file(str(structure_factors)))
        if len(blocks) != 1:
            raise HeteromerControlPreparationError(
                "6RTZ structure factors must contain exactly one reflection block"
            )
        mtz = gemmi.CifToMtz().convert_block_to_mtz(blocks[0])
        mtz.update_reso()
    except (RuntimeError, ValueError) as error:
        raise HeteromerControlPreparationError(
            f"cannot convert 6RTZ structure factors: {error}"
        ) from error
    if mtz.spacegroup is None or mtz.nreflections < 1:
        raise HeteromerControlPreparationError("converted 6RTZ MTZ is incomplete")
    observation, _, _ = select_observations(mtz, None)
    if observation is None:
        raise HeteromerControlPreparationError("converted 6RTZ MTZ lacks observations")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        mtz.write_to_file(str(temporary))
        os.replace(temporary, output)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    return mtz


def prepare_6rtz_heteromer_control(
    request: HeteromerControlPreparationRequest,
) -> HeteromerControlPreparationResult:
    """Prepare fixed exact-model inputs for the 6RTZ adapter-isolation run."""

    output = request.output_directory.absolute()
    if output.exists() and any(output.iterdir()):
        raise HeteromerControlPreparationError(
            f"6RTZ preparation output is not empty: {output}"
        )
    control = _control_spec(request.protocol)
    coordinates = _verify_source(
        request.coordinates,
        sha256=control.source.coordinates.sha256,
        size=control.source.coordinates.size_bytes,
        label="6RTZ coordinates",
    )
    structure_factors = _verify_source(
        request.structure_factors,
        sha256=control.source.structure_factors.sha256,
        size=control.source.structure_factors.size_bytes,
        label="6RTZ structure factors",
    )
    sequences = _entity_sequences(coordinates)
    expected = tuple(control.proteins)
    for entity_id, protein in zip((1, 2), expected, strict=True):
        sequence = sequences.get(entity_id)
        if (
            sequence is None
            or len(sequence) != protein.sequence_length
            or hashlib.sha256(sequence.encode("ascii")).hexdigest()
            != protein.sequence_sha256
        ):
            raise HeteromerControlPreparationError(
                f"6RTZ entity {entity_id} differs from frozen protein "
                f"{protein.protein_id}"
            )

    output.mkdir(parents=True, exist_ok=True)
    model_directory = output / "models"
    parent_model = model_directory / "component_A.pdb"
    partner_model = model_directory / "component_B.pdb"
    parent_observed, parent_ranges = _extract_polymer_chain(
        coordinates,
        parent_model,
        chain_name=_PARENT_CHAIN,
        full_sequence=sequences[1],
    )
    _extract_polymer_chain(
        coordinates,
        partner_model,
        chain_name=_PARTNER_CHAIN,
        full_sequence=sequences[2],
    )
    mtz_path = output / "derived" / "6RTZ.mtz"
    mtz = _convert_structure_factors(structure_factors, mtz_path)
    observation, _, _ = select_observations(mtz, None)
    assert observation is not None

    parent_group = _sequence_group(sequences[1])
    partner_group = _sequence_group(sequences[2])
    sequence_groups = output / "sequence_groups.jsonl"
    atomic_write_text(
        sequence_groups,
        f"{canonical_json_text(parent_group)}\n{canonical_json_text(partner_group)}\n",
    )
    mapping_id = content_id(
        "coordmap_",
        {
            "source_sha256": control.source.coordinates.sha256,
            "chain": _PARENT_CHAIN,
            "sequence_sha256": parent_group.sha256,
        },
    )
    coordinate_id = content_id(
        "coord_",
        {"mapping_id": mapping_id, "model_sha256": sha256_file(parent_model)},
    )
    model_id = content_id(
        "model_",
        {
            "coordinate_id": coordinate_id,
            "variant": "experimental_cleaned_source_chain",
            "model_sha256": sha256_file(parent_model),
        },
    )
    model_mass = assess_mass(parent_observed)
    if model_mass.exact_da is None:
        raise HeteromerControlPreparationError("6RTZ A model mass is not exact")
    model = ProcessedModelRecord(
        schema_version="1.0",
        model_id=model_id,
        coordinate_id=coordinate_id,
        variant_type="experimental_cleaned_source_chain",
        residue_ranges=parent_ranges,
        processing_tool="gemmi",
        processing_version=getattr(gemmi, "__version__", "unknown"),
        processing_parameters={
            "adapter_version": _ADAPTER_VERSION,
            "mapping_id": mapping_id,
            "sequence_identity": 1.0,
            "source_pdb_id": _CRYSTAL_ID,
            "source_chain": _PARENT_CHAIN,
            "observed_residue_count": len(parent_observed),
            "full_sequence_length": len(parent_group.sequence),
        },
        model_mass_da=model_mass.exact_da,
        full_candidate_sequence_group_id=parent_group.sequence_group_id,
        model_sha256=sha256_file(parent_model),
        quality_flags=("fixed_6rtz_exact_parent_control",),
    )
    processed_models = output / "processed_models.jsonl"
    atomic_write_text(processed_models, f"{canonical_json_text(model)}\n")
    model_manifest = output / "model_preparation_manifest.json"
    atomic_write_json(
        model_manifest,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "entries": [
                {
                    "model_id": model.model_id,
                    "model_path": "models/component_A.pdb",
                    "model_sha256": model.model_sha256,
                    "mapping_id": mapping_id,
                }
            ],
        },
    )
    hypothesis_id = content_id(
        "mrhyp_",
        {
            "crystal_id": _CRYSTAL_ID,
            "sequence_group_id": parent_group.sequence_group_id,
            "model_id": model.model_id,
            "mtz_sha256": sha256_file(mtz_path),
            "copy_count": 1,
        },
    )
    hypothesis = MrHypothesis(
        schema_version="1.0",
        hypothesis_id=hypothesis_id,
        crystal_id=_CRYSTAL_ID,
        sequence_group_id=parent_group.sequence_group_id,
        model_id=model.model_id,
        copy_count_expected=1,
        copy_number_to_search=1,
        fixed_solution_id=None,
        space_group=mtz.spacegroup.hm,
        obs_labels=observation.rendered,
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=PrototypeProfile.PILOT,
        priority_features={
            "exact_sequence_mapping": True,
            "structural_source_class": "experimental",
            "coordinate_mapping_id": mapping_id,
            "candidate_source_sequence_identity": 1.0,
            "control_role": "fixed_6rtz_parent_A",
        },
        status=MrHypothesisStatus.QUEUED,
    )
    hypotheses = output / "mr_hypotheses.jsonl"
    atomic_write_text(hypotheses, f"{canonical_json_text(hypothesis)}\n")
    crystal_manifest = output / "crystals.json"
    crystal = CrystalManifest(
        schema_version="1.0",
        crystals=(
            CrystalEntry(
                crystal_id=_CRYSTAL_ID,
                mtz="derived/6RTZ.mtz",
                catalogue_id=control.catalogue_id,
                obs_labels=observation.rendered,
                free_flag_labels=(
                    "FreeR_flag"
                    if mtz.column_with_label("FreeR_flag") is not None
                    else None
                ),
                allow_remote_sequence_submission=False,
                notes="Fixed public 6RTZ HisF/HisH 1A+1B adapter-isolation control",
            ),
        ),
    )
    atomic_write_json(crystal_manifest, crystal.model_dump(mode="json"))

    files = {
        "crystal_manifest": crystal_manifest,
        "sequence_groups": sequence_groups,
        "processed_models": processed_models,
        "model_preparation_manifest": model_manifest,
        "hypotheses": hypotheses,
        "mtz": mtz_path,
        "parent_model": parent_model,
        "partner_model": partner_model,
    }
    preparation_manifest = output / "preparation_manifest.json"
    preparation_id = content_id(
        "heteromerprep_",
        {
            "adapter_version": _ADAPTER_VERSION,
            "source_coordinates_sha256": control.source.coordinates.sha256,
            "source_structure_factors_sha256": (
                control.source.structure_factors.sha256
            ),
            "files": {role: sha256_file(path) for role, path in files.items()},
        },
    )
    atomic_write_json(
        preparation_manifest,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "preparation_id": preparation_id,
            "created_at": utc_now_iso(),
            "control_key": _CONTROL_KEY,
            "crystal_id": _CRYSTAL_ID,
            "composition": {"A": 1, "B": 1},
            "parent_sequence_group_id": parent_group.sequence_group_id,
            "partner_sequence_group_id": partner_group.sequence_group_id,
            "parent_hypothesis_id": hypothesis.hypothesis_id,
            "partner_model_identity_fraction": 1.0,
            "source": {
                "coordinates_sha256": control.source.coordinates.sha256,
                "structure_factors_sha256": control.source.structure_factors.sha256,
            },
            "files": {
                role: {
                    "path": path.relative_to(output).as_posix(),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
                for role, path in files.items()
            },
        },
    )
    return HeteromerControlPreparationResult(
        preparation_manifest=preparation_manifest,
        crystal_manifest=crystal_manifest,
        sequence_groups_jsonl=sequence_groups,
        processed_models_jsonl=processed_models,
        model_preparation_manifest=model_manifest,
        hypotheses_jsonl=hypotheses,
        mtz=mtz_path,
        parent_model=parent_model,
        partner_model=partner_model,
        parent_sequence_group_id=parent_group.sequence_group_id,
        partner_sequence_group_id=partner_group.sequence_group_id,
        parent_hypothesis_id=hypothesis.hypothesis_id,
    )
