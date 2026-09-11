"""One-stage CLI for the fixed truth-blind RF reference Nextflow graph.

Each command accepts original paths and invokes an existing authenticated
reference boundary. There are no science settings, truth inputs, track switches
or independent scientific loops here. Nextflow emits one hypothesis, prior/seed
or finalist per external-tool invocation and supplies the allocated CPU count.
The original pinned production adapters own all external commands and statuses.

Invoke with ``python -P -m tests.fixtures.ranking_four_arm_cli`` and explicitly
bind PYTHONPATH to the immutable checkout's src and root. ``--source-root`` must
match every loaded application and fixture module before any stage runs. Native
JSON runtime logs retain actual command paths and numeric tool exit statuses;
the CLI neither guesses them from typed results nor rewrites them on transport.

Context and scheduling documents live beside, never inside, checksum-bound
bundles. Their parsing does not authenticate science: the original full input
and receipt validators do. Missing, changed or foreign inputs fail loudly.
Existing typed scientific failures remain recorded outcomes, not CLI success
claims. Only the original fixtures produce source/input/output-bound receipts;
this entry point is not a production M6 profile or benchmark acceptance record.
"""

import argparse
import sys
from pathlib import Path
from typing import get_args

from tests.fixtures.ranking_four_arm_aggregate import (
    ReferenceRunInputs,
    build_reference_run,
)
from tests.fixtures.ranking_four_arm_context import (
    ReferenceFinalistContext,
    ReferenceIdentityContext,
    ReferencePlanContext,
    ReferencePreparedContext,
    ReferenceReviewContext,
)
from tests.fixtures.ranking_four_arm_continuation import (
    ReferencePreparedCopyRequest,
    reference_copy_tasks,
    run_prepared_reference_copy_task,
)
from tests.fixtures.ranking_four_arm_execution import (
    ReferenceChildOutputRequest,
    collect_reference_child_outputs,
)
from tests.fixtures.ranking_four_arm_finalists import build_reference_finalists
from tests.fixtures.ranking_four_arm_first_copy import (
    ReferenceFirstCopyRequest,
    build_prepared_reference_reviews,
    run_reference_first_copy_task,
)
from tests.fixtures.ranking_four_arm_identity import (
    ReferenceIdentityInputs,
    build_reference_case_identity,
)
from tests.fixtures.ranking_four_arm_plan import (
    ReferencePlanInputs,
    plan_reference_nextflow,
)
from tests.fixtures.ranking_four_arm_prepared import (
    ReferencePreparedInputs,
    bind_reference_prepared_case,
)
from tests.fixtures.ranking_four_arm_reference import AdmissionPrior
from tests.fixtures.ranking_four_arm_refinement import (
    ReferenceRefinementRequest,
    run_reference_refinement_task,
)

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.logging import configure_logging
from genome_to_diffraction.schemas.base import ContractModel


def validate_module_origins(source_root: Path) -> None:
    """Reject installed, shadowed or mixed-checkout scientific/fixture modules."""

    root = source_root.resolve(strict=True)
    if not root.is_dir() or Path(__file__).resolve() != (
        root / "tests/fixtures/ranking_four_arm_cli.py"
    ):
        raise ValueError("reference CLI does not originate in the explicit checkout")
    for name, module in tuple(sys.modules.items()):
        if name == "genome_to_diffraction" or name.startswith("genome_to_diffraction."):
            expected = root / "src" / Path(*name.split("."))
        elif name in {"tests", "tests.fixtures"} or name.startswith("tests.fixtures."):
            expected = root / Path(*name.split("."))
        else:
            continue
        filename = getattr(module, "__file__", None)
        # tests.fixtures is an existing namespace package, not an installed
        # package. Its complete search path must still be this one checkout.
        if name == "tests.fixtures" and filename is None:
            locations = getattr(module, "__path__", ())
            if tuple(Path(path).resolve() for path in locations) != (expected,):
                raise ValueError("reference fixture namespace has a foreign origin")
            continue
        if filename is None or Path(filename).resolve() not in {
            expected.with_suffix(".py"),
            expected / "__init__.py",
        }:
            raise ValueError(f"reference module has a foreign source origin: {name}")


def _original(value: str) -> Path:
    return Path(value).resolve(strict=True)


