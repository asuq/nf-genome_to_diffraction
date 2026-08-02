"""Tests for safe HPC configuration and identifier contracts."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.hpc.models import (
    ConfigurationError,
    HpcConfig,
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
    assert config.local_state_root == repository.resolve() / ".untracked" / "hpc-test"
    assert config.ssh_alias == "marmic"


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
    assert validate_run_id(valid) == valid
    assert validate_run_id(valid_p0) == valid_p0
    assert validate_profile("smoke") == "smoke"
    assert validate_profile("p0") == "p0"
    assert validate_log_lines(2_000) == 2_000
    with pytest.raises(ValidationError):
        validate_run_id("../../unrelated")
    with pytest.raises(ValidationError):
        validate_log_lines(2_001)
    with pytest.raises(ValidationError):
        validate_profile("p0;touch-bad")
