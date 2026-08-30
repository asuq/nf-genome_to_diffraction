#!/usr/bin/env python3
# ruff: noqa: E501
"""Build or verify the deterministic private documentation atlas HTML tree."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from collections.abc import Iterable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import build_inventory as inventory_builder

CURRENT = Path("docs/atlas/current")
INVENTORY_PATH = Path("docs/atlas/generated/executable-inventory.json")
SUBSYSTEMS_PATH = Path("docs/atlas/sources/subsystems.json")
OVERVIEW_PATH = Path("docs/atlas/current/overview.html")


STYLE = """\
:root { color-scheme: light dark; --bg:#f6f8fb; --panel:#fff; --text:#172033; --muted:#5e6b82; --line:#d6deea; --accent:#1663c7; --accent2:#087f5b; --code:#eef3fa; }
:root[data-theme='dark'] { --bg:#0f1521; --panel:#171f2e; --text:#e8eef8; --muted:#a8b4c8; --line:#334057; --accent:#71a7ff; --accent2:#5bd6aa; --code:#202a3b; }
* { box-sizing:border-box; }
body { margin:0; font:15px/1.55 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:var(--bg); color:var(--text); }
header { position:sticky; top:0; z-index:3; background:color-mix(in srgb,var(--panel) 94%,transparent); border-bottom:1px solid var(--line); backdrop-filter:blur(8px); }
.bar { max-width:1280px; margin:auto; padding:12px 24px; display:flex; gap:18px; align-items:center; flex-wrap:wrap; }
.brand { font-weight:750; margin-right:auto; }
nav a { color:var(--muted); margin-right:14px; text-decoration:none; }
nav a:hover,a { color:var(--accent); }
button,input { font:inherit; }
button { border:1px solid var(--line); border-radius:8px; padding:6px 10px; background:var(--panel); color:var(--text); cursor:pointer; }
main { max-width:1280px; margin:auto; padding:28px 24px 64px; }
h1 { font-size:2rem; line-height:1.15; margin:0 0 10px; }
h2 { margin-top:34px; border-bottom:1px solid var(--line); padding-bottom:8px; }
h3 { margin-bottom:6px; }
p.lead { color:var(--muted); max-width:78ch; font-size:1.05rem; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px; }
.card,section.symbol { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:16px; box-shadow:0 1px 2px rgba(0,0,0,.04); }
.card h3 { margin-top:0; }
.meta,.muted { color:var(--muted); }
.badge { display:inline-block; border:1px solid var(--line); border-radius:999px; padding:2px 8px; color:var(--muted); font-size:.8rem; }
code,pre { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; background:var(--code); }
code { padding:2px 5px; border-radius:5px; overflow-wrap:anywhere; }
pre { padding:12px; border-radius:8px; overflow:auto; }
table { width:100%; border-collapse:collapse; background:var(--panel); }
th,td { text-align:left; vertical-align:top; border-bottom:1px solid var(--line); padding:9px 10px; }
th { position:sticky; top:58px; background:var(--panel); }
.search { width:100%; max-width:700px; padding:10px 12px; border:1px solid var(--line); border-radius:9px; background:var(--panel); color:var(--text); margin:12px 0 18px; }
.stats { display:flex; gap:10px; flex-wrap:wrap; margin:18px 0; }
.stats span { background:var(--panel); border:1px solid var(--line); border-radius:9px; padding:8px 10px; }
iframe.overview { width:100%; min-height:760px; border:1px solid var(--line); border-radius:12px; background:var(--panel); }
ul.clean { list-style:none; padding:0; }
ul.clean li { padding:5px 0; }
.breadcrumbs { color:var(--muted); margin-bottom:14px; }
footer { color:var(--muted); border-top:1px solid var(--line); padding-top:20px; margin-top:42px; }
@media (max-width:700px) { main,.bar { padding-left:14px; padding-right:14px; } iframe.overview { min-height:620px; } th { position:static; } }
"""


SCRIPT = """\
(() => {
  const root = document.documentElement;
  const stored = localStorage.getItem('nf-gtd-atlas-theme');
  if (stored) root.dataset.theme = stored;
  document.querySelector('[data-theme-toggle]')?.addEventListener('click', () => {
    const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    localStorage.setItem('nf-gtd-atlas-theme', next);
  });
  const input = document.querySelector('[data-atlas-search]');
  if (input) input.addEventListener('input', () => {
    const query = input.value.trim().toLowerCase();
    document.querySelectorAll('[data-search-row]').forEach((row) => {
      row.hidden = query && !row.dataset.searchRow.includes(query);
    });
  });
})();
"""


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attribute = (
            "href"
            if tag in {"a", "link"}
            else "src"
            if tag
            in {
                "iframe",
                "script",
            }
            else None
        )
        if attribute is None:
            return
        for name, value in attrs:
            if name == attribute and value:
                self.targets.append(value)


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _slug(value: str) -> str:
    readable = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()[:64]
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"{readable or 'item'}-{digest}"


def _module_slug(path: str) -> str:
    replacements = (
        ("src/genome_to_diffraction/", "python-"),
        ("tests/", "test-"),
        ("modules/local/", "nextflow-module-"),
        ("workflows/", "nextflow-workflow-"),
        ("bootstrap/", "wrapper-"),
    )
    for prefix, replacement in replacements:
        if path.startswith(prefix):
            return _slug(replacement + path.removeprefix(prefix))
    if "/" not in path and path.endswith(".nf"):
        return _slug("entrypoint-" + path)
    return _slug(path)


def _json_bytes(document: Any) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("ascii")


def _page(relative: Path, title: str, body: str, inventory_id: str) -> bytes:
    depth = len(relative.parent.parts)
    prefix = "../" * depth
    navigation = "".join(
        f'<a href="{prefix}{target}">{label}</a>'
        for target, label in (
            ("index.html", "Home"),
            ("portals/scientist.html", "Scientist"),
            ("portals/developer.html", "Developer"),
            ("portals/validation.html", "Validation"),
            ("inventory.html", "Inventory"),
        )
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_escape(title)} - nf-genome_to_diffraction</title><link rel="stylesheet" href="{prefix}assets/atlas.css"></head>
<body><header><div class="bar"><div class="brand">nf-genome_to_diffraction atlas</div><nav>{navigation}</nav><button data-theme-toggle type="button">Light / Dark</button></div></header>
<main>{body}<footer>Deterministic private atlas inventory <code>{_escape(inventory_id)}</code></footer></main>
<script src="{prefix}assets/atlas.js"></script></body></html>
"""
    return document.encode("utf-8")


def _source_href(relative_page: Path, source_path: str, line: int | None = None) -> str:
    depth = len(relative_page.parent.parts)
    prefix = "../" * (depth + 3)
    suffix = f"#L{line}" if line else ""
    return f"{prefix}{source_path}{suffix}"


def _module_records(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for module in inventory["python_modules"]:
        records.append({"surface": "python", **module})
    for module in inventory["test_modules"]:
        records.append({"surface": "test", **module})
    for item in inventory["nextflow_files"]:
        records.append(
            {
                "surface": "nextflow",
                "path": item["path"],
                "subsystem": item["subsystem"],
                "sha256": item["sha256"],
                "substantive": bool(
                    item["declarations"] or item["includes"] or "/" not in item["path"]
                ),
                "symbols": [
                    {
                        "kind": declaration["kind"],
                        "name": declaration["name"],
                        "qualname": declaration["name"],
                        "line": declaration["line"],
                        "public": True,
                    }
                    for declaration in item["declarations"]
                ],
                "includes": item["includes"],
            }
        )
    for item in inventory["shell_files"]:
        records.append(
            {
                "surface": "shell",
                "path": item["path"],
                "subsystem": item["subsystem"],
                "sha256": item["sha256"],
                "substantive": bool(item["functions"]),
                "symbols": [
                    {
                        "kind": "shell_function",
                        "name": function["name"],
                        "qualname": function["name"],
                        "line": function["line"],
                        "public": not function["name"].startswith("_"),
                    }
                    for function in item["functions"]
                ],
            }
        )
    return sorted(records, key=lambda item: (item["surface"], item["path"]))


def _subsystem_metadata(root: Path) -> list[dict[str, Any]]:
    document = json.loads((root / SUBSYSTEMS_PATH).read_text(encoding="utf-8"))
    return list(document["subsystems"])


def _module_page(module: dict[str, Any], inventory_id: str) -> tuple[Path, bytes]:
    relative = Path("modules") / f"{_module_slug(module['path'])}.html"
    source = _source_href(relative, module["path"])
    symbol_sections: list[str] = []
    for symbol in module.get("symbols", []):
        anchor = _slug(symbol["qualname"])
        signature = symbol.get("signature") or f"{symbol['kind']} {symbol['name']}"
        calls = symbol.get("calls", [])
        call_html = (
            "<p><strong>Calls:</strong> "
            + ", ".join(f"<code>{_escape(item)}</code>" for item in calls)
            + "</p>"
            if calls
            else ""
        )
        doc = symbol.get("doc") or "No summary docstring is currently available."
        symbol_source = _source_href(relative, module["path"], symbol["line"])
        symbol_sections.append(
            f'<section class="symbol" id="{anchor}"><h3><code>{_escape(signature)}</code></h3>'
            f'<p>{_escape(doc)}</p><p class="meta">{_escape(symbol["kind"])}; line {symbol["line"]}; '
            f'{"public" if symbol.get("public") else "internal"} - <a href="{symbol_source}">source</a></p>{call_html}</section>'
        )
    includes = module.get("includes", [])
    include_html = (
        "<h2>Includes</h2><ul>"
        + "".join(f"<li><code>{_escape(item)}</code></li>" for item in includes)
        + "</ul>"
        if includes
        else ""
    )
    body = (
        f'<div class="breadcrumbs"><a href="../portals/developer.html">Developer</a> / Module</div>'
        f'<h1>{_escape(module["path"])}</h1><p class="lead">{_escape(module["surface"])} surface in '
        f'<a href="../subsystems/{_slug(module["subsystem"])}.html">{_escape(module["subsystem"])}</a>.</p>'
        f'<div class="stats"><span>{len(module.get("symbols", []))} symbols</span><span>{"substantive" if module.get("substantive") else "inventory only"}</span></div>'
        f'<p><a href="{source}">Open complete source</a></p>{include_html}<h2>Functions, classes and processes</h2>'
        + "".join(symbol_sections)
    )
    return relative, _page(relative, module["path"], body, inventory_id)


def _subsystem_page(
    subsystem: dict[str, Any],
    modules: list[dict[str, Any]],
    inventory_id: str,
) -> tuple[Path, bytes]:
    relative = Path("subsystems") / f"{_slug(subsystem['id'])}.html"
    module_links = []
    for module in modules:
        if module["subsystem"] != subsystem["id"]:
            continue
        target = (
            f"../modules/{_module_slug(module['path'])}.html"
            if module.get("substantive")
            else _source_href(relative, module["path"])
        )
        module_links.append(
            f'<li><a href="{target}"><code>{_escape(module["path"])}</code></a> '
            f'<span class="badge">{_escape(module["surface"])}</span></li>'
        )
    body = (
        '<div class="breadcrumbs"><a href="../index.html">Home</a> / Subsystem</div>'
        f'<h1>{_escape(subsystem["title"])}</h1><div class="grid">'
        f'<section class="card"><h3>Scientific view</h3><p>{_escape(subsystem["scientific_summary"])}</p></section>'
        f'<section class="card"><h3>Developer view</h3><p>{_escape(subsystem["developer_summary"])}</p></section></div>'
        f'<h2>Substantive and inventory modules</h2><ul class="clean">{"".join(module_links) or "<li>No classified modules.</li>"}</ul>'
    )
    return relative, _page(relative, subsystem["title"], body, inventory_id)


def _contract_page(contract: dict[str, Any], inventory_id: str) -> tuple[Path, bytes]:
    relative = Path("contracts") / f"{_slug(contract['path'])}.html"
    source = _source_href(relative, contract["path"])
    required = "".join(
        f"<li><code>{_escape(item)}</code></li>" for item in contract["required_fields"]
    )
    body = (
        '<div class="breadcrumbs"><a href="../index.html">Home</a> / Data contract</div>'
        f"<h1>{_escape(contract.get('title') or contract['path'])}</h1>"
        f'<p class="lead"><code>{_escape(contract["path"])}</code></p>'
        f'<p><a href="{source}">Open JSON Schema source</a></p>'
        f"<h2>Required top-level fields</h2><ul>{required or '<li>None declared at the top level.</li>'}</ul>"
        '<p class="muted">Producer/consumer graphs and curated scientific field semantics are added after the pass-1 code cleanup stabilises active contract names.</p>'
    )
    return relative, _page(
        relative, contract.get("title") or contract["path"], body, inventory_id
    )


def _inventory_page(
    inventory: dict[str, Any], modules: list[dict[str, Any]]
) -> tuple[Path, bytes]:
    relative = Path("inventory.html")
    rows: list[str] = []
    for module in modules:
        module_target = (
            f"modules/{_module_slug(module['path'])}.html"
            if module.get("substantive")
            else _source_href(relative, module["path"])
        )
        rows.append(
            f'<tr data-search-row="{_escape((module["surface"] + " " + module["path"] + " " + module["subsystem"]).lower())}">'
            f'<td>{_escape(module["surface"])}</td><td><a href="{module_target}"><code>{_escape(module["path"])}</code></a></td>'
            f"<td>{_escape(module['subsystem'])}</td><td>module</td></tr>"
        )
        for symbol in module.get("symbols", []):
            anchor = _slug(symbol["qualname"])
            text = " ".join(
                (
                    module["surface"],
                    module["path"],
                    module["subsystem"],
                    symbol["kind"],
                    symbol["qualname"],
                )
            ).lower()
            rows.append(
                f'<tr data-search-row="{_escape(text)}"><td>{_escape(module["surface"])}</td>'
                f'<td><a href="{module_target}#{anchor}"><code>{_escape(module["path"])}</code></a></td>'
                f"<td>{_escape(module['subsystem'])}</td><td><code>{_escape(symbol['qualname'])}</code></td></tr>"
            )
    body = (
        '<h1>Executable Surface Inventory</h1><p class="lead">Complete searchable extraction of active Python, tests, Nextflow, reviewed shell functions, schemas and entrypoints.</p>'
        '<input class="search" type="search" placeholder="Filter by path, subsystem, symbol or surface" data-atlas-search>'
        "<table><thead><tr><th>Surface</th><th>Source</th><th>Subsystem</th><th>Module / symbol</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    return relative, _page(
        relative, "Executable Surface Inventory", body, inventory["inventory_id"]
    )


def _portal_page(
    name: str,
    title: str,
    lead: str,
    subsystems: list[dict[str, Any]],
    inventory: dict[str, Any],
) -> tuple[Path, bytes]:
    relative = Path("portals") / f"{name}.html"
    cards: list[str] = []
    for subsystem in subsystems:
        summary = subsystem[
            "scientific_summary" if name == "scientist" else "developer_summary"
        ]
        target = f"../subsystems/{_slug(subsystem['id'])}.html"
        cards.append(
            f'<article class="card"><h3><a href="{target}">{_escape(subsystem["title"])}</a></h3><p>{_escape(summary)}</p></article>'
        )
    extra = ""
    if name == "validation":
        extra = (
            '<div class="stats">'
            f"<span>{len(inventory['test_modules'])} test modules</span>"
            f"<span>{len(inventory['schemas'])} active schemas</span>"
            f"<span>{len(inventory['active_milestone_identifiers'])} milestone-name occurrences queued for cleanup</span></div>"
            '<p><a href="../inventory.html">Search validation and implementation surfaces</a></p>'
        )
        cards = [
            '<article class="card"><h3>Known controls</h3><p>Positive, adverse, wrong-component, and runtime controls remain isolated from normal analyses.</p></article>',
            '<article class="card"><h3>Robustness validation</h3><p>Operational, leakage, cache-mutation, child-completeness, and reproducibility evidence.</p></article>',
            '<article class="card"><h3>Release structure</h3><p>Atlas freshness, active-contract tests, wheel contents, schemas, links, and milestone-name cleanup.</p></article>',
        ]
    body = f'<h1>{_escape(title)}</h1><p class="lead">{_escape(lead)}</p>{extra}<div class="grid">{"".join(cards)}</div>'
    return relative, _page(relative, title, body, inventory["inventory_id"])


def _external_tools_page(inventory_id: str) -> tuple[Path, bytes]:
    relative = Path("external-tools.html")
    tools = (
        (
            "Nextflow",
            "DSL2 orchestration, task fan-out, caching, and executor ownership.",
        ),
        (
            "Slurm",
            "Scheduler admission, placement, resource accounting, and terminal state.",
        ),
        (
            "Phenix",
            "Licensed crystallographic preflight, Phaser, refinement, maps, and sequence mapping.",
        ),
        ("MMseqs2", "Catalogue-wide PDB sequence discovery."),
        (
            "ProstT5 + Foldseek",
            "Whole-catalogue structural search against the local PDB resource.",
        ),
        ("PSORTb + DeepTMHMM", "Offline localisation and membrane-topology evidence."),
        ("Pixi + Apptainer", "Locked software environment and container execution."),
    )
    cards = "".join(
        f'<article class="card"><h3>{_escape(name)}</h3><p>{_escape(summary)}</p><span class="badge">boundary page pending curation</span></article>'
        for name, summary in tools
    )
    body = f'<h1>External Tool Boundaries</h1><p class="lead">First-class contract pages record exact versions, commands, inputs, outputs, failures, licensing, and network constraints without documenting external internals.</p><div class="grid">{cards}</div>'
    return relative, _page(relative, "External Tool Boundaries", body, inventory_id)


def _index_page(
    inventory: dict[str, Any],
    subsystems: list[dict[str, Any]],
    modules: list[dict[str, Any]],
) -> tuple[Path, bytes]:
    relative = Path("index.html")
    substantive = sum(bool(item.get("substantive")) for item in modules)
    body = (
        '<h1>Documentation Atlas</h1><p class="lead">Two audience portals and one validation portal converge on shared canonical subsystems, then drill into modules, functions, processes, contracts, tests, and external boundaries.</p>'
        '<div class="grid"><article class="card"><h3><a href="portals/scientist.html">Scientist / Operator</a></h3><p>Scientific purpose, workflow, evidence, decisions, and honest claim boundaries.</p></article>'
        '<article class="card"><h3><a href="portals/developer.html">Developer</a></h3><p>Architecture, executable surfaces, contracts, call relationships, and source.</p></article>'
        '<article class="card"><h3><a href="portals/validation.html">Validation & Evidence</a></h3><p>Controls, robustness checks, fixtures, accepted evidence, and release gates.</p></article></div>'
        f'<div class="stats"><span>{len(subsystems)} subsystems</span><span>{substantive} substantive modules</span>'
        f"<span>{sum(len(item.get('symbols', [])) for item in modules)} symbols</span><span>{len(inventory['schemas'])} schemas</span></div>"
        '<p><a href="inventory.html">Search the complete executable inventory</a> - <a href="external-tools.html">Inspect external tool boundaries</a></p>'
        '<h2>Atlas architecture</h2><iframe class="overview" src="overview.html" title="Documentation atlas architecture"></iframe>'
    )
    return relative, _page(
        relative, "Documentation Atlas", body, inventory["inventory_id"]
    )


def _validate_links(root: Path, outputs: dict[Path, bytes]) -> None:
    expected = {(root / path).resolve() for path in outputs}
    missing: list[str] = []
    for relative, content in sorted(outputs.items()):
        if relative.suffix != ".html":
            continue
        parser = _LinkParser()
        parser.feed(content.decode("utf-8"))
        page = (root / relative).resolve()
        for target in parser.targets:
            split = urlsplit(target)
            if split.scheme or split.netloc or not split.path:
                continue
            resolved = (page.parent / unquote(split.path)).resolve()
            if resolved not in expected and not resolved.is_file():
                missing.append(f"{relative.as_posix()} -> {target}")
    if missing:
        raise ValueError(
            "atlas contains missing local links:\n- " + "\n- ".join(missing)
        )


def build_outputs(root: Path) -> dict[Path, bytes]:
    root = root.resolve()
    inventory = inventory_builder.build_inventory(root)
    inventory_bytes = inventory_builder._json_bytes(inventory)
    subsystems = _subsystem_metadata(root)
    modules = _module_records(inventory)
    if any(module["subsystem"] == "unclassified" for module in modules):
        subsystems.append(
            {
                "id": "unclassified",
                "title": "Unclassified Cleanup Inventory",
                "scientific_summary": (
                    "Executable surfaces awaiting a role-based subsystem during the "
                    "pre-release clean break."
                ),
                "developer_summary": (
                    "Diagnostic inventory entries that must be classified or removed "
                    "before release."
                ),
            }
        )
    outputs: dict[Path, bytes] = {INVENTORY_PATH: inventory_bytes}
    outputs[CURRENT / "assets/atlas.css"] = STYLE.encode("utf-8")
    outputs[CURRENT / "assets/atlas.js"] = SCRIPT.encode("utf-8")
    pages: list[tuple[Path, bytes]] = [
        _index_page(inventory, subsystems, modules),
        _inventory_page(inventory, modules),
        _external_tools_page(inventory["inventory_id"]),
        _portal_page(
            "scientist",
            "Scientist / Operator Portal",
            "Navigate from genome and diffraction inputs through evidence-ranked structural hypotheses and review checkpoints.",
            [item for item in subsystems if item["id"] != "validation"],
            inventory,
        ),
        _portal_page(
            "developer",
            "Developer Portal",
            "Navigate the role-based architecture, contracts, orchestration, modules, functions, tests, and source links.",
            subsystems,
            inventory,
        ),
        _portal_page(
            "validation",
            "Validation & Evidence Portal",
            "Internal controls and release evidence remain separate from the normal scientific application workflow.",
            subsystems,
            inventory,
        ),
    ]
    pages.extend(
        _subsystem_page(item, modules, inventory["inventory_id"]) for item in subsystems
    )
    pages.extend(
        _module_page(item, inventory["inventory_id"])
        for item in modules
        if item.get("substantive")
    )
    pages.extend(
        _contract_page(item, inventory["inventory_id"]) for item in inventory["schemas"]
    )
    outputs.update({CURRENT / path: data for path, data in pages})
    managed_files = [
        {
            "path": path.relative_to(CURRENT).as_posix(),
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        }
        for path, data in sorted(outputs.items())
        if path.is_relative_to(CURRENT)
    ]
    manifest = {
        "schema_version": "1.0",
        "inventory_id": inventory["inventory_id"],
        "files": managed_files,
    }
    outputs[CURRENT / "manifest.json"] = _json_bytes(manifest)
    _validate_links(root, outputs)
    return outputs


def _write(root: Path, outputs: dict[Path, bytes]) -> None:
    manifest_path = root / CURRENT / "manifest.json"
    previous: set[Path] = set()
    if manifest_path.is_file():
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        previous = {root / CURRENT / item["path"] for item in document.get("files", [])}
        previous.add(manifest_path)
    expected = {root / path for path in outputs}
    for path in sorted(previous - expected):
        if path.is_file() and path.resolve().is_relative_to((root / CURRENT).resolve()):
            path.unlink()
    for relative, data in outputs.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def _check(root: Path, outputs: dict[Path, bytes]) -> bool:
    stale = [
        relative.as_posix()
        for relative, expected in outputs.items()
        if not (root / relative).is_file() or (root / relative).read_bytes() != expected
    ]
    if stale:
        print("documentation atlas is stale:", file=sys.stderr)
        for path in stale:
            print(f"- {path}", file=sys.stderr)
        return False
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[2])
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    outputs = build_outputs(root)
    if args.check:
        if not _check(root, outputs):
            return 1
    else:
        _write(root, outputs)
    inventory = inventory_builder.build_inventory(root)
    print(
        json.dumps(
            {
                "inventory_id": inventory["inventory_id"],
                "generated_files": len(outputs),
                "status": "current" if args.check else "built",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
