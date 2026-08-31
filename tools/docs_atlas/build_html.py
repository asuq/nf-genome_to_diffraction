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
PORTAL_CONTENT_PATH = Path("docs/atlas/sources/portal-content.json")
DIAGRAM_PATHS = (
    Path("docs/atlas/current/diagrams/scientist-workflow.html"),
    Path("docs/atlas/current/diagrams/developer-architecture.html"),
)
OBSOLETE_GENERATED = (
    Path("docs/atlas/current/overview.html"),
    Path("docs/atlas/current/portals/scientist.html"),
    Path("docs/atlas/current/portals/developer.html"),
    Path("docs/atlas/current/portals/validation.html"),
    Path("docs/atlas/current/scientist.html"),
    Path("docs/atlas/current/developer.html"),
    Path("docs/atlas/current/diagrams/scientist-workflow.visual-check.json"),
    Path("docs/atlas/current/diagrams/developer-architecture.visual-check.json"),
)


STYLE = """\
:root { color-scheme:dark; --bg:#0c1320; --panel:#141e2d; --panel2:#1b283a; --text:#e8eef8; --muted:#a8b5c9; --line:#314057; --accent:#79adff; --accent2:#61d8ae; --warn:#ffd274; --warn-bg:#302713; --code:#202c3d; --shadow:0 14px 40px rgba(0,0,0,.28); }
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { margin:0; font:15px/1.58 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:var(--bg); color:var(--text); }
a { color:var(--accent); }
a:focus-visible,button:focus-visible,input:focus-visible,summary:focus-visible { outline:3px solid var(--accent); outline-offset:3px; }
.skip-link { position:fixed; left:12px; top:-60px; z-index:10; padding:9px 12px; background:var(--panel); border:2px solid var(--accent); border-radius:8px; }
.skip-link:focus { top:10px; }
header { position:sticky; top:0; z-index:3; background:color-mix(in srgb,var(--panel) 94%,transparent); border-bottom:1px solid var(--line); backdrop-filter:blur(10px); }
.bar { max-width:1360px; margin:auto; padding:11px 24px; display:flex; gap:18px; align-items:center; flex-wrap:wrap; }
.brand { font-weight:780; margin-right:auto; letter-spacing:-.01em; }
nav { display:flex; gap:4px; flex-wrap:wrap; }
nav a { color:var(--muted); padding:6px 9px; border-radius:7px; text-decoration:none; }
nav a:hover,nav a[aria-current='page'] { color:var(--text); background:var(--panel2); }
button,input { font:inherit; }
button { border:1px solid var(--line); border-radius:8px; padding:6px 10px; background:var(--panel); color:var(--text); cursor:pointer; }
main { max-width:1360px; margin:auto; padding:36px 24px 72px; }
h1 { max-width:26ch; font-size:clamp(2rem,4vw,3.5rem); line-height:1.06; letter-spacing:-.035em; margin:0 0 14px; }
h2 { margin-top:44px; border-bottom:1px solid var(--line); padding-bottom:9px; letter-spacing:-.015em; }
h3 { margin-bottom:6px; }
p.lead { color:var(--muted); max-width:76ch; font-size:1.12rem; }
.eyebrow { color:var(--accent); font-weight:750; font-size:.78rem; letter-spacing:.12em; text-transform:uppercase; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px; }
.stage-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(285px,1fr)); gap:16px; counter-reset:stage; }
.card,details.symbol,.rail,.warning,.detail-panel { background:var(--panel); border:1px solid var(--line); border-radius:13px; padding:18px; box-shadow:var(--shadow); }
.card h3 { margin-top:0; }
.card-link { color:inherit; text-decoration:none; }
.card-link::after { content:'  →'; color:var(--accent); }
.stage-number { color:var(--accent); font:700 .78rem/1 ui-monospace,SFMono-Regular,Menlo,monospace; letter-spacing:.08em; }
.meta,.muted { color:var(--muted); }
.badge { display:inline-block; border:1px solid var(--line); border-radius:999px; padding:3px 9px; color:var(--muted); font-size:.78rem; }
.badge.maturity { color:var(--accent2); border-color:color-mix(in srgb,var(--accent2) 45%,var(--line)); }
.warning { color:var(--warn); background:var(--warn-bg); border-color:color-mix(in srgb,var(--warn) 35%,var(--line)); box-shadow:none; }
.rail { border-left:5px solid var(--accent2); box-shadow:none; }
.detail-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }
.detail-panel h2,.detail-panel h3 { margin-top:0; }
.composition-loop { margin:18px 0; padding:16px; border:1px solid var(--line); border-radius:12px; background:var(--panel); }
.composition-loop h2,.composition-loop h3 { margin:0 0 8px; }
.composition-slots,.composition-cycle { display:flex; align-items:center; gap:7px; flex-wrap:wrap; }
.composition-slot,.composition-cycle-step { padding:6px 9px; border:1px solid var(--line); border-radius:8px; background:var(--panel2); }
.composition-slot.reviewed { border-color:var(--accent2); color:var(--accent2); }
.composition-arrow { color:var(--accent); font-weight:800; }
.composition-cycle { margin-top:12px; }
.composition-loopback { margin-top:10px; padding:8px 10px; border-left:3px solid var(--accent); background:var(--panel2); }
.composition-limits { color:var(--muted); font-size:.88rem; }
details { margin:14px 0; }
summary { cursor:pointer; font-weight:700; }
details.symbol { padding:0; overflow:hidden; }
details.symbol > summary { padding:15px 18px; }
details.symbol > .symbol-body { padding:0 18px 18px; border-top:1px solid var(--line); }
code,pre { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; background:var(--code); }
code { padding:2px 5px; border-radius:5px; overflow-wrap:anywhere; }
pre { padding:12px; border-radius:8px; overflow:auto; white-space:pre-wrap; }
table { width:100%; border-collapse:collapse; background:var(--panel); }
th,td { text-align:left; vertical-align:top; border-bottom:1px solid var(--line); padding:9px 10px; }
th { position:sticky; top:58px; background:var(--panel); }
.search { width:100%; max-width:760px; padding:10px 12px; border:1px solid var(--line); border-radius:9px; background:var(--panel); color:var(--text); margin:12px 0 18px; }
.stats { display:flex; gap:10px; flex-wrap:wrap; margin:18px 0; }
.stats span { background:var(--panel); border:1px solid var(--line); border-radius:9px; padding:8px 10px; }
ul.clean { list-style:none; padding:0; }
ul.clean li { padding:5px 0; }
.breadcrumbs { color:var(--muted); margin-bottom:18px; }
.breadcrumbs a { color:inherit; }
.callout-links { display:flex; gap:12px; flex-wrap:wrap; }
.callout-links a { border:1px solid var(--line); border-radius:9px; padding:8px 11px; text-decoration:none; background:var(--panel); }
.stage-reference { display:grid; grid-template-columns:230px minmax(0,1fr); gap:28px; align-items:start; }
.stage-navigator { position:sticky; top:76px; max-height:calc(100vh - 96px); overflow:auto; padding:14px; border:1px solid var(--line); border-radius:12px; background:var(--panel); }
.stage-navigator > a { display:block; margin-bottom:12px; font-weight:700; text-decoration:none; }
.stage-navigator ol { margin:0; padding-left:22px; }
.stage-navigator li { padding:4px 0; }
.stage-navigator a[aria-current='step'] { color:var(--text); font-weight:750; }
.stage-select-label,.stage-select { display:none; }
.stage-content { min-width:0; }
footer { color:var(--muted); border-top:1px solid var(--line); padding-top:20px; margin-top:48px; }
@media (max-width:700px) { main,.bar { padding-left:14px; padding-right:14px; } .detail-grid { grid-template-columns:1fr; } th { position:static; } .stage-reference { display:block; } .stage-navigator { top:0; z-index:2; max-height:none; margin:0 -14px 18px; padding:9px 14px; border-width:0 0 1px; border-radius:0; overflow:visible; } .stage-navigator > a,.stage-navigator ol { display:none; } .stage-select-label { display:block; color:var(--muted); font-size:.76rem; } .stage-select { display:block; width:100%; margin-top:4px; padding:8px; border:1px solid var(--line); border-radius:8px; background:var(--panel2); color:var(--text); } }
"""


