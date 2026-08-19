"""Observed, truthless, checksum-bound evidence for M6 edge controls.

The M6 fault-control document selects a deterministic stimulus; it is never an
outcome oracle.  This module converts actual adapter records into one typed
``M6EdgeObservation``.  Matthews evidence remains target-agnostic so the trusted
collector can join the frozen target digest and copy count later.  MTZ evidence
is copied from ``MtzPreflightRecord``; remote controls are measured at the
configuration/consent guard or by parsing a local raw HTTP fixture; missing
Phenix is measured by running ``validate_manifest_environment`` against an
isolated, deliberately missing runtime; and missing-model evidence verifies a
checksum-bound exhausted-route bundle.

No external service or scheduler is used.  The only external-runtime call is a
read-only Phenix-manifest validation that must fail for the isolated fixture.
Malformed inputs, contradictory claimed states, changed source checksums, or
content-ID tampering fail loudly.  ``observation_id`` is the cache/content key
over the complete typed evidence.  Focused unit tests cover all evidence kinds,
canonical replay, contradictions, raw HTTP parsing, and tamper rejection.
"""

import hashlib
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_digest, content_id
from genome_to_diffraction.phenix.runtime import (
    PhenixRuntimeVerificationError,
    validate_manifest_environment,
)
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    Sha256Hex,
)
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document
from genome_to_diffraction.schemas.manifests import (
    CrystalManifest,
    PipelineConfig,
    require_remote_submission_authorisation,
)
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MtzPreflightRecord,
    SequenceGroupRecord,
)

