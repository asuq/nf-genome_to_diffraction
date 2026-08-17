"""Focused regressions for observed, checksum-bound M6 edge evidence."""

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from genome_to_diffraction.benchmarks.m6_edge import (
    M6EdgeObservation,
    M6HttpRateLimitEvidence,
    M6ModelExhaustionEvidence,
    M6PhenixValidationEvidence,
    M6RemoteGuardEvidence,
    make_edge_observation,
    observe_isolated_missing_phenix,
    observe_matthews,
    observe_missing_model,
    observe_mtz_preflight,
    observe_rate_limit_fixture,
    observe_remote_disabled,
    verify_edge_observations,
    write_missing_model_stimulus,
)
from genome_to_diffraction.benchmarks.m6_nextflow import M6CaseEvidence
from genome_to_diffraction.benchmarks.m6_prepare import _fault_control
from genome_to_diffraction.benchmarks.m6_protocol import load_m6_protocol
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_text, sequence_digest
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MtzPreflightRecord,
    SequenceGroupRecord,
)

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "benchmarks/m6/protocol.yaml"


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _config(tmp_path: Path, *, remote_enabled: bool) -> Path:
    value = yaml.safe_load((ROOT / "examples/config.yaml").read_text(encoding="utf-8"))
    value["providers"]["esm_atlas"]["enabled"] = remote_enabled
    return _write_json(tmp_path / "config.json", value)


def _crystal(tmp_path: Path, *, consent: bool) -> Path:
    value = json.loads(
        (ROOT / "examples/crystal_manifest.json").read_text(encoding="utf-8")
    )
    value["crystals"][0]["allow_remote_sequence_submission"] = consent
    return _write_json(tmp_path / "crystal.json", value)


def _preflight(**updates: object) -> MtzPreflightRecord:
    value = json.loads(
        (ROOT / "tests/fixtures/stubs/mtz_preflight.jsonl").read_text(encoding="utf-8")
    )
    value.update(updates)
    return MtzPreflightRecord.model_validate(value)


def _write_preflight(path: Path, record: MtzPreflightRecord) -> Path:
    path.write_text(f"{canonical_json_text(record)}\n", encoding="utf-8")
    return path


def _group(sequence: str) -> SequenceGroupRecord:
    digest = sequence_digest(sequence)
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=10_000.0,
        mass_method="test",
        residue_policy="test",
        source_record_count=1,
    )


def _matthews(
    group: SequenceGroupRecord, *, copy_count: int, rank: int
) -> MatthewsHypothesis:
    return MatthewsHypothesis(
        schema_version="1.0",
        hypothesis_id=f"matthews_{group.sha256}_{copy_count}",
        crystal_id="M6C053",
        sequence_group_id=group.sequence_group_id,
        copy_count=copy_count,
        sequence_mass_da=10_000.0,
        total_mass_da=10_000.0 * copy_count,
        v_asu_a3=100_000.0,
        matthews_coefficient=10.0 / copy_count,
        solvent_fraction=0.5,
        matthews_prior=1.0 / rank,
        prior_backend="test",
        rank_within_candidate=rank,
        retained=True,
        physical_status="plausible",
        sds_page_nearest_band_kda=1.0,
        sds_page_absolute_difference_kda=9.0,
        sds_page_fractional_difference=9.0,
        sds_page_prior_label="weak",
    )


