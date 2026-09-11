"""CLI routing checks only; mocked stage calls are not scientific validation."""

import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.fixtures import ranking_four_arm_cli as cli
from tests.fixtures.ranking_four_arm_context import ReferenceIdentityContext
from tests.unit.test_ranking_four_arm_context import _context

_ROOT = Path(__file__).resolve().parents[2]


def test_reference_cli_checks_every_module_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.validate_module_origins(_ROOT)
    with pytest.raises(ValueError, match="explicit checkout"):
        cli.validate_module_origins(tmp_path)
    foreign = ModuleType("genome_to_diffraction.foreign")
    foreign.__file__ = str(tmp_path / "foreign.py")
    monkeypatch.setitem(sys.modules, foreign.__name__, foreign)
    with pytest.raises(ValueError, match="foreign source origin"):
        cli.validate_module_origins(_ROOT)


def test_reference_cli_rejects_foreign_fixture_namespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    namespace = sys.modules["tests.fixtures"]
    monkeypatch.setattr(namespace, "__path__", [str(tmp_path)])
    with pytest.raises(ValueError, match="namespace has a foreign origin"):
        cli.validate_module_origins(_ROOT)


@pytest.mark.parametrize("stage", ("first-copy", "copy", "refine"))
def test_reference_cli_dispatches_one_original_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    finalists = _context(tmp_path)
    prepared = finalists.review.prepared
    context = {
        "first-copy": prepared,
        "copy": finalists.review,
        "refine": finalists,
    }[stage]
    context_file = tmp_path / "context.json"
    context_file.write_text(context.model_dump_json(), encoding="ascii")
    flag, function = {
        "first-copy": ("prepared-context", "run_reference_first_copy_task"),
        "copy": ("review-context", "run_prepared_reference_copy_task"),
        "refine": ("finalist-context", "run_reference_refinement_task"),
    }[stage]
    calls = []
    monkeypatch.setattr(cli, function, calls.append)
    output = tmp_path / "new-output"
    arguments = [
        "--source-root",
        str(_ROOT),
        stage,
        f"--{flag}",
        str(context_file),
        "--threads",
        "3",
        "--output",
        str(output),
    ]
    if stage == "first-copy":
        arguments.extend(("--hypothesis-id", "hyp-one"))
    else:
        arguments.extend(
            ("--admission-prior", "solvent_density", "--seed-solution-id", "seed-one")
        )
    assert cli.main(arguments) == 0
    assert len(calls) == 1
    request = calls[0]
    assert request.threads == 3
    assert request.output_directory == output / "bundle"
    if stage == "first-copy":
        assert request.prepared_path == prepared.prepared_path
        assert request.prepared_inputs == prepared.inputs()
        assert request.hypothesis_id == "hyp-one"
    else:
        assert request.inputs == finalists.review.inputs()
        assert request.admission_prior == "solvent_density"
        assert request.seed_solution_id == "seed-one"
    if stage == "refine":
        assert request.copy_receipts == finalists.copy_receipts
        assert request.finalists_path == finalists.finalists_path
    # The mocked boundary did not execute science or create authentic receipts.
    assert not output.exists()


def test_reference_cli_identity_keeps_empty_union_and_original_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    finalists = _context(tmp_path)
    context_file = tmp_path / "context.json"
    context_file.write_text(finalists.model_dump_json(), encoding="ascii")
    calls = []

    def identity(inputs: cli.ReferenceIdentityInputs, output: Path) -> Path:
        calls.append(inputs)
        return output / "reference_case_identity.json"

    monkeypatch.setattr(cli, "build_reference_case_identity", identity)
    output = tmp_path / "new-output"
    assert (
        cli.main(
            [
                "--source-root",
                str(_ROOT),
                "identity",
                "--finalist-context",
                str(context_file),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert len(calls) == 1
    assert calls[0].refinement_receipts == ()
    assert calls[0].continuation == finalists.review.inputs()
    assert calls[0].copy_receipts == finalists.copy_receipts
    context = ReferenceIdentityContext.model_validate_json(
        (output / "context.json").read_bytes()
    )
    assert context.finalists == finalists
    assert context.refinement_receipts == ()
    assert context.identity_path == output / "bundle/reference_case_identity.json"
    # Context transport is not a generated scientific identity or its validator.
    assert not context.identity_path.exists()


def test_reference_cli_rejects_overwrite_and_unapproved_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _context(tmp_path).review.prepared
    context_file = tmp_path / "context.json"
    context_file.write_text(prepared.model_dump_json(), encoding="ascii")
    calls = []
    monkeypatch.setattr(cli, "run_reference_first_copy_task", calls.append)
    args = [
        "--source-root",
        str(_ROOT),
        "first-copy",
        "--prepared-context",
        str(context_file),
        "--hypothesis-id",
        "hyp-one",
        "--threads",
        "2",
        "--output",
        str(tmp_path / "new-output"),
    ]
    for extra in (("--truth", "truth.json"), ("--seed-cap", "6"), ("--threads", "0")):
        with pytest.raises(SystemExit):
            cli.main([*args, *extra])
    (tmp_path / "new-output").mkdir()
    marker = tmp_path / "new-output/retained.json"
    marker.write_text(json.dumps({"unchanged": True}), encoding="ascii")
    with pytest.raises(ValueError, match="must not already exist"):
        cli.main(args)
    assert json.loads(marker.read_text(encoding="ascii")) == {"unchanged": True}
    assert not calls


def test_reference_cli_checkpoint_transports_external_baseline_without_relabelling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = {}
    for name in ("result", "trace", "baseline"):
        paths[name] = tmp_path / name
        paths[name].write_text("routing fixture only\n", encoding="ascii")
    calls = []
    monkeypatch.setattr(cli, "collect_reference_child_outputs", calls.append)
    output = tmp_path / "checkpoint-output"
    assert (
        cli.main(
            [
                "--source-root",
                str(_ROOT),
                "checkpoint",
                "--result",
                str(paths["result"]),
                "--trace",
                str(paths["trace"]),
                "--baseline",
                str(paths["baseline"]),
                "--baseline-sha256",
                "a" * 64,
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert len(calls) == 1
    assert calls[0].result == paths["result"]
    assert calls[0].trace == paths["trace"]
    assert calls[0].baseline == paths["baseline"]
    assert calls[0].expected_baseline_sha256 == "a" * 64
    assert calls[0].output == output / "reference_child_outputs.json"
    assert not output.exists()