M6EdgeKind = Literal[
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


def _json_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = load_json_document(path)
    except ContractLoadError as error:
        raise ValueError(f"invalid M6 {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"M6 {label} is not a JSON object: {path}")
    return cast(dict[str, object], value)


def _json_integer(
    document: Mapping[str, object], key: str, label: str, *, minimum: int = 0
) -> int:
    value = document.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"M6 {label} {key} is not an integer")
    if value < minimum:
        raise ValueError(f"M6 {label} {key} is below the minimum {minimum}: {value}")
    return value


M6EdgeMeasurementStatus = Literal["measured", "unavailable", "contradicted"]

_EDGE_ADAPTER = "m6-edge-observation-v1"
_MODEL_EXHAUSTION_ADAPTER = "m6-missing-model-stimulus-v1"
_EDGE_KINDS = frozenset(
    {
        "missing_pdb_model",
        "wrong_sds_mass",
        "non_top_matthews",
        "map_only_mtz",
        "ambiguous_columns_equivalent",
        "ambiguous_columns_conflicting",
        "remote_disabled",
        "remote_rate_limited",
        "missing_phenix",
    }
)
M6_RATE_LIMIT_HTTP_FIXTURE = (
    "HTTP/1.1 429 Too Many Requests\r\n"
    "Content-Type: application/json\r\n"
    "Retry-After: 60\r\n"
    "Content-Length: 24\r\n"
    "\r\n"
    '{"error":"rate_limited"}'
)


class M6UnavailableEdgeEvidence(ContractModel):
    """Typed absence of the adapter evidence needed for one edge measurement."""

    evidence_kind: Literal["unavailable"]
    reason_code: NonEmptyString
    source_sha256: dict[str, Sha256Hex] = Field(default_factory=dict)


class M6ModelExhaustionEvidence(ContractModel):
    """Observed empty coordinate/model route after a deterministic stimulus."""

    evidence_kind: Literal["model_exhaustion"]
    route_manifest_sha256: Sha256Hex
    stimulus_source_hits_sha256: Sha256Hex
    accepted_hits_sha256: Sha256Hex
    coordinate_sources_sha256: Sha256Hex
    processed_models_sha256: Sha256Hex
    accepted_hit_count: int = Field(ge=0)
    coordinate_source_count: int = Field(ge=0)
    processed_model_count: int = Field(ge=0)
    hypothesis_count: int = Field(ge=0)
    route_completed: bool


class M6RetainedMatthewsFact(ContractModel):
    """One retained copy-number prior, without target-side interpretation."""

    hypothesis_id: NonEmptyString
    copy_count: int = Field(gt=0)
    rank_within_candidate: int = Field(gt=0)
    physical_status: Literal["plausible", "review", "impossible"]
    matthews_prior: float = Field(ge=0, le=1)


class M6MatthewsCandidateEvidence(ContractModel):
    """One exact-sequence candidate's SDS assessment and retained copy priors."""

    sequence_group_id: NonEmptyString
    sequence_sha256: Sha256Hex
    sds_page_nearest_band_kda: float | None = Field(default=None, gt=0)
    sds_page_absolute_difference_kda: float | None = Field(default=None, ge=0)
    sds_page_fractional_difference: float | None = Field(default=None, ge=0)
    sds_page_prior_label: Literal["strong", "compatible", "weak", "unavailable"]
    retained_hypotheses: tuple[M6RetainedMatthewsFact, ...]

    @model_validator(mode="after")
    def _validate_group_and_retained_order(self) -> Self:
        if self.sequence_group_id != f"seq_{self.sequence_sha256}":
            raise ValueError("Matthews edge group and sequence digest differ")
        keys = tuple(
            (item.rank_within_candidate, item.copy_count, item.hypothesis_id)
            for item in self.retained_hypotheses
        )
        if tuple(sorted(set(keys))) != keys:
            raise ValueError("retained Matthews facts must be unique and sorted")
        if self.sds_page_prior_label == "unavailable" and any(
            value is not None
            for value in (
                self.sds_page_nearest_band_kda,
                self.sds_page_absolute_difference_kda,
                self.sds_page_fractional_difference,
            )
        ):
            raise ValueError("unavailable SDS evidence must not contain distances")
        return self


class M6MatthewsEdgeEvidence(ContractModel):
    """All target-agnostic candidate summaries from one Matthews JSONL."""

    evidence_kind: Literal["matthews"]
    matthews_jsonl_sha256: Sha256Hex
    candidate_summaries: tuple[M6MatthewsCandidateEvidence, ...]

    @model_validator(mode="after")
    def _validate_candidate_order(self) -> Self:
        keys = tuple(
            (item.sequence_sha256, item.sequence_group_id)
            for item in self.candidate_summaries
        )
        if tuple(sorted(set(keys))) != keys:
            raise ValueError("Matthews candidate evidence must be unique and sorted")
        return self


class M6MtzEdgeEvidence(ContractModel):
    """Actual candidate selection and warnings emitted by MTZ preflight."""

    evidence_kind: Literal["mtz_preflight"]
    preflight_jsonl_sha256: Sha256Hex
    preflight_record_sha256: Sha256Hex
    preflight_id: NonEmptyString
    mtz_sha256: Sha256Hex
    observation_candidates: tuple[str, ...]
    selected_observation_labels: str | None
    warning_codes: tuple[str, ...]
    decision: Literal["pass", "pass_with_review", "fail"]
    available_columns: tuple[tuple[str, str], ...]


class M6RemoteGuardEvidence(ContractModel):
    """Observed provider enablement, per-crystal consent, and attempt count."""

    evidence_kind: Literal["remote_guard"]
    analysis_config_sha256: Sha256Hex
    crystal_manifest_sha256: Sha256Hex
    provider_enabled: bool
    consent_allowed: bool
    authorisation_denied: bool
    authorisation_failure_code: Literal[
        "run_remote_disabled", "crystal_consent_denied", "not_denied"
    ]
    request_count: int = Field(ge=0)


class M6HttpRateLimitEvidence(ContractModel):
    """Parsed deterministic local HTTP response from a guarded request fixture."""

    evidence_kind: Literal["http_rate_limit"]
    analysis_config_sha256: Sha256Hex
    crystal_manifest_sha256: Sha256Hex
    fault_control_sha256: Sha256Hex
    fixture_sha256: Sha256Hex
    provider_enabled: bool
    consent_allowed: bool
    request_count: int = Field(ge=0)
    http_status_code: int = Field(ge=100, le=599)
    retry_after_seconds: int | None = Field(default=None, ge=0)


class M6PhenixValidationEvidence(ContractModel):
    """Result of validating a checksum-bound isolated missing Phenix runtime."""

    evidence_kind: Literal["phenix_validation"]
    supplied_manifest_sha256: Sha256Hex
    isolated_manifest_sha256: Sha256Hex
    validation_succeeded: bool
    failure_code: Literal["environment_file_missing", "unexpected_validation_result"]


M6EdgeEvidence = Annotated[
    M6UnavailableEdgeEvidence
    | M6ModelExhaustionEvidence
    | M6MatthewsEdgeEvidence
    | M6MtzEdgeEvidence
    | M6RemoteGuardEvidence
    | M6HttpRateLimitEvidence
    | M6PhenixValidationEvidence,
    Field(discriminator="evidence_kind"),
]


class M6EdgeObservation(ContractModel):
    """One immutable runner observation for a requested edge stimulus."""

    schema_version: Literal["1.0"]
    adapter_version: Literal["m6-edge-observation-v1"]
    observation_id: NonEmptyString
    case_id: NonEmptyString
    edge_kind: M6EdgeKind
    measurement_status: M6EdgeMeasurementStatus
    evidence_sha256: Sha256Hex
    evidence: M6EdgeEvidence

    @model_validator(mode="after")
    def _validate_status_and_identity(self) -> Self:
        expected_evidence = {
            "missing_pdb_model": "model_exhaustion",
            "wrong_sds_mass": "matthews",
            "non_top_matthews": "matthews",
            "map_only_mtz": "mtz_preflight",
            "ambiguous_columns_equivalent": "mtz_preflight",
            "ambiguous_columns_conflicting": "mtz_preflight",
            "remote_disabled": "remote_guard",
            "remote_rate_limited": "http_rate_limit",
            "missing_phenix": "phenix_validation",
        }[self.edge_kind]
        evidence_kind = self.evidence.evidence_kind
        if evidence_kind != "unavailable" and evidence_kind != expected_evidence:
            raise ValueError("edge kind and evidence kind disagree")
        expected_status = _measurement_status(self.edge_kind, self.evidence)
        if self.measurement_status != expected_status:
            raise ValueError("edge measurement status contradicts its evidence")
        evidence_sha256 = canonical_digest(self.evidence.model_dump(mode="json"))
        if self.evidence_sha256 != evidence_sha256:
            raise ValueError("edge evidence checksum changed")
        if self.observation_id != content_id("m6edge_", self.identity_payload()):
            raise ValueError("edge observation content identifier changed")
        return self

    def identity_payload(self) -> dict[str, object]:
        """Return the full content identity excluding only ``observation_id``."""

        return {
            "schema_version": self.schema_version,
            "adapter_version": self.adapter_version,
            "case_id": self.case_id,
            "edge_kind": self.edge_kind,
            "measurement_status": self.measurement_status,
            "evidence_sha256": self.evidence_sha256,
            "evidence": self.evidence.model_dump(mode="json"),
        }


def edge_stimulus(fault_control: Mapping[str, object]) -> M6EdgeKind | None:
    """Return only the requested edge adapter, never a scientific outcome."""

    raw = fault_control.get("edge_stimulus")
    if raw is None:
        return None
    if not isinstance(raw, str) or raw not in _EDGE_KINDS:
        raise ValueError("M6 edge stimulus is invalid")
    return cast(M6EdgeKind, raw)


def _measurement_status(
    edge_kind: M6EdgeKind, evidence: M6EdgeEvidence
) -> M6EdgeMeasurementStatus:
    if isinstance(evidence, M6UnavailableEdgeEvidence):
        return "unavailable"
    measured = False
    if edge_kind == "missing_pdb_model":
        assert isinstance(evidence, M6ModelExhaustionEvidence)
        measured = (
            evidence.route_completed
            and evidence.accepted_hit_count == 0
            and evidence.coordinate_source_count == 0
            and evidence.processed_model_count == 0
            and evidence.hypothesis_count == 0
        )
    elif edge_kind in {"wrong_sds_mass", "non_top_matthews"}:
        assert isinstance(evidence, M6MatthewsEdgeEvidence)
        measured = bool(evidence.candidate_summaries) and all(
            summary.retained_hypotheses for summary in evidence.candidate_summaries
        )
    elif edge_kind == "map_only_mtz":
        assert isinstance(evidence, M6MtzEdgeEvidence)
        measured = (
            evidence.selected_observation_labels is None
            and not evidence.observation_candidates
            and "no_observed_data" in evidence.warning_codes
        )
    elif edge_kind == "ambiguous_columns_equivalent":
        assert isinstance(evidence, M6MtzEdgeEvidence)
        warnings = set(evidence.warning_codes)
        measured = (
            len(evidence.observation_candidates) >= 2
            and evidence.selected_observation_labels
            in set(evidence.observation_candidates)
            and {
                "equivalent_observation_arrays",
                "observation_selection_deterministic",
            }
            <= warnings
        )
    elif edge_kind == "ambiguous_columns_conflicting":
        assert isinstance(evidence, M6MtzEdgeEvidence)
        measured = (
            len(evidence.observation_candidates) >= 2
            and evidence.selected_observation_labels is None
            and "ambiguous_observation_arrays" in evidence.warning_codes
        )
    elif edge_kind == "remote_disabled":
        assert isinstance(evidence, M6RemoteGuardEvidence)
        measured = (
            not evidence.provider_enabled
            and not evidence.consent_allowed
            and evidence.authorisation_denied
            and evidence.authorisation_failure_code == "run_remote_disabled"
            and evidence.request_count == 0
        )
    elif edge_kind == "remote_rate_limited":
        assert isinstance(evidence, M6HttpRateLimitEvidence)
        measured = (
            evidence.provider_enabled
            and evidence.consent_allowed
            and evidence.request_count == 1
            and evidence.http_status_code == 429
            and evidence.retry_after_seconds is not None
        )
    else:
        assert isinstance(evidence, M6PhenixValidationEvidence)
        measured = (
            not evidence.validation_succeeded
            and evidence.failure_code == "environment_file_missing"
        )
    return "measured" if measured else "contradicted"


def make_edge_observation(
    *, case_id: str, edge_kind: M6EdgeKind, evidence: M6EdgeEvidence
) -> M6EdgeObservation:
    """Construct one canonical observation from measured adapter evidence."""

    status = _measurement_status(edge_kind, evidence)
    evidence_sha256 = canonical_digest(evidence.model_dump(mode="json"))
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "adapter_version": _EDGE_ADAPTER,
        "case_id": case_id,
        "edge_kind": edge_kind,
        "measurement_status": status,
        "evidence_sha256": evidence_sha256,
        "evidence": evidence.model_dump(mode="json"),
    }
    return M6EdgeObservation(
        **payload,
        observation_id=content_id("m6edge_", payload),
    )