def test_edge_observation_rejects_status_checksum_and_content_id_tampering() -> None:
    evidence = M6RemoteGuardEvidence(
        evidence_kind="remote_guard",
        analysis_config_sha256="1" * 64,
        crystal_manifest_sha256="2" * 64,
        provider_enabled=False,
        consent_allowed=False,
        authorisation_denied=True,
        authorisation_failure_code="run_remote_disabled",
        request_count=0,
    )
    observation = make_edge_observation(
        case_id="M6C061",
        edge_kind="remote_disabled",
        evidence=evidence,
    )
    assert observation.measurement_status == "measured"

    raw = observation.model_dump(mode="json")
    raw["measurement_status"] = "contradicted"
    with pytest.raises(ValidationError, match="status contradicts"):
        M6EdgeObservation.model_validate(raw)
    raw = observation.model_dump(mode="json")
    raw["evidence_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="checksum changed"):
        M6EdgeObservation.model_validate(raw)
    raw = observation.model_dump(mode="json")
    raw["observation_id"] = "m6edge_tampered"
    with pytest.raises(ValidationError, match="identifier changed"):
        M6EdgeObservation.model_validate(raw)


def test_fault_controls_select_all_edge_stimuli_without_declaring_outcomes() -> None:
    protocol = load_m6_protocol(PROTOCOL)
    edge_kinds = {
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
    observed: set[str] = set()
    for case in protocol.cases:
        if case.case_kind not in edge_kinds:
            continue
        control = _fault_control(case)
        assert control is not None
        assert control["edge_stimulus"] == case.case_kind
        assert "typed_outcome" not in control
        assert "scientific_status" not in control
        observed.add(case.case_kind)
    assert observed == edge_kinds


def test_remote_disabled_calls_the_two_level_authorisation_guard(
    tmp_path: Path,
) -> None:
    observation = observe_remote_disabled(
        case_id="M6C061",
        analysis_config=_config(tmp_path, remote_enabled=False),
        crystal_manifest=_crystal(tmp_path, consent=False),
        request_count=0,
    )
    assert observation.measurement_status == "measured"
    evidence = observation.evidence
    assert isinstance(evidence, M6RemoteGuardEvidence)
    assert evidence.authorisation_denied is True
    assert evidence.authorisation_failure_code == "run_remote_disabled"

    contradiction = observe_remote_disabled(
        case_id="M6C061",
        analysis_config=_config(tmp_path, remote_enabled=True),
        crystal_manifest=_crystal(tmp_path, consent=True),
        request_count=1,
    )
    assert contradiction.measurement_status == "contradicted"


def test_rate_limit_requires_a_parsed_429_and_retry_after(tmp_path: Path) -> None:
    config = _config(tmp_path, remote_enabled=True)
    crystal = _crystal(tmp_path, consent=True)
    fixture = "\r\n".join(
        (
            "HTTP/1.1 429 Too Many Requests",
            "Retry-After: 17",
            "Content-Length: 0",
            "",
            "",
        )
    )
    fault = _write_json(
        tmp_path / "fault.json",
        {"schema_version": "1.0", "local_http_response": fixture},
    )
    observed = observe_rate_limit_fixture(
        case_id="M6C062",
        analysis_config=config,
        crystal_manifest=crystal,
        fault_control=fault,
    )
    assert observed.measurement_status == "measured"
    assert isinstance(observed.evidence, M6HttpRateLimitEvidence)
    assert observed.evidence.http_status_code == 429
    assert observed.evidence.retry_after_seconds == 17

    _write_json(
        fault,
        {
            "schema_version": "1.0",
            "local_http_response": ("HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"),
        },
    )
    contradicted = observe_rate_limit_fixture(
        case_id="M6C062",
        analysis_config=config,
        crystal_manifest=crystal,
        fault_control=fault,
    )
    assert contradicted.measurement_status == "contradicted"

    _write_json(fault, {"schema_version": "1.0"})
    unavailable = observe_rate_limit_fixture(
        case_id="M6C062",
        analysis_config=config,
        crystal_manifest=crystal,
        fault_control=fault,
    )
    assert unavailable.measurement_status == "unavailable"


def test_preflight_edges_are_derived_from_candidates_selection_and_warnings(
    tmp_path: Path,
) -> None:
    equivalent = _preflight(
        observation_candidates=["IX,SIGIX", "IY,SIGIY"],
        selected_observation_labels="IX,SIGIX",
        warning_codes=[
            "equivalent_observation_arrays",
            "observation_selection_deterministic",
        ],
    )
    path = _write_preflight(tmp_path / "preflight.jsonl", equivalent)
    observed = observe_mtz_preflight(
        case_id="M6C059",
        edge_kind="ambiguous_columns_equivalent",
        preflight_jsonl=path,
    )
    assert observed.measurement_status == "measured"

    contradicted = equivalent.model_copy(
        update={"warning_codes": ("observation_selection_deterministic",)}
    )
    _write_preflight(path, contradicted)
    mismatch = observe_mtz_preflight(
        case_id="M6C059",
        edge_kind="ambiguous_columns_equivalent",
        preflight_jsonl=path,
    )
    assert mismatch.measurement_status == "contradicted"

    map_only = _preflight(
        selected_observation_labels=None,
        selected_observation_type=None,
        observation_candidates=[],
        warning_codes=["no_observed_data"],
        decision="fail",
        execution_status="failed_input_contract",
        available_columns=[],
    )
    _write_preflight(path, map_only)
    assert (
        observe_mtz_preflight(
            case_id="M6C057",
            edge_kind="map_only_mtz",
            preflight_jsonl=path,
        ).measurement_status
        == "measured"
    )

    conflicting = map_only.model_copy(
        update={
            "observation_candidates": ("IX,SIGIX", "IY,SIGIY"),
            "warning_codes": ("ambiguous_observation_arrays",),
        }
    )
    _write_preflight(path, conflicting)
    assert (
        observe_mtz_preflight(
            case_id="M6C060",
            edge_kind="ambiguous_columns_conflicting",
            preflight_jsonl=path,
        ).measurement_status
        == "measured"
    )


def test_matthews_evidence_is_reduced_per_sequence_group_and_truthless(
    tmp_path: Path,
) -> None:
    first = _group("AAAA")
    second = _group("CCCC")
    rows = (
        _matthews(first, copy_count=1, rank=1),
        _matthews(first, copy_count=2, rank=2),
        _matthews(second, copy_count=1, rank=1),
    )
    path = tmp_path / "matthews.jsonl"
    path.write_text(
        "".join(f"{canonical_json_text(row)}\n" for row in rows),
        encoding="utf-8",
    )
    observed = observe_matthews(
        case_id="M6C053",
        edge_kind="wrong_sds_mass",
        matthews_jsonl=path,
        sequence_groups=(second, first),
    )
    assert observed.measurement_status == "measured"
    evidence = observed.evidence
    assert evidence.evidence_kind == "matthews"
    assert len(evidence.candidate_summaries) == 2
    first_summary = next(
        item
        for item in evidence.candidate_summaries
        if item.sequence_sha256 == first.sha256
    )
    assert [item.copy_count for item in first_summary.retained_hypotheses] == [1, 2]
    assert "target" not in json.dumps(observed.model_dump(mode="json"))


def test_missing_model_requires_checksum_verified_empty_route(tmp_path: Path) -> None:
    case = tmp_path / "case"
    selected = case / "selected-candidates"
    selected.mkdir(parents=True)
    hits = selected / "accepted_structural_hits.jsonl"
    hits.write_text('{"hit":"stimulus input"}\n', encoding="utf-8")
    write_missing_model_stimulus(
        accepted_hits=hits,
        output_directory=case / "missing-model-stimulus",
    )
    route_manifest = case / "missing-model-stimulus/model_route_manifest.json"
    _write_json(
        case / "bundle_manifest.json",
        {"output_sha256": {"missing_model_route": sha256_file(route_manifest)}},
    )
    observed = observe_missing_model(
        case_id="M6C051",
        case_bundle=case,
        hypothesis_count=0,
    )
    assert observed.measurement_status == "measured"
    assert isinstance(observed.evidence, M6ModelExhaustionEvidence)
    assert observed.evidence.accepted_hit_count == 0

    (case / "missing-model-stimulus/accepted_hits.jsonl").write_text(
        "changed\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="checksums changed"):
        observe_missing_model(
            case_id="M6C051",
            case_bundle=case,
            hypothesis_count=0,
        )


def test_missing_phenix_requires_an_actual_isolated_validation_failure(
    tmp_path: Path,
) -> None:
    source = json.loads(
        (ROOT / "tests/fixtures/stubs/phenix_install_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    source["status"] = "verified"
    source["required_commands"][0]["smoke_test_status"] = "passed"
    supplied = _write_json(tmp_path / "supplied.json", source)
    observed = observe_isolated_missing_phenix(
        case_id="M6C063",
        supplied_manifest=supplied,
        isolated_manifest=tmp_path / "isolated.json",
    )
    assert observed.measurement_status == "measured"
    assert isinstance(observed.evidence, M6PhenixValidationEvidence)
    assert observed.evidence.validation_succeeded is False
    assert observed.evidence.supplied_manifest_sha256 == sha256_file(supplied)


def test_case_contract_requires_unique_case_bound_edge_observations() -> None:
    assert "edge_observations" in M6CaseEvidence.model_json_schema()["required"]
    evidence = M6RemoteGuardEvidence(
        evidence_kind="remote_guard",
        analysis_config_sha256="1" * 64,
        crystal_manifest_sha256="2" * 64,
        provider_enabled=False,
        consent_allowed=False,
        authorisation_denied=True,
        authorisation_failure_code="run_remote_disabled",
        request_count=0,
    )
    first = make_edge_observation(
        case_id="M6C061", edge_kind="remote_disabled", evidence=evidence
    )
    with pytest.raises(ValueError, match="unique and sorted"):
        verify_edge_observations("M6C061", (first, first))
    with pytest.raises(ValueError, match="another case"):
        verify_edge_observations("M6C062", (first,))


def test_direct_rate_limit_contract_rejects_a_claimed_success_without_429() -> None:
    evidence = M6HttpRateLimitEvidence(
        evidence_kind="http_rate_limit",
        analysis_config_sha256="1" * 64,
        crystal_manifest_sha256="2" * 64,
        fault_control_sha256="3" * 64,
        fixture_sha256="4" * 64,
        provider_enabled=True,
        consent_allowed=True,
        request_count=1,
        http_status_code=200,
        retry_after_seconds=None,
    )
    observation = make_edge_observation(
        case_id="M6C062",
        edge_kind="remote_rate_limited",
        evidence=evidence,
    )
    assert observation.measurement_status == "contradicted"
