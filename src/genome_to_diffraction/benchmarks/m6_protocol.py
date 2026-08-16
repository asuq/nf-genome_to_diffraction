"""Frozen scientific contract for the independent M6 benchmark.

The tracked protocol is truth-facing and must never be placed in a runner
archive.  It fixes public source identities, the blinded case matrix, leakage
policy, and predeclared release gates.  Execution code receives only opaque
case identifiers and checksum-addressed inputs produced by ``m6_runner``.

No external command is executed here.  Invalid, incomplete, unbalanced, or
scientifically inconsistent protocols fail before any expensive work begins.
"""

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import Field, model_validator

from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    OperatorIdentifier,
    PositiveFloat,
    PositiveInt,
    Sha256Hex,
    UtcTimestamp,
)

M6CaseKind = Literal[
    "operational_positive",
    "leakage_positive",
    "target_absent",
    "wrong_related_catalogue",
    "assumption_violation",
    "duplicate_locus",
    "missing_pdb_model",
    "wrong_sds_mass",
    "non_top_matthews",
    "map_only_mtz",
    "ambiguous_columns_equivalent",
    "ambiguous_columns_conflicting",
    "remote_disabled",
    "remote_rate_limited",
    "missing_phenix",
]


class M6FrozenResourceSpec(ContractModel):
    """One immutable public file referenced by the truth protocol."""

    role: Literal["coordinates", "structure_factors", "cluster_snapshot"]
    url: str = Field(pattern=r"^https://")
    sha256: Sha256Hex
    size_bytes: PositiveInt


class M6CatalogueBundleSpec(ContractModel):
    """One checksum-frozen NCBI Datasets response containing proteomes."""

    bundle_id: OperatorIdentifier
    request_url: str = Field(pattern=r"^https://")
    sha256: Sha256Hex
    size_bytes: PositiveInt
    assembly_accessions: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_accessions(self) -> Self:
        if len(self.assembly_accessions) != len(set(self.assembly_accessions)):
            raise ValueError("catalogue-bundle assembly accessions must be unique")
        if any(
            not accession.startswith("GCF_") or "." not in accession
            for accession in self.assembly_accessions
        ):
            raise ValueError("catalogue bundles require versioned RefSeq assemblies")
        return self


class M6CatalogueSpec(ContractModel):
    """One RefSeq protein catalogue inside a frozen NCBI response."""

    catalogue_id: OperatorIdentifier
    assembly_accession: str = Field(pattern=r"^GCF_[0-9]+\.[0-9]+$")
    bundle_id: OperatorIdentifier
    annotation_provider: Literal["NCBI RefSeq"]
    protein_fasta_sha256: Sha256Hex
    protein_fasta_size_bytes: PositiveInt


class M6CrystallographicSourceSpec(ContractModel):
    """Frozen coordinates and structure factors for one PDB entry."""

    pdb_id: str = Field(pattern=r"^[0-9A-Z]{4}$")
    pdb_entity_ids: tuple[PositiveInt, ...] = Field(min_length=1)
    coordinates: M6FrozenResourceSpec
    structure_factors: M6FrozenResourceSpec

    @model_validator(mode="after")
    def _validate_roles(self) -> Self:
        if len(self.pdb_entity_ids) != len(set(self.pdb_entity_ids)):
            raise ValueError("PDB polymer entity IDs must be unique")
        if self.coordinates.role != "coordinates":
            raise ValueError("coordinate resource has the wrong role")
        if self.structure_factors.role != "structure_factors":
            raise ValueError("structure-factor resource has the wrong role")
        if self.pdb_id not in self.coordinates.url.upper():
            raise ValueError("coordinate URL does not contain its PDB ID")
        if self.pdb_id not in self.structure_factors.url.upper():
            raise ValueError("structure-factor URL does not contain its PDB ID")
        return self


class M6PositiveTargetSpec(ContractModel):
    """Truth for one independently selected prokaryotic homomer."""

    target_key: OperatorIdentifier
    source: M6CrystallographicSourceSpec
    organism: NonEmptyString
    catalogue_id: OperatorIdentifier
    target_protein_id: NonEmptyString
    target_sequence_length: PositiveInt
    target_sequence_sha256: Sha256Hex
    construct_sequence_length: PositiveInt
    expected_asu_copy_count: PositiveInt
    resolution_angstrom: PositiveFloat
    rcsb_30_cluster_line_sha256: Sha256Hex
    rcsb_70_cluster_line_sha256: Sha256Hex
    allowed_30_to_70_model_count: int = Field(ge=0)
    correct_family_model_eligible: bool = True