def _read_jsonl[T: ContractModel](path: Path, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    )


def _matthews_candidate_key(
    item: M6MatthewsCandidateEvidence,
) -> tuple[str, str]:
    return item.sequence_sha256, item.sequence_group_id


def observe_matthews(
    *,
    case_id: str,
    edge_kind: Literal["wrong_sds_mass", "non_top_matthews"],
    matthews_jsonl: Path,
    sequence_groups: Iterable[SequenceGroupRecord],
) -> M6EdgeObservation:
    """Summarise every candidate without consulting target truth."""

    try:
        source = matthews_jsonl.resolve(strict=True)
    except OSError:
        return make_edge_observation(
            case_id=case_id,
            edge_kind=edge_kind,
            evidence=M6UnavailableEdgeEvidence(
                evidence_kind="unavailable",
                reason_code="matthews_output_missing",
            ),
        )
    groups = {group.sequence_group_id: group for group in sequence_groups}
    rows = _read_jsonl(source, MatthewsHypothesis)
    by_group: dict[str, list[MatthewsHypothesis]] = {}
    for row in rows:
        by_group.setdefault(row.sequence_group_id, []).append(row)
    summaries: list[M6MatthewsCandidateEvidence] = []
    for group_id, group_rows in sorted(by_group.items()):
        group = groups.get(group_id)
        if group is None:
            raise ValueError(
                f"Matthews edge evidence references unknown group: {group_id}"
            )
        first = group_rows[0]
        sds_values = {
            (
                item.sds_page_nearest_band_kda,
                item.sds_page_absolute_difference_kda,
                item.sds_page_fractional_difference,
                item.sds_page_prior_label,
            )
            for item in group_rows
        }
        if len(sds_values) != 1:
            raise ValueError("Matthews rows disagree on one candidate's SDS evidence")
        retained = tuple(
            M6RetainedMatthewsFact(
                hypothesis_id=item.hypothesis_id,
                copy_count=item.copy_count,
                rank_within_candidate=item.rank_within_candidate,
                physical_status=item.physical_status.value,
                matthews_prior=item.matthews_prior,
            )
            for item in sorted(
                (item for item in group_rows if item.retained),
                key=lambda item: (
                    item.rank_within_candidate,
                    item.copy_count,
                    item.hypothesis_id,
                ),
            )
        )
        summaries.append(
            M6MatthewsCandidateEvidence(
                sequence_group_id=group_id,
                sequence_sha256=group.sha256,
                sds_page_nearest_band_kda=first.sds_page_nearest_band_kda,
                sds_page_absolute_difference_kda=(
                    first.sds_page_absolute_difference_kda
                ),
                sds_page_fractional_difference=(first.sds_page_fractional_difference),
                sds_page_prior_label=first.sds_page_prior_label,
                retained_hypotheses=retained,
            )
        )
    evidence = M6MatthewsEdgeEvidence(
        evidence_kind="matthews",
        matthews_jsonl_sha256=sha256_file(source),
        candidate_summaries=tuple(sorted(summaries, key=_matthews_candidate_key)),
    )
    return make_edge_observation(
        case_id=case_id,
        edge_kind=edge_kind,
        evidence=evidence,
    )