SCRIPT = """\
(() => {
  const input = document.querySelector('[data-atlas-search]');
  if (input) input.addEventListener('input', () => {
    const query = input.value.trim().toLowerCase();
    document.querySelectorAll('[data-search-row]').forEach((row) => {
      row.hidden = query && !row.dataset.searchRow.includes(query);
    });
  });
  document.querySelector('[data-stage-select]')?.addEventListener('change', (event) => {
    window.location.href = event.currentTarget.value;
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
    current_top = relative.parts[0] if relative.parts else relative.name
    current_target = {
        "stages": "documentation.html",
        "modules": "documentation.html",
        "contracts": "documentation.html",
        "external-tools.html": "documentation.html",
    }.get(current_top, current_top)
    navigation = "".join(
        f'<a href="{prefix}{target}"{(' aria-current="page"' if current_target == target else "")}>{label}</a>'
        for target, label in (
            ("documentation.html", "Documentation"),
            ("validation.html", "Validation & Evidence"),
            ("inventory.html", "Inventory"),
        )
    )
    document = f"""<!doctype html>
<html lang="en" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_escape(title)} - nf-genome_to_diffraction</title><link rel="stylesheet" href="{prefix}assets/atlas.css"></head>
<body><a class="skip-link" href="#main-content">Skip to main content</a><header><div class="bar"><div class="brand">nf-genome_to_diffraction</div><nav aria-label="Primary">{navigation}</nav></div></header>
<main id="main-content">{body}<footer>Deterministic private atlas inventory <code>{_escape(inventory_id)}</code></footer></main>
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
        search_text = " ".join(
            (str(signature), str(doc), str(symbol["kind"]), " ".join(calls))
        ).lower()
        symbol_sections.append(
            f'<details class="symbol" id="{anchor}" data-search-row="{_escape(search_text)}"><summary><code>{_escape(signature)}</code></summary>'
            f'<div class="symbol-body"><p>{_escape(doc)}</p><p class="meta">{_escape(symbol["kind"])}; line {symbol["line"]}; '
            f'{"public" if symbol.get("public") else "internal"} - <a href="{symbol_source}">source</a></p>{call_html}</div></details>'
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
        f'<div class="breadcrumbs"><a href="../documentation.html#developer">Documentation</a> / Module</div>'
        f'<h1>{_escape(module["path"])}</h1><p class="lead">{_escape(module["surface"])} surface in '
        f'<a href="../subsystems/{_slug(module["subsystem"])}.html">{_escape(module["subsystem"])}</a>.</p>'
        f'<div class="stats"><span>{len(module.get("symbols", []))} symbols</span><span>{"substantive" if module.get("substantive") else "inventory only"}</span></div>'
        f'<p><a href="{source}">Open complete source</a></p>{include_html}<h2>Functions, classes and processes</h2>'
        '<p class="muted">Implementation symbols are collapsed by default. Search, then expand only the item you need.</p>'
        '<input class="search" type="search" placeholder="Filter symbols on this page" aria-label="Filter symbols on this page" data-atlas-search>'
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
        '<div class="breadcrumbs"><a href="../documentation.html">Documentation</a> / Subsystem</div>'
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
        '<div class="breadcrumbs"><a href="../documentation.html#developer">Documentation</a> / Data contract</div>'
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


def _portal_content(root: Path) -> dict[str, Any]:
    return json.loads((root / PORTAL_CONTENT_PATH).read_text(encoding="utf-8"))


def _subsystem_links(
    ids: list[str], subsystems: list[dict[str, Any]], prefix: str
) -> str:
    by_id = {item["id"]: item for item in subsystems}
    return "".join(
        f'<a href="{prefix}subsystems/{_slug(identifier)}.html">{_escape(by_id[identifier]["title"])}</a>'
        for identifier in ids
    )


def _list(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{_escape(item)}</li>" for item in items) + "</ul>"


def _composition_loop() -> str:
    components = '<span class="composition-arrow">→</span>'.join(
        f'<span class="composition-slot{(" reviewed" if number == 1 else "")}">Component {number}</span>'
        for number in range(1, 7)
    )
    cycle = '<span class="composition-arrow">→</span>'.join(
        f'<span class="composition-cycle-step">{label}</span>'
        for label in (
            "Choose another protein from the supplied list",
            "Test 1, 2, 3, or 4 copies with Molecular Replacement",
            "Collect states",
            "Human review",
        )
    )
    return (
        '<section class="composition-loop" aria-label="Additional distinct-component search loop">'
        '<h3>How the additional distinct-component loop works</h3>'
        '<p>The first component is reviewed before expansion. The workflow may then add as many as five different components, one at each depth.</p>'
        f'<div class="composition-slots" aria-label="Component depth progression">{components}</div>'
        f'<div class="composition-cycle" aria-label="Work repeated at each additional-component depth">{cycle}</div>'
        '<div class="composition-loopback"><strong>Stop</strong> → publish the reviewed result &nbsp; | &nbsp; <strong>Continue</strong> ↻ repeat the cycle for the next component.</div>'
        '<p class="composition-limits">Limits: at most 25 attempts per depth, up to three retained parent states, 100 additional-component attempts per crystal, and six total components. Depths four through six remain provisional.</p>'
        '</section>'
    )


def _model_discovery_guide() -> str:
    return (
        '<section class="composition-loop" aria-label="Protein structure model search routes">'
        '<h3>Where protein structure models come from</h3>'
        '<p><strong>PDB sequence route:</strong> MMseqs2 searches the local PDB SEQRES database. Keep E-value ≤ 1e-5, query coverage ≥ 50%, and at most three hits per supplied protein.</p>'
        '<p><strong>PDB structure-sensitive route:</strong> ProstT5 converts a protein sequence into a predicted 3Di structural alphabet; Foldseek searches local PDB100. Keep E-value ≤ 1e-3, query coverage ≥ 50%, and at most three hits per supplied protein.</p>'
        '<p><strong>Exact prediction route:</strong> AlphaFold DB is used only when an explicit accession map links a supplied protein to the prediction. Public ESM Atlas is disabled by default.</p>'
        '<h3>What must pass before testing</h3>'
        '<p>The hit must map back to a supplied protein sequence. Its coordinate file, checksum, chain, residue sequence, and supported single-model structure must validate. A normal no-hit remains a valid search result.</p>'
        '</section>'
    )


def _stage_page(
    stage: dict[str, Any],
    stages: list[dict[str, Any]],
    subsystems: list[dict[str, Any]],
    inventory_id: str,
) -> tuple[Path, bytes]:
    relative = Path("stages") / f"{stage['id']}.html"
    subsystem_links = _subsystem_links(stage["subsystems"], subsystems, "../")
    commands = "\n".join(stage["commands"])
    previous_next: list[str] = []
    index = stages.index(stage)
    if index:
        previous = stages[index - 1]
        previous_next.append(
            f'<a href="{previous["id"]}.html">← {_escape(previous["title"])}</a>'
        )
    if index + 1 < len(stages):
        following = stages[index + 1]
        previous_next.append(
            f'<a href="{following["id"]}.html">{_escape(following["title"])} →</a>'
        )
    stage_links = "".join(
        f'<li><a href="{item["id"]}.html"{(' aria-current="step"' if item["id"] == stage["id"] else "")}>{_escape(item["number"])}. {_escape(item["title"])}</a></li>'
        for item in stages
    )
    stage_options = "".join(
        f'<option value="{item["id"]}.html"{(" selected" if item["id"] == stage["id"] else "")}>{_escape(item["number"])}. {_escape(item["title"])}</option>'
        for item in stages
    )
    composition_visual = _composition_loop() if stage["id"] == "composition" else ""
    content_body = (
        '<div class="breadcrumbs"><a href="../documentation.html">Documentation</a> / Workflow stage</div>'
        f'<div class="eyebrow">Stage {_escape(stage["number"])}</div><h1>{_escape(stage["title"])}</h1>'
        f'<p class="lead">{_escape(stage["summary"])}</p>'
        f'<p><span class="badge maturity">Current maturity: {_escape(stage["maturity"])}</span></p>'
        f'<aside class="warning" role="note"><strong>Visible limitation.</strong> {_escape(stage["warning"])}</aside>'
        f"{composition_visual}"
        '<div class="detail-grid">'
        f'<section class="detail-panel"><h2>Purpose</h2><p>{_escape(stage["purpose"])}</p></section>'
        f'<section class="detail-panel"><h2>Inputs</h2>{_list(stage["inputs"])}</section>'
        f'<section class="detail-panel"><h2>Outputs</h2>{_list(stage["outputs"])}</section>'
        f'<section class="detail-panel"><h2>Decisions and statuses</h2>{_list(stage["decisions"])}</section>'
        "</div><h2>Claim and failure boundaries</h2>"
        f"{_list(stage['boundaries'])}"
        "<details><summary>Run commands and implementation links</summary>"
        "<p>Use commands only with the reviewed configuration, immutable source, and owned inputs for the intended site. Placeholders are deliberate.</p>"
        f'<pre><code>{_escape(commands)}</code></pre><div class="callout-links">{subsystem_links}'
        '<a href="../inventory.html">Search implementation inventory</a></div></details>'
        f'<nav class="callout-links" aria-label="Workflow stage navigation">{"".join(previous_next)}</nav>'
    )
    navigator = (
        '<nav class="stage-navigator" aria-label="Workflow stages">'
        '<a href="../documentation.html">← Return to workflow viewer</a>'
        f'<ol>{stage_links}</ol><label class="stage-select-label" for="stage-select">Workflow reference</label>'
        f'<select class="stage-select" id="stage-select" data-stage-select><option value="../documentation.html">Return to workflow viewer</option>{stage_options}</select></nav>'
    )
    body = f'<div class="stage-reference">{navigator}<article class="stage-content">{content_body}</article></div>'
    return relative, _page(relative, stage["title"], body, inventory_id)


VIEWER_DRAWER_STYLE = """
    /* Documentation navigation injected by the deterministic atlas builder. */
    html, body { max-width: 100%; overflow-x: clip; }
    @media (min-width: 701px) { html:not([data-embed="true"]) body { padding-top: 4rem; padding-bottom: .5rem; } }
    html[data-atlas-docs-open="true"] body { padding-right: 440px; }
    html[data-atlas-docs-open="true"] .toolbar { right: calc(440px + 1rem); }
    html[data-atlas-docs-open="true"] .toolbar .preset-wrap,
    html[data-atlas-docs-open="true"] .toolbar #btn-motion,
    html[data-atlas-docs-open="true"] .toolbar #btn-present,
    html[data-atlas-docs-open="true"] .toolbar .export-wrap,
    html[data-atlas-docs-open="true"] .toolbar .atlas-docs-toggle { display: none !important; }
    html[data-atlas-docs-open="true"] .header { padding-right: 210px; }
    #btn-theme, .focus-chip, .semantic-sigil { display: none !important; }
    .atlas-docs-drawer {
      position: fixed; inset: 0 0 0 auto; z-index: 2147483000;
      width: 440px; max-width: 100vw; height: 100dvh; overflow: auto;
      background: color-mix(in srgb, var(--toolbar-menu-bg) 97%, transparent);
      color: var(--toolbar-text); border-left: 1px solid var(--toolbar-border);
      box-shadow: -20px 0 60px rgba(0,0,0,.34); padding: 0 22px 28px;
      font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .atlas-docs-drawer[hidden] { display: none !important; }
    .atlas-docs-head { position: sticky; top: 0; z-index: 1; margin: 0 -22px 18px; padding: 18px 22px 14px; display: flex; gap: 14px; align-items: start; background: var(--toolbar-menu-bg); border-bottom: 1px solid var(--toolbar-border); }
    .atlas-docs-head > div { flex: 1; min-width: 0; }
    .atlas-docs-eyebrow { display: block; color: var(--frontend-stroke); font: 700 11px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: .1em; text-transform: uppercase; }
    .atlas-docs-drawer h2 { margin: 5px 0 0; color: var(--toolbar-text); font-size: 20px; line-height: 1.2; }
    .atlas-docs-drawer h3 { margin: 24px 0 7px; color: var(--toolbar-text); font-size: 14px; }
    .atlas-docs-drawer p { color: color-mix(in srgb, var(--toolbar-text) 78%, transparent); margin: 6px 0 12px; }
    .atlas-docs-close { flex: none; border: 1px solid var(--toolbar-border); border-radius: 8px; background: var(--toolbar-bg); color: var(--toolbar-text); width: 34px; height: 34px; cursor: pointer; font-size: 20px; }
    .atlas-view-switch { display: inline-flex; border: 1px solid var(--toolbar-border); border-radius: .625rem; overflow: hidden; background: var(--toolbar-bg); backdrop-filter: blur(10px); }
    .atlas-view-switch a { min-height: 2.625rem; display: inline-flex; align-items: center; padding: .5rem .7rem; color: var(--toolbar-text); text-decoration: none; font-size: .72rem; font-weight: 600; }
    .atlas-view-switch a + a { border-left: 1px solid var(--toolbar-border); }
    .atlas-view-switch a[aria-current="page"] { color: var(--frontend-stroke); background: color-mix(in srgb, var(--frontend-fill) 42%, var(--toolbar-bg)); }
    .atlas-docs-utility a { display: block; border: 1px solid var(--toolbar-border); border-radius: 8px; padding: 8px 10px; color: var(--toolbar-text); text-decoration: none; background: var(--toolbar-bg); }
    .atlas-docs-list { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--toolbar-border); }
    .atlas-docs-list li { margin: 0; padding: 13px 0; border-bottom: 1px solid var(--toolbar-border); }
    .atlas-docs-list a { color: var(--toolbar-text); text-decoration: none; }
    .atlas-docs-list a:hover strong, .atlas-docs-list a:focus-visible strong { color: var(--frontend-stroke); }
    .atlas-docs-list strong { display: block; font-size: 14px; line-height: 1.3; }
    .atlas-docs-list small { display: block; margin-top: 4px; color: color-mix(in srgb, var(--toolbar-text) 66%, transparent); }
    .atlas-docs-index { color: var(--frontend-stroke); margin-right: 7px; font: 700 11px/1 ui-monospace, SFMono-Regular, Menlo, monospace; }
    .atlas-docs-maturity { display: inline-block; margin-top: 7px; padding: 2px 7px; border: 1px solid color-mix(in srgb, var(--database-stroke) 60%, var(--toolbar-border)); border-radius: 999px; color: var(--database-stroke); font-size: 10px; }
    .atlas-docs-warning { margin: 8px 0 0 !important; padding-left: 9px; border-left: 2px solid var(--security-stroke); color: color-mix(in srgb, var(--security-stroke) 82%, var(--toolbar-text)) !important; font-size: 11px; }
    .atlas-docs-rail, .atlas-docs-clean-break { margin: 18px 0; padding: 13px 14px; border-left: 3px solid var(--external-stroke); background: color-mix(in srgb, var(--external-fill) 52%, transparent); }
    .atlas-docs-clean-break { border-left-color: var(--security-stroke); background: color-mix(in srgb, var(--security-fill) 52%, transparent); }
    .atlas-docs-rail a, .atlas-docs-clean-break a, .atlas-docs-utility a { color: var(--frontend-stroke); }
    .atlas-docs-utility { display: grid; gap: 8px; margin-top: 18px; }
    .atlas-docs-foot { margin-top: 20px !important; font: 10px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; opacity: .72; overflow-wrap: anywhere; }
    .atlas-node-detail h3 { margin-top: 18px; }
    .atlas-node-detail ul { margin: 6px 0 12px; padding-left: 20px; color: color-mix(in srgb, var(--toolbar-text) 78%, transparent); }
    .atlas-node-detail li { margin: 4px 0; }
    .composition-loop { margin: 18px 0; padding: 13px; border: 1px solid var(--toolbar-border); border-radius: 10px; background: var(--toolbar-bg); }
    .composition-loop h3 { margin-top: 0; }
    .composition-slots, .composition-cycle { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .composition-slot, .composition-cycle-step { padding: 5px 7px; border: 1px solid var(--toolbar-border); border-radius: 7px; background: color-mix(in srgb, var(--toolbar-bg) 80%, transparent); }
    .composition-slot.reviewed { border-color: var(--database-stroke); color: var(--database-stroke); }
    .composition-arrow { color: var(--frontend-stroke); font-weight: 800; }
    .composition-cycle { margin-top: 10px; }
    .composition-loopback { margin-top: 9px; padding: 7px 9px; border-left: 3px solid var(--frontend-stroke); background: color-mix(in srgb, var(--frontend-fill) 26%, transparent); }
    .composition-limits { font-size: 11px; color: color-mix(in srgb, var(--toolbar-text) 68%, transparent) !important; }
    .atlas-node-back { border: 0; padding: 0; background: transparent; color: var(--frontend-stroke); cursor: pointer; font: inherit; }
    .atlas-node-detail[hidden], .atlas-docs-index-panel[hidden] { display: none !important; }
    .header { margin-bottom: .25rem; }
    .guided-views { margin-bottom: .25rem; }
    html[data-atlas-audience="scientist"] .guided-views { display: none !important; }
    .atlas-workflow-intro { display: grid; grid-template-columns: 170px minmax(0, 1fr); gap: 8px 18px; margin: .25rem -29.5rem 0 0; padding: .7rem .8rem; border: 1px solid var(--toolbar-border); border-radius: .75rem; background: color-mix(in srgb, var(--toolbar-bg) 92%, transparent); color: var(--toolbar-text); }
    .atlas-workflow-intro h2 { margin: 0; color: var(--frontend-stroke); font: 700 .82rem/1.35 ui-sans-serif, system-ui, sans-serif; }
    .atlas-workflow-intro p { margin: 0; color: color-mix(in srgb, var(--toolbar-text) 82%, transparent); font: .74rem/1.45 ui-sans-serif, system-ui, sans-serif; }
    .atlas-workflow-copy { min-width: 0; }
    .atlas-workflow-steps { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 6px; list-style: none; margin: .45rem 0; padding: 0; }
    .atlas-workflow-steps li { min-width: 0; padding: .35rem .45rem; border-left: 2px solid var(--frontend-stroke); background: color-mix(in srgb, var(--frontend-fill) 24%, transparent); color: color-mix(in srgb, var(--toolbar-text) 78%, transparent); font: .67rem/1.35 ui-sans-serif, system-ui, sans-serif; }
    .atlas-workflow-steps strong { display: block; margin-bottom: .14rem; color: var(--frontend-stroke); font-size: .6rem; letter-spacing: .06em; text-transform: uppercase; }
    .atlas-workflow-intro .atlas-workflow-inputs { color: color-mix(in srgb, var(--toolbar-text) 68%, transparent); }
    html[data-atlas-docs-open="true"] .atlas-workflow-intro { margin-right: -210px; }
    .atlas-arrow-legend { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; margin: .25rem -29.5rem 0 0; padding: .55rem .75rem; border: 1px solid var(--toolbar-border); border-radius: .75rem; background: color-mix(in srgb, var(--toolbar-bg) 88%, transparent); color: var(--toolbar-text); font: 600 .68rem/1.35 ui-sans-serif, system-ui, sans-serif; }
    html[data-atlas-docs-open="true"] .atlas-arrow-legend { margin-right: -210px; }
    .atlas-arrow-key { display: inline-flex; gap: 7px; align-items: center; }
    .atlas-arrow-key::before { content: ""; width: 26px; border-top: 3px solid var(--arrow-emphasis); }
    .atlas-arrow-key.decision::before { border-top-color: var(--security-stroke); border-top-style: dashed; }
    .atlas-arrow-key.context::before { border-top-color: var(--database-stroke); border-top-style: dashed; }
    @media (max-width: 700px) {
      html[data-atlas-docs-open="true"] body { padding-right: 0; }
      html[data-atlas-docs-open="true"] .toolbar { right: 1rem; }
      .toolbar .preset-wrap,
      .toolbar #btn-motion,
      .toolbar #btn-present,
      .toolbar .export-wrap { display: none !important; }
      .atlas-docs-drawer { width: 100vw; }
      .atlas-view-switch a { padding-inline: .52rem; }
      .atlas-workflow-intro { display: block; margin-right: 0; }
      .atlas-workflow-intro h2 { margin-bottom: .35rem; }
      .atlas-workflow-intro p { font-size: .78rem; }
      .atlas-workflow-intro p + p { margin-top: .35rem; }
      .atlas-workflow-steps { grid-template-columns: 1fr; }
      .atlas-workflow-steps li { padding: .5rem .6rem; font-size: .75rem; }
      .atlas-workflow-steps strong { font-size: .65rem; }
      .atlas-arrow-legend { margin-right: 0; }
    }
    @media print { .atlas-docs-drawer, .atlas-docs-toggle, .atlas-view-switch { display: none !important; } }
"""


VIEWER_DRAWER_SCRIPT = """
  <script>
  (() => {
    const root = document.documentElement;
    const drawer = document.getElementById('atlas-docs-drawer');
    const toggle = document.getElementById('atlas-docs-toggle');
    const close = document.getElementById('atlas-docs-close');
    const indexPanel = document.getElementById('atlas-docs-index-panel');
    const details = Array.from(drawer.querySelectorAll('[data-atlas-node-doc]'));
    const backButtons = Array.from(drawer.querySelectorAll('[data-atlas-docs-index]'));
    const forceDark = () => {
      if (root.dataset.theme !== 'dark') root.dataset.theme = 'dark';
      try { localStorage.setItem('archify-theme', 'dark'); } catch (_) {}
    };
    const showIndex = () => {
      details.forEach((detail) => { detail.hidden = true; });
      indexPanel.hidden = false;
    };
    const showNode = (nodeId) => {
      const detail = details.find((candidate) => candidate.dataset.atlasNodeDoc === nodeId);
      if (!detail) return false;
      indexPanel.hidden = true;
      details.forEach((candidate) => { candidate.hidden = candidate !== detail; });
      drawer.hidden = false;
      root.dataset.atlasDocsOpen = 'true';
      toggle.setAttribute('aria-expanded', 'true');
      drawer.scrollTop = 0;
      return true;
    };
    const closeDrawer = (restoreFocus = false) => {
      if (drawer.hidden) return;
      drawer.hidden = true;
      delete root.dataset.atlasDocsOpen;
      toggle.setAttribute('aria-expanded', 'false');
      if (restoreFocus) toggle.focus();
    };
    toggle.addEventListener('click', () => {
      showIndex();
      drawer.hidden = false;
      root.dataset.atlasDocsOpen = 'true';
      toggle.setAttribute('aria-expanded', 'true');
      close.focus();
    });
    backButtons.forEach((button) => button.addEventListener('click', showIndex));
    close.addEventListener('click', () => closeDrawer(true));
    const syncNodeSelection = (node) => requestAnimationFrame(() => {
      if (node.hasAttribute('data-focus-selected')) showNode(node.dataset.nodeId);
      else closeDrawer(false);
    });
    document.addEventListener('click', (event) => {
      const node = event.target.closest?.('svg [data-node-id]');
      if (node) syncNodeSelection(node);
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !drawer.hidden) {
        event.preventDefault();
        event.stopImmediatePropagation();
        closeDrawer(true);
      }
      const node = event.target.closest?.('svg [data-node-id]');
      if (node && (event.key === 'Enter' || event.key === ' ')) syncNodeSelection(node);
      if (event.key.toLowerCase() === 't' && !event.target.closest?.('input, textarea, select, [contenteditable]')) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }, true);
    new MutationObserver(() => {
      forceDark();
      if (root.dataset.present === 'true') closeDrawer(false);
    }).observe(root, { attributes: true, attributeFilter: ['data-present', 'data-theme'] });
    forceDark();
  })();
  </script>
"""


def _derive_viewer_home(base: bytes, drawer: str, audience: str) -> bytes:
    document = base.decode("utf-8")
    had_final_newline = document.endswith("\n")
    document = "\n".join(line.rstrip() for line in document.splitlines())
    if had_final_newline:
        document += "\n"
    if 'id="atlas-docs-drawer"' in document:
        raise ValueError(
            "base Archify artifact already contains atlas documentation UI"
        )
    toolbar_end = '\n  </div>\n\n  <div class="container">'
    if document.count("</style>") != 1 or document.count(toolbar_end) != 1:
        raise ValueError(
            "unexpected Archify viewer structure; refusing unsafe injection"
        )
    document = document.replace("</style>", f"{VIEWER_DRAWER_STYLE}\n  </style>", 1)
    canonical_script = (
        "  <script>\n"
        "    document.documentElement.dataset.theme = 'dark';\n"
        "    try { localStorage.setItem('archify-theme', 'dark'); } catch (_) {}\n"
        + (
            "    if (location.hash === '#developer') location.replace('developer-view.html#developer');\n"
            if audience == "scientist"
            else "    try { history.replaceState(null, '', 'documentation.html#developer'); } catch (_) {}\n"
        )
        + "  </script>\n"
    )
    async_font_marker = "  <!-- Async font load:"
    if document.count(async_font_marker) != 1:
        raise ValueError("unexpected Archify viewer head; refusing unsafe injection")
    document = document.replace(
        async_font_marker, f"{canonical_script}{async_font_marker}", 1
    )
    scientist_current = ' aria-current="page"' if audience == "scientist" else ""
    developer_current = ' aria-current="page"' if audience == "developer" else ""
    view_switch = (
        '\n    <nav class="atlas-view-switch" aria-label="Documentation view">'
        f'<a href="documentation.html"{scientist_current}>Scientist</a>'
        f'<a href="developer-view.html#developer"{developer_current}>Developer</a></nav>'
    )
    toggle = (
        '\n    <button id="atlas-docs-toggle" class="atlas-docs-toggle" type="button" '
        'aria-label="Open documentation" aria-controls="atlas-docs-drawer" '
        'aria-expanded="false">Documentation</button>'
    )
    document = document.replace(
        toolbar_end,
        f"{view_switch}{toggle}{toolbar_end}",
        1,
    )
    if audience == "scientist":
        if document.count("<html ") != 1:
            raise ValueError("unexpected Archify root; refusing audience annotation")
        document = document.replace(
            "<html ", '<html data-atlas-audience="scientist" ', 1
        )
        header_marker = (
            '      </div>\n    </div>\n\n'
            '    <script id="archify-guided-views-data"'
        )
        if document.count(header_marker) != 1:
            raise ValueError(
                "unexpected Archify header; refusing unsafe legend injection"
            )
        arrow_legend = (
            '      <section class="atlas-workflow-intro" aria-labelledby="atlas-workflow-intro-title">'
            '<h2 id="atlas-workflow-intro-title">What this workflow does</h2>'
            '<div class="atlas-workflow-copy"><p>The workflow narrows many possible proteins into a small set of structural explanations that scientists can inspect.</p>'
            '<ol class="atlas-workflow-steps"><li><strong>1 · Check data</strong>Check the MTZ diffraction measurements.</li><li><strong>2 · Find models</strong>Find protein structure models for proteins on the supplied list.</li><li><strong>3 · Choose copy counts</strong>Use Matthews analysis to keep copy counts that physically fit.</li><li><strong>4 · Test and review</strong>Place each model hypothesis with Molecular Replacement, then inspect maps.</li><li><strong>5 · Expand or finish</strong>Test other proteins if needed, then write a reviewed report.</li></ol>'
            '<p class="atlas-workflow-inputs"><strong>You provide:</strong> an organism or sample name; a required protein FASTA, annotation source/version, and MTZ file; and optional genome FASTA, GFF/GBFF, localisation, and molecular-weight evidence. The input boxes below mark required and optional items separately.</p></div>'
            '</section>\n'
            '      <div class="atlas-arrow-legend no-print" aria-label="Arrow meanings">'
            '<span class="atlas-arrow-key">Solid green: forward workflow step</span>'
            '<span class="atlas-arrow-key decision">Dashed red: review decision or stop</span>'
            '<span class="atlas-arrow-key context">Dashed purple: optional/context input, evidence influence, or repeat</span>'
            "</div>\n"
        )
        document = document.replace(
            header_marker,
            header_marker.replace(
                '      </div>\n    </div>',
                f'      </div>\n{arrow_legend}    </div>',
                1,
            ),
            1,
        )
    if document.count("</body>") != 1:
        raise ValueError("unexpected Archify viewer body; refusing unsafe injection")
    derived = document.replace("</body>", f"{drawer}{VIEWER_DRAWER_SCRIPT}\n</body>", 1)
    had_final_newline = derived.endswith("\n")
    derived = "\n".join(line.rstrip() for line in derived.splitlines())
    if had_final_newline:
        derived += "\n"
    return derived.encode("utf-8")


def _drawer_shell(title: str, content: str, details: str, inventory_id: str) -> str:
    return (
        '<aside class="atlas-docs-drawer" id="atlas-docs-drawer" aria-label="Documentation" hidden>'
        '<div class="atlas-docs-head"><div><span class="atlas-docs-eyebrow">Documentation</span>'
        f'<h2>{_escape(title)}</h2></div><button class="atlas-docs-close" id="atlas-docs-close" type="button" aria-label="Close documentation">&times;</button></div>'
        f'<div class="atlas-docs-index-panel" id="atlas-docs-index-panel">{content}'
        '<div class="atlas-docs-utility"><a href="validation.html">Validation &amp; Evidence</a>'
        '<a href="inventory.html">Search implementation inventory</a></div></div>'
        f"{details}"
        f'<p class="atlas-docs-foot">Inventory {_escape(inventory_id)}</p></aside>'
    )


def _node_detail(
    node_id: str, record: dict[str, Any], links: list[tuple[str, str]]
) -> str:
    link_html = "".join(
        f'<a href="{href}">{_escape(label)}</a>' for label, href in links
    )
    return (
        f'<section class="atlas-node-detail" data-atlas-node-doc="{_escape(node_id)}" hidden>'
        '<button class="atlas-node-back" type="button" data-atlas-docs-index>← All documentation</button>'
        f"<h2>{_escape(record['title'])}</h2><p>{_escape(record['summary'])}</p>"
        f'<span class="atlas-docs-maturity">{_escape(record["maturity"])}</span>'
        f'<p class="atlas-docs-warning">{_escape(record["warning"])}</p>'
        f'{record.get("extra_html", "")}'
        f"<h3>Purpose</h3><p>{_escape(record['purpose'])}</p>"
        f"<h3>Key inputs</h3>{_list(record['inputs'])}"
        f"<h3>Key outputs</h3>{_list(record['outputs'])}"
        f"<h3>Decisions</h3>{_list(record['decisions'])}"
        f"<h3>Boundaries</h3>{_list(record['boundaries'])}"
        f'<div class="atlas-docs-utility">{link_html}</div></section>'
    )


def _scientist_node_details(stages: list[dict[str, Any]]) -> str:
    by_id = {stage["id"]: stage for stage in stages}
    input_links = [("Open all input details", "stages/inputs-records.html")]
    mapping = {
        "organism_metadata": (
            {
                "title": "Organism or sample name",
                "summary": "A human-readable name tells scientists which organism or sample the protein list describes.",
                "purpose": "Keep the biological source understandable in reports and prevent similarly named input sets from being confused.",
                "inputs": [
                    "Human-readable organism or sample name",
                    "Assembly accession and version, when available",
                    "Internal protein-list identifier",
                ],
                "outputs": ["Biological-source metadata attached to the run"],
                "decisions": [
                    "Do not infer the organism name from search results",
                    "Keep the name consistent with the supplied protein and genome files",
                ],
                "boundaries": [
                    "The current manifest has no dedicated organism_name field",
                    "It currently stores an internal identifier, assembly metadata, and notes",
                ],
                "maturity": "input-contract gap documented",
                "warning": "Add a dedicated organism/sample-name field before the final workflow contract is considered complete.",
            },
            input_links,
        ),
        "protein_sequences": (
            {
                "title": "Protein sequences — required",
                "summary": "A protein FASTA file lists every protein sequence the workflow is allowed to test.",
                "purpose": "Define the identity space without allowing external model databases to invent new reportable proteins.",
                "inputs": ["Protein FASTA file (.faa; manifest field proteome_faa)"],
                "outputs": [
                    "Checked protein records",
                    "Groups of entries that have identical protein sequences",
                ],
                "decisions": ["Reject an absent, malformed, or changed protein FASTA"],
                "boundaries": ["This file is required", "Use one annotation source per supplied protein list"],
                "maturity": "implemented required input",
                "warning": "A model hit can be reported as an identity only when it maps back to this supplied list.",
            },
            input_links,
        ),
        "genome_sequence": (
            {
                "title": "Genome sequence — optional",
                "summary": "A genome FASTA file records the nucleotide sequence associated with the protein list.",
                "purpose": "Preserve the genomic source and support traceable links between proteins and their genomic context.",
                "inputs": ["Genome FASTA file (.fna; manifest field genome_fasta)"],
                "outputs": ["Checksum-recorded optional genome source"],
                "decisions": ["Keep the input explicitly missing when no genome FASTA is supplied"],
                "boundaries": ["The current workflow does not predict genes from this genome"],
                "maturity": "implemented optional input",
                "warning": "The required protein FASTA remains the sequence source used for candidate testing.",
            },
            input_links,
        ),
        "annotation_input": (
            {
                "title": "Gene annotation",
                "summary": "The annotation source and version are required; GFF, GBFF, and protein-to-locus mapping files are optional supporting files.",
                "purpose": "Connect protein sequences to gene names, products, and genome locations without mixing annotation providers.",
                "inputs": [
                    "Annotation provider and version — required",
                    "GFF or GFF3 file — optional",
                    "GenBank flat file (GBFF) — optional",
                    "Protein-to-locus mapping file — optional",
                ],
                "outputs": ["Traceable protein-to-gene annotation records"],
                "decisions": ["Use exactly one annotation source for one protein list"],
                "boundaries": ["The workflow does not merge competing annotations"],
                "maturity": "implemented required metadata with optional files",
                "warning": "Record the exact annotation release; a provider name alone is not enough.",
            },
            input_links,
        ),
        "diffraction_data": (
            {
                "title": "Diffraction data — required",
                "summary": "Each crystal needs an MTZ file containing the measured diffraction data and a unique crystal name.",
                "purpose": "Provide the experimental measurements used for preflight, Molecular Replacement, refinement, and map calculation.",
                "inputs": [
                    "Diffraction MTZ file",
                    "Unique crystal name or identifier",
                    "Optional observation, resolution, or space-group declarations",
                ],
                "outputs": ["Checked diffraction-file identity used throughout the analysis"],
                "decisions": ["Reject a missing, changed, or internally inconsistent MTZ file"],
                "boundaries": ["An MTZ file supplies diffraction evidence; it does not identify a protein by itself"],
                "maturity": "implemented required input",
                "warning": "Every crystal must remain linked to its own MTZ file throughout the run.",
            },
            input_links,
        ),
        "preflight": (
            by_id["preflight"],
            [("Open full detail", "stages/preflight.html")],
        ),
        "discover_prepare": (
            by_id["discovery-models"],
            [("Open full detail", "stages/discovery-models.html")],
        ),
    }
    discovery = dict(by_id["discovery-models"])
    discovery["extra_html"] = _model_discovery_guide()
    mapping["discover_prepare"] = (
        discovery,
        [("Open full detail", "stages/discovery-models.html")],
    )
    first_component = {
        "title": "First-component joint search and review",
        "summary": f"{by_id['rank-mr']['summary']} {by_id['review-refine-maps']['summary']}",
        "purpose": f"{by_id['rank-mr']['purpose']} {by_id['review-refine-maps']['purpose']}",
        "inputs": by_id["rank-mr"]["inputs"],
        "outputs": by_id["review-refine-maps"]["outputs"],
        "decisions": by_id["rank-mr"]["decisions"]
        + by_id["review-refine-maps"]["decisions"],
        "boundaries": by_id["rank-mr"]["boundaries"]
        + by_id["review-refine-maps"]["boundaries"],
        "maturity": "joint copy-count search implemented; reviewed solutions retained",
        "warning": "Matthews analysis selects plausible copy counts for direct joint testing; sequential same-component placement is rescue-only.",
    }
    mapping["first_component_search_review"] = (
        first_component,
        [
            ("Open copy-search detail", "stages/rank-mr.html"),
            ("Open map-review detail", "stages/review-refine-maps.html"),
        ],
    )
    composition = {
        "title": "Additional-component search loop",
        "summary": by_id["composition"]["summary"],
        "purpose": by_id["composition"]["purpose"],
        "inputs": by_id["composition"]["inputs"],
        "outputs": by_id["composition"]["outputs"],
        "decisions": by_id["composition"]["decisions"],
        "boundaries": by_id["composition"]["boundaries"],
        "maturity": "depth three validated; deeper component searches restricted",
        "warning": "Depths four through six remain provisional, and deeper private analysis still requires complete review evidence.",
        "extra_html": _composition_loop(),
    }
    mapping["next_distinct_component"] = (
        composition,
        [("Open composition detail", "stages/composition.html")],
    )
    mapping["additional_component_copy_search"] = (
        composition,
        [("Open composition detail", "stages/composition.html")],
    )
    mapping["report"] = (
        by_id["report"],
        [("Open report detail", "stages/report.html")],
    )
    localisation = {
        "title": "User-provided localisation and molecular-weight evidence",
        "summary": "The user supplies these observations with the input data; they then remain available across discovery, ranking, review, and composition.",
        "purpose": "Order search waves without turning localisation or apparent molecular weight into identity, ASU-mass, or oligomeric-state proof.",
        "inputs": [
            "User-provided molecular-weight observations",
            "User-provided or offline-derived localisation evidence",
            "Missing-evidence state when either input is unavailable",
        ],
        "outputs": [
            "Inputs that can change which candidates are tested first",
            "Neutral missing-evidence records",
            "Traceable localisation and topology evidence",
        ],
        "decisions": [
            "Bind supplied evidence at the beginning",
            "Use it to change which candidates are tested first",
            "Keep missing evidence neutral",
        ],
        "boundaries": [
            "This evidence is supplied before staged processing begins",
            "Apparent molecular weight is a monomer prior",
            "Localisation cannot establish exact identity",
        ],
        "maturity": "implemented as cross-cutting input evidence",
        "warning": "Evidence can change search order but cannot prove identity or composition.",
    }
    mapping["localisation_weight"] = (
        localisation,
        [("Open full detail", f"subsystems/{_slug('localisation_weight')}.html")],
    )
    return "".join(_node_detail(node_id, *value) for node_id, value in mapping.items())


def _developer_node_details(
    layers: list[dict[str, Any]], subsystems: list[dict[str, Any]]
) -> str:
    by_id = {layer["id"]: layer for layer in layers}
    by_subsystem = {item["id"]: item for item in subsystems}
    node_to_layer = {
        "control_plane": "control-plane",
        "public_entrypoints": "entrypoints",
        "phase3_entrypoint": "entrypoints",
        "nextflow": "nextflow",
        "process_modules": "process-modules",
        "python_services": "python-services",
        "contracts": "python-services",
        "external_tools": "external-boundaries",
        "human_review": "evidence-publication",
        "evidence_store": "evidence-publication",
        "publication": "evidence-publication",
    }
    details: list[str] = []
    for node_id, layer_id in node_to_layer.items():
        layer = by_id[layer_id]
        primary = layer["subsystems"][0]
        links = [
            (
                f"Open full detail: {by_subsystem[primary]['title']}",
                f"subsystems/{_slug(primary)}.html",
            )
        ]
        details.append(_node_detail(node_id, layer, links))
    validation = {
        "title": "Internal validation",
        "summary": "Known controls, robustness checks, fixtures, and release gates run outside the normal scientific application path.",
        "purpose": "Test scientific and operational boundaries without mixing control truth into private analyses.",
        "inputs": [
            "Frozen control definitions",
            "Exact-source workflow build",
            "Isolated validation profiles",
        ],
        "outputs": [
            "Control and robustness evidence",
            "Release-gate results",
            "Explicit unresolved findings",
        ],
        "decisions": [
            "Keep validation outside normal analysis",
            "Fail stale or incomplete evidence",
            "Separate local, HPC, and scientific acceptance",
        ],
        "boundaries": [
            "A passing unit test is not scientific validation",
            "Controls cannot tune private unknown-crystal heuristics",
            "Incomplete validation remains visible",
        ],
        "maturity": "cross-cutting; final closure pending",
        "warning": "All required review evidence must be complete before deeper private analysis.",
    }
    details.append(
        _node_detail(
            "validation_plane",
            validation,
            [("Open full detail", "validation.html")],
        )
    )
    return "".join(details)


def _scientist_page(
    stages: list[dict[str, Any]], inventory: dict[str, Any], base: bytes
) -> tuple[Path, bytes]:
    relative = Path("documentation.html")
    items = "".join(
        '<li><a href="stages/'
        f'{stage["id"]}.html"><strong><span class="atlas-docs-index">{_escape(stage["number"])}</span>{_escape(stage["title"])}</strong>'
        f'<small>{_escape(stage["summary"])}</small><span class="atlas-docs-maturity">{_escape(stage["maturity"])}</span></a>'
        f'<p class="atlas-docs-warning">{_escape(stage["warning"])}</p></li>'
        for stage in stages
    )
    content = (
        "<p>Use the guided workflow as the primary map. Open a stage below for purpose, inputs, outputs, decisions, claim limits, maturity, and detailed run commands.</p>"
        f'<ol class="atlas-docs-list">{items}</ol>'
        '<section class="atlas-docs-rail"><strong>User-provided localisation and molecular-weight evidence</strong>'
        "<p>The user supplies these observations at the beginning. They can change which candidates are tested first; missing evidence is neutral, and apparent molecular weight is never ASU total mass.</p>"
        f'<a href="subsystems/{_slug("localisation_weight")}.html">Inspect the evidence contract</a></section>'
        '<section class="atlas-docs-clean-break"><strong>Visible maturity boundaries</strong>'
        "<p>Deeper private analysis remains unauthorised until every required review gate is complete. Depth three is positively qualified by the known three-component control (PDB 9ECN); depths four through six remain provisional.</p></section>"
    )
    drawer = _drawer_shell(
        "Scientist",
        content,
        _scientist_node_details(stages),
        inventory["inventory_id"],
    )
    return relative, _derive_viewer_home(base, drawer, "scientist")


def _developer_page(
    layers: list[dict[str, Any]],
    subsystems: list[dict[str, Any]],
    inventory: dict[str, Any],
    base: bytes,
) -> tuple[Path, bytes]:
    relative = Path("developer-view.html")
    items = "".join(
        '<li><strong><span class="atlas-docs-index">'
        f"{_escape(layer['number'])}</span>{_escape(layer['title'])}</strong>"
        f'<small>{_escape(layer["summary"])}</small><div class="atlas-docs-utility">'
        f"{_subsystem_links(layer['subsystems'], subsystems, '')}</div></li>"
        for layer in layers
    )
    content = (
        "<p>The diagram owns the architecture view. This drawer leads from each responsibility layer to its implementation evidence.</p>"
        f'<ol class="atlas-docs-list">{items}</ol>'
        '<section class="atlas-docs-clean-break"><strong>Current transitional application entrypoint</strong>'
        "<p><code>phase3_application.nf</code> is the current reviewed Phase III entrypoint while archival <code>main.nf</code> remains the v0.2 route. The accepted large clean break makes Phase III the sole public <code>main.nf</code>, retains <code>prepare_databases.nf</code>, and removes superseded roots, milestone names, aliases, and shims together.</p></section>"
        '<div class="atlas-docs-utility"><a href="external-tools.html">External runtime boundaries</a></div>'
    )
    drawer = _drawer_shell(
        "Developer architecture",
        content,
        _developer_node_details(layers, subsystems),
        inventory["inventory_id"],
    )
    return relative, _derive_viewer_home(base, drawer, "developer")


def _validation_page(inventory: dict[str, Any]) -> tuple[Path, bytes]:
    relative = Path("validation.html")
    body = (
        '<div class="breadcrumbs"><a href="documentation.html">Documentation</a> / Cross-cutting area</div>'
        '<div class="eyebrow">Cross-cutting</div><h1>Validation &amp; Evidence</h1>'
        '<p class="lead">Controls, robustness evidence, source-record checks, and release gates remain separate from normal scientific analyses while supporting both audience views.</p>'
        '<div class="stats">'
        f"<span>{len(inventory['test_modules'])} test modules</span><span>{len(inventory['schemas'])} active schemas</span>"
        f"<span>{len(inventory['active_milestone_identifiers'])} legacy milestone-name occurrences queued for clean break</span></div>"
        '<div class="grid"><article class="card"><h3>Known controls</h3><p>Positive, adverse, wrong-component, no-false-component, and runtime controls remain isolated from private analyses.</p></article>'
        '<article class="card"><h3>Operational and robustness evidence</h3><p>Exact-source execution, leakage, cache mutation, child completeness, resource records, and reproducibility are separately classified.</p></article>'
        '<article class="card"><h3>Release gates</h3><p>Schema, example, atlas freshness, link, source inventory, packaging, and structural-cleanliness checks fail closed.</p></article></div>'
        '<h2>Honest maturity vocabulary</h2><p><span class="badge maturity">implemented</span> <span class="badge maturity">locally tested</span> <span class="badge maturity">HPC-qualified</span> <span class="badge maturity">scientifically validated</span> <span class="badge maturity">authorised to run</span></p>'
        '<aside class="warning"><strong>These states are not synonyms.</strong> A path can be implemented and locally green while still lacking fixed-HPC qualification, scientific validation, or authorisation for private data.</aside>'
        '<p><a href="inventory.html">Search tests, schemas, modules, and symbols</a></p>'
    )
    return relative, _page(
        relative, "Validation & Evidence", body, inventory["inventory_id"]
    )


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
        ("MMseqs2", "Search the local PDB for sequences related to proteins in the supplied list."),
        (
            "ProstT5 + Foldseek",
            "Structural search for proteins in the supplied list against the local PDB resource.",
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


def _index_redirect() -> tuple[Path, bytes]:
    relative = Path("index.html")
    content = b"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=documentation.html"><meta name="robots" content="noindex"><title></title><script>location.replace('documentation.html');</script></head><body></body></html>
"""
    return relative, content


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
    portal_content = _portal_content(root)
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
    for diagram_path in DIAGRAM_PATHS:
        source = root / diagram_path
        if not source.is_file():
            raise FileNotFoundError(
                f"required frozen Archify artifact is missing: {diagram_path}"
            )
        outputs[diagram_path] = source.read_bytes()
    outputs[CURRENT / "assets/atlas.css"] = STYLE.encode("utf-8")
    outputs[CURRENT / "assets/atlas.js"] = SCRIPT.encode("utf-8")
    pages: list[tuple[Path, bytes]] = [
        _index_redirect(),
        _scientist_page(
            portal_content["scientist_stages"],
            inventory,
            outputs[CURRENT / "diagrams/scientist-workflow.html"],
        ),
        _developer_page(
            portal_content["developer_layers"],
            subsystems,
            inventory,
            outputs[CURRENT / "diagrams/developer-architecture.html"],
        ),
        _validation_page(inventory),
        _inventory_page(inventory, modules),
        _external_tools_page(inventory["inventory_id"]),
    ]
    pages.extend(
        _stage_page(
            stage,
            portal_content["scientist_stages"],
            subsystems,
            inventory["inventory_id"],
        )
        for stage in portal_content["scientist_stages"]
    )
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
    for relative in OBSOLETE_GENERATED:
        path = root / relative
        if path.is_file() and path not in expected:
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