class M6AssumptionProteinSpec(ContractModel):
    """One known protein species in a heteromeric ASU truth control."""

    protein_id: NonEmptyString
    sequence_length: PositiveInt
    sequence_sha256: Sha256Hex


class M6AssumptionControlSpec(ContractModel):
    """Known multi-species ASU used only to test fail-closed abstention."""

    target_key: OperatorIdentifier
    source: M6CrystallographicSourceSpec
    organism: NonEmptyString
    molecular_system: NonEmptyString
    catalogue_id: OperatorIdentifier
    proteins: tuple[M6AssumptionProteinSpec, ...] = Field(min_length=2)
    asu_distinct_protein_species: PositiveInt
    asu_protein_copy_count: PositiveInt
    resolution_angstrom: PositiveFloat

    @model_validator(mode="after")
    def _validate_composition(self) -> Self:
        if len(self.proteins) != self.asu_distinct_protein_species:
            raise ValueError("assumption-control species count is inconsistent")
        protein_ids = [protein.protein_id for protein in self.proteins]
        if len(protein_ids) != len(set(protein_ids)):
            raise ValueError("assumption-control proteins must be unique")
        if self.asu_protein_copy_count < self.asu_distinct_protein_species:
            raise ValueError("ASU copy count cannot be smaller than species count")
        return self


class M6WrongCataloguePairSpec(ContractModel):
    """One predeclared correct-target/wrong-related-proteome pairing."""

    target_key: OperatorIdentifier
    wrong_catalogue_id: OperatorIdentifier
    exact_target_sequence_absent: Literal[True]


class M6CaseSpec(ContractModel):
    """One truth-labelled case mapped to an opaque runner identifier."""

    case_id: str = Field(pattern=r"^M6C[0-9]{3}$")
    case_kind: M6CaseKind
    target_key: OperatorIdentifier
    wrong_catalogue_id: OperatorIdentifier | None = None
    expected_outcome: Literal[
        "target_recovery",
        "no_exact_assignment",
        "assumption_violation_or_abstention",
        "duplicate_locus_ambiguity",
        "typed_completed_or_abstained",
        "typed_infrastructure_failure",
    ]
    variation: NonEmptyString

    @model_validator(mode="after")
    def _validate_shape(self) -> Self:
        expected_by_kind: dict[str, str] = {
            "operational_positive": "target_recovery",
            "leakage_positive": "target_recovery",
            "target_absent": "no_exact_assignment",
            "wrong_related_catalogue": "no_exact_assignment",
            "assumption_violation": "assumption_violation_or_abstention",
            "duplicate_locus": "duplicate_locus_ambiguity",
            "missing_pdb_model": "typed_completed_or_abstained",
            "wrong_sds_mass": "typed_completed_or_abstained",
            "non_top_matthews": "typed_completed_or_abstained",
            "map_only_mtz": "typed_completed_or_abstained",
            "ambiguous_columns_equivalent": "typed_completed_or_abstained",
            "ambiguous_columns_conflicting": "typed_completed_or_abstained",
            "remote_disabled": "typed_completed_or_abstained",
            "remote_rate_limited": "typed_completed_or_abstained",
            "missing_phenix": "typed_infrastructure_failure",
        }
        if self.expected_outcome != expected_by_kind[self.case_kind]:
            raise ValueError("case kind and expected outcome disagree")
        if self.case_kind == "wrong_related_catalogue":
            if self.wrong_catalogue_id is None:
                raise ValueError("wrong-related case lacks its wrong catalogue")
        elif self.wrong_catalogue_id is not None:
            raise ValueError("only wrong-related cases may name a wrong catalogue")
        return self


class M6TrackCriteria(ContractModel):
    """Predeclared minimum positive-control outcomes for one M6 track."""

    positive_case_count: Literal[12]
    minimum_top_25: int = Field(ge=0, le=12)
    minimum_top_10: int = Field(ge=0, le=12)
    minimum_top_5: int = Field(ge=0, le=12)
    correct_family_denominator: int = Field(ge=1, le=12)
    minimum_correct_family_model: int = Field(ge=0, le=12)
    minimum_credible_seed: int = Field(ge=0, le=12)
    minimum_true_copy: int = Field(ge=0, le=12)

    @model_validator(mode="after")
    def _validate_nested_ranks(self) -> Self:
        if not self.minimum_top_5 <= self.minimum_top_10 <= self.minimum_top_25:
            raise ValueError("top-rank thresholds must be nested")
        if self.minimum_correct_family_model > self.correct_family_denominator:
            raise ValueError("correct-family threshold exceeds its denominator")
        return self


