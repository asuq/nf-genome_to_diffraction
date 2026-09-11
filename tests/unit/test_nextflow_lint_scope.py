"""Keep ignored generated repositories out of the actual source syntax gate."""

import subprocess
from collections.abc import Sequence

import pytest

from tests.scripts import check_nextflow


def test_syntax_gate_keeps_defaults_and_excludes_only_local_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []

    def record(
        command: Sequence[str],
        *,
        environment: dict[str, str],
        expected_success: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(tuple(command))
        assert environment["NXF_SYNTAX_PARSER"] == "v2"
        assert expected_success
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(check_nextflow, "_run", record)
    check_nextflow.check_syntax()
    assert len(commands) == 1
    command = commands[0]
    assert command[:2] == ("nextflow", "lint") and command[-1] == "."
    assert command[2:-1:2] == ("-exclude",) * 7
    assert command[3:-1:2] == (
        ".git",
        ".lineage",
        ".nextflow",
        ".nf-test",
        "nf-test.config",
        "work",
        ".untracked",
    )
