#!/usr/bin/env python3
"""Build the deterministic executable-surface inventory for the documentation atlas.

The inventory extracts current repository facts. Curated scientific explanations
and diagram topology remain separately reviewed sources under ``docs/atlas/sources``.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import re
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
DEFAULT_OUTPUT = Path("docs/atlas/generated/executable-inventory.json")
SUBSYSTEMS_PATH = Path("docs/atlas/sources/subsystems.json")
MILESTONE_PATTERN = re.compile(r"\b(?:M\d+|P\d+|RG\d+|R0A|T\d+)\b")
NEXTFLOW_DECLARATION = re.compile(
    r"^\s*(process|workflow)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
    re.MULTILINE,
)
NEXTFLOW_INCLUDE = re.compile(r"^\s*include\s*\{([^}]*)\}", re.MULTILINE)
BASH_FUNCTION = re.compile(
    r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Subsystem:
    """Curated subsystem path classification."""

    identifier: str
    title: str
    patterns: tuple[str, ...]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(document: Any) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("ascii")


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _load_subsystems(root: Path) -> tuple[Subsystem, ...]:
    document = json.loads((root / SUBSYSTEMS_PATH).read_text(encoding="utf-8"))
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("atlas subsystem metadata has an unsupported schema")
    return tuple(
        Subsystem(
            identifier=str(item["id"]),
            title=str(item["title"]),
            patterns=tuple(str(pattern) for pattern in item["patterns"]),
        )
        for item in document["subsystems"]
    )


def _subsystem(path: str, subsystems: tuple[Subsystem, ...]) -> str:
    for subsystem in subsystems:
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in subsystem.patterns):
            return subsystem.identifier
    return "unclassified"


def _annotation(node: ast.expr | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = f" -> {_annotation(node.returns)}" if node.returns is not None else ""
    return f"{prefix} {node.name}({ast.unparse(node.args)}){returns}"


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


class _PythonVisitor(ast.NodeVisitor):
    def __init__(self, source: str) -> None:
        self.source = source
        self.stack: list[str] = []
        self.symbols: list[dict[str, Any]] = []
        self.imports: set[str] = set()
        self.cli_commands: list[dict[str, Any]] = []

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.update(alias.name for alias in node.names)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        self.imports.add(module)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualname = ".".join((*self.stack, node.name))
        self.symbols.append(
            {
                "kind": "class",
                "name": node.name,
                "qualname": qualname,
                "line": node.lineno,
                "end_line": node.end_lineno,
                "public": not node.name.startswith("_"),
                "doc": (ast.get_docstring(node) or "").split("\n", maxsplit=1)[0],
                "bases": sorted(ast.unparse(base) for base in node.bases),
                "decorators": sorted(ast.unparse(item) for item in node.decorator_list),
            }
        )
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualname = ".".join((*self.stack, node.name))
        calls = sorted(
            {
                name
                for child in ast.walk(node)
                if isinstance(child, ast.Call)
                if (name := _call_name(child.func)) is not None
            }
        )
        self.symbols.append(
            {
                "kind": (
                    "async_function"
                    if isinstance(node, ast.AsyncFunctionDef)
                    else "function"
                ),
                "name": node.name,
                "qualname": qualname,
                "line": node.lineno,
                "end_line": node.end_lineno,
                "public": not node.name.startswith("_"),
                "signature": _signature(node),
                "doc": (ast.get_docstring(node) or "").split("\n", maxsplit=1)[0],
                "decorators": sorted(ast.unparse(item) for item in node.decorator_list),
                "calls": calls,
            }
        )
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_parser"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            self.cli_commands.append(
                {"command": node.args[0].value, "line": node.lineno}
            )
        self.generic_visit(node)


def _python_modules(
    root: Path,
    subsystems: tuple[Subsystem, ...],
    directory: Path,
) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = []
    for path in sorted(directory.rglob("*.py")):
        relative = _relative(path, root)
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=relative)
        except SyntaxError as error:
            raise ValueError(
                f"cannot parse Python module {relative}: {error}"
            ) from error
        visitor = _PythonVisitor(source)
        visitor.visit(tree)
        substantive = any(
            item["kind"] == "class"
            or item.get("end_line", item["line"]) - item["line"] >= 2
            for item in visitor.symbols
        )
        modules.append(
            {
                "path": relative,
                "subsystem": _subsystem(relative, subsystems),
                "sha256": _sha256(path.read_bytes()),
                "substantive": substantive,
                "imports": sorted(visitor.imports),
                "symbols": sorted(
                    visitor.symbols,
                    key=lambda item: (item["line"], item["qualname"]),
                ),
                "cli_commands": sorted(
                    visitor.cli_commands,
                    key=lambda item: (item["line"], item["command"]),
                ),
            }
        )
    return modules


def _nextflow_files(
    root: Path, subsystems: tuple[Subsystem, ...]
) -> list[dict[str, Any]]:
    candidates = [*root.glob("*.nf")]
    for directory in (root / "workflows", root / "modules" / "local"):
        candidates.extend(directory.rglob("*.nf"))
    records: list[dict[str, Any]] = []
    for path in sorted(set(candidates)):
        relative = _relative(path, root)
        source = path.read_text(encoding="utf-8")
        declarations = [
            {
                "kind": kind,
                "name": name,
                "line": source.count("\n", 0, match.start()) + 1,
            }
            for match in NEXTFLOW_DECLARATION.finditer(source)
            for kind, name in [match.groups()]
        ]
        includes = sorted(
            {
                token.strip()
                for match in NEXTFLOW_INCLUDE.finditer(source)
                for token in match.group(1).replace("\n", " ").split(";")
                if token.strip()
            }
        )
        records.append(
            {
                "path": relative,
                "subsystem": _subsystem(relative, subsystems),
                "sha256": _sha256(path.read_bytes()),
                "declarations": declarations,
                "includes": includes,
            }
        )
    return records


def _shell_files(root: Path, subsystems: tuple[Subsystem, ...]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    bootstrap = root / "bootstrap"
    for path in sorted(item for item in bootstrap.iterdir() if item.is_file()):
        source = path.read_text(encoding="utf-8", errors="strict")
        functions = [
            {
                "name": match.group(1),
                "line": source.count("\n", 0, match.start()) + 1,
            }
            for match in BASH_FUNCTION.finditer(source)
        ]
        if not functions and not source.startswith("#!"):
            continue
        relative = _relative(path, root)
        records.append(
            {
                "path": relative,
                "subsystem": _subsystem(relative, subsystems),
                "sha256": _sha256(path.read_bytes()),
                "functions": functions,
            }
        )
    return records


def _schemas(root: Path, subsystems: tuple[Subsystem, ...]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((root / "schemas").rglob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        relative = _relative(path, root)
        records.append(
            {
                "path": relative,
                "subsystem": _subsystem(relative, subsystems),
                "sha256": _sha256(path.read_bytes()),
                "id": document.get("$id"),
                "title": document.get("title"),
                "required_fields": sorted(document.get("required", [])),
            }
        )
    return records


def _project_scripts(root: Path) -> list[dict[str, str]]:
    document = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return [
        {"name": name, "target": target}
        for name, target in sorted(
            document.get("project", {}).get("scripts", {}).items()
        )
    ]


def _configuration_files(root: Path) -> list[dict[str, str]]:
    paths = [root / "nextflow.config", root / "pixi.toml", root / "pyproject.toml"]
    paths.extend(sorted((root / "conf").glob("*.config")))
    return [
        {"path": _relative(path, root), "sha256": _sha256(path.read_bytes())}
        for path in paths
        if path.is_file()
    ]


def _milestone_occurrences(root: Path) -> list[dict[str, Any]]:
    paths: list[Path] = []
    for relative in (
        "src/genome_to_diffraction",
        "workflows",
        "modules/local",
        "bootstrap",
    ):
        base = root / relative
        if base.is_dir():
            paths.extend(path for path in base.rglob("*") if path.is_file())
    paths.extend(root.glob("*.nf"))
    records: list[dict[str, Any]] = []
    for path in sorted(set(paths)):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            for match in MILESTONE_PATTERN.finditer(line):
                records.append(
                    {
                        "token": match.group(0),
                        "path": _relative(path, root),
                        "line": line_number,
                    }
                )
    return records


def build_inventory(root: Path) -> dict[str, Any]:
    """Return a deterministic inventory of repository executable surfaces."""

    root = root.resolve()
    subsystems = _load_subsystems(root)
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "subsystems": [
            {"id": item.identifier, "title": item.title} for item in subsystems
        ],
        "project_scripts": _project_scripts(root),
        "root_nextflow_entrypoints": sorted(path.name for path in root.glob("*.nf")),
        "python_modules": _python_modules(
            root, subsystems, root / "src" / "genome_to_diffraction"
        ),
        "test_modules": _python_modules(root, subsystems, root / "tests"),
        "nextflow_files": _nextflow_files(root, subsystems),
        "shell_files": _shell_files(root, subsystems),
        "schemas": _schemas(root, subsystems),
        "configuration_files": _configuration_files(root),
        "active_milestone_identifiers": _milestone_occurrences(root),
    }
    digest = _sha256(_json_bytes(document))
    return {**document, "inventory_id": f"atlasinv_{digest}"}


def _counts(document: dict[str, Any]) -> dict[str, int]:
    return {
        "python_modules": len(document["python_modules"]),
        "python_symbols": sum(
            len(module["symbols"]) for module in document["python_modules"]
        ),
        "test_modules": len(document["test_modules"]),
        "nextflow_files": len(document["nextflow_files"]),
        "nextflow_declarations": sum(
            len(item["declarations"]) for item in document["nextflow_files"]
        ),
        "shell_files": len(document["shell_files"]),
        "shell_functions": sum(
            len(item["functions"]) for item in document["shell_files"]
        ),
        "schemas": len(document["schemas"]),
        "milestone_occurrences": len(document["active_milestone_identifiers"]),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[2])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    document = build_inventory(root)
    expected = _json_bytes(document)
    if args.check:
        if not output.is_file() or output.read_bytes() != expected:
            print(f"documentation atlas inventory is stale: {output}", file=sys.stderr)
            return 1
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(expected)
    print(
        json.dumps(
            {"inventory_id": document["inventory_id"], **_counts(document)},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