def observe_mtz_preflight(
    *,
    case_id: str,
    edge_kind: Literal[
        "map_only_mtz",
        "ambiguous_columns_equivalent",
        "ambiguous_columns_conflicting",
    ],
    preflight_jsonl: Path,
) -> M6EdgeObservation:
    """Retain actual observation candidates, selection, columns, and warnings."""

    source = preflight_jsonl.resolve(strict=True)
    records = _read_jsonl(source, MtzPreflightRecord)
    if len(records) != 1:
        return make_edge_observation(
            case_id=case_id,
            edge_kind=edge_kind,
            evidence=M6UnavailableEdgeEvidence(
                evidence_kind="unavailable",
                reason_code="preflight_record_count_changed",
                source_sha256={"preflight_jsonl": sha256_file(source)},
            ),
        )
    record = records[0]
    evidence = M6MtzEdgeEvidence(
        evidence_kind="mtz_preflight",
        preflight_jsonl_sha256=sha256_file(source),
        preflight_record_sha256=canonical_digest(record.model_dump(mode="json")),
        preflight_id=record.preflight_id,
        mtz_sha256=record.mtz_sha256,
        observation_candidates=record.observation_candidates,
        selected_observation_labels=record.selected_observation_labels,
        warning_codes=tuple(sorted(set(record.warning_codes))),
        decision=record.decision.value,
        available_columns=tuple(
            sorted(
                (column.label, column.type_code) for column in record.available_columns
            )
        ),
    )
    return make_edge_observation(
        case_id=case_id,
        edge_kind=edge_kind,
        evidence=evidence,
    )


