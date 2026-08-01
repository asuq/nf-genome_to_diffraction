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
    except (ContractError, OSError, ValueError) as error:
        logger.error("command failed", extra={"error": str(error)})
        return 1
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
