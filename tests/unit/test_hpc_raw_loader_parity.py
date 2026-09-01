"""Strict mutation parity for repository-owned HPC JSON state."""

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from genome_to_diffraction.hpc.client import (
    _failure_signature,
    _json_mapping,
    _jsonl_mappings,
    _validate_inspectable_review_result,
)
from genome_to_diffraction.hpc.m4_import import _load_object as load_m4_object
from genome_to_diffraction.hpc.models import (
    FailureClass,
    HpcConfig,
    HpcInterfaceError,
    RemoteOperationError,
    load_local_run,
)
from genome_to_diffraction.hpc.p0_inputs import _load_spec

PathLoader = Callable[[Path], object]

_RUN_ID = "gtd-smoke-20260819T000000Z-aaaaaaaaaaaa-bbbbbbbb"
_PATH_LOADERS: tuple[tuple[str, PathLoader], ...] = (
    ("hpc-config", HpcConfig.load),
    ("client-mapping", lambda path: _json_mapping(path, "fixture")),
    ("client-jsonl", lambda path: _jsonl_mappings(path, "fixture")),
    (
        "inspectable-result",
        lambda path: _validate_inspectable_review_result(path, "fixture"),
    ),
    ("m4-import", lambda path: load_m4_object(path, "fixture")),
)


def _contents(mutation: str) -> str:
    return (
        '{"root":{"value":1,"value":2}}\n'
        if mutation == "duplicate"
        else '{"root":{"value":NaN}}\n'
    )


@pytest.mark.parametrize(("loader_name", "loader"), _PATH_LOADERS)
@pytest.mark.parametrize("mutation", ("duplicate", "non-finite"))
def test_hpc_json_loaders_reject_ambiguous_numeric_documents(
    tmp_path: Path,
    loader_name: str,
    loader: PathLoader,
    mutation: str,
) -> None:
    path = tmp_path / f"{loader_name}-{mutation}.json"
    path.write_text(_contents(mutation), encoding="utf-8")

    with pytest.raises(HpcInterfaceError) as captured:
        loader(path)

    assert str(path) in str(captured.value)
    assert "/root/value" in str(captured.value)
    expected = "duplicate mapping key" if mutation == "duplicate" else "numeric"
    assert expected in str(captured.value)


@pytest.mark.parametrize("mutation", ("duplicate", "non-finite"))
def test_local_run_loader_rejects_ambiguous_numeric_documents(
    tmp_path: Path, mutation: str
) -> None:
    path = tmp_path / _RUN_ID / "run.json"
    path.parent.mkdir()
    path.write_text(_contents(mutation), encoding="utf-8")

    with pytest.raises(HpcInterfaceError) as captured:
        load_local_run(tmp_path, _RUN_ID)

    assert str(path) in str(captured.value)
    assert "/root/value" in str(captured.value)


@pytest.mark.parametrize("mutation", ("duplicate", "non-finite"))
def test_p0_spec_loader_rejects_ambiguous_numeric_documents(
    tmp_path: Path, mutation: str
) -> None:
    path = tmp_path / f"p0-{mutation}.json"
    path.write_text(_contents(mutation), encoding="utf-8")
    confirmation = hashlib.sha256(path.read_bytes()).hexdigest()

    with pytest.raises(HpcInterfaceError) as captured:
        _load_spec(path, confirmation)

    assert str(path) in str(captured.value)
    assert "/root/value" in str(captured.value)


@pytest.mark.parametrize("mutation", ("duplicate", "non-finite"))
def test_failure_signature_rejects_ambiguous_job_result(
    tmp_path: Path, mutation: str
) -> None:
    result = tmp_path / "state" / "job-result.json"
    result.parent.mkdir()
    result.write_text(_contents(mutation), encoding="utf-8")

    with pytest.raises(
        RemoteOperationError, match=r"job-result\.json is invalid"
    ) as error:
        _failure_signature(tmp_path)

    assert error.value.failure_class == FailureClass.TRANSFER_FAILURE
    assert error.value.__cause__ is not None
    assert "/root/value" in str(error.value.__cause__)