def _threads(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("threads must be positive")
    return parsed


def _context[T: ContractModel](path: Path, model: type[T]) -> T:
    if path.is_symlink() or not path.is_file():
        raise ValueError("reference context requires an original regular file")
    return model.model_validate_json(path.read_bytes())


def _save_context(output: Path, context: ContractModel) -> None:
    atomic_write_json(output / "context.json", context.model_dump(mode="json"))


def _plan(args: argparse.Namespace, output: Path) -> None:
    inputs = ReferencePlanInputs(
        runner_root=args.runner_root,
        database_manifest=args.database_manifest,
        software_lock=args.software_lock,
    )
    path = plan_reference_nextflow(inputs, output / "bundle")
    _save_context(
        output,
        ReferencePlanContext(
            runner_root=inputs.runner_root,
            database_manifest=inputs.database_manifest,
            software_lock=inputs.software_lock,
            plan_path=path,
        ),
    )


def _prepare(args: argparse.Namespace, output: Path) -> None:
    plan = _context(args.plan_context, ReferencePlanContext)
    inputs = ReferencePreparedInputs(
        plan_path=plan.plan_path,
        plan_inputs=plan.inputs(),
        case_id=args.case_id,
        catalogue_bundle=args.catalogue_bundle,
        prepared_case=args.prepared_case,
        coordinate_stage=args.coordinate_stage,
        phenix_manifest=args.phenix_manifest,
    )
    path = bind_reference_prepared_case(inputs, output / "bundle")
    _save_context(
        output,
        ReferencePreparedContext(
            plan=plan,
            case_id=inputs.case_id,
            catalogue_bundle=inputs.catalogue_bundle,
            prepared_case=inputs.prepared_case,
            coordinate_stage=inputs.coordinate_stage,
            phenix_manifest=inputs.phenix_manifest,
            prepared_path=path,
        ),
    )


def _first_copy(args: argparse.Namespace, output: Path) -> None:
    prepared = _context(args.prepared_context, ReferencePreparedContext)
    run_reference_first_copy_task(
        ReferenceFirstCopyRequest(
            prepared_path=prepared.prepared_path,
            prepared_inputs=prepared.inputs(),
            hypothesis_id=args.hypothesis_id,
            threads=args.threads,
            output_directory=output / "bundle",
        )
    )


def _reviews(args: argparse.Namespace, output: Path) -> None:
    prepared = _context(args.prepared_context, ReferencePreparedContext)
    receipts = tuple(args.first_copy_receipt)
    path = build_prepared_reference_reviews(
        prepared.prepared_path,
        prepared.inputs(),
        first_copy_receipts=receipts,
        output=output / "bundle",
    )
    context = ReferenceReviewContext(
        prepared=prepared, first_copy_receipts=receipts, reviews_path=path
    )
    tasks = reference_copy_tasks(context.inputs())
    _save_context(output, context)
    atomic_write_json(
        output / "copy_tasks.json",
        {"tasks": [task.model_dump(mode="json") for task in tasks]},
    )


def _copy(args: argparse.Namespace, output: Path) -> None:
    review = _context(args.review_context, ReferenceReviewContext)
    run_prepared_reference_copy_task(
        ReferencePreparedCopyRequest(
            inputs=review.inputs(),
            admission_prior=args.admission_prior,
            seed_solution_id=args.seed_solution_id,
            threads=args.threads,
            output_directory=output / "bundle",
        )
    )


def _finalists(args: argparse.Namespace, output: Path) -> None:
    review = _context(args.review_context, ReferenceReviewContext)
    receipts = tuple(args.copy_receipt)
    path = build_reference_finalists(
        review.inputs(), copy_receipts=receipts, output=output / "bundle"
    )
    _save_context(
        output,
        ReferenceFinalistContext(
            review=review, copy_receipts=receipts, finalists_path=path
        ),
    )


def _refine(args: argparse.Namespace, output: Path) -> None:
    finalists = _context(args.finalist_context, ReferenceFinalistContext)
    run_reference_refinement_task(
        ReferenceRefinementRequest(
            inputs=finalists.review.inputs(),
            copy_receipts=finalists.copy_receipts,
            finalists_path=finalists.finalists_path,
            admission_prior=args.admission_prior,
            seed_solution_id=args.seed_solution_id,
            threads=args.threads,
            output_directory=output / "bundle",
        )
    )


def _identity(args: argparse.Namespace, output: Path) -> None:
    finalists = _context(args.finalist_context, ReferenceFinalistContext)
    receipts = tuple(args.refinement_receipt)
    path = build_reference_case_identity(
        ReferenceIdentityInputs(
            continuation=finalists.review.inputs(),
            copy_receipts=finalists.copy_receipts,
            finalists_path=finalists.finalists_path,
            refinement_receipts=receipts,
        ),
        output / "bundle",
    )
    _save_context(
        output,
        ReferenceIdentityContext(
            finalists=finalists, refinement_receipts=receipts, identity_path=path
        ),
    )


def _aggregate(args: argparse.Namespace, output: Path) -> None:
    build_reference_run(
        ReferenceRunInputs(
            plan_context=args.plan_context,
            prepared_contexts=tuple(args.prepared_context),
            identity_contexts=tuple(args.identity_context),
        ),
        output / "bundle",
    )


def _checkpoint(args: argparse.Namespace, output: Path) -> None:
    # File integrity only. The fixed native profile must separately revalidate
    # the original scientific boundaries and actual native resource/command evidence.
    collect_reference_child_outputs(
        ReferenceChildOutputRequest(
            result=args.result,
            trace=args.trace,
            output=output / "reference_child_outputs.json",
            baseline=args.baseline,
            expected_baseline_sha256=args.baseline_sha256,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    """Expose only original-input transport and one scheduler-owned stage."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=_original, required=True)
    stages = parser.add_subparsers(dest="stage", required=True)
    handlers = {
        "plan": _plan,
        "prepare": _prepare,
        "first-copy": _first_copy,
        "reviews": _reviews,
        "copy": _copy,
        "finalists": _finalists,
        "refine": _refine,
        "identity": _identity,
        "aggregate": _aggregate,
        "checkpoint": _checkpoint,
    }
    for stage, handler in handlers.items():
        command = stages.add_parser(stage)
        command.set_defaults(handler=handler)
        command.add_argument("--output", type=Path, required=True)
        if stage == "plan":
            for flag in ("runner-root", "database-manifest", "software-lock"):
                command.add_argument(f"--{flag}", type=_original, required=True)
        elif stage == "checkpoint":
            command.add_argument("--result", type=_original, required=True)
            command.add_argument("--trace", type=_original, required=True)
            command.add_argument("--baseline", type=_original)
            command.add_argument("--baseline-sha256")
        elif stage == "aggregate":
            command.add_argument("--plan-context", type=_original, required=True)
            command.add_argument(
                "--prepared-context", type=_original, action="append", required=True
            )
            command.add_argument(
                "--identity-context", type=_original, action="append", default=[]
            )
        elif stage == "prepare":
            for flag in (
                "plan-context",
                "catalogue-bundle",
                "prepared-case",
                "phenix-manifest",
            ):
                command.add_argument(f"--{flag}", type=_original, required=True)
            command.add_argument("--coordinate-stage", type=_original)
            command.add_argument("--case-id", required=True)
        else:
            context = (
                "prepared-context"
                if stage in {"first-copy", "reviews"}
                else "review-context"
                if stage in {"copy", "finalists"}
                else "finalist-context"
            )
            command.add_argument(f"--{context}", type=_original, required=True)
        if stage in {"first-copy", "copy", "refine"}:
            command.add_argument("--threads", type=_threads, required=True)
        if stage == "first-copy":
            command.add_argument("--hypothesis-id", required=True)
        if stage in {"copy", "refine"}:
            command.add_argument(
                "--admission-prior",
                choices=get_args(AdmissionPrior.__value__),
                required=True,
            )
            command.add_argument("--seed-solution-id", required=True)
        receipt = {
            "reviews": "first-copy-receipt",
            "finalists": "copy-receipt",
            "identity": "refinement-receipt",
        }.get(stage)
        if receipt is not None:
            command.add_argument(
                f"--{receipt}", type=_original, action="append", default=[]
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate the immutable import origin and run exactly one stage."""

    args = build_parser().parse_args(argv)
    logger = configure_logging(log_format="json")
    validate_module_origins(args.source_root)
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("reference CLI output must not already exist")
    output = args.output.resolve()
    args.handler(args, output)
    logger.info(
        "reference stage completed", extra={"stage": args.stage, "output": output}
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
