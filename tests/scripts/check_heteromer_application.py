"""Exercise control-independent catalogue partner search and fixed controls."""

import sys
import tempfile
from collections import Counter
from hashlib import sha256
from pathlib import Path
from shutil import copy2, copytree

from tests.scripts.check_nextflow import _assert_files, _environment, _read_trace, _run

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"


def _command(root: Path, *, control: bool) -> tuple[list[str], Path]:
    label = "control" if control else "application"
    output = root / f"{label}-results"
    command = [
        "nextflow",
        "run",
        "main.nf",
        "-profile",
        "test",
        "-stub-run",
        "-params-file",
        "tests/fixtures/stubs/main_params.yaml",
        "--analysis_stage",
        "heteromer",
        "--approved_mr_seeds",
        "examples/approvals/approved_mr_seeds.tsv",
        "--outdir",
        str(output),
        "--cache_root",
        str(root / f"{label}-cache"),
    ]
    if control:
        command.extend(
            [
                "--heteromer_control_preparation",
                "tests/fixtures/stubs/approved_partner_search",
            ]
        )
    return command, output


def _counts(output: Path) -> Counter[str]:
    rows = _read_trace(output / "pipeline_info" / "trace.tsv")
    if not rows or any(row["status"] != "COMPLETED" for row in rows):
        raise RuntimeError("heteromer application did not complete every task")
    return Counter(row["process"].split(":")[-1] for row in rows)


def _scientific_fanout_command(root: Path) -> tuple[list[str], Path]:
    """Feed real production workflows queue-owned shared inputs and siblings."""

    inputs = root / "scientific-fanout-inputs"
    inputs.mkdir()
    project = inputs / "project"
    project.mkdir()
    fixture = REPOSITORY / "tests/fixtures/stubs/integrated_scientific_fanout/main.nf"
    (project / "main.nf").write_text(
        fixture.read_text(encoding="ascii").replace(
            "'../../../../workflows/",
            f"'{REPOSITORY}/workflows/",
        ),
        encoding="ascii",
    )
    fixtures = project / "tests/fixtures/stubs"
    fixtures.mkdir(parents=True)
    copytree(STUBS / "first_copy_phaser", fixtures / "first_copy_phaser")
    for name in (
        "additional_copy_result.jsonl",
        "additional_copy_result.json",
        "phaser_command.json",
        "add_copy.eff",
        "additional_copy_series_results.jsonl",
        "additional_copy_series_summary.json",
        "brief_refinement_result.json",
        "sequence_map_result.json",
        "t12_command.json",
    ):
        copy2(STUBS / name, fixtures / name)
    bundle = inputs / "control-bundle"
    copytree(STUBS / "first_copy_controls", bundle)
    extra = next((STUBS / "exact_predicted_funnel/hypotheses").glob("*.jsonl"))
    copy2(extra, bundle / "hypotheses" / extra.name)
    model = STUBS / "predicted_model_preparation/models/stub.pdb"
    digest = sha256(model.read_bytes()).hexdigest()

    seeds = inputs / "seeds.tsv"
    seeds.write_text(
        "seed_solution_id\tsearch_model\tsearch_model_sha256\n"
        + "".join(f"sol_seed_{label}\t{model}\t{digest}\n" for label in ("a", "b")),
        encoding="ascii",
    )
    finalists = inputs / "finalists.tsv"
    finalists.write_text(
        "seed_solution_id\tsequence_group_id\tinput_copy_count\t"
        "parent_coordinate\tparent_coordinate_sha256\tparent_mtz\t"
        "parent_mtz_sha256\tresolution\tobservation_labels\n"
        + "".join(
            f"sol_finalist_{label}\tseq_fanout\t2\t{model}\t{digest}\t"
            f"{model}\t{digest}\t2.5\tF,SIGF\n"
            for label in ("a", "b")
        ),
        encoding="ascii",
    )
    phase3_finalists = inputs / "phase3-finalists.tsv"
    phase3_finalists.write_text(
        finalists.read_text(encoding="ascii").replace("sol_finalist_", "sol_phase3_"),
        encoding="ascii",
    )
    phase3_dispatch = inputs / "phase3-dispatch"
    phase3_dispatch.mkdir()
    copy2(model, phase3_dispatch / "input.mtz")
    (phase3_dispatch / "crystal_id.txt").write_text(
        "test_crystal_01\n", encoding="ascii"
    )
    (phase3_dispatch / "phase3_diffraction_selection.json").write_text(
        '{"selection":"original"}\n', encoding="ascii"
    )
    (phase3_dispatch / "phase3_free_r_identity.json").write_text(
        '{"free_r":"original"}\n', encoding="ascii"
    )
    phase3_approved = inputs / "phase3-approved-seeds"
    phase3_approved.mkdir()
    copy2(seeds, phase3_approved / "additional_copy_seeds.tsv")
    copy2(
        STUBS / "approved_mr_seed_stage/validated_mr_seed_decisions.json",
        phase3_approved / "validated_mr_seed_decisions.json",
    )
    (phase3_approved / "live_m4_stage_manifest.json").write_text(
        '{"phase3_approval_provenance":{"crystal_id":"test_crystal_01"}}\n',
        encoding="ascii",
    )
    output = root / "scientific-fanout-results"
    command = [
        "nextflow",
        "-C",
        "tests/fixtures/stubs/p6_empty_partner/nextflow.config",
        "run",
        str(project / "main.nf"),
        "-stub-run",
        "--control_bundle",
        str(bundle),
        "--seeds",
        str(seeds),
        "--review_validation",
        str(STUBS / "approved_mr_seed_stage/validated_mr_seed_decisions.json"),
        "--review_package",
        str(STUBS / "mr_seed_review/mr_seed_review_manifest.json"),
        "--hypotheses",
        str(STUBS / "exact_predicted_funnel/mr_hypotheses.jsonl"),
        "--finalists",
        str(finalists),
        "--phase3_finalists",
        str(phase3_finalists),
        "--phase3_dispatch",
        str(phase3_dispatch),
        "--phase3_approved",
        str(phase3_approved),
        "--sequence_groups",
        str(STUBS / "sequence_groups.jsonl"),
        "--source_records",
        str(STUBS / "source_records.jsonl"),
        "--preflight",
        str(STUBS / "mtz_preflight.jsonl"),
        "--mtz",
        str(model),
        "--phenix_manifest",
        str(STUBS / "phenix_install_manifest.json"),
        "--outdir",
        str(output),
        "--cache_root",
        str(root / "scientific-fanout-cache"),
    ]
    return command, output


