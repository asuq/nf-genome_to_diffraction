"""Command-line entry point for contracts and foundation utilities."""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from genome_to_diffraction import __version__
from genome_to_diffraction.checksums import atomic_write_text
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.logging import configure_logging, parse_log_level
from genome_to_diffraction.phenix.errors import (
    PhenixError,
    PhenixInstallCommandError,
)
from genome_to_diffraction.phenix.installer import InstallRequest, install_phenix
from genome_to_diffraction.phenix.runtime import (
    execute_from_manifest,
    verify_manifest,
)
from genome_to_diffraction.schema_check import validate_repository
from genome_to_diffraction.schemas.io import (
    ContractError,
    InputFormat,
    contract_json_schema,
    contract_kinds,
    load_contract,
)


def _add_contract_input(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("kind", choices=contract_kinds(), help="contract kind")
    parser.add_argument("input", type=Path, help="JSON, YAML, or supported TSV input")
    parser.add_argument(
        "--format",
        choices=("auto", "json", "yaml", "tsv"),
        default="auto",
        help="input format (default: infer from suffix)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="genome-to-diffraction")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="DEBUG, INFO, WARNING, ERROR, or CRITICAL",
    )
    parser.add_argument(
        "--log-format",
        choices=("human", "json"),
        default="human",
        help="diagnostic log rendering (default: human)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="disable tqdm progress bars",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    schema_parser = subparsers.add_parser(
        "schema-check", help="validate repository schemas and fixtures"
    )
    schema_parser.add_argument(
        "--repository",
        type=Path,
        default=Path.cwd(),
        help="repository root (default: current directory)",
    )

    contract_parser = subparsers.add_parser(
        "contract", help="validate or canonicalise a versioned contract"
    )
    contract_actions = contract_parser.add_subparsers(
        dest="contract_action", required=True
    )
    validate_parser = contract_actions.add_parser(
        "validate", help="validate a JSON, YAML, or supported TSV contract"
    )
    _add_contract_input(validate_parser)
    canonicalise_parser = contract_actions.add_parser(
        "canonicalise", help="write validated RFC 8785 canonical JSON"
    )
    _add_contract_input(canonicalise_parser)
    canonicalise_parser.add_argument(
        "--output",
        type=Path,
        help="output path (default: standard output)",
    )
    schema_output_parser = contract_actions.add_parser(
        "schema", help="write a Draft 2020-12 JSON Schema for a contract"
    )
    schema_output_parser.add_argument("kind", choices=contract_kinds())
    schema_output_parser.add_argument(
        "--output",
        type=Path,
        help="output path (default: standard output)",
    )

    phenix_parser = subparsers.add_parser(
        "phenix", help="install, verify, or execute the external Phenix runtime"
    )
    phenix_actions = phenix_parser.add_subparsers(dest="phenix_action", required=True)
    install_parser = phenix_actions.add_parser(
        "install", help="install a user-supplied Phenix command-line installer"
    )
    install_parser.add_argument(
        "--installer", type=Path, required=True, help="user-supplied installer file"
    )
    install_parser.add_argument(
        "--installer-sha256",
        required=True,
        help="expected full SHA-256 of the installer file",
    )
    install_parser.add_argument(
        "--prefix",
        type=Path,
        required=True,
        help="new absolute versioned prefix, such as /opt/phenix-2.1-XXXX",
    )
    install_parser.add_argument(
        "--expected-release",
        default="2.1",
        help="required PHENIX_VERSION release family (default: 2.1)",
    )
    install_parser.add_argument(
        "--expected-build", help="optional exact PHENIX_VERSION value"
    )
    install_parser.add_argument(
        "--temp-dir",
        type=Path,
        required=True,
        help="absolute executable temporary directory with at least 25 GiB free",
    )
    install_parser.add_argument(
        "--manifest", type=Path, required=True, help="new manifest output path"
    )
    install_parser.add_argument(
        "--current-link",
        type=Path,
        help="optional controlled symlink updated only after verification",
    )
    install_parser.add_argument(
        "--operator-note",
        action="append",
        default=[],
        help="repeatable provenance note stored in the manifest",
    )
    install_parser.add_argument(
        "--minimum-install-free-gb",
        type=float,
        default=15.0,
        help="minimum installation-filesystem free space (default: 15 GiB)",
    )
    install_parser.add_argument(
        "--minimum-temp-free-gb",
        type=float,
        default=25.0,
        help="minimum temporary-filesystem free space (default: 25 GiB)",
    )
    install_parser.add_argument(
        "--allow-home-root",
        action="store_true",
        help="allow the home root itself as an administrative target",
    )
    install_parser.add_argument(
        "--command-timeout-seconds",
        type=float,
        default=120.0,
        help="per-command smoke-test timeout (default: 120)",
    )

    verify_parser = phenix_actions.add_parser(
        "verify", help="revalidate a recorded Phenix installation manifest"
    )
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--verification-log", type=Path)
    verify_parser.add_argument("--command-timeout-seconds", type=float, default=120.0)

    execute_parser = phenix_actions.add_parser(
        "exec", help="execute one command in an isolated verified Phenix shell"
    )
    execute_parser.add_argument("--manifest", type=Path, required=True)
    execute_parser.add_argument(
        "phenix_command",
        nargs=argparse.REMAINDER,
        help="exact command and arguments, conventionally after --",
    )
    return parser


def _run_contract(args: argparse.Namespace, logger: logging.Logger) -> int:
    if args.contract_action == "schema":
        payload = f"{canonical_json_text(contract_json_schema(args.kind))}\n"
        if args.output is None:
            sys.stdout.write(payload)
        else:
            atomic_write_text(args.output, payload)
            logger.info(
                "wrote contract schema",
                extra={"contract_kind": args.kind, "output": str(args.output)},
            )
        return 0

    model = load_contract(
        args.input,
        args.kind,
        input_format=cast(InputFormat, args.format),
        progress=not args.no_progress,
    )
    if args.contract_action == "validate":
        print(f"Valid {args.kind}: {args.input}")
        return 0

    payload = f"{canonical_json_text(model)}\n"
    if args.output is None:
        sys.stdout.write(payload)
    else:
        atomic_write_text(args.output, payload)
        logger.info(
            "wrote canonical contract",
            extra={"contract_kind": args.kind, "output": str(args.output)},
        )
    return 0


def _run_phenix(args: argparse.Namespace, logger: logging.Logger) -> int:
    gib = 1024**3
    if args.phenix_action == "install":
        request = InstallRequest(
            installer=args.installer,
            installer_sha256=args.installer_sha256,
            installation_prefix=args.prefix,
            expected_release=args.expected_release,
            expected_build=args.expected_build,
            temporary_directory=args.temp_dir,
            manifest_path=args.manifest,
            current_symlink=args.current_link,
            operator_notes=tuple(args.operator_note),
            minimum_install_free_bytes=int(args.minimum_install_free_gb * gib),
            minimum_temporary_free_bytes=int(args.minimum_temp_free_gb * gib),
            allow_home_root=args.allow_home_root,
            progress=not args.no_progress,
            command_timeout_seconds=args.command_timeout_seconds,
        )
        manifest = install_phenix(request)
        print(f"Verified Phenix {manifest.phenix_version}: {args.manifest}")
        return 0
    if args.phenix_action == "verify":
        inspection = verify_manifest(
            args.manifest,
            progress=not args.no_progress,
            timeout_seconds=args.command_timeout_seconds,
            verification_log=args.verification_log,
        )
        print(
            f"Verified Phenix {inspection.phenix_version}: {inspection.phenix_prefix}"
        )
        return 0
    if args.phenix_action == "exec":
        command = list(args.phenix_command)
        if command and command[0] == "--":
            command = command[1:]
        return execute_from_manifest(args.manifest, command)
    raise AssertionError(f"unhandled Phenix action: {args.phenix_action}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        level = parse_log_level(args.log_level)
    except ValueError as level_error:
        parser.error(str(level_error))
    logger = configure_logging(level=level, log_format=args.log_format)

    try:
        if args.command == "schema-check":
            errors = validate_repository(args.repository)
            if errors:
                for schema_error in errors:
                    logger.error(
                        "schema validation failed", extra={"error": schema_error}
                    )
                return 1
            print("All schemas, fixtures, and review TSV contracts are valid.")
            return 0
        if args.command == "contract":
            return _run_contract(args, logger)
        if args.command == "phenix":
            return _run_phenix(args, logger)
    except PhenixInstallCommandError as error:
        logger.error(
            "Phenix installer command failed",
            extra={"error": str(error), "exit_status": error.returncode},
        )
        return error.returncode
    except (ContractError, PhenixError, OSError, ValueError) as error:
        logger.error("command failed", extra={"error": str(error)})
        return 1
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
