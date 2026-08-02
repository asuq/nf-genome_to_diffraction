"""Build a reviewed immutable zipapp for the local HPC approval boundary."""

import argparse
import json
import os
import sys
import zipapp
from collections.abc import Sequence
from pathlib import Path

from genome_to_diffraction.checksums import sha256_file

REPOSITORY = Path(__file__).resolve().parents[1]


def _include(path: Path) -> bool:
    """Exclude bytecode and caches from the installed controller archive."""

    return "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}


def build(output: Path) -> dict[str, str]:
    """Build the controller zipapp atomically and return its provenance."""

    if not output.is_absolute():
        output = (Path.cwd() / output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        zipapp.create_archive(
            REPOSITORY / "src",
            target=temporary,
            interpreter=f"{Path(sys.executable).resolve()} -I",
            main="genome_to_diffraction.hpc.cli:entrypoint",
            compressed=True,
            filter=_include,
        )
        temporary.chmod(0o555)
        os.replace(temporary, output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "application": str(output),
        "python": str(Path(sys.executable).resolve()),
        "sha256": sha256_file(output),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Build an application at the requested ignored output path."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
