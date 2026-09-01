"""Prepare the fixed 9ECN ``2A+2B+2C`` Phase III validation input.

The preparation reads the checksum-frozen A04 entry from the M6 protocol and
never accepts an operator-selected PDB, composition, chain, sequence, or copy
count.  It extracts one exact experimental model for McrA, McrB, and McrG,
converts the deposited structure factors to MTZ, and writes one joint two-copy
McrA first-search hypothesis plus a complete three-component model registry.

9ECN McrG has a deposited 73-residue N-terminal expression tag.  The mmCIF
reference alignment binds deposited entity positions 74--321 to the exact
248-residue catalogue protein; only observed residues from that aligned region
are present in chain E and are retained in the component-C model.  Source and
catalogue sequence identities are both recorded.  No Phaser command is built or
executed here, and no scientific composition claim is made.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import gemmi

from genome_to_diffraction.benchmarks.heteromer_control import (
    HeteromerControlPreparationError,
    HeteromerControlPreparationRequest,
    _convert_structure_factors,
    _download_source,
    _verify_source,
)
from genome_to_diffraction.benchmarks.m6_protocol import (
    M6AssumptionControlSpec,
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

_TARGET_KEY = "A04"
_CRYSTAL_ID = "9ECN"
_ADAPTER_VERSION = "9ecn-fixed-two-a-two-b-two-c-inputs-v1"
_CATALOGUE_ID = "cat-macetivorans"
_SOURCE_ENTITY_3_SHA256 = (
    "b6705cd2889ac9e77b5f632b72bab42cab2a1238e28db2dd207b785f0149906f"
)
_SOURCE_ENTITY_3_LENGTH = 321
_COMPONENTS = (
    ("A", 1, ("A", "B"), "A", "WP_011024419.1", 570),
    ("B", 2, ("C", "D"), "C", "WP_011024423.1", 434),
    ("C", 3, ("E", "F"), "E", "WP_011024420.1", 248),
)
_ALIGNMENTS = {
    "A": (1, 570, 1, 570),
    "B": (1, 570, 1, 570),
    "C": (1, 434, 1, 434),
    "D": (1, 434, 1, 434),
    "E": (74, 321, 1, 248),
    "F": (74, 321, 1, 248),
}
_MODIFIED_RESIDUES = {"DYA": "D", "MGN": "Q"}


@dataclass(frozen=True)
class Phase3ControlPreparationResult:
    """Stable files required by the fixed 9ECN validation ladder."""

    preparation_manifest: Path
    crystal_manifest: Path
    sequence_groups_jsonl: Path
    processed_models_jsonl: Path
    model_preparation_manifest: Path
    hypotheses_jsonl: Path
    mtz: Path
    component_models: tuple[Path, Path, Path]
    component_sequence_group_ids: tuple[str, str, str]
    parent_hypothesis_id: str


@dataclass(frozen=True)
class _SequenceEvidence:
    source_sequences: dict[int, str]
    catalogue_sequences: dict[int, str]
    accessions: dict[int, str]


def _control_spec(protocol_path: Path) -> M6AssumptionControlSpec:
    protocol = load_m6_protocol(protocol_path)
    matches = [
        control
        for control in protocol.assumption_controls
        if control.target_key == _TARGET_KEY
    ]
    if len(matches) != 1:
        raise HeteromerControlPreparationError(
            "protocol does not uniquely define fixed 9ECN"
        )
    control = matches[0]
    expected_proteins = tuple(
        (protein_id, length) for _, _, _, _, protein_id, length in _COMPONENTS
    )
    observed_proteins = tuple(
        (protein.protein_id, protein.sequence_length) for protein in control.proteins
    )
    if (
        control.source.pdb_id != _CRYSTAL_ID
        or control.source.pdb_entity_ids != (1, 2, 3)
        or control.catalogue_id != _CATALOGUE_ID
        or control.asu_distinct_protein_species != 3
        or control.asu_protein_copy_count != 6
        or observed_proteins != expected_proteins
    ):
        raise HeteromerControlPreparationError(
            "A04 no longer defines fixed 9ECN 2A+2B+2C"
        )
    return control


def _sequences(
    coordinates: Path, control: M6AssumptionControlSpec
) -> _SequenceEvidence:
    try:
        block = gemmi.cif.read_file(str(coordinates)).sole_block()
        source_sequences = {
            int(str(row[0])): canonical_sequence(str(row[1]).strip().strip(";"))
            for row in block.find(
                [
                    "_entity_poly.entity_id",
                    "_entity_poly.pdbx_seq_one_letter_code_can",
                ]
            )
        }
        reference_rows = list(
            block.find(
                [
                    "_struct_ref.entity_id",
                    "_struct_ref.pdbx_db_accession",
                    "_struct_ref.pdbx_seq_one_letter_code",
                ]
            )
        )
        catalogue_sequences = {
            int(str(row[0])): canonical_sequence(str(row[2]).strip().strip(";"))
            for row in reference_rows
        }
        accessions = {int(str(row[0])): str(row[1]) for row in reference_rows}
        asymmetry = {
            str(row[0]): int(str(row[1]))
            for row in block.find(["_struct_asym.id", "_struct_asym.entity_id"])
            if str(row[0]) in _ALIGNMENTS
        }
        alignments = {
            str(row[0]): tuple(int(str(row[index])) for index in range(1, 5))
            for row in block.find(
                [
                    "_struct_ref_seq.pdbx_strand_id",
                    "_struct_ref_seq.seq_align_beg",
                    "_struct_ref_seq.seq_align_end",
                    "_struct_ref_seq.db_align_beg",
                    "_struct_ref_seq.db_align_end",
                ]
            )
        }
    except (RuntimeError, TypeError, ValueError) as error:
        raise HeteromerControlPreparationError(
            f"cannot parse fixed 9ECN sequence evidence: {error}"
        ) from error

    expected_asymmetry = {
        chain: entity_id
        for _, entity_id, chains, _, _, _ in _COMPONENTS
        for chain in chains
    }
    if asymmetry != expected_asymmetry or alignments != _ALIGNMENTS:
        raise HeteromerControlPreparationError(
            "9ECN chain/entity/reference alignment changed"
        )
    proteins = control.proteins
    if set(source_sequences) != {1, 2, 3} or set(catalogue_sequences) != {1, 2, 3}:
        raise HeteromerControlPreparationError(
            "9ECN does not contain exactly three protein sequences"
        )
    for entity_id, protein in enumerate(proteins, start=1):
        catalogue_sequence = catalogue_sequences[entity_id]
        catalogue_digest = hashlib.sha256(
            catalogue_sequence.encode("ascii")
        ).hexdigest()
        if (
            len(catalogue_sequence) != protein.sequence_length
            or catalogue_digest != protein.sequence_sha256
        ):
            raise HeteromerControlPreparationError(
                f"9ECN entity {entity_id} catalogue sequence changed"
            )
    for entity_id in (1, 2):
        if source_sequences[entity_id] != catalogue_sequences[entity_id]:
            raise HeteromerControlPreparationError(
                f"9ECN entity {entity_id} is no longer an exact construct"
            )
    if (
        len(source_sequences[3]) != _SOURCE_ENTITY_3_LENGTH
        or hashlib.sha256(source_sequences[3].encode("ascii")).hexdigest()
        != _SOURCE_ENTITY_3_SHA256
        or not source_sequences[3].endswith(catalogue_sequences[3])
    ):
        raise HeteromerControlPreparationError(
            "9ECN McrG expression-tag relationship changed"
        )
    return _SequenceEvidence(source_sequences, catalogue_sequences, accessions)


def _sequence_group(sequence: str) -> SequenceGroupRecord:
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    mass = assess_mass(sequence)
    if mass.exact_da is None:
        raise HeteromerControlPreparationError("9ECN sequence mass is not exact")
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


def _extract_component_chain(
    coordinates: Path,
    output: Path,
    *,
    chain_name: str,
    catalogue_sequence: str,
) -> tuple[str, tuple[str, ...]]:
    """Retain observed aligned residues while validating modified monomers."""

    try:
        structure = gemmi.read_structure(str(coordinates))
        selected = gemmi.Selection(f"/1/{chain_name};polymer").copy_structure_selection(
            structure
        )
    except (RuntimeError, ValueError) as error:
        raise HeteromerControlPreparationError(
            f"cannot extract 9ECN chain {chain_name}: {error}"
        ) from error
    if len(selected) != 1 or len(selected[0]) != 1:
        raise HeteromerControlPreparationError(
            f"9ECN chain {chain_name} did not resolve exactly once"
        )
    polymer = list(selected[0][0].get_polymer())
    if not polymer:
        raise HeteromerControlPreparationError(
            f"9ECN chain {chain_name} contains no observed polymer"
        )
    source_start, source_end, catalogue_start, catalogue_end = _ALIGNMENTS[chain_name]
    observed: list[str] = []
    previous_label = 0
    for residue in polymer:
        label_seq = residue.label_seq
        if (
            label_seq is None
            or label_seq <= previous_label
            or label_seq < source_start
            or label_seq > source_end
        ):
            raise HeteromerControlPreparationError(
                f"9ECN chain {chain_name} has invalid aligned residue numbering"
            )
        catalogue_index = label_seq - source_start + catalogue_start - 1
        if catalogue_index < 0 or catalogue_index >= len(catalogue_sequence):
            raise HeteromerControlPreparationError(
                f"9ECN chain {chain_name} escaped its catalogue alignment"
            )
        expected = catalogue_sequence[catalogue_index]
        actual = _MODIFIED_RESIDUES.get(residue.name)
        if actual is None:
            actual = gemmi.find_tabulated_residue(residue.name).one_letter_code.upper()
        if actual != expected:
            raise HeteromerControlPreparationError(
                f"9ECN chain {chain_name} residue {label_seq} differs from catalogue"
            )
        observed.append(expected)
        previous_label = label_seq
    if catalogue_end != len(catalogue_sequence):
        raise HeteromerControlPreparationError(
            f"9ECN chain {chain_name} catalogue alignment is incomplete"
        )
    selected.remove_hydrogens()
    atomic_write_bytes(output, selected.make_pdb_string().encode("ascii"))
    first, last = polymer[0].seqid, polymer[-1].seqid
    return "".join(observed), (f"{chain_name}:{first}-{last}",)


def prepare_9ecn_phase3_control(
    request: HeteromerControlPreparationRequest,
) -> Phase3ControlPreparationResult:
    """Prepare the fixed 9ECN three-component control without running Phaser."""

    output = request.output_directory.absolute()
    if output.exists() and any(output.iterdir()):
        raise HeteromerControlPreparationError(
            f"9ECN preparation output is not empty: {output}"
        )
    control = _control_spec(request.protocol)
    if request.download_missing:
        if request.coordinates is not None or request.structure_factors is not None:
            raise HeteromerControlPreparationError(
                "download mode does not accept caller-supplied source paths"
            )
        coordinates = _download_source(
            control.source.coordinates, output / "sources/9ECN.cif"
        )
        structure_factors = _download_source(
            control.source.structure_factors, output / "sources/9ECN-sf.cif"
        )
    else:
        if request.coordinates is None or request.structure_factors is None:
            raise HeteromerControlPreparationError(
                "supply both 9ECN source paths or enable fixed download mode"
            )
        coordinates = _verify_source(
            request.coordinates,
            sha256=control.source.coordinates.sha256,
            size=control.source.coordinates.size_bytes,
            label="9ECN coordinates",
        )
        structure_factors = _verify_source(
            request.structure_factors,
            sha256=control.source.structure_factors.sha256,
            size=control.source.structure_factors.size_bytes,
            label="9ECN structure factors",
        )

    sequence_evidence = _sequences(coordinates, control)
    output.mkdir(parents=True, exist_ok=True)
    component_models: list[Path] = []
    groups: list[SequenceGroupRecord] = []
    models: list[ProcessedModelRecord] = []
    model_entries: list[dict[str, object]] = []
    component_rows: list[dict[str, object]] = []
    for label, entity_id, chains, representative, protein_id, _ in _COMPONENTS:
        sequence = sequence_evidence.catalogue_sequences[entity_id]
        group = _sequence_group(sequence)
        model_path = output / f"models/component_{label}.pdb"
        observed, ranges = _extract_component_chain(
            coordinates,
            model_path,
            chain_name=representative,
            catalogue_sequence=sequence,
        )
        mapping_id = content_id(
            "coordmap_",
            {
                "source_sha256": control.source.coordinates.sha256,
                "chain": representative,
                "sequence_sha256": group.sha256,
            },
        )
        coordinate_id = content_id(
            "coord_",
            {"mapping_id": mapping_id, "model_sha256": sha256_file(model_path)},
        )
        model_id = content_id(
            "model_",
            {
                "coordinate_id": coordinate_id,
                "variant": "experimental_cleaned_source_chain",
                "model_sha256": sha256_file(model_path),
            },
        )
        model_mass = assess_mass(observed)
        if model_mass.exact_da is None:
            raise HeteromerControlPreparationError(
                f"9ECN component {label} model mass is not exact"
            )
        model = ProcessedModelRecord(
            schema_version="1.0",
            model_id=model_id,
            coordinate_id=coordinate_id,
            variant_type="experimental_cleaned_source_chain",
            residue_ranges=ranges,
            processing_tool="gemmi",
            processing_version=getattr(gemmi, "__version__", "unknown"),
            processing_parameters={
                "adapter_version": _ADAPTER_VERSION,
                "mapping_id": mapping_id,
                "sequence_identity": 1.0,
                "source_pdb_id": _CRYSTAL_ID,
                "source_chain": representative,
                "source_entity_id": entity_id,
                "observed_residue_count": len(observed),
                "full_sequence_length": len(sequence),
                "construct_has_expression_tag": entity_id == 3,
            },
            model_mass_da=model_mass.exact_da,
            full_candidate_sequence_group_id=group.sequence_group_id,
            model_sha256=sha256_file(model_path),
            quality_flags=(f"fixed_9ecn_exact_component_{label.lower()}",),
        )
        groups.append(group)
        models.append(model)
        component_models.append(model_path)
        model_entries.append(
            {
                "component_label": label,
                "model_id": model_id,
                "model_path": f"models/component_{label}.pdb",
                "model_sha256": model.model_sha256,
                "mapping_id": mapping_id,
            }
        )
        component_rows.append(
            {
                "label": label,
                "entity_id": entity_id,
                "asu_chains": list(chains),
                "representative_model_chain": representative,
                "requested_copy_count": 2,
                "protein_id": protein_id,
                "sequence_group_id": group.sequence_group_id,
                "catalogue_sequence_sha256": group.sha256,
                "source_construct_sequence_sha256": hashlib.sha256(
                    sequence_evidence.source_sequences[entity_id].encode("ascii")
                ).hexdigest(),
                "reference_accession": sequence_evidence.accessions[entity_id],
                "model_id": model_id,
                "model_sha256": model.model_sha256,
            }
        )

    sequence_groups = output / "sequence_groups.jsonl"
    atomic_write_text(
        sequence_groups,
        "".join(f"{canonical_json_text(group)}\n" for group in groups),
    )
    processed_models = output / "processed_models.jsonl"
    atomic_write_text(
        processed_models,
        "".join(f"{canonical_json_text(model)}\n" for model in models),
    )
    model_manifest = output / "model_preparation_manifest.json"
    atomic_write_json(
        model_manifest,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "entries": model_entries,
        },
    )

    mtz_path = output / "derived/9ECN.mtz"
    mtz = _convert_structure_factors(structure_factors, mtz_path)
    observation, _, _ = select_observations(mtz, None)
    if observation is None or mtz.spacegroup is None:
        raise HeteromerControlPreparationError("converted 9ECN MTZ is incomplete")
    parent = groups[0]
    hypothesis_id = content_id(
        "mrhyp_",
        {
            "crystal_id": _CRYSTAL_ID,
            "sequence_group_id": parent.sequence_group_id,
            "model_id": models[0].model_id,
            "mtz_sha256": sha256_file(mtz_path),
            "copy_count": 2,
        },
    )
    hypothesis = MrHypothesis(
        schema_version="1.0",
        hypothesis_id=hypothesis_id,
        crystal_id=_CRYSTAL_ID,
        sequence_group_id=parent.sequence_group_id,
        model_id=models[0].model_id,
        copy_count_expected=2,
        copy_number_to_search=2,
        fixed_solution_id=None,
        space_group=mtz.spacegroup.hm,
        obs_labels=observation.rendered,
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=PrototypeProfile.PILOT,
        priority_features={
            "exact_sequence_mapping": True,
            "coordinate_mapping_id": str(model_entries[0]["mapping_id"]),
            "candidate_source_sequence_identity": 1.0,
            "structural_source_class": "experimental",
            "control_role": "fixed_9ecn_parent_A",
        },
        status=MrHypothesisStatus.QUEUED,
    )
    hypotheses = output / "mr_hypotheses.jsonl"
    atomic_write_text(hypotheses, f"{canonical_json_text(hypothesis)}\n")
    crystal_manifest = output / "crystals.json"
    atomic_write_json(
        crystal_manifest,
        CrystalManifest(
            schema_version="1.0",
            crystals=(
                CrystalEntry(
                    crystal_id=_CRYSTAL_ID,
                    mtz="derived/9ECN.mtz",
                    catalogue_id=_CATALOGUE_ID,
                    obs_labels=observation.rendered,
                    free_flag_labels=(
                        "FreeR_flag"
                        if mtz.column_with_label("FreeR_flag") is not None
                        else None
                    ),
                    allow_remote_sequence_submission=False,
                    notes="Fixed public 9ECN McrA/McrB/McrG 2A+2B+2C control",
                ),
            ),
        ).model_dump(mode="json"),
    )

    files = {
        "crystal_manifest": crystal_manifest,
        "sequence_groups": sequence_groups,
        "processed_models": processed_models,
        "model_preparation_manifest": model_manifest,
        "hypotheses": hypotheses,
        "mtz": mtz_path,
        "component_A_model": component_models[0],
        "component_B_model": component_models[1],
        "component_C_model": component_models[2],
    }
    preparation_manifest = output / "preparation_manifest.json"
    preparation_id = content_id(
        "phase3controlprep_",
        {
            "adapter_version": _ADAPTER_VERSION,
            "source_coordinates_sha256": control.source.coordinates.sha256,
            "source_structure_factors_sha256": control.source.structure_factors.sha256,
            "files": {role: sha256_file(path) for role, path in files.items()},
        },
    )
    atomic_write_json(
        preparation_manifest,
        {
            "schema_version": "2.0",
            "adapter_version": _ADAPTER_VERSION,
            "preparation_id": preparation_id,
            "created_at": utc_now_iso(),
            "control_key": _TARGET_KEY,
            "crystal_id": _CRYSTAL_ID,
            "composition": {"A": 2, "B": 2, "C": 2},
            "components": component_rows,
            "parent_hypothesis_id": hypothesis_id,
            "source": {
                "coordinates_sha256": control.source.coordinates.sha256,
                "structure_factors_sha256": control.source.structure_factors.sha256,
            },
            "claim_boundary": "known_control_input_only_no_scientific_result",
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
    return Phase3ControlPreparationResult(
        preparation_manifest=preparation_manifest,
        crystal_manifest=crystal_manifest,
        sequence_groups_jsonl=sequence_groups,
        processed_models_jsonl=processed_models,
        model_preparation_manifest=model_manifest,
        hypotheses_jsonl=hypotheses,
        mtz=mtz_path,
        component_models=cast(tuple[Path, Path, Path], tuple(component_models)),
        component_sequence_group_ids=cast(
            tuple[str, str, str], tuple(group.sequence_group_id for group in groups)
        ),
        parent_hypothesis_id=hypothesis_id,
    )


__all__ = ["Phase3ControlPreparationResult", "prepare_9ecn_phase3_control"]
