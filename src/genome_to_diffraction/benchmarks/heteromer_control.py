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

import csv
import hashlib
import io
import os
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import gemmi

from genome_to_diffraction.benchmarks.m6_protocol import (
    M6FrozenResourceSpec,
    load_m6_protocol,
)
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
from genome_to_diffraction.matthews.enumerate import COPY_RANGE_BACKEND, prior_score
from genome_to_diffraction.matthews.probability import PRIOR_BACKEND
from genome_to_diffraction.mr.stage_add_copy import (
    LiveAddCopyStageRequest,
    prepare_live_add_copy_stage,
)
from genome_to_diffraction.review.mr_seed import (
    MrSeedReviewRequest,
    build_mr_seed_review,
)
from genome_to_diffraction.schemas.io import load_json_document
from genome_to_diffraction.schemas.manifests import (
    CrystalEntry,
    CrystalManifest,
    PipelineConfig,
    PrototypeProfile,
)
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    PhysicalStatus,
    ProcessedModelRecord,
    SequenceGroupRecord,
    SourceProteinRecord,
)
from genome_to_diffraction.status import ExecutionStatus
from genome_to_diffraction.time import utc_now_iso

_CONTROL_KEY = "A01"
_CRYSTAL_ID = "6RTZ"
_PARENT_CHAIN = "A"
_PARTNER_CHAIN = "B"
_ADAPTER_VERSION = "6rtz-fixed-a-one-b-inputs-v1"
_PARENT_PROTEIN_ID = "WP_004080486.1"


@dataclass(frozen=True)
class _ControlDefinition:
    control_key: str
    crystal_id: str
    parent_chain: str
    partner_chain: str
    adapter_version: str
    parent_protein_id: str
    parent_copy_count: int
    partner_copy_count: int
    molecular_system: str
    source_sequence_sha256: tuple[str, str] | None = None


_CONTROL_6RTZ = _ControlDefinition(
    control_key=_CONTROL_KEY,
    crystal_id=_CRYSTAL_ID,
    parent_chain=_PARENT_CHAIN,
    partner_chain=_PARTNER_CHAIN,
    adapter_version=_ADAPTER_VERSION,
    parent_protein_id=_PARENT_PROTEIN_ID,
    parent_copy_count=1,
    partner_copy_count=1,
    molecular_system="HisF/HisH",
)
_CONTROL_3U7Q = _ControlDefinition(
    control_key="A03",
    crystal_id="3U7Q",
    parent_chain="A",
    partner_chain="B",
    adapter_version="3u7q-fixed-two-a-two-b-inputs-v1",
    parent_protein_id="3U7Q_entity_1_Q440E_construct",
    parent_copy_count=2,
    partner_copy_count=2,
    molecular_system="NifD/NifK",
    source_sequence_sha256=(
        "1f3742d53379b781879aabd6f0335aa6e2e994a357d2fccc26a1cff14a34dba9",
        "90d14f01041688fc46b92288b9762c0ede104bcf2ea9d941449a64cff1ac80df",
    ),
)


class HeteromerControlPreparationError(ValueError):
    """The fixed public control cannot be prepared without changing identity."""


@dataclass(frozen=True)
class HeteromerControlPreparationRequest:
    """Inputs for the fixed 6RTZ preparation operation."""

    protocol: Path
    output_directory: Path
    coordinates: Path | None = None
    structure_factors: Path | None = None
    download_missing: bool = False
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


@dataclass(frozen=True)
class HeteromerControlReviewRequest:
    """Inputs for the fixed explicit HisF composition-review checkpoint."""

    preparation_manifest: Path
    parent_result_directory: Path
    output_directory: Path
    progress: bool = True


@dataclass(frozen=True)
class HeteromerControlReviewResult:
    """Review and validated approved-stage directories for the P3 bridge."""

    review_package: Path
    decisions_tsv: Path
    approved_stage: Path


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