def _check_complete_scientific_fanout(root: Path, environment: dict[str, str]) -> None:
    command, output = _scientific_fanout_command(root)
    _run(command, environment=environment)
    rows = _read_trace(output / "pipeline_info/trace.tsv")
    if any(row["status"] != "COMPLETED" for row in rows):
        raise RuntimeError("scientific fan-out did not complete every task")
    counts = Counter(row["process"].split(":")[-1] for row in rows)
    expected = {
        "RUN_FIRST_COPY_PHASER": 3,
        "RUN_ADDITIONAL_COPY_PHASER": 2,
        "RUN_PHASE3_ADDITIONAL_COPY_PHASER": 2,
        "RUN_BRIEF_REFINEMENT": 2,
        "RUN_PHASE3_BRIEF_REFINEMENT": 2,
    }
    if counts != expected:
        raise RuntimeError(
            "scientific fan-out lost hypotheses, approved seeds, or finalists: "
            f"expected={expected}, observed={dict(sorted(counts.items()))}"
        )
    tags = {row["tag"] for row in rows}
    required_tags = {
        "first-copy-phaser:mrhyp_" + "a" * 64,
        "first-copy-phaser:mrhyp_" + "b" * 64,
        "first-copy-phaser:mrhyp_" + "d" * 64,
        "add-copy:sol_seed_a",
        "add-copy:sol_seed_b",
        "phase3-add-copy:test_crystal_01:sol_seed_a",
        "phase3-add-copy:test_crystal_01:sol_seed_b",
        "t12:sol_finalist_a",
        "t12:sol_finalist_b",
        "phase3-t12:sol_phase3_a",
        "phase3-t12:sol_phase3_b",
    }
    if not required_tags.issubset(tags):
        raise RuntimeError("scientific fan-out omitted a distinct task identity")
    retained = {
        path.relative_to(output).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in output.rglob("*")
        if path.is_file() and "pipeline_info" not in path.relative_to(output).parts
    }

    _run([*command, "-resume"], environment=environment)
    resumed = _read_trace(output / "pipeline_info/trace.tsv")
    if len(resumed) != len(rows) or any(row["status"] != "CACHED" for row in resumed):
        raise RuntimeError("scientific fan-out did not fully resume from cache")
    if {row["hash"] for row in resumed} != {row["hash"] for row in rows}:
        raise RuntimeError("scientific fan-out changed task identities on resume")
    if retained != {
        path.relative_to(output).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in output.rglob("*")
        if path.is_file() and "pipeline_info" not in path.relative_to(output).parts
    }:
        raise RuntimeError("scientific fan-out changed published bytes on resume")

    selection = (
        root
        / "scientific-fanout-inputs"
        / "phase3-dispatch"
        / "phase3_diffraction_selection.json"
    )
    selection.write_text('{"selection":"mutated"}\n', encoding="ascii")
    _run([*command, "-resume"], environment=environment)
    mutated = _read_trace(output / "pipeline_info/trace.tsv")
    rerun = Counter(
        row["process"].split(":")[-1] for row in mutated if row["status"] == "COMPLETED"
    )
    if rerun != {
        "RUN_PHASE3_ADDITIONAL_COPY_PHASER": 2,
        "RUN_PHASE3_BRIEF_REFINEMENT": 2,
    }:
        raise RuntimeError(
            "diffraction mutation did not isolate the four Phase III tasks: "
            f"{dict(sorted(rerun.items()))}"
        )
    if sum(row["status"] == "CACHED" for row in mutated) != 7:
        raise RuntimeError("diffraction mutation invalidated unrelated scientific jobs")
    for label in ("a", "b"):
        additional = output / f"phase3_additional_copy_test_crystal_01_sol_seed_{label}"
        if (additional / "phase3_diffraction_selection.json").read_bytes() != (
            selection.read_bytes()
        ):
            raise RuntimeError(
                "Phase III same-component placement lost selected MTZ evidence"
            )
        if (additional / "phase3_crystal_id.txt").read_text(encoding="ascii") != (
            "test_crystal_01\n"
        ):
            raise RuntimeError("Phase III same-component placement crossed crystals")
        result = output / f"t12_sol_phase3_{label}"
        if (result / "phase3_diffraction_selection.json").read_bytes() != (
            selection.read_bytes()
        ):
            raise RuntimeError(
                "Phase III refinement did not retain selected MTZ evidence"
            )
        if (result / "phase3_crystal_id.txt").read_text(encoding="ascii") != (
            "test_crystal_01\n"
        ):
            raise RuntimeError("Phase III refinement lost its exact crystal identity")


