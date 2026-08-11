"""Machine-readable interface for repository-specific fixed HPC tests."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from genome_to_diffraction.hpc.client import HpcController
from genome_to_diffraction.hpc.models import (
    HpcConfig,
    HpcInterfaceError,
)
from genome_to_diffraction.logging import configure_logging, parse_log_level

DEFAULT_CONFIG = Path.home() / ".config" / "nf-gtd-hpc-test" / "config.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nf-gtd-hpc-test",
        description="Run one immutable fixed nf-genome_to_diffraction test on Marmic",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--log-format", choices=("human", "json"), default="human")
    parser.add_argument("--no-progress", action="store_true")
    actions = parser.add_subparsers(dest="operation", required=True)

    deploy_tools = actions.add_parser(
        "deploy-tools",
        help="deploy the two fixed remote scripts from a pushed commit",
    )
    deploy_tools.add_argument("--revision", required=True)

    readiness = actions.add_parser(
        "readiness",
        help="inspect fixed remote prerequisites without staging or submitting",
    )
    readiness.add_argument("profile", choices=("p0", "p1", "p2"))

    p0_configure = actions.add_parser(
        "p0-configure",
        help="install one absent validated P0 site-path configuration",
    )
    p0_configure.add_argument("--paths-file", type=Path, required=True)
    p0_configure.add_argument("--confirm-sha256", required=True)

    p0_inputs_stage = actions.add_parser(
        "p0-inputs-stage",
        help="stage the fixed checksum-frozen three-crystal P0 input bundle",
    )
    p0_inputs_stage.add_argument("--confirm-spec-sha256", required=True)

    actions.add_parser(
        "database-readiness",
        help="inspect the separate fixed database-administration prerequisites",
    )
    database_stage = actions.add_parser(
        "database-stage",
        help="stage an immutable commit for fixed database administration",
    )
    database_stage.add_argument("--revision", required=True)
    database_submit = actions.add_parser(
        "database-submit",
        help="submit the separately approval-gated database job",
    )
    database_submit.add_argument("--run-id", required=True)
    database_archive = actions.add_parser(
        "database-archive-failed",
        help=(
            "archive reviewed retained staging from a failed or cancelled database run"
        ),
    )
    database_archive.add_argument("--run-id", required=True)
    database_archive.add_argument("--confirm", required=True)

    stage = actions.add_parser("stage", help="stage an immutable pushed commit")
    stage.add_argument("profile", choices=("smoke", "p0", "p1", "p2"))
    stage.add_argument("--revision", required=True)
    stage.add_argument("--parent-run")

    submit = actions.add_parser("submit", help="submit the fixed Slurm profile")
    submit.add_argument("profile", choices=("smoke", "p0", "p1", "p2"))
    submit.add_argument("--run-id", required=True)

    for operation, help_text in (
        ("status", "query the recorded scheduler job"),
        ("wait", "wait with bounded queue and execution time"),
        ("collect", "collect approved small artefacts"),
        ("cancel", "cancel only the recorded scheduler job"),
    ):
        action = actions.add_parser(operation, help=help_text)
        action.add_argument("--run-id", required=True)

    logs = actions.add_parser("logs", help="retrieve a bounded log tail")
    logs.add_argument("--run-id", required=True)
    logs.add_argument("--tail", type=int, default=200)

    clean = actions.add_parser(
        "clean", help="delete one inactive run after external approval"
    )
    clean.add_argument("--run-id", required=True)
    clean.add_argument("--confirm", required=True)
    return parser


def _run(args: argparse.Namespace, controller: HpcController) -> dict[str, object]:
    if args.operation == "deploy-tools":
        return controller.deploy_tools(args.revision)
    if args.operation == "readiness":
        return controller.readiness(args.profile)
    if args.operation == "p0-configure":
        return controller.p0_configure(args.paths_file, args.confirm_sha256)
    if args.operation == "p0-inputs-stage":
        return controller.p0_inputs_stage(args.confirm_spec_sha256)
    if args.operation == "database-readiness":
        return controller.database_readiness()
    if args.operation == "database-stage":
        return controller.database_stage(args.revision)
    if args.operation == "database-submit":
        return controller.database_submit(args.run_id)
    if args.operation == "database-archive-failed":
        return controller.database_archive_failed(args.run_id, args.confirm)
    if args.operation == "stage":
        return controller.stage(
            args.profile,
            args.revision,
            parent_run_id=args.parent_run,
        )
    if args.operation == "submit":
        return controller.submit(args.profile, args.run_id)
    if args.operation == "status":
        return controller.status(args.run_id)
    if args.operation == "wait":
        return controller.wait(args.run_id)
    if args.operation == "logs":
        return controller.logs(args.run_id, args.tail)
    if args.operation == "collect":
        return controller.collect(args.run_id)
    if args.operation == "cancel":
        return controller.cancel(args.run_id)
    if args.operation == "clean":
        return controller.clean(args.run_id, args.confirm)
    raise AssertionError(f"unhandled operation: {args.operation}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the controller and emit exactly one JSON object on stdout."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        level = parse_log_level(args.log_level)
    except ValueError as error:
        parser.error(str(error))
    logger = configure_logging(
        level=level,
        logger_name="genome_to_diffraction.hpc",
        log_format=args.log_format,
    )
    try:
        config = HpcConfig.load(args.config)
        controller = HpcController(
            config,
            logger=logger,
            progress=not args.no_progress and sys.stderr.isatty(),
        )
        result: dict[str, Any] = _run(args, controller)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True, default=str))
        return 0
    except (HpcInterfaceError, OSError) as error:
        failure_class = getattr(error, "failure_class", "wrapper_failure")
        logger.error(
            "HPC operation failed",
            extra={
                "operation": args.operation,
                "failure_class": str(failure_class),
                "error": str(error),
            },
        )
        payload = {
            "operation": args.operation,
            "ok": False,
            "failure_class": str(failure_class),
            "message": str(error),
        }
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
        return 1


def entrypoint() -> None:
    """Console-script and zipapp entry point."""

    sys.exit(main())


if __name__ == "__main__":
    entrypoint()
