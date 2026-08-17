"""Tests for safe HPC configuration and identifier contracts."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.hpc.models import (
    ConfigurationError,
    HpcConfig,
    LocalRunRecord,
    ValidationError,
    validate_log_lines,
    validate_profile,
    validate_run_id,
)


def _configuration(repository: Path) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "repository": str(repository),
        "ssh_alias": "marmic",
        "remote_dispatcher": "/approved/root/_tooling/nf-gtd-hpc-remote",
        "local_state_root": str(repository / ".untracked" / "hpc-test"),
    }


def test_configuration_loads_only_the_repository_specific_layout(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository with spaces"
    repository.mkdir()
    (repository / ".git").mkdir()
    path = tmp_path / "config.json"
    path.write_text(json.dumps(_configuration(repository)), encoding="utf-8")

    config = HpcConfig.load(path)

    assert config.repository == repository.resolve()
    assert config.site_id == "marmic"
    assert config.local_state_root == repository.resolve() / ".untracked" / "hpc-test"
    assert config.ssh_alias == "marmic"
    assert config.database_execution_timeout_seconds == 24 * 60 * 60


def test_viper_configuration_requires_explicit_site_identity(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()
    raw = _configuration(repository)
    raw.update(
        {
            "schema_version": "1.1",
            "site_id": "viper-cpu",
            "ssh_alias": "viper-cpu",
            "remote_dispatcher": (
                "/viper/u1/test-user/.local/libexec/nf-gtd/nf-gtd-hpc-remote"
            ),
        }
    )
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    config = HpcConfig.load(path)

    assert config.site_id == "viper-cpu"
    assert config.ssh_alias == "viper-cpu"


def test_schema_1_1_rejects_missing_site_identity(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()
    raw = _configuration(repository)
    raw["schema_version"] = "1.1"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="requires site_id"):
        HpcConfig.load(path)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ssh_alias", "marmic;touch-bad"),
        ("remote_dispatcher", "/approved/root/../bad/nf-gtd-hpc-remote"),
        ("remote_dispatcher", "/approved/root/_tooling/other"),
        ("local_state_root", "/tmp/unrelated"),
    ],
)
def test_configuration_rejects_authority_expansion(
    tmp_path: Path, key: str, value: str
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()
    raw = _configuration(repository)
    raw[key] = value
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ConfigurationError):
        HpcConfig.load(path)


def test_run_and_log_identifiers_are_bounded() -> None:
    valid = "gtd-smoke-20260802T120000Z-0123456789ab-01234567"
    valid_p0 = "gtd-p0-20260802T120000Z-0123456789ab-01234567"
    valid_p1 = "gtd-p1-20260802T120000Z-0123456789ab-01234567"
    valid_p2 = "gtd-p2-20260802T120000Z-0123456789ab-01234567"
    valid_p2_diverse = "gtd-p2-diverse-20260802T120000Z-0123456789ab-01234567"
    valid_p2_control = "gtd-p2-control-20260802T120000Z-0123456789ab-01234567"
    valid_m4_copy = "gtd-m4-copy-20260802T120000Z-0123456789ab-01234567"
    valid_database = "gtd-database-20260802T120000Z-0123456789ab-01234567"
    assert validate_run_id(valid) == valid
    assert validate_run_id(valid_p0) == valid_p0
    assert validate_run_id(valid_p1) == valid_p1
    assert validate_run_id(valid_p2) == valid_p2
    assert validate_run_id(valid_p2_diverse) == valid_p2_diverse
    assert validate_run_id(valid_p2_control) == valid_p2_control
    assert validate_run_id(valid_m4_copy) == valid_m4_copy
    assert validate_run_id(valid_database) == valid_database
    assert validate_profile("smoke") == "smoke"
    assert validate_profile("p0") == "p0"
    assert validate_profile("p1") == "p1"
    assert validate_profile("p2") == "p2"
    assert validate_profile("p2-diverse") == "p2-diverse"
    assert validate_profile("p2-control") == "p2-control"
    assert validate_profile("m6-nextflow-smoke") == "m6-nextflow-smoke"
    assert validate_profile("m4-copy") == "m4-copy"
    assert validate_profile("database") == "database"
    assert validate_log_lines(2_000) == 2_000
    with pytest.raises(ValidationError):
        validate_run_id("../../unrelated")
    with pytest.raises(ValidationError):
        validate_log_lines(2_001)
    with pytest.raises(ValidationError):
        validate_profile("p0;touch-bad")


def test_database_wait_limit_is_strictly_bounded(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()
    raw = _configuration(repository)
    raw["database_execution_timeout_seconds"] = 24 * 60 * 60 + 1
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="between"):
        HpcConfig.load(path)


def test_legacy_run_records_are_marmic_only() -> None:
    record = LocalRunRecord.from_json(
        {
            "schema_version": "1.0",
            "run_id": "gtd-smoke-20260802T120000Z-0123456789ab-01234567",
            "commit": "1" * 40,
            "owner_id": "2" * 32,
            "profile": "smoke",
            "iteration": 1,
            "parent_run_id": None,
            "failure_signature": None,
        }
    )

    assert record.site_id == "marmic"