def main() -> int:
    """Keep a reviewed catalogue application independent of fixed 6RTZ data."""

    with tempfile.TemporaryDirectory(
        prefix="nf-gtd-heteromer-application-",
        dir="/tmp",
    ) as temporary:
        root = Path(temporary)
        environment = _environment(root / "nxf-home")
        application, application_output = _command(root, control=False)
        _run(application, environment=environment)
        application_counts = _counts(application_output)
        required = (
            "STAGE_APPROVED_MR_SEEDS",
            "BUILD_PARTNER_PLAN",
            "RUN_PLANNED_PARTNER_PHASER",
            "SUMMARIZE_PARTNER_ATTEMPTS",
        )
        if any(application_counts[name] != 1 for name in required):
            raise RuntimeError(
                "control-independent application lost its reviewed partner chain: "
                f"{dict(sorted(application_counts.items()))}"
            )
        if application_counts["RUN_APPROVED_PARTNER_PHASER"] != 0:
            raise RuntimeError("normal application scheduled the fixed 6RTZ control")
        if (application_output / "approved_partner_search").exists():
            raise RuntimeError("normal application published fixed-control evidence")
        _assert_files(
            application_output,
            {
                "validated_mr_seed_decisions.json",
                "partner_search_plan.json",
                "partner_candidates.jsonl",
                "selected_partner_candidate_ids.txt",
                "partner_attempt_summary.json",
                "partner_search_result.json",
            },
        )

        resumed = _run([*application, "-resume"], environment=environment)
        if "cached" not in f"{resumed.stdout}\n{resumed.stderr}".lower():
            raise RuntimeError("control-independent application did not resume")

        control, control_output = _command(root, control=True)
        _run(control, environment=environment)
        control_counts = _counts(control_output)
        if control_counts["RUN_APPROVED_PARTNER_PHASER"] != 1:
            raise RuntimeError("explicit fixed-control execution was not retained")
        if any(control_counts[name] != 1 for name in required):
            raise RuntimeError("fixed control lost the shared catalogue partner chain")
        if not (control_output / "approved_partner_search").is_dir():
            raise RuntimeError("fixed-control result was not retained")

        _check_complete_scientific_fanout(root, environment)

    print("Control-independent heteromer application and complete fan-out passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
