"""Command-line entry point for foundation utilities."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from genome_to_diffraction import __version__
from genome_to_diffraction.schema_check import validate_repository


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="genome-to-diffraction")
    parser.add_argument("--version", action="version", version=__version__)
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the foundation CLI and return a process exit code."""

    args = _build_parser().parse_args(argv)
    if args.command == "schema-check":
        errors = validate_repository(args.repository)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1
        print("All schemas, fixtures, and review TSV contracts are valid.")
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
