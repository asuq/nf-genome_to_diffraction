"""Build a fixed positive/negative first-copy molecular-replacement control pair.

The positive uses the checksum-frozen 8OOX diffraction data and exact 8OOW
model.  The deliberate negative uses the independently qualified cached 1UBQ
ubiquitin chain against the same target composition and diffraction data.  The
bundle feeds the production first-copy Phaser adapter and records raw evidence;
it does not calibrate a general classifier or validate a complete ASU.

Inputs are the tracked pair/specification, one prepared public control, the
qualified database manifest, Task 05 sequence groups and MTZ preflight.  Outputs
are a relocatable model registry, two typed hypotheses, and an immutable control
manifest.  Missing, changed, ambiguous, or unsafe inputs fail before execution.
The cache key is the canonical identity of all input checksums and control
roles.  Unit tests cover positive construction, the unrelated-control policy,
checksum drift, and unsafe database paths; real Phenix execution belongs to the
scheduled ``p2-control`` profile.
"""

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, cast

import gemmi
import yaml
from pydantic import Field, JsonValue, ValidationError, model_validator
from tqdm import tqdm

from genome_to_diffraction import __version__
from genome_to_diffraction.catalogue.mass import assess_mass
from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.mr.policy import SCORE_GATE_LLG, SCORE_GATE_TFZ
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    OperatorIdentifier,
    PositiveFloat,
    PositiveInt,
    Sha256Hex,
)
from genome_to_diffraction.schemas.manifests import DatabaseManifest, PrototypeProfile
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    MtzPreflightRecord,
    PreflightDecision,
    ProcessedModelRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.status import InputContractError
from genome_to_diffraction.time import utc_now_iso

from .public_control import PublicControlSpec, load_public_control_spec

_LOGGER = logging.getLogger("genome_to_diffraction.benchmarks.mr_controls")
_ADAPTER_VERSION = "public-first-copy-control-pair-v1"
_NEGATIVE_VARIANT = "control_unrelated_cleaned_source_chain"


class MrControlInputError(InputContractError):
    """A frozen control input or relationship failed validation."""


class NegativeControlSpec(ContractModel):
    """One independently anchored model expected not to solve the control MTZ."""

    pdb_id: str = Field(pattern=r"^[0-9A-Z]{4}$")
    seqres_token: NonEmptyString
    entity_id: NonEmptyString
    coordinate_sha256: Sha256Hex
    source_sequence_sha256: Sha256Hex
    source_sequence_length: PositiveInt
    phaser_identity_percent: PositiveFloat = Field(le=5.0)
    expected_outcome: Literal["completed_no_hit"]
    relationship_to_target: Literal["deliberately unrelated ubiquitin negative control"]


class ControlScoreGate(ContractModel):
    """Frozen provisional score policy under test."""

    llg_greater_than: float
    tfz_greater_than: float
    combination: Literal["or"]

    @model_validator(mode="after")
    def _current_policy(self) -> ControlScoreGate:
        if self.llg_greater_than != SCORE_GATE_LLG:
            raise ValueError("control pair requires strict LLG > 50")
        if self.tfz_greater_than != SCORE_GATE_TFZ:
            raise ValueError("control pair requires strict TFZ > 5")
        return self


class FirstCopyControlPairSpec(ContractModel):
    """Tracked scientific policy for one same-MTZ positive/negative pair."""

    schema_version: Literal["1.0"]
    control_pair_id: OperatorIdentifier
    positive_control_specification: str = Field(
        pattern=r"^[0-9A-Za-z][0-9A-Za-z._-]*\.yaml$"
    )
    positive_model_id: OperatorIdentifier
    positive_expected_outcome: Literal["completed_hit"]
    negative_control: NegativeControlSpec
    score_gate: ControlScoreGate
    limitations: tuple[NonEmptyString, ...] = Field(min_length=1)


@dataclass(frozen=True)
class MrControlBundleRequest:
    """Immutable inputs for building a two-hypothesis control bundle."""

    specification: Path
    public_control_preparation: Path
    database_manifest: Path
    sequence_groups_jsonl: Path
    preflight_jsonl: Path
    output_directory: Path
    progress: bool = True


@dataclass(frozen=True)
class MrControlBundleOutput:
    """Relocatable model/hypothesis bundle consumed by Nextflow."""

    control_pair_id: str
    manifest_json: Path
    processed_models_jsonl: Path
    model_preparation_manifest: Path
    hypotheses_jsonl: Path
    hypothesis_directory: Path