def _remote_guard(
    analysis_config: Path, crystal_manifest: Path
) -> tuple[bool, bool, bool, str]:
    config_document = _json_object(analysis_config, "analysis configuration")
    crystal_document = _json_object(crystal_manifest, "crystal manifest")
    config = PipelineConfig.model_validate(config_document)
    crystals = CrystalManifest.model_validate(crystal_document)
    if len(crystals.crystals) != 1:
        raise ValueError("M6 edge crystal manifest must contain exactly one crystal")
    crystal = crystals.crystals[0]
    enabled = config.providers.esm_atlas.enabled
    consent = crystal.allow_remote_sequence_submission
    denied = False
    failure_code = "not_denied"
    try:
        require_remote_submission_authorisation(
            crystal,
            run_allows_remote=enabled,
        )
    except ValueError as error:
        denied = True
        failure_code = (
            "run_remote_disabled"
            if "disabled for this run" in str(error)
            else "crystal_consent_denied"
        )
    return enabled, consent, denied, failure_code


def observe_remote_disabled(
    *,
    case_id: str,
    analysis_config: Path,
    crystal_manifest: Path,
    request_count: int,
) -> M6EdgeObservation:
    """Measure the configuration/consent guard and its request ledger count."""

    config_path = analysis_config.resolve(strict=True)
    crystal_path = crystal_manifest.resolve(strict=True)
    enabled, consent, denied, failure_code = _remote_guard(config_path, crystal_path)
    evidence = M6RemoteGuardEvidence(
        evidence_kind="remote_guard",
        analysis_config_sha256=sha256_file(config_path),
        crystal_manifest_sha256=sha256_file(crystal_path),
        provider_enabled=enabled,
        consent_allowed=consent,
        authorisation_denied=denied,
        authorisation_failure_code=cast(
            Literal["run_remote_disabled", "crystal_consent_denied", "not_denied"],
            failure_code,
        ),
        request_count=request_count,
    )
    return make_edge_observation(
        case_id=case_id,
        edge_kind="remote_disabled",
        evidence=evidence,
    )