def _download_source(resource: M6FrozenResourceSpec, destination: Path) -> Path:
    if destination.exists():
        return _verify_source(
            destination,
            sha256=resource.sha256,
            size=resource.size_bytes,
            label=f"downloaded {resource.role}",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            try:
                with urllib.request.urlopen(resource.url, timeout=120) as response:
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > resource.size_bytes:
                            raise HeteromerControlPreparationError(
                                f"downloaded {resource.role} exceeds frozen size"
                            )
                        handle.write(chunk)
            except (OSError, urllib.error.URLError) as error:
                raise HeteromerControlPreparationError(
                    f"cannot download fixed {resource.role}: {error}"
                ) from error
            handle.flush()
            os.fsync(handle.fileno())
        _verify_source(
            temporary,
            sha256=resource.sha256,
            size=resource.size_bytes,
            label=f"downloaded {resource.role}",
        )
        os.replace(temporary, destination)
        return destination
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _control_spec(protocol_path: Path, definition: _ControlDefinition):
    protocol = load_m6_protocol(protocol_path)
    matches = [
        control
        for control in protocol.assumption_controls
        if control.target_key == definition.control_key
    ]
    if len(matches) != 1:
        raise HeteromerControlPreparationError(
            f"protocol does not uniquely define {definition.control_key}"
        )
    control = matches[0]
    if (
        control.source.pdb_id != definition.crystal_id
        or control.source.pdb_entity_ids != (1, 2)
        or control.asu_distinct_protein_species != 2
        or control.asu_protein_copy_count
        != definition.parent_copy_count + definition.partner_copy_count
        or len(control.proteins) != 2
    ):
        raise HeteromerControlPreparationError(
            f"{definition.control_key} no longer defines the fixed "
            f"{definition.parent_copy_count}A+{definition.partner_copy_count}B control"
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
    if not observed or observed not in full_sequence:
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


def _prepare_heteromer_control(
    request: HeteromerControlPreparationRequest,
    definition: _ControlDefinition,
) -> HeteromerControlPreparationResult:
    """Prepare one protocol-frozen exact-model heteromer control."""

    output = request.output_directory.absolute()
    if output.exists() and any(output.iterdir()):
        raise HeteromerControlPreparationError(
            f"{definition.crystal_id} preparation output is not empty: {output}"
        )
    control = _control_spec(request.protocol, definition)
    if request.download_missing:
        if request.coordinates is not None or request.structure_factors is not None:
            raise HeteromerControlPreparationError(
                "download mode does not accept caller-supplied source paths"
            )
        source_directory = output / "sources"
        coordinates = _download_source(
            control.source.coordinates,
            source_directory / f"{definition.crystal_id}.cif",
        )
        structure_factors = _download_source(
            control.source.structure_factors,
            source_directory / f"{definition.crystal_id}-sf.cif",
        )
    else:
        if request.coordinates is None or request.structure_factors is None:
            raise HeteromerControlPreparationError(
                "supply both source paths or enable fixed download mode"
            )
        coordinates = _verify_source(
            request.coordinates,
            sha256=control.source.coordinates.sha256,
            size=control.source.coordinates.size_bytes,
            label=f"{definition.crystal_id} coordinates",
        )
        structure_factors = _verify_source(
            request.structure_factors,
            sha256=control.source.structure_factors.sha256,
            size=control.source.structure_factors.size_bytes,
            label=f"{definition.crystal_id} structure factors",
        )
    sequences = _entity_sequences(coordinates)
    expected = tuple(control.proteins)
    sequence_relationships: list[dict[str, object]] = []
    for entity_id, protein in zip((1, 2), expected, strict=True):
        sequence = sequences.get(entity_id)
        source_sha256 = (
            hashlib.sha256(sequence.encode("ascii")).hexdigest()
            if sequence is not None
            else None
        )
        expected_source_sha256 = (
            definition.source_sequence_sha256[entity_id - 1]
            if definition.source_sequence_sha256 is not None
            else protein.sequence_sha256
        )
        if (
            sequence is None
            or len(sequence) != protein.sequence_length
            or source_sha256 != expected_source_sha256
        ):
            raise HeteromerControlPreparationError(
                f"{definition.crystal_id} entity {entity_id} differs from frozen "
                "protein "
                f"{protein.protein_id}"
            )
        sequence_relationships.append(
            {
                "entity_id": entity_id,
                "source_construct_sequence_sha256": source_sha256,
                "catalogue_protein_id": protein.protein_id,
                "catalogue_sequence_sha256": protein.sequence_sha256,
                "exact_catalogue_sequence": source_sha256 == protein.sequence_sha256,
            }
        )

    output.mkdir(parents=True, exist_ok=True)
    model_directory = output / "models"
    parent_model = model_directory / "component_A.pdb"
    partner_model = model_directory / "component_B.pdb"
    parent_observed, parent_ranges = _extract_polymer_chain(
        coordinates,
        parent_model,
        chain_name=definition.parent_chain,
        full_sequence=sequences[1],
    )
    _extract_polymer_chain(
        coordinates,
        partner_model,
        chain_name=definition.partner_chain,
        full_sequence=sequences[2],
    )
    mtz_path = output / "derived" / f"{definition.crystal_id}.mtz"
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
            "chain": definition.parent_chain,
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
        raise HeteromerControlPreparationError(
            f"{definition.crystal_id} A model mass is not exact"
        )
    model = ProcessedModelRecord(
        schema_version="1.0",
        model_id=model_id,
        coordinate_id=coordinate_id,
        variant_type="experimental_cleaned_source_chain",
        residue_ranges=parent_ranges,
        processing_tool="gemmi",
        processing_version=getattr(gemmi, "__version__", "unknown"),
        processing_parameters={
            "adapter_version": definition.adapter_version,
            "mapping_id": mapping_id,
            "sequence_identity": 1.0,
            "source_pdb_id": definition.crystal_id,
            "source_chain": definition.parent_chain,
            "observed_residue_count": len(parent_observed),
            "full_sequence_length": len(parent_group.sequence),
        },
        model_mass_da=model_mass.exact_da,
        full_candidate_sequence_group_id=parent_group.sequence_group_id,
        model_sha256=sha256_file(parent_model),
        quality_flags=(f"fixed_{definition.crystal_id.lower()}_exact_parent_control",),
    )
    processed_models = output / "processed_models.jsonl"
    atomic_write_text(processed_models, f"{canonical_json_text(model)}\n")
    model_manifest = output / "model_preparation_manifest.json"
    atomic_write_json(
        model_manifest,
        {
            "schema_version": "1.0",
            "adapter_version": definition.adapter_version,
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
            "crystal_id": definition.crystal_id,
            "sequence_group_id": parent_group.sequence_group_id,
            "model_id": model.model_id,
            "mtz_sha256": sha256_file(mtz_path),
            "copy_count": definition.parent_copy_count,
        },
    )
    matthews_id = content_id(
        "matthews_",
        {
            "crystal_id": definition.crystal_id,
            "sequence_group_id": parent_group.sequence_group_id,
            "copy_count": definition.parent_copy_count,
            "mtz_sha256": sha256_file(mtz_path),
            "prior_backend": PRIOR_BACKEND,
            "copy_range_backend": COPY_RANGE_BACKEND,
        },
    )
    hypothesis = MrHypothesis(
        schema_version="1.0",
        hypothesis_id=hypothesis_id,
        crystal_id=definition.crystal_id,
        sequence_group_id=parent_group.sequence_group_id,
        model_id=model.model_id,
        copy_count_expected=definition.parent_copy_count,
        copy_number_to_search=definition.parent_copy_count,
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
            "control_role": f"fixed_{definition.crystal_id.lower()}_parent_A",
            "matthews_hypothesis_id": matthews_id,
            "matthews_prior_backend": PRIOR_BACKEND,
            "matthews_copy_range_policy": (
                "dynamic_by_asu_sequence_mass_and_solvent_bounds"
            ),
            "matthews_copy_range_complete": False,
            "matthews_copy_range_exemption": "fixed_known_control",
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
                crystal_id=definition.crystal_id,
                mtz=f"derived/{definition.crystal_id}.mtz",
                catalogue_id=control.catalogue_id,
                obs_labels=observation.rendered,
                free_flag_labels=(
                    "FreeR_flag"
                    if mtz.column_with_label("FreeR_flag") is not None
                    else None
                ),
                allow_remote_sequence_submission=False,
                notes=(
                    f"Fixed public {definition.crystal_id} "
                    f"{definition.molecular_system} "
                    f"{definition.parent_copy_count}A+"
                    f"{definition.partner_copy_count}B control"
                ),
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
            "adapter_version": definition.adapter_version,
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
            "adapter_version": definition.adapter_version,
            "preparation_id": preparation_id,
            "created_at": utc_now_iso(),
            "control_key": definition.control_key,
            "crystal_id": definition.crystal_id,
            "composition": {
                "A": definition.parent_copy_count,
                "B": definition.partner_copy_count,
            },
            "parent_sequence_group_id": parent_group.sequence_group_id,
            "partner_sequence_group_id": partner_group.sequence_group_id,
            "parent_protein_id": definition.parent_protein_id,
            "parent_hypothesis_id": hypothesis.hypothesis_id,
            "parent_matthews_hypothesis_id": matthews_id,
            "partner_model_identity_fraction": 1.0,
            "sequence_relationships": sequence_relationships,
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


def prepare_6rtz_heteromer_control(
    request: HeteromerControlPreparationRequest,
) -> HeteromerControlPreparationResult:
    """Prepare fixed exact-model inputs for the 6RTZ ``1A + 1B`` control."""

    return _prepare_heteromer_control(request, _CONTROL_6RTZ)


def prepare_3u7q_heteromer_control(
    request: HeteromerControlPreparationRequest,
) -> HeteromerControlPreparationResult:
    """Prepare fixed exact-model inputs for the 3U7Q ``2A + 2B`` control."""

    return _prepare_heteromer_control(request, _CONTROL_3U7Q)


def _prepared_file(
    preparation_root: Path,
    files: object,
    role: str,
) -> Path:
    if not isinstance(files, dict) or not isinstance(files.get(role), dict):
        raise HeteromerControlPreparationError(
            f"6RTZ preparation lacks required file role: {role}"
        )
    entry = cast(dict[str, object], files[role])
    relative = entry.get("path")
    digest = entry.get("sha256")
    if not isinstance(relative, str) or not isinstance(digest, str):
        raise HeteromerControlPreparationError(
            f"6RTZ preparation file role is invalid: {role}"
        )
    path = (preparation_root / relative).resolve(strict=True)
    if not path.is_file() or not path.is_relative_to(preparation_root):
        raise HeteromerControlPreparationError(
            f"6RTZ preparation file escaped its root: {role}"
        )
    if sha256_file(path) != digest:
        raise HeteromerControlPreparationError(
            f"6RTZ preparation file checksum differs: {role}"
        )
    return path


def _control_pipeline_config() -> PipelineConfig:
    return PipelineConfig.model_validate(
        {
            "schema_version": "1.0",
            "prototype": {
                "asu_model": "single_protein_species_multi_copy",
                "profile": "pilot",
            },
            "catalogue": {
                "min_length_aa": 30,
                "ambiguous_residue_policy": "warn",
                "remove_terminal_stop": True,
            },
            "providers": {
                "pdb_sequence": {"enabled": True, "max_hits": 3},
                "foldseek_prostt5_pdb": {"enabled": True, "max_hits": 3},
                "esm_atlas": {
                    "enabled": False,
                    "max_hits": 0,
                    "requests_per_minute": 10,
                    "max_sequence_length": 1500,
                },
                "afdb_exact": {"enabled": False, "max_hits": 0},
            },
            "matthews": {
                "max_hypotheses_per_candidate": 4,
                "min_solvent_fraction": 0.10,
                "max_solvent_fraction": 0.90,
            },
            "search_limits": {
                "max_structural_hypotheses": 10,
                "max_first_copy_jobs": 10,
            },
            "review": {
                "primary_shortlist_size": 10,
                "extended_shortlist_size": 10,
            },
            "retention": {
                "max_full_artifact_finalists": 10,
                "retain_all_logs": True,
            },
        }
    )


def build_6rtz_control_review(
    request: HeteromerControlReviewRequest,
) -> HeteromerControlReviewResult:
    """Build and approve the fixed HisF parent through normal review adapters."""

    preparation_path = request.preparation_manifest.resolve(strict=True)
    preparation_root = preparation_path.parent
    raw = load_json_document(preparation_path)
    if (
        not isinstance(raw, dict)
        or raw.get("adapter_version") != _ADAPTER_VERSION
        or raw.get("crystal_id") != _CRYSTAL_ID
        or raw.get("composition") != {"A": 1, "B": 1}
    ):
        raise HeteromerControlPreparationError(
            "fixed 6RTZ preparation manifest is invalid"
        )
    output = request.output_directory.absolute()
    if output.exists() or output.is_symlink():
        raise HeteromerControlPreparationError(
            f"6RTZ review output already exists: {output}"
        )
    output.mkdir(parents=True)
    files = raw.get("files")
    hypotheses = _prepared_file(preparation_root, files, "hypotheses")
    sequence_groups = _prepared_file(preparation_root, files, "sequence_groups")
    mtz_path = _prepared_file(preparation_root, files, "mtz")
    hypothesis = MrHypothesis.model_validate_json(
        hypotheses.read_text(encoding="utf-8").strip()
    )
    groups = [
        SequenceGroupRecord.model_validate_json(line)
        for line in sequence_groups.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    parent_group = next(
        (
            group
            for group in groups
            if group.sequence_group_id == hypothesis.sequence_group_id
        ),
        None,
    )
    if parent_group is None or parent_group.molecular_mass_da is None:
        raise HeteromerControlPreparationError(
            "fixed 6RTZ parent sequence group is missing"
        )
    matthews_id = hypothesis.priority_features.get("matthews_hypothesis_id")
    if not isinstance(matthews_id, str):
        raise HeteromerControlPreparationError(
            "fixed 6RTZ parent lacks Matthews provenance"
        )
    mtz = gemmi.read_mtz_file(str(mtz_path))
    if mtz.spacegroup is None:
        raise HeteromerControlPreparationError("fixed 6RTZ MTZ lacks space group")
    asu_volume = mtz.cell.volume / len(mtz.spacegroup.operations())
    coefficient = asu_volume / parent_group.molecular_mass_da
    solvent_fraction = max(0.0, min(1.0, 1.0 - 1.23 / coefficient))
    support = output / "support"
    support.mkdir()
    source_record = SourceProteinRecord(
        schema_version="1.0",
        source_record_id=content_id(
            "source_",
            {
                "catalogue_id": "cat-tmaritima",
                "protein_id": _PARENT_PROTEIN_ID,
                "sequence_group_id": parent_group.sequence_group_id,
            },
        ),
        catalogue_id="cat-tmaritima",
        original_protein_id=_PARENT_PROTEIN_ID,
        original_header=f"{_PARENT_PROTEIN_ID} fixed 6RTZ HisF control",
        description="imidazole glycerol phosphate synthase subunit HisF",
        sequence_group_id=parent_group.sequence_group_id,
        source_annotation_provider="fixed RCSB/RefSeq 6RTZ control",
    )
    source_records = support / "source_records.jsonl"
    atomic_write_text(source_records, f"{canonical_json_text(source_record)}\n")
    matthews = MatthewsHypothesis(
        schema_version="1.0",
        hypothesis_id=matthews_id,
        crystal_id=_CRYSTAL_ID,
        sequence_group_id=parent_group.sequence_group_id,
        copy_count=1,
        sequence_mass_da=parent_group.molecular_mass_da,
        total_mass_da=parent_group.molecular_mass_da,
        v_asu_a3=asu_volume,
        matthews_coefficient=coefficient,
        solvent_fraction=solvent_fraction,
        matthews_prior=prior_score(
            solvent_fraction,
            resolution_high_a=mtz.resolution_high(),
            copy_count=1,
        ),
        prior_backend=PRIOR_BACKEND,
        rank_within_candidate=1,
        retained=True,
        physical_status=PhysicalStatus.PLAUSIBLE,
        sds_page_prior_label="unavailable",
        warnings=("fixed_control_review_support",),
    )
    matthews_path = support / "matthews_hypotheses.jsonl"
    atomic_write_text(matthews_path, f"{canonical_json_text(matthews)}\n")
    config_path = support / "pipeline_config.json"
    atomic_write_json(config_path, _control_pipeline_config().model_dump(mode="json"))
    funnel_manifest = support / "funnel_manifest.json"
    atomic_write_json(
        funnel_manifest,
        {
            "schema_version": "1.0",
            "funnel_id": content_id(
                "funnel_", {"hypothesis_id": hypothesis.hypothesis_id}
            ),
            "adapter_version": "fixed-6rtz-parent-review-v1",
            "selected_hypothesis_count": 1,
            "hypotheses": [{"hypothesis_id": hypothesis.hypothesis_id}],
            "execution_status": ExecutionStatus.COMPLETED_SUCCESS.value,
        },
    )
    parent_result = request.parent_result_directory.resolve(strict=True)
    expected_name = f"first_copy_phaser_{hypothesis.hypothesis_id}"
    if parent_result.name != expected_name or not parent_result.is_dir():
        raise HeteromerControlPreparationError(
            "fixed parent result directory has the wrong workflow identity"
        )
    review_directory = output / "mr_seed_review"
    review = build_mr_seed_review(
        MrSeedReviewRequest(
            hypotheses_jsonl=hypotheses,
            results_jsonl=parent_result / "normalised_mr_result.jsonl",
            result_root=parent_result.parent,
            funnel_manifest=funnel_manifest,
            sequence_groups_jsonl=sequence_groups,
            source_records_jsonl=source_records,
            matthews_hypotheses_jsonl=matthews_path,
            pipeline_config=config_path,
            output_directory=review_directory,
            progress=request.progress,
        )
    )
    review_document = load_json_document(review.manifest_json)
    items = review_document.get("items") if isinstance(review_document, dict) else None
    matches = (
        [
            item
            for item in items
            if isinstance(item, dict)
            and item.get("sequence_group_id") == parent_group.sequence_group_id
            and item.get("inspectable_solution") is True
        ]
        if isinstance(items, list)
        else []
    )
    if len(matches) != 1 or not isinstance(matches[0].get("solution_id"), str):
        raise HeteromerControlPreparationError(
            "fixed HisF review did not yield one inspectable solution"
        )
    decision_buffer = io.StringIO(newline="")
    writer = csv.writer(decision_buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(
        (
            "checkpoint",
            "item_id",
            "decision",
            "reviewer",
            "reviewed_at",
            "comment",
            "override_reason",
        )
    )
    writer.writerow(
        (
            "mr_seed",
            matches[0]["solution_id"],
            "approve",
            "fixed_6rtz_control_policy",
            utc_now_iso(),
            "Predeclared exact HisF parent for the known 6RTZ P3 control",
            "",
        )
    )
    decisions = output / "approved_mr_seeds.tsv"
    atomic_write_text(decisions, decision_buffer.getvalue())
    approved_directory = output / "approved_mr_seed_stage"
    prepare_live_add_copy_stage(
        LiveAddCopyStageRequest(
            review_package=review_directory,
            decisions=decisions,
            hypotheses_jsonl=hypotheses,
            output_directory=approved_directory,
            progress=request.progress,
        )
    )
    return HeteromerControlReviewResult(
        review_package=review_directory,
        decisions_tsv=decisions,
        approved_stage=approved_directory,
    )
