"""Tests for approved fixed-parent, one-additional-copy Phaser execution."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.mr import (
    AddCopyRunRequest,
    PhaserInputError,
    run_additional_copy_phaser,
)
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    PhenixInstallManifest,
    PrototypeProfile,
)
from genome_to_diffraction.schemas.results import (
    AdditionalCopyResult,
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    MtzPreflightRecord,
    NormalisedMrResult,
)
from genome_to_diffraction.status import ExecutionStatus

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"
PHASER_FIXTURES = REPOSITORY / "tests/fixtures/phaser"
SEQUENCE_GROUP_ID = (
    "seq_f50b9a1db8767fb7cdc8b89cf1a78c9fac1e0e2d5bb5367aeec14709396d5c5e"
)
HYPOTHESIS_ID = "mrhyp_" + "d" * 64
SEED_ID = "sol_" + "a" * 64
REVIEW_ID = "rev_" + "b" * 64
PACKAGE_ID = "reviewpkg_" + "c" * 64
POSITIVE_LOG = (PHASER_FIXTURES / "phenix_2_1_positive.log").read_text(encoding="utf-8")
NO_SOLUTION_LOG = (PHASER_FIXTURES / "phenix_2_1_no_solution_packing.log").read_text(
    encoding="utf-8"
)


def _manifest() -> PhenixInstallManifest:
    model = load_contract(
        STUBS / "phenix_install_manifest.json",
        "phenix-install-manifest",
        progress=False,
    )
    assert isinstance(model, PhenixInstallManifest)
    return model


def _request(
    tmp_path: Path,
    *,
    parent_status: ExecutionStatus = ExecutionStatus.COMPLETED_HIT,
    parent_packed: bool = True,
    parent_copy_count: int = 1,
) -> AddCopyRunRequest:
    package = tmp_path / "review package"
    assets = package / "assets" / SEED_ID
    assets.mkdir(parents=True)
    parent = assets / "solution.pdb"
    parent.write_text(
        "REMARK Log-Likelihood Gain: 27.0\n"
        "REMARK ENSEMBLE ense_1 EULER 1 2 3 FRAC 0.1 0.2 0.3\n"
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  "
        "1.00 20.00           C\n",
        encoding="utf-8",
    )
    parent_result = NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=HYPOTHESIS_ID,
        tool_version="Phenix 2.1-6048; Phaser 2.8.4",
        execution_status=parent_status,
        llg=27.0,
        tfz=5.1,
        placed_copy_count=parent_copy_count,
        packing_summary={"top_solution_packed": parent_packed},
        solution_coordinate_path="solution.pdb",
        solution_coordinate_sha256=sha256_file(parent),
        output_mtz_path="solution.mtz",
        output_mtz_sha256="0" * 64,
        raw_log_pointer="phaser.log",
    )
    result_path = assets / "normalised_mr_result.jsonl"
    result_path.write_text(f"{canonical_json_text(parent_result)}\n", encoding="utf-8")
    model = tmp_path / "search model.pdb"
    model.write_text("ATOM\n", encoding="utf-8")
    command_path = assets / "phaser_command.json"
    command_path.write_text(
        json.dumps(
            {
                "model_sha256": sha256_file(model),
                "model_identity_percent": 85.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    copied = {
        "solution_coordinate": f"assets/{SEED_ID}/solution.pdb",
        "normalised_result": f"assets/{SEED_ID}/normalised_mr_result.jsonl",
        "command": f"assets/{SEED_ID}/phaser_command.json",
    }
    manifest_path = package / "mr_seed_review_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "package_id": PACKAGE_ID,
                "items": [
                    {
                        "solution_id": SEED_ID,
                        "hypothesis_id": HYPOTHESIS_ID,
                        "copied_assets": copied,
                        "copied_asset_sha256": {
                            "solution_coordinate": sha256_file(parent),
                            "normalised_result": sha256_file(result_path),
                            "command": sha256_file(command_path),
                        },
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    validation = tmp_path / "validated approvals.json"
    validation.write_text(
        json.dumps(
            {
                "review_id": REVIEW_ID,
                "checkpoint": "mr_seed",
                "package_id": PACKAGE_ID,
                "package_manifest_sha256": sha256_file(manifest_path),
                "approved_solution_ids": [SEED_ID],
                "execution_status": "completed_success",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    hypothesis = MrHypothesis(
        schema_version="1.0",
        hypothesis_id=HYPOTHESIS_ID,
        crystal_id="test_crystal_01",
        sequence_group_id=SEQUENCE_GROUP_ID,
        model_id="model_" + "d" * 64,
        copy_count_expected=3,
        copy_number_to_search=1,
        fixed_solution_id=None,
        space_group="P 21 21 21",
        obs_labels="I,SIGI",
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=PrototypeProfile.PILOT,
        status=MrHypothesisStatus.QUEUED,
    )
    hypotheses = tmp_path / "hypotheses.jsonl"
    hypotheses.write_text(f"{canonical_json_text(hypothesis)}\n", encoding="utf-8")
    mtz = tmp_path / "data.mtz"
    mtz.write_bytes(b"synthetic MTZ")
    stub_preflight = MtzPreflightRecord.model_validate_json(
        (STUBS / "mtz_preflight.jsonl").read_text(encoding="utf-8")
    )
    preflight = stub_preflight.model_copy(
        update={"mtz_sha256": hashlib.sha256(mtz.read_bytes()).hexdigest()}
    )
    preflights = tmp_path / "preflight.jsonl"
    preflights.write_text(f"{canonical_json_text(preflight)}\n", encoding="utf-8")
    return AddCopyRunRequest(
        review_validation_json=validation,
        review_package_manifest=manifest_path,
        seed_solution_id=SEED_ID,
        hypotheses_jsonl=hypotheses,
        sequence_groups_jsonl=STUBS / "sequence_groups.jsonl",
        preflight_jsonl=preflights,
        mtz=mtz,
        search_model=model,
        phenix_manifest=STUBS / "phenix_install_manifest.json",
        output_directory=tmp_path / "add copy output",
        threads=8,
        progress=False,
    )


def _fake_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    log_text: str,
    write_solution: bool,
    placement_count: int = 2,
) -> None:
    def fake_validate(path: Path) -> PhenixInstallManifest:
        del path
        return _manifest()

    def fake_capture(
        manifest_path: Path,
        arguments: list[str],
        *,
        working_directory: Path,
        timeout_seconds: float | None,
    ) -> subprocess.CompletedProcess[bytes]:
        del manifest_path, timeout_seconds
        assert arguments[0] == "phenix.phaser"
        parameters = Path(arguments[1]).read_text(encoding="utf-8")
        assert "solution_at_origin = True" in parameters
        assert "model_id = search_copy" in parameters
        assert "copies = 1" in parameters
        assert "jobs = 8" in parameters
        assert 'pdb = "' in parameters
        assert 'hklin = "' in parameters
        (working_directory / "PHASER.log").write_text(log_text, encoding="utf-8")
        if write_solution:
            placements = "".join(
                f"REMARK ENSEMBLE copy_{index} EULER 0 0 0 FRAC 0 0 0\n"
                for index in range(1, placement_count + 1)
            )
            (working_directory / "PHASER.1.pdb").write_text(
                placements + "ATOM\n",
                encoding="utf-8",
            )
            (working_directory / "PHASER.1.mtz").write_bytes(b"result MTZ")
        return subprocess.CompletedProcess(arguments, 0, b"capture\n", b"")

    monkeypatch.setattr(
        "genome_to_diffraction.mr.add_copy.validate_manifest_environment",
        fake_validate,
    )
    monkeypatch.setattr(
        "genome_to_diffraction.mr.add_copy.capture_from_manifest", fake_capture
    )


def test_packed_additional_copy_advances_child_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    _fake_runtime(monkeypatch, log_text=POSITIVE_LOG, write_solution=True)

    output = run_additional_copy_phaser(request)

    assert output.result.execution_status == "completed_hit"
    assert output.result.additional_copy_supported is True
    assert output.result.parent_copy_count == 1
    assert output.result.best_supported_copy_count == 2
    assert output.result.phaser_placement_count == 2
    assert output.result.parent_retained is True
    assert output.result.failed_addition_proves_absence is False
    assert output.result.llg_delta_from_parent == pytest.approx(1622.91 - 27.0)
    assert output.result.child_solution_id is not None


def test_approved_packed_no_hit_parent_can_advance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path, parent_status=ExecutionStatus.COMPLETED_NO_HIT)
    _fake_runtime(monkeypatch, log_text=POSITIVE_LOG, write_solution=True)

    result = run_additional_copy_phaser(request).result

    assert result.execution_status == "completed_hit"
    assert result.additional_copy_supported is True
    assert result.parent_copy_count == 1
    assert result.best_supported_copy_count == 2


def test_supported_copy_two_advances_to_copy_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_request = _request(tmp_path)
    child_directory = tmp_path / "copy two"
    child_coordinate = child_directory / "PHASER.1.pdb"
    child_directory.mkdir()
    child_coordinate.write_text(
        "REMARK ENSEMBLE copy_1 EULER 0 0 0 FRAC 0 0 0\n"
        "REMARK ENSEMBLE copy_2 EULER 0 0 0 FRAC 0 0 0\n"
        "ATOM\n",
        encoding="utf-8",
    )
    child_result = AdditionalCopyResult(
        schema_version="1.0",
        attempt_id="addcopy_" + "1" * 64,
        review_id=REVIEW_ID,
        seed_solution_id=SEED_ID,
        parent_solution_id=SEED_ID,
        child_solution_id="copystate_" + "2" * 64,
        hypothesis_id=HYPOTHESIS_ID,
        sequence_group_id=SEQUENCE_GROUP_ID,
        parent_copy_count=1,
        attempted_copy_number=2,
        expected_copy_count=3,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        llg=100.0,
        tfz=8.0,
        phaser_placement_count=2,
        top_solution_packed=True,
        additional_copy_supported=True,
        best_supported_copy_count=2,
        output_coordinate_path=child_coordinate.name,
        output_coordinate_sha256=sha256_file(child_coordinate),
        output_mtz_path="PHASER.1.mtz",
        output_mtz_sha256="3" * 64,
        raw_log_pointer="PHASER.log",
        command_pointer="phaser_command.json",
    )
    child_result_path = child_directory / "additional_copy_result.jsonl"
    child_result_path.write_text(
        f"{canonical_json_text(child_result)}\n", encoding="utf-8"
    )
    request = AddCopyRunRequest(
        **{
            **first_request.__dict__,
            "output_directory": tmp_path / "copy three",
            "parent_result_jsonl": child_result_path,
            "parent_coordinate": child_coordinate,
        }
    )
    _fake_runtime(
        monkeypatch,
        log_text=POSITIVE_LOG,
        write_solution=True,
        placement_count=3,
    )

    result = run_additional_copy_phaser(request).result

    assert result.parent_solution_id == child_result.child_solution_id
    assert result.parent_copy_count == 2
    assert result.attempted_copy_number == 3
    assert result.best_supported_copy_count == 3
    assert result.phaser_placement_count == 3
    assert result.llg_delta_from_parent == pytest.approx(1622.91 - 100.0)
    command = json.loads(
        (request.output_directory / "phaser_command.json").read_text(encoding="utf-8")
    )
    assert command["parent_solution_id"] == child_result.child_solution_id
    assert command["parent_copy_count"] == 2
    assert command["parent_result_sha256"] == sha256_file(child_result_path)


def test_copy_three_refuses_to_advance_beyond_expected_count(tmp_path: Path) -> None:
    request = _request(tmp_path)
    parent_coordinate = tmp_path / "complete-parent.pdb"
    parent_coordinate.write_text("ATOM\n", encoding="utf-8")
    parent_result = AdditionalCopyResult(
        schema_version="1.0",
        attempt_id="addcopy_" + "4" * 64,
        review_id=REVIEW_ID,
        seed_solution_id=SEED_ID,
        parent_solution_id="copystate_" + "5" * 64,
        child_solution_id="copystate_" + "6" * 64,
        hypothesis_id=HYPOTHESIS_ID,
        sequence_group_id=SEQUENCE_GROUP_ID,
        parent_copy_count=2,
        attempted_copy_number=3,
        expected_copy_count=3,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        phaser_placement_count=3,
        top_solution_packed=True,
        additional_copy_supported=True,
        best_supported_copy_count=3,
        output_coordinate_path=parent_coordinate.name,
        output_coordinate_sha256=sha256_file(parent_coordinate),
        output_mtz_path="PHASER.1.mtz",
        output_mtz_sha256="7" * 64,
        raw_log_pointer="PHASER.log",
        command_pointer="phaser_command.json",
    )
    parent_result_path = tmp_path / "complete-parent.jsonl"
    parent_result_path.write_text(
        f"{canonical_json_text(parent_result)}\n", encoding="utf-8"
    )
    sequential_request = AddCopyRunRequest(
        **{
            **request.__dict__,
            "parent_result_jsonl": parent_result_path,
            "parent_coordinate": parent_coordinate,
        }
    )

    with pytest.raises(PhaserInputError, match="no expected additional copy"):
        run_additional_copy_phaser(sequential_request)


def test_sequential_parent_coordinate_checksum_mismatch_fails(tmp_path: Path) -> None:
    request = _request(tmp_path)
    parent_coordinate = tmp_path / "changed-parent.pdb"
    parent_coordinate.write_text("ATOM\n", encoding="utf-8")
    parent_result = AdditionalCopyResult(
        schema_version="1.0",
        attempt_id="addcopy_" + "8" * 64,
        review_id=REVIEW_ID,
        seed_solution_id=SEED_ID,
        parent_solution_id=SEED_ID,
        child_solution_id="copystate_" + "9" * 64,
        hypothesis_id=HYPOTHESIS_ID,
        sequence_group_id=SEQUENCE_GROUP_ID,
        parent_copy_count=1,
        attempted_copy_number=2,
        expected_copy_count=3,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        phaser_placement_count=2,
        top_solution_packed=True,
        additional_copy_supported=True,
        best_supported_copy_count=2,
        output_coordinate_path=parent_coordinate.name,
        output_coordinate_sha256="a" * 64,
        output_mtz_path="PHASER.1.mtz",
        output_mtz_sha256="b" * 64,
        raw_log_pointer="PHASER.log",
        command_pointer="phaser_command.json",
    )
    parent_result_path = tmp_path / "changed-parent.jsonl"
    parent_result_path.write_text(
        f"{canonical_json_text(parent_result)}\n", encoding="utf-8"
    )
    sequential_request = AddCopyRunRequest(
        **{
            **request.__dict__,
            "parent_result_jsonl": parent_result_path,
            "parent_coordinate": parent_coordinate,
        }
    )

    with pytest.raises(PhaserInputError, match="not a supported child"):
        run_additional_copy_phaser(sequential_request)


def test_no_additional_solution_retains_parent_without_absence_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG, write_solution=False)

    result = run_additional_copy_phaser(request).result

    assert result.execution_status == "completed_no_hit"
    assert result.additional_copy_supported is False
    assert result.best_supported_copy_count == 1
    assert result.parent_solution_id == SEED_ID
    assert result.failed_addition_proves_absence is False
    assert result.rejection_reason == "phaser_reported_no_additional_solution"


def test_changed_search_model_fails_before_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    request.search_model.write_text("changed\n", encoding="utf-8")
    called = False

    def unexpected(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        nonlocal called
        del args, kwargs
        called = True
        raise AssertionError("runtime must not be called")

    monkeypatch.setattr(
        "genome_to_diffraction.mr.add_copy.capture_from_manifest", unexpected
    )
    with pytest.raises(PhaserInputError, match="search model checksum differs"):
        run_additional_copy_phaser(request)
    assert called is False


def test_changed_parent_result_fails_before_runtime(tmp_path: Path) -> None:
    request = _request(tmp_path)
    manifest = json.loads(request.review_package_manifest.read_text(encoding="utf-8"))
    relative = manifest["items"][0]["copied_assets"]["normalised_result"]
    parent_result = request.review_package_manifest.parent / relative
    parent_result.write_text("{}\n", encoding="utf-8")

    with pytest.raises(PhaserInputError, match="parent result checksum differs"):
        run_additional_copy_phaser(request)


@pytest.mark.parametrize(
    ("parent_status", "parent_packed", "parent_copy_count", "message"),
    [
        (
            ExecutionStatus.FAILED_PARSE,
            True,
            1,
            "successfully parsed parent",
        ),
        (
            ExecutionStatus.COMPLETED_NO_HIT,
            False,
            1,
            "exactly one packed placed copy",
        ),
        (
            ExecutionStatus.COMPLETED_HIT,
            True,
            2,
            "exactly one packed placed copy",
        ),
    ],
)
def test_unusable_parent_still_fails_before_runtime(
    tmp_path: Path,
    parent_status: ExecutionStatus,
    parent_packed: bool,
    parent_copy_count: int,
    message: str,
) -> None:
    request = _request(
        tmp_path,
        parent_status=parent_status,
        parent_packed=parent_packed,
        parent_copy_count=parent_copy_count,
    )

    with pytest.raises(PhaserInputError, match=message):
        run_additional_copy_phaser(request)


def test_nextflow_finishes_sibling_attempts_after_contract_failure() -> None:
    module = (REPOSITORY / "modules/local/run_additional_copy_phaser.nf").read_text(
        encoding="utf-8"
    )

    assert "errorStrategy 'finish'" in module