def _parse_http_rate_limit(raw: str) -> tuple[int, int | None, str]:
    try:
        payload = raw.encode("ascii", errors="strict")
    except UnicodeEncodeError as error:
        raise ValueError("HTTP fixture is not ASCII") from error
    header, separator, _ = payload.partition(b"\r\n\r\n")
    if not separator:
        raise ValueError("HTTP fixture lacks a CRLF header boundary")
    lines = header.split(b"\r\n")
    match = re.fullmatch(rb"HTTP/1\.[01] ([0-9]{3}) [!-~ ]+", lines[0])
    if match is None:
        raise ValueError("HTTP fixture has an invalid status line")
    status = int(match.group(1))
    retry_values: list[bytes] = []
    for line in lines[1:]:
        name, colon, value = line.partition(b":")
        if not colon or not name:
            raise ValueError("HTTP fixture has a malformed header")
        if name.lower() == b"retry-after":
            retry_values.append(value.strip())
    if len(retry_values) > 1:
        raise ValueError("HTTP fixture repeats Retry-After")
    retry_after: int | None = None
    if retry_values:
        if re.fullmatch(rb"[0-9]+", retry_values[0]) is None:
            raise ValueError("HTTP fixture Retry-After is not delta-seconds")
        retry_after = int(retry_values[0])
    return status, retry_after, hashlib.sha256(payload).hexdigest()


def observe_rate_limit_fixture(
    *,
    case_id: str,
    analysis_config: Path,
    crystal_manifest: Path,
    fault_control: Path,
) -> M6EdgeObservation:
    """Parse one raw local HTTP response after the normal remote consent guard."""

    config_path = analysis_config.resolve(strict=True)
    crystal_path = crystal_manifest.resolve(strict=True)
    fault_path = fault_control.resolve(strict=True)
    fault = _json_object(fault_path, "fault control")
    enabled, consent, denied, _ = _remote_guard(config_path, crystal_path)
    raw = fault.get("local_http_response") if isinstance(fault, dict) else None
    if not isinstance(raw, str):
        return make_edge_observation(
            case_id=case_id,
            edge_kind="remote_rate_limited",
            evidence=M6UnavailableEdgeEvidence(
                evidence_kind="unavailable",
                reason_code="local_http_fixture_missing",
                source_sha256={"fault_control": sha256_file(fault_path)},
            ),
        )
    try:
        status, retry_after, fixture_sha256 = _parse_http_rate_limit(raw)
    except ValueError:
        return make_edge_observation(
            case_id=case_id,
            edge_kind="remote_rate_limited",
            evidence=M6UnavailableEdgeEvidence(
                evidence_kind="unavailable",
                reason_code="local_http_fixture_unparseable",
                source_sha256={"fault_control": sha256_file(fault_path)},
            ),
        )
    evidence = M6HttpRateLimitEvidence(
        evidence_kind="http_rate_limit",
        analysis_config_sha256=sha256_file(config_path),
        crystal_manifest_sha256=sha256_file(crystal_path),
        fault_control_sha256=sha256_file(fault_path),
        fixture_sha256=fixture_sha256,
        provider_enabled=enabled,
        consent_allowed=consent,
        request_count=0 if denied else 1,
        http_status_code=status,
        retry_after_seconds=retry_after,
    )
    return make_edge_observation(
        case_id=case_id,
        edge_kind="remote_rate_limited",
        evidence=evidence,
    )


