"""Tests for deterministic typed bundles from disabled provider routes."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_text, sha256_file
from genome_to_diffraction.cli import main
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.schemas.io import load_contract, load_json_document
from genome_to_diffraction.schemas.providers import (
    ProviderExecutionPlan,
    ProviderKey,
    ProviderPlanEntry,
)
from genome_to_diffraction.status import ExecutionStatus
from genome_to_diffraction.structure_search.provider_empty import (
    DisabledProviderBundleError,
    DisabledProviderBundleRequest,
    emit_disabled_provider_bundle,
)

REPOSITORY = Path(__file__).resolve().parents[2]
PLAN = REPOSITORY / "examples/provider_plan.json"
SEQUENCES = REPOSITORY / "tests/fixtures/stubs/sequence_groups.jsonl"


def _plan() -> ProviderExecutionPlan:
    model = load_contract(PLAN, "provider-execution-plan", progress=False)
    assert isinstance(model, ProviderExecutionPlan)
    return model


def _write_entry(tmp_path: Path, provider: ProviderKey) -> Path:
    entry = next(item for item in _plan().entries if item.provider is provider)
    path = tmp_path / f"{provider.value}.json"
    atomic_write_text(path, f"{canonical_json_text(entry)}\n")
    return path


def _emit(tmp_path: Path, *, name: str = "bundle"):
    return emit_disabled_provider_bundle(
        DisabledProviderBundleRequest(
            provider_entry_json=_write_entry(tmp_path, ProviderKey.ESM_ATLAS),
            sequence_groups_jsonl=SEQUENCES,
            output_directory=tmp_path / name,
        )
    )


def test_disabled_provider_bundle_is_typed_total_and_checksum_bound(
    tmp_path: Path,
) -> None:
    output = _emit(tmp_path)

    assert output.results
    assert all(
        item.execution_status is ExecutionStatus.SKIPPED_POLICY
        and item.hit_count == 0
        and item.provider == "esm_atlas"
        for item in output.results
    )
    assert output.hits_jsonl.read_text(encoding="utf-8") == ""
    assert output.coordinate_sources_jsonl.read_text(encoding="utf-8") == ""
    manifest = load_json_document(output.search_manifest)
    assert isinstance(manifest, dict)
    assert manifest["provider"] == "esm_atlas"
    assert manifest["query_count"] == len(output.results)
    assert manifest["hit_count"] == 0
    outputs = manifest["outputs"]
    assert isinstance(outputs, dict)
    for payload in outputs.values():
        assert isinstance(payload, dict)
        path = output.search_manifest.parent / str(payload["path"])
        assert sha256_file(path, progress=False) == payload["sha256"]


def test_disabled_provider_bundle_is_byte_deterministic(tmp_path: Path) -> None:
    first = _emit(tmp_path / "first")
    second = _emit(tmp_path / "second")

    first_files = {
        path.relative_to(first.search_manifest.parent): path.read_bytes()
        for path in first.search_manifest.parent.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second.search_manifest.parent): path.read_bytes()
        for path in second.search_manifest.parent.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files


def test_enabled_provider_entry_is_rejected_before_output(tmp_path: Path) -> None:
    output = tmp_path / "must-not-exist"

    with pytest.raises(DisabledProviderBundleError, match="enabled, not disabled"):
        emit_disabled_provider_bundle(
            DisabledProviderBundleRequest(
                provider_entry_json=_write_entry(tmp_path, ProviderKey.PDB_SEQUENCE),
                sequence_groups_jsonl=SEQUENCES,
                output_directory=output,
            )
        )

    assert not output.exists()


def test_tampered_provider_entry_is_rejected_before_output(tmp_path: Path) -> None:
    entry = _write_entry(tmp_path, ProviderKey.ESM_ATLAS)
    document = json.loads(entry.read_text(encoding="utf-8"))
    document["disabled_reason"] = "tampered"
    entry.write_text(json.dumps(document) + "\n", encoding="utf-8")
    output = tmp_path / "must-not-exist"

    with pytest.raises(DisabledProviderBundleError, match="entry ID"):
        emit_disabled_provider_bundle(
            DisabledProviderBundleRequest(entry, SEQUENCES, output)
        )

    assert not output.exists()


def test_duplicate_sequence_groups_are_rejected_before_output(tmp_path: Path) -> None:
    sequences = tmp_path / "duplicate.jsonl"
    source = SEQUENCES.read_text(encoding="utf-8")
    sequences.write_text(f"{source}{source}", encoding="utf-8")
    output = tmp_path / "must-not-exist"

    with pytest.raises(DisabledProviderBundleError, match="duplicate sequence-group"):
        emit_disabled_provider_bundle(
            DisabledProviderBundleRequest(
                _write_entry(tmp_path, ProviderKey.ESM_ATLAS), sequences, output
            )
        )

    assert not output.exists()


def test_empty_sequence_groups_are_rejected_before_output(tmp_path: Path) -> None:
    sequences = tmp_path / "empty.jsonl"
    sequences.write_text("", encoding="utf-8")
    output = tmp_path / "must-not-exist"

    with pytest.raises(DisabledProviderBundleError, match="input is empty"):
        emit_disabled_provider_bundle(
            DisabledProviderBundleRequest(
                _write_entry(tmp_path, ProviderKey.ESM_ATLAS), sequences, output
            )
        )

    assert not output.exists()


def test_provider_entry_contract_remains_directly_readable(tmp_path: Path) -> None:
    entry = _write_entry(tmp_path, ProviderKey.ESM_ATLAS)
    assert ProviderPlanEntry.model_validate_json(entry.read_bytes()).provider is (
        ProviderKey.ESM_ATLAS
    )


def test_disabled_provider_cli_writes_complete_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "cli-bundle"

    assert (
        main(
            [
                "structure-search",
                "emit-disabled-provider",
                "--provider-entry",
                str(_write_entry(tmp_path, ProviderKey.ESM_ATLAS)),
                "--sequence-groups",
                str(SEQUENCES),
                "--outdir",
                str(output),
            ]
        )
        == 0
    )

    assert "disabled-provider results" in capsys.readouterr().out
    assert (output / "search_results.jsonl").is_file()
    assert (output / "structural_hits.jsonl").read_text(encoding="utf-8") == ""
    assert (output / "coordinate_sources.jsonl").read_text(encoding="utf-8") == ""