class M6AcceptanceCriteria(ContractModel):
    """All frozen M6 correctness and positive-performance gates."""

    candidate_retention_fraction: float = Field(ge=1.0, le=1.0)
    maximum_exact_false_assignments: Literal[0]
    open_set_case_count: Literal[20]
    required_assumption_abstentions: Literal[4]
    assumption_case_count: Literal[4]
    required_duplicate_locus_ambiguities: Literal[2]
    duplicate_locus_case_count: Literal[2]
    operational: M6TrackCriteria
    leakage_controlled: M6TrackCriteria


class M6LeakagePolicy(ContractModel):
    """Pinned model-leakage exclusion and independent cluster cross-check."""

    sequence_tool: Literal["MMseqs2"]
    sequence_tool_version: NonEmptyString
    maximum_allowed_identity_fraction: float = Field(ge=0.7, le=0.7)
    minimum_exclusion_coverage_fraction: float = Field(ge=0.8, le=0.8)
    exact_deposited_coordinates_excluded: Literal[True]
    applies_to_all_model_routes: Literal[True]
    rcsb_30_snapshot: M6FrozenResourceSpec
    rcsb_70_snapshot: M6FrozenResourceSpec
    m5_positive_30_cluster_line_sha256: tuple[Sha256Hex, ...] = Field(
        min_length=11, max_length=11
    )

    @model_validator(mode="after")
    def _validate_snapshots(self) -> Self:
        if self.rcsb_30_snapshot.role != "cluster_snapshot":
            raise ValueError("30% RCSB file has the wrong role")
        if self.rcsb_70_snapshot.role != "cluster_snapshot":
            raise ValueError("70% RCSB file has the wrong role")
        if len(set(self.m5_positive_30_cluster_line_sha256)) != 11:
            raise ValueError("M5 positive cluster identifiers must be unique")
        return self