def observe_isolated_missing_phenix(
    *,
    case_id: str,
    supplied_manifest: Path,
    isolated_manifest: Path,
) -> M6EdgeObservation:
    """Validate one real-manifest-derived runtime whose environment is absent."""

    supplied = supplied_manifest.resolve(strict=True)
    document = _json_object(supplied, "Phenix manifest")
    missing_root = Path("/nonexistent/nf-gtd-m6-isolated-missing-phenix")
    if missing_root.exists():
        raise ValueError("fixed isolated missing-Phenix path unexpectedly exists")
    document["installation_prefix"] = str(missing_root)
    document["phenix_env_sh"] = str(missing_root / "phenix_env.sh")
    atomic_write_json(isolated_manifest, document)
    validation_succeeded = False
    failure_code: Literal[
        "environment_file_missing", "unexpected_validation_result"
    ] = "unexpected_validation_result"
    try:
        validate_manifest_environment(isolated_manifest.resolve(strict=True))
        validation_succeeded = True
    except PhenixRuntimeVerificationError as error:
        if "environment file is missing" in str(error):
            failure_code = "environment_file_missing"
    evidence = M6PhenixValidationEvidence(
        evidence_kind="phenix_validation",
        supplied_manifest_sha256=sha256_file(supplied),
        isolated_manifest_sha256=sha256_file(isolated_manifest),
        validation_succeeded=validation_succeeded,
        failure_code=failure_code,
    )
    return make_edge_observation(
        case_id=case_id,
        edge_kind="missing_phenix",
        evidence=evidence,
    )


def write_missing_model_stimulus(
    *,
    accepted_hits: Path,
    output_directory: Path,
) -> Path:
    """Emit a checksum-bound, actually empty coordinate/model provider result."""

    source = accepted_hits.resolve(strict=True)
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    provider_hits = output / "accepted_hits.jsonl"
    coordinates = output / "coordinate_sources.jsonl"
    models = output / "processed_models.jsonl"
    atomic_write_text(provider_hits, "")
    atomic_write_text(coordinates, "")
    atomic_write_text(models, "")
    manifest = output / "model_route_manifest.json"
    atomic_write_json(
        manifest,
        {
            "schema_version": "1.0",
            "adapter_version": _MODEL_EXHAUSTION_ADAPTER,
            "route_completed": True,
            "accepted_hit_count": 0,
            "coordinate_source_count": 0,
            "processed_model_count": 0,
            "input_sha256": {"stimulus_source_hits": sha256_file(source)},
            "output_sha256": {
                "accepted_hits": sha256_file(provider_hits),
                "coordinate_sources": sha256_file(coordinates),
                "processed_models": sha256_file(models),
            },
        },
    )
    return manifest


def observe_missing_model(
    *, case_id: str, case_bundle: Path, hypothesis_count: int
) -> M6EdgeObservation:
    """Verify and retain the exhausted model-route bundle."""

    root = case_bundle / "missing-model-stimulus"
    manifest_path = root / "model_route_manifest.json"
    if not manifest_path.is_file():
        return make_edge_observation(
            case_id=case_id,
            edge_kind="missing_pdb_model",
            evidence=M6UnavailableEdgeEvidence(
                evidence_kind="unavailable",
                reason_code="model_route_evidence_missing",
            ),
        )
    manifest = _json_object(manifest_path, "missing-model route manifest")
    bundle_manifest = _json_object(
        case_bundle / "bundle_manifest.json", "case bundle manifest"
    )
    bundle_outputs = (
        bundle_manifest.get("output_sha256")
        if isinstance(bundle_manifest, dict)
        else None
    )
    if not isinstance(bundle_outputs, dict) or bundle_outputs.get(
        "missing_model_route"
    ) != sha256_file(manifest_path):
        raise ValueError("M6 case bundle does not bind missing-model evidence")
    coordinates = root / "coordinate_sources.jsonl"
    models = root / "processed_models.jsonl"
    inputs = manifest.get("input_sha256")
    outputs = manifest.get("output_sha256")
    source_hits = case_bundle / "selected-candidates/accepted_structural_hits.jsonl"
    accepted_hits = root / "accepted_hits.jsonl"
    if (
        manifest.get("adapter_version") != _MODEL_EXHAUSTION_ADAPTER
        or not isinstance(inputs, dict)
        or not isinstance(outputs, dict)
        or inputs.get("stimulus_source_hits") != sha256_file(source_hits)
        or outputs.get("accepted_hits") != sha256_file(accepted_hits)
        or outputs.get("coordinate_sources") != sha256_file(coordinates)
        or outputs.get("processed_models") != sha256_file(models)
    ):
        raise ValueError("M6 missing-model route checksums changed")
    evidence = M6ModelExhaustionEvidence(
        evidence_kind="model_exhaustion",
        route_manifest_sha256=sha256_file(manifest_path),
        stimulus_source_hits_sha256=sha256_file(source_hits),
        accepted_hits_sha256=sha256_file(accepted_hits),
        coordinate_sources_sha256=sha256_file(coordinates),
        processed_models_sha256=sha256_file(models),
        accepted_hit_count=_json_integer(
            manifest, "accepted_hit_count", "missing-model route manifest"
        ),
        coordinate_source_count=sum(
            1 for line in coordinates.read_text(encoding="utf-8").splitlines() if line
        ),
        processed_model_count=sum(
            1 for line in models.read_text(encoding="utf-8").splitlines() if line
        ),
        hypothesis_count=hypothesis_count,
        route_completed=manifest.get("route_completed") is True,
    )
    return make_edge_observation(
        case_id=case_id,
        edge_kind="missing_pdb_model",
        evidence=evidence,
    )