def load_first_copy_control_pair(path: Path) -> FirstCopyControlPairSpec:
    """Load and validate one tracked first-copy control-pair specification."""

    resolved = path.resolve(strict=True)
    try:
        document = yaml.safe_load(resolved.read_text(encoding="utf-8"))
        return FirstCopyControlPairSpec.model_validate(document)
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise MrControlInputError(
            f"invalid first-copy control-pair specification {resolved}: {error}"
        ) from error


def _read_json(path: Path, *, label: str) -> tuple[Path, dict[str, object]]:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_file():
        raise MrControlInputError(f"{label} is not a regular file: {path}")
    try:
        value: object = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MrControlInputError(f"cannot read {label}: {resolved}") from error
    if not isinstance(value, dict):
        raise MrControlInputError(f"{label} must be a JSON object: {resolved}")
    return resolved, cast(dict[str, object], value)


def _read_jsonl[T: ContractModel](
    path: Path, model: type[T], *, label: str, progress: bool
) -> tuple[T, ...]:
    resolved = path.resolve(strict=True)
    records: list[T] = []
    with resolved.open(encoding="utf-8") as handle:
        iterator = tqdm(
            enumerate(handle, start=1),
            desc=f"Validate {label}",
            unit="record",
            disable=not progress,
        )
        for line_number, line in iterator:
            if not line.strip():
                raise MrControlInputError(
                    f"blank {label} record at line {line_number}: {resolved}"
                )
            try:
                records.append(model.model_validate_json(line))
            except (ValidationError, TypeError, ValueError) as error:
                raise MrControlInputError(
                    f"invalid {label} record at line {line_number}: {resolved}"
                ) from error
    if not records:
        raise MrControlInputError(f"{label} input is empty: {resolved}")
    return tuple(records)


def _one[T](values: tuple[T, ...], predicate: Callable[[T], bool], *, label: str) -> T:
    matches = [value for value in values if predicate(value)]
    if len(matches) != 1:
        raise MrControlInputError(
            f"expected exactly one {label}; observed {len(matches)}"
        )
    return matches[0]


def _verified_path(
    text: object,
    digest: object,
    *,
    allowed_root: Path,
    expected_digest: str,
    label: str,
    progress: bool,
) -> Path:
    if not isinstance(text, str) or not isinstance(digest, str):
        raise MrControlInputError(f"{label} path/checksum is missing")
    candidate = Path(text)
    resolved = candidate.resolve(strict=True)
    if (
        candidate.is_symlink()
        or not resolved.is_file()
        or not resolved.is_relative_to(allowed_root)
    ):
        raise MrControlInputError(f"{label} escaped its frozen preparation root")
    if digest != expected_digest:
        raise MrControlInputError(f"{label} manifest/specification checksum differs")
    actual = sha256_file(
        resolved,
        progress=progress,
        description=f"Verify {label}",
        logger=_LOGGER,
    )
    if actual != expected_digest:
        raise MrControlInputError(f"{label} file checksum differs")
    return resolved


