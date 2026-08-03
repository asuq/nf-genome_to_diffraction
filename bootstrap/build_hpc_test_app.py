"""Build a reviewed immutable zipapp for the local HPC approval boundary."""

import argparse
import json
import os
import sys
import zipfile
from collections.abc import Sequence
from pathlib import Path

from genome_to_diffraction.checksums import sha256_file

REPOSITORY = Path(__file__).resolve().parents[1]
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_MAIN = (
    b"# -*- coding: utf-8 -*-\n"
    b"import genome_to_diffraction.hpc.cli\n"
    b"genome_to_diffraction.hpc.cli.entrypoint()\n"
)


def _include(path: Path) -> bool:
    """Exclude bytecode and caches from the installed controller archive."""

    return "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}


def _write_entry(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    """Write one canonical regular-file member to the application archive."""

    info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(
        info,
        payload,
        compress_type=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    )


def _source_entries() -> list[tuple[str, bytes]]:
    """Return sorted source members and reject symlinked build inputs."""

    source = REPOSITORY / "src"
    entries = [("__main__.py", _MAIN)]
    for path in sorted(source.rglob("*")):
        if not _include(path):
            continue
        if path.is_symlink():
            raise ValueError(f"zipapp source must be a regular file: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"zipapp source must be a regular file: {path}")
        entries.append((path.relative_to(source).as_posix(), path.read_bytes()))
    return sorted(entries, key=lambda entry: entry[0])


def build(output: Path) -> dict[str, str]:
    """Build the controller zipapp atomically and return its provenance."""

    if not output.is_absolute():
        output = (Path.cwd() / output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        interpreter = f"#!{Path(sys.executable).resolve()} -I\n".encode("utf-8")
        with temporary.open("wb") as raw:
            raw.write(interpreter)
            with zipfile.ZipFile(raw, mode="a") as archive:
                for name, payload in _source_entries():
                    _write_entry(archive, name, payload)
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