def observe_case_edge(
    *,
    case_id: str,
    case_bundle: Path,
    fault_control: Mapping[str, object],
    sequence_groups: Iterable[SequenceGroupRecord],
    hypothesis_count: int,
) -> tuple[M6EdgeObservation, ...]:
    """Dispatch one requested stimulus to its actual retained adapter evidence."""

    stimulus = edge_stimulus(fault_control)
    if stimulus is None:
        return ()
    case = case_bundle.resolve(strict=True)
    preflight_jsonl = case / "preflight_bundle/preflight/mtz_preflight.jsonl"
    if stimulus == "missing_pdb_model":
        observation = observe_missing_model(
            case_id=case_id,
            case_bundle=case,
            hypothesis_count=hypothesis_count,
        )
    elif stimulus in {"wrong_sds_mass", "non_top_matthews"}:
        observation = observe_matthews(
            case_id=case_id,
            edge_kind=stimulus,
            matthews_jsonl=case / "matthews/matthews_hypotheses.jsonl",
            sequence_groups=sequence_groups,
        )
    elif stimulus in {
        "map_only_mtz",
        "ambiguous_columns_equivalent",
        "ambiguous_columns_conflicting",
    }:
        observation = observe_mtz_preflight(
            case_id=case_id,
            edge_kind=stimulus,
            preflight_jsonl=preflight_jsonl,
        )
    elif stimulus == "remote_disabled":
        observation = observe_remote_disabled(
            case_id=case_id,
            analysis_config=case / "analysis_config.json",
            crystal_manifest=case / "preflight_bundle/crystal_manifest.json",
            request_count=0,
        )
    elif stimulus == "remote_rate_limited":
        observation = observe_rate_limit_fixture(
            case_id=case_id,
            analysis_config=case / "analysis_config.json",
            crystal_manifest=case / "preflight_bundle/crystal_manifest.json",
            fault_control=case / "fault_control.json",
        )
    else:
        path = case / "preflight_bundle/phenix_edge_observation.json"
        if path.is_file():
            observation = M6EdgeObservation.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            evidence = observation.evidence
            isolated = case / "preflight_bundle/isolated_missing_phenix_manifest.json"
            bundle = _json_object(
                case / "preflight_bundle/bundle_manifest.json",
                "preflight bundle manifest",
            )
            outputs = bundle.get("output_sha256") if isinstance(bundle, dict) else None
            if (
                not isinstance(evidence, M6PhenixValidationEvidence)
                or not isolated.is_file()
                or sha256_file(isolated) != evidence.isolated_manifest_sha256
                or not isinstance(outputs, dict)
                or outputs.get("phenix_edge_observation") != sha256_file(path)
                or outputs.get("isolated_phenix_manifest") != sha256_file(isolated)
            ):
                raise ValueError("M6 preflight bundle does not bind Phenix evidence")
        else:
            observation = make_edge_observation(
                case_id=case_id,
                edge_kind="missing_phenix",
                evidence=M6UnavailableEdgeEvidence(
                    evidence_kind="unavailable",
                    reason_code="phenix_validation_observation_missing",
                ),
            )
    return verify_edge_observations(case_id, (observation,))


def verify_edge_observations(
    case_id: str, observations: Iterable[M6EdgeObservation]
) -> tuple[M6EdgeObservation, ...]:
    """Return a canonical unique tuple and reject cross-case evidence."""

    ordered = tuple(sorted(observations, key=lambda item: item.edge_kind))
    if any(item.case_id != case_id for item in ordered):
        raise ValueError("M6 edge observation belongs to another case")
    kinds = tuple(item.edge_kind for item in ordered)
    if tuple(sorted(set(kinds))) != kinds:
        raise ValueError("M6 edge observations must be unique and sorted")
    return ordered