def _database_negative_coordinate(
    manifest: DatabaseManifest,
    negative: NegativeControlSpec,
    *,
    progress: bool,
) -> Path:
    cache_resources = [
        resource
        for resource in manifest.resources
        if resource.name == "coordinate_cache" and resource.status == "ready"
    ]
    if len(cache_resources) != 1:
        raise MrControlInputError("database manifest lacks one ready coordinate cache")
    cache = cache_resources[0]
    qualification = cache.parameters.get("qualification")
    if not isinstance(qualification, dict):
        raise MrControlInputError("coordinate cache lacks qualification evidence")
    expected = {
        "provider": "pdb",
        "source_id": negative.pdb_id.lower(),
        "object_sha256": negative.coordinate_sha256,
    }
    if any(qualification.get(key) != value for key, value in expected.items()):
        raise MrControlInputError("coordinate cache does not bind the frozen negative")
    relative_text = qualification.get("object_relative_path")
    if not isinstance(relative_text, str):
        raise MrControlInputError("coordinate cache object path is missing")
    relative = PurePosixPath(relative_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise MrControlInputError("coordinate cache object path is unsafe")
    root = Path(cache.root_path).resolve(strict=True)
    coordinate = (root / Path(*relative.parts)).resolve(strict=True)
    if not coordinate.is_file() or not coordinate.is_relative_to(root):
        raise MrControlInputError("negative coordinate escaped its database root")
    actual = sha256_file(
        coordinate,
        progress=progress,
        description="Verify negative control coordinate",
        logger=_LOGGER,
    )
    if actual != negative.coordinate_sha256:
        raise MrControlInputError("negative coordinate checksum differs")

    mapping_evidence: dict[str, JsonValue] | None = None
    for resource in manifest.resources:
        if resource.name != "pdb_foldseek":
            continue
        qualification_value = resource.parameters.get("qualification")
        if isinstance(qualification_value, dict):
            candidate = qualification_value.get("coordinate_mapping")
            if isinstance(candidate, dict):
                mapping_evidence = candidate
    if mapping_evidence is None:
        raise MrControlInputError("database manifest lacks fixed 1UBQ mapping evidence")
    required_mapping: dict[str, JsonValue] = {
        "entry_id": negative.pdb_id,
        "seqres_token": negative.seqres_token,
        "entity_id": negative.entity_id,
        "sequence_length": negative.source_sequence_length,
        "sequence_sha256": negative.source_sequence_sha256,
    }
    if any(
        mapping_evidence.get(key) != value for key, value in required_mapping.items()
    ):
        raise MrControlInputError("database 1UBQ mapping evidence differs from policy")
    return coordinate


def _clean_polymer_chain(
    source: Path, *, chain_name: str, expected_sequence_sha256: str
) -> tuple[bytes, str, tuple[str, ...], int]:
    try:
        structure = gemmi.read_structure(str(source))
        structure.setup_entities()
    except (OSError, RuntimeError, ValueError) as error:
        raise MrControlInputError(
            f"cannot parse control coordinate: {source}"
        ) from error
    if len(structure) != 1:
        raise MrControlInputError(
            "control coordinate must contain one structural model"
        )
    chains = [chain for chain in structure[0] if chain.name == chain_name]
    if len(chains) != 1:
        raise MrControlInputError("control chain did not resolve exactly once")
    polymer = list(chains[0].get_polymer())
    if not polymer:
        raise MrControlInputError("control chain has no observed polymer residues")
    sequence = "".join(
        gemmi.find_tabulated_residue(residue.name).one_letter_code.upper()
        for residue in polymer
    )
    if any(letter in {" ", "-", "?", "X"} for letter in sequence):
        raise MrControlInputError("control chain has an unsupported observed residue")
    if hashlib.sha256(sequence.encode("ascii")).hexdigest() != expected_sequence_sha256:
        raise MrControlInputError(
            "control chain sequence differs from its fixed anchor"
        )
    selected = gemmi.Selection(f"/1/{chain_name};polymer").copy_structure_selection(
        structure
    )
    if len(selected) != 1 or len(selected[0]) != 1:
        raise MrControlInputError("control selection did not yield one polymer chain")
    selected.remove_hydrogens()
    selected[0][0].name = "A"
    payload = selected.make_pdb_string().encode("ascii")
    first = polymer[0].seqid
    last = polymer[-1].seqid
    ranges = (f"{chain_name}:{first}-{last}",)
    atom_count = sum(len(residue) for residue in selected[0][0].get_polymer())
    return payload, sequence, ranges, atom_count


def _model_record(
    *,
    role: Literal["known_positive", "deliberate_unrelated_negative"],
    coordinate_id: str,
    model_id: str,
    sequence_group_id: str,
    model_sha256: str,
    observed_sequence: str,
    residue_ranges: tuple[str, ...],
    mapping_id: str | None,
    identity_fraction: float | None,
    negative_identity_percent: float | None,
    atom_count: int,
) -> ProcessedModelRecord:
    mass = assess_mass(observed_sequence)
    if mass.exact_da is None:
        raise MrControlInputError("control model lacks an exact observed-sequence mass")
    parameters: dict[str, JsonValue] = {
        "adapter_version": _ADAPTER_VERSION,
        "control_role": role,
        "observed_residue_count": len(observed_sequence),
        "atom_count": atom_count,
    }
    variant = "experimental_cleaned_source_chain"
    flags = [f"control_role_{role}"]
    if role == "known_positive":
        assert mapping_id is not None and identity_fraction is not None
        parameters.update(
            {"mapping_id": mapping_id, "sequence_identity": identity_fraction}
        )
    else:
        assert negative_identity_percent is not None
        variant = _NEGATIVE_VARIANT
        parameters.update(
            {
                "phaser_identity_percent": negative_identity_percent,
                "relationship_to_target": "deliberately_unrelated",
                "identity_interpretation": "error_model_input_not_sequence_homology",
            }
        )
        flags.extend(("deliberately_unrelated", "negative_control_only"))
    return ProcessedModelRecord(
        schema_version="1.0",
        model_id=model_id,
        coordinate_id=coordinate_id,
        variant_type=variant,
        residue_ranges=residue_ranges,
        processing_tool="gemmi",
        processing_version=str(gemmi.__version__),
        processing_parameters=parameters,
        model_mass_da=mass.exact_da,
        full_candidate_sequence_group_id=sequence_group_id,
        model_sha256=model_sha256,
        quality_flags=tuple(flags),
    )


def build_mr_control_bundle(
    request: MrControlBundleRequest,
) -> MrControlBundleOutput:
    """Build the exact-model positive and unrelated-model negative bundle."""

    pair_path = request.specification.resolve(strict=True)
    pair = load_first_copy_control_pair(pair_path)
    positive_spec_path = (
        pair_path.parent / pair.positive_control_specification
    ).resolve(strict=True)
    if not positive_spec_path.is_relative_to(pair_path.parent):
        raise MrControlInputError("positive-control specification escaped its root")
    positive_spec: PublicControlSpec = load_public_control_spec(positive_spec_path)
    positive_model_spec = _one(
        positive_spec.mr_models,
        lambda item: item.model_id == pair.positive_model_id,
        label="declared positive model",
    )
    if positive_model_spec.leakage_class != "operational_exact":
        raise MrControlInputError("positive control model is not the exact model")

    preparation_path, preparation = _read_json(
        request.public_control_preparation, label="public-control preparation manifest"
    )
    preparation_root = preparation_path.parent.parent.resolve(strict=True)
    if preparation.get("control_id") != positive_spec.control_id:
        raise MrControlInputError("prepared and tracked positive-control IDs differ")
    derived = preparation.get("derived")
    if not isinstance(derived, dict):
        raise MrControlInputError("public-control preparation lacks derived files")
    positive_entry = derived.get("exact_mr_model")
    if not isinstance(positive_entry, dict):
        raise MrControlInputError("public-control preparation lacks the exact model")
    positive_path = _verified_path(
        positive_entry.get("path"),
        positive_entry.get("sha256"),
        allowed_root=preparation_root,
        expected_digest=positive_model_spec.expected_model_sha256,
        label="positive MR model",
        progress=request.progress,
    )

    database_path = request.database_manifest.resolve(strict=True)
    try:
        database = DatabaseManifest.model_validate_json(
            database_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise MrControlInputError(
            f"invalid database manifest: {database_path}"
        ) from error
    negative_coordinate = _database_negative_coordinate(
        database, pair.negative_control, progress=request.progress
    )

    groups = _read_jsonl(
        request.sequence_groups_jsonl,
        SequenceGroupRecord,
        label="sequence groups",
        progress=request.progress,
    )
    group = _one(
        groups,
        lambda item: item.sha256 == positive_spec.target_sequence_sha256,
        label="public-control target sequence group",
    )
    preflights = _read_jsonl(
        request.preflight_jsonl,
        MtzPreflightRecord,
        label="MTZ preflights",
        progress=request.progress,
    )
    preflight = _one(
        preflights,
        lambda item: item.crystal_id == positive_spec.control_id,
        label="public-control MTZ preflight",
    )
    if (
        preflight.decision is PreflightDecision.FAIL
        or preflight.selected_observation_labels is None
    ):
        raise MrControlInputError("public-control preflight is not MR-eligible")

    output = request.output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        raise MrControlInputError(f"control-bundle output is not empty: {output}")
    model_root = output / "models"
    hypothesis_root = output / "hypotheses"
    model_root.mkdir(parents=True)
    hypothesis_root.mkdir()

    positive_payload = positive_path.read_bytes()
    positive_model_path = model_root / "positive_exact.pdb"
    atomic_write_bytes(positive_model_path, positive_payload)
    positive_sha256 = sha256_file(positive_model_path)
    positive_structure = gemmi.read_structure(str(positive_model_path))
    positive_polymer = list(positive_structure[0][0].get_polymer())
    positive_sequence = "".join(
        gemmi.find_tabulated_residue(residue.name).one_letter_code.upper()
        for residue in positive_polymer
    )
    positive_ranges = (f"A:{positive_polymer[0].seqid}-{positive_polymer[-1].seqid}",)
    positive_atom_count = sum(len(residue) for residue in positive_polymer)

    negative_payload, negative_sequence, negative_ranges, negative_atom_count = (
        _clean_polymer_chain(
            negative_coordinate,
            chain_name=pair.negative_control.seqres_token,
            expected_sequence_sha256=pair.negative_control.source_sequence_sha256,
        )
    )
    if len(negative_sequence) != pair.negative_control.source_sequence_length:
        raise MrControlInputError("negative source sequence length differs")
    negative_model_path = model_root / "negative_1ubq_chain_a.pdb"
    atomic_write_bytes(negative_model_path, negative_payload)
    negative_sha256 = sha256_file(negative_model_path)

    positive_coordinate_id = content_id(
        "coord_",
        {
            "provider": "pdb",
            "pdb_id": positive_model_spec.model_id,
            "sha256": positive_sha256,
        },
    )
    negative_coordinate_id = content_id(
        "coord_",
        {
            "provider": "pdb",
            "pdb_id": pair.negative_control.pdb_id,
            "sha256": pair.negative_control.coordinate_sha256,
        },
    )
    positive_mapping_id = content_id(
        "coordmap_",
        {
            "control_pair_id": pair.control_pair_id,
            "role": "known_positive",
            "sequence_group_id": group.sequence_group_id,
            "model_sha256": positive_sha256,
        },
    )
    positive_model_id = content_id(
        "model_", {"role": "known_positive", "model_sha256": positive_sha256}
    )
    negative_model_id = content_id(
        "model_",
        {"role": "deliberate_unrelated_negative", "model_sha256": negative_sha256},
    )
    positive_record = _model_record(
        role="known_positive",
        coordinate_id=positive_coordinate_id,
        model_id=positive_model_id,
        sequence_group_id=group.sequence_group_id,
        model_sha256=positive_sha256,
        observed_sequence=positive_sequence,
        residue_ranges=positive_ranges,
        mapping_id=positive_mapping_id,
        identity_fraction=1.0,
        negative_identity_percent=None,
        atom_count=positive_atom_count,
    )
    negative_record = _model_record(
        role="deliberate_unrelated_negative",
        coordinate_id=negative_coordinate_id,
        model_id=negative_model_id,
        sequence_group_id=group.sequence_group_id,
        model_sha256=negative_sha256,
        observed_sequence=negative_sequence,
        residue_ranges=negative_ranges,
        mapping_id=None,
        identity_fraction=None,
        negative_identity_percent=pair.negative_control.phaser_identity_percent,
        atom_count=negative_atom_count,
    )
    records = (positive_record, negative_record)
    records_jsonl = output / "processed_models.jsonl"
    atomic_write_text(
        records_jsonl,
        "".join(f"{canonical_json_text(record)}\n" for record in records),
    )

    model_manifest = output / "model_preparation_manifest.json"
    entries = []
    for role, record, model_path in (
        ("known_positive", positive_record, positive_model_path),
        ("deliberate_unrelated_negative", negative_record, negative_model_path),
    ):
        entries.append(
            {
                "control_role": role,
                "model_id": record.model_id,
                "coordinate_id": record.coordinate_id,
                "model_path": model_path.relative_to(output).as_posix(),
                "model_sha256": record.model_sha256,
            }
        )
    atomic_write_json(
        model_manifest,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "generated_at": utc_now_iso(),
            "scope": "fixed_same_mtz_positive_negative_first_copy_controls",
            "entries": entries,
        },
    )

    hypotheses: list[MrHypothesis] = []
    for role, record in (
        ("known_positive", positive_record),
        ("deliberate_unrelated_negative", negative_record),
    ):
        features: dict[str, JsonValue] = {
            "control_pair_id": pair.control_pair_id,
            "control_role": role,
            "exact_sequence_mapping": role == "known_positive",
        }
        if role == "known_positive":
            features.update(
                {
                    "structural_source_class": "experimental",
                    "coordinate_mapping_id": positive_mapping_id,
                    "candidate_source_sequence_identity": 1.0,
                }
            )
        else:
            features.update(
                {
                    "structural_source_class": "deliberate_unrelated_control",
                    "source_pdb_id": pair.negative_control.pdb_id,
                    "source_sequence_sha256": (
                        pair.negative_control.source_sequence_sha256
                    ),
                    "source_sequence_length": (
                        pair.negative_control.source_sequence_length
                    ),
                    "target_sequence_length": group.length_aa,
                    "phaser_identity_percent": (
                        pair.negative_control.phaser_identity_percent
                    ),
                    "identity_interpretation": (
                        "error_model_input_not_sequence_homology"
                    ),
                }
            )
        identity = {
            "control_pair_id": pair.control_pair_id,
            "control_role": role,
            "crystal_id": positive_spec.control_id,
            "sequence_group_id": group.sequence_group_id,
            "model_id": record.model_id,
            "copy_count_expected": positive_spec.expected_asu_copy_count,
            "copy_number_to_search": 1,
            "space_group": preflight.space_group,
            "obs_labels": preflight.selected_observation_labels,
        }
        hypothesis = MrHypothesis(
            schema_version="1.0",
            hypothesis_id=content_id("mrhyp_", identity),
            crystal_id=positive_spec.control_id,
            sequence_group_id=group.sequence_group_id,
            model_id=record.model_id,
            copy_count_expected=positive_spec.expected_asu_copy_count,
            copy_number_to_search=1,
            space_group=preflight.space_group,
            obs_labels=preflight.selected_observation_labels,
            search_stage=MrSearchStage.FIRST_COPY,
            resource_profile=PrototypeProfile.PILOT,
            priority_features=features,
            status=MrHypothesisStatus.QUEUED,
        )
        hypotheses.append(hypothesis)
        atomic_write_text(
            hypothesis_root / f"{hypothesis.hypothesis_id}.jsonl",
            f"{canonical_json_text(hypothesis)}\n",
        )
    hypotheses_jsonl = output / "mr_hypotheses.jsonl"
    atomic_write_text(
        hypotheses_jsonl,
        "".join(f"{canonical_json_text(item)}\n" for item in hypotheses),
    )

    manifest_path = output / "control_pair_manifest.json"
    input_checksums = {
        "control_pair_specification": sha256_file(pair_path),
        "positive_control_specification": sha256_file(positive_spec_path),
        "public_control_preparation": sha256_file(preparation_path),
        "database_manifest": sha256_file(database_path),
        "sequence_groups": sha256_file(request.sequence_groups_jsonl),
        "preflight": sha256_file(request.preflight_jsonl),
    }
    cache_key = content_id(
        "controlbundle_",
        {
            "adapter_version": _ADAPTER_VERSION,
            "control_pair_id": pair.control_pair_id,
            "input_checksums": input_checksums,
            "model_checksums": [record.model_sha256 for record in records],
            "hypothesis_ids": [item.hypothesis_id for item in hypotheses],
        },
    )
    atomic_write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "software_version": __version__,
            "generated_at": utc_now_iso(),
            "control_pair_id": pair.control_pair_id,
            "cache_key": cache_key,
            "crystal_id": positive_spec.control_id,
            "target_sequence_group_id": group.sequence_group_id,
            "expected_asu_copy_count": positive_spec.expected_asu_copy_count,
            "score_gate": pair.score_gate.model_dump(mode="json"),
            "expected_outcomes": {
                hypotheses[0].hypothesis_id: pair.positive_expected_outcome,
                hypotheses[1].hypothesis_id: pair.negative_control.expected_outcome,
            },
            "input_checksums": input_checksums,
            "model_checksums": {
                "known_positive": positive_record.model_sha256,
                "deliberate_unrelated_negative": negative_record.model_sha256,
            },
            "hypothesis_ids": [item.hypothesis_id for item in hypotheses],
            "limitations": list(pair.limitations),
        },
    )
    _LOGGER.info(
        "first-copy control pair prepared",
        extra={
            "control_pair_id": pair.control_pair_id,
            "cache_key": cache_key,
            "output_directory": str(output),
        },
    )
    return MrControlBundleOutput(
        control_pair_id=pair.control_pair_id,
        manifest_json=manifest_path,
        processed_models_jsonl=records_jsonl,
        model_preparation_manifest=model_manifest,
        hypotheses_jsonl=hypotheses_jsonl,
        hypothesis_directory=hypothesis_root,
    )