class M6BenchmarkProtocol(ContractModel):
    """Complete approved M6 scientific protocol and 63-case truth matrix."""

    schema_version: Literal["1.0"]
    protocol_id: OperatorIdentifier
    frozen_at: UtcTimestamp
    intended_use: NonEmptyString
    generalisation_claim: Literal[False]
    excluded_operator_crystals: tuple[OperatorIdentifier, ...] = Field(
        min_length=3, max_length=3
    )
    catalogue_bundles: tuple[M6CatalogueBundleSpec, ...] = Field(
        min_length=2, max_length=2
    )
    catalogues: tuple[M6CatalogueSpec, ...] = Field(min_length=15, max_length=15)
    positives: tuple[M6PositiveTargetSpec, ...] = Field(min_length=12, max_length=12)
    assumption_controls: tuple[M6AssumptionControlSpec, ...] = Field(
        min_length=4, max_length=4
    )
    wrong_catalogue_pairs: tuple[M6WrongCataloguePairSpec, ...] = Field(
        min_length=8, max_length=8
    )
    leakage_policy: M6LeakagePolicy
    cases: tuple[M6CaseSpec, ...] = Field(min_length=63, max_length=63)
    criteria: M6AcceptanceCriteria
    interpretation_policy: tuple[NonEmptyString, ...] = Field(min_length=4)

    @model_validator(mode="after")
    def _validate_protocol(self) -> Self:
        if set(self.excluded_operator_crystals) != {
            "AD4QS1P4G2_18",
            "CD4QS2P2G1_15",
            "CD6QS2P2G1_5",
        }:
            raise ValueError("the three unknown operator crystals must remain excluded")

        bundles = {bundle.bundle_id: bundle for bundle in self.catalogue_bundles}
        catalogues = {
            catalogue.catalogue_id: catalogue for catalogue in self.catalogues
        }
        if len(catalogues) != len(self.catalogues):
            raise ValueError("catalogue IDs must be unique")
        for catalogue in self.catalogues:
            bundle = bundles.get(catalogue.bundle_id)
            if bundle is None or catalogue.assembly_accession not in (
                bundle.assembly_accessions
            ):
                raise ValueError("catalogue is not present in its frozen source bundle")

        target_keys = [target.target_key for target in self.positives]
        assumption_keys = [control.target_key for control in self.assumption_controls]
        all_target_keys = set(target_keys) | set(assumption_keys)
        if len(set(target_keys)) != 12 or len(set(assumption_keys)) != 4:
            raise ValueError("M6 target keys must be unique")
        if set(target_keys) & set(assumption_keys):
            raise ValueError("positive and assumption target keys overlap")
        if any(target.catalogue_id not in catalogues for target in self.positives):
            raise ValueError("positive target references an unknown catalogue")
        if any(len(target.source.pdb_entity_ids) != 1 for target in self.positives):
            raise ValueError("positive controls require one PDB polymer entity")
        if any(
            control.catalogue_id not in catalogues
            for control in self.assumption_controls
        ):
            raise ValueError("assumption control references an unknown catalogue")
        if any(
            len(control.source.pdb_entity_ids) != control.asu_distinct_protein_species
            for control in self.assumption_controls
        ):
            raise ValueError(
                "assumption-control PDB entities must match the protein species"
            )
        expected_counts = {target.expected_asu_copy_count for target in self.positives}
        if expected_counts != {1, 2, 3, 4, 6}:
            raise ValueError("positive ASU counts must cover 1, 2, 3, 4, and 6")
        positive_clusters = {
            target.rcsb_30_cluster_line_sha256 for target in self.positives
        }
        if len(positive_clusters) != 12:
            raise ValueError("M6 positives must occupy 12 distinct 30% clusters")
        if positive_clusters & set(
            self.leakage_policy.m5_positive_30_cluster_line_sha256
        ):
            raise ValueError("M6 and M5 positive 30% clusters overlap")
        eligible_count = sum(
            target.correct_family_model_eligible for target in self.positives
        )
        if (
            eligible_count
            != self.criteria.leakage_controlled.correct_family_denominator
        ):
            raise ValueError("leakage correct-family denominator is inconsistent")

        pair_map = {
            pair.target_key: pair.wrong_catalogue_id
            for pair in self.wrong_catalogue_pairs
        }
        if len(pair_map) != 8 or not set(pair_map) <= set(target_keys):
            raise ValueError("wrong-catalogue pairs require eight distinct positives")
        if any(catalogue_id not in catalogues for catalogue_id in pair_map.values()):
            raise ValueError("wrong-catalogue pair references an unknown catalogue")

        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("M6 case IDs must be unique")
        if any(case.target_key not in all_target_keys for case in self.cases):
            raise ValueError("M6 case references an unknown target")
        counts = {
            kind: sum(case.case_kind == kind for case in self.cases)
            for kind in set(case.case_kind for case in self.cases)
        }
        expected_case_counts = {
            "operational_positive": 12,
            "leakage_positive": 12,
            "target_absent": 12,
            "wrong_related_catalogue": 8,
            "assumption_violation": 4,
            "duplicate_locus": 2,
            "missing_pdb_model": 2,
            "wrong_sds_mass": 2,
            "non_top_matthews": 2,
            "map_only_mtz": 2,
            "ambiguous_columns_equivalent": 1,
            "ambiguous_columns_conflicting": 1,
            "remote_disabled": 1,
            "remote_rate_limited": 1,
            "missing_phenix": 1,
        }
        if counts != expected_case_counts:
            raise ValueError("M6 case matrix does not match the frozen 63-case balance")
        for kind in ("operational_positive", "leakage_positive", "target_absent"):
            observed = {
                case.target_key for case in self.cases if case.case_kind == kind
            }
            if observed != set(target_keys):
                raise ValueError(f"{kind} cases must cover all 12 positives")
        observed_pairs = {
            case.target_key: case.wrong_catalogue_id
            for case in self.cases
            if case.case_kind == "wrong_related_catalogue"
        }
        if observed_pairs != pair_map:
            raise ValueError("wrong-related cases differ from the frozen pairings")
        observed_assumptions = {
            case.target_key
            for case in self.cases
            if case.case_kind == "assumption_violation"
        }
        if observed_assumptions != set(assumption_keys):
            raise ValueError("assumption cases must cover all four controls")
        return self


def load_m6_protocol(path: Path) -> M6BenchmarkProtocol:
    """Load and fully cross-validate the approved truth-facing M6 protocol."""

    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise PublicControlError(f"M6 protocol is not a file: {path}")
    try:
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
        return M6BenchmarkProtocol.model_validate(payload)
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise PublicControlError(f"invalid M6 protocol {resolved}: {error}") from error
