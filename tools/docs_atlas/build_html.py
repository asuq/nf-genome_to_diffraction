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
    Path("docs/atlas/current/diagrams/scientist-workflow.visual-check.json"),
    Path("docs/atlas/current/diagrams/developer-architecture.visual-check.json"),
)


STYLE = """\
:root { color-scheme:light dark; --bg:#f4f7fb; --panel:#fff; --panel2:#edf3f9; --text:#172033; --muted:#5d6a80; --line:#d5deea; --accent:#1769d2; --accent2:#087f5b; --warn:#9a5b00; --warn-bg:#fff7df; --code:#eaf0f7; --shadow:0 12px 34px rgba(28,45,74,.08); }
:root[data-theme='dark'] { --bg:#0c1320; --panel:#141e2d; --panel2:#1b283a; --text:#e8eef8; --muted:#a8b5c9; --line:#314057; --accent:#79adff; --accent2:#61d8ae; --warn:#ffd274; --warn-bg:#302713; --code:#202c3d; --shadow:0 14px 40px rgba(0,0,0,.28); }
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
footer { color:var(--muted); border-top:1px solid var(--line); padding-top:20px; margin-top:48px; }
@media (max-width:760px) { main,.bar { padding-left:14px; padding-right:14px; } .detail-grid { grid-template-columns:1fr; } th { position:static; } }
"""


SCRIPT = """\
(() => {
  const root = document.documentElement;
  const stored = localStorage.getItem('nf-gtd-atlas-theme');
  if (stored === 'light' || stored === 'dark') root.dataset.theme = stored;
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
    current_top = relative.parts[0] if relative.parts else relative.name
    current_target = {
        "stages": "scientist.html",
        "modules": "developer.html",
        "contracts": "developer.html",
        "external-tools.html": "developer.html",
    }.get(current_top, current_top)
    navigation = "".join(
        f'<a href="{prefix}{target}"{(' aria-current="page"' if current_target == target else "")}>{label}</a>'
        for target, label in (
            ("scientist.html", "Scientist / Operator"),
            ("developer.html", "Developer"),
            ("validation.html", "Validation & Evidence"),
            ("inventory.html", "Inventory"),
        )
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_escape(title)} - nf-genome_to_diffraction</title><link rel="stylesheet" href="{prefix}assets/atlas.css"></head>
<body><a class="skip-link" href="#main-content">Skip to main content</a><header><div class="bar"><div class="brand">nf-genome_to_diffraction</div><nav aria-label="Primary">{navigation}</nav><button data-theme-toggle type="button" aria-label="Toggle light and dark theme">Light / Dark</button></div></header>
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
        f'<div class="breadcrumbs"><a href="../developer.html">Developer</a> / Module</div>'
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
        '<div class="breadcrumbs"><a href="../developer.html">Developer</a> / Subsystem</div>'
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
        '<div class="breadcrumbs"><a href="../developer.html">Developer</a> / Data contract</div>'
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
    body = (
        '<div class="breadcrumbs"><a href="../scientist.html">Scientist / Operator</a> / Workflow stage</div>'
        f'<div class="eyebrow">Stage {_escape(stage["number"])}</div><h1>{_escape(stage["title"])}</h1>'
        f'<p class="lead">{_escape(stage["summary"])}</p>'
        f'<p><span class="badge maturity">Current maturity: {_escape(stage["maturity"])}</span></p>'
        f'<aside class="warning" role="note"><strong>Visible limitation.</strong> {_escape(stage["warning"])}</aside>'
        '<div class="detail-grid">'
        f'<section class="detail-panel"><h2>Purpose</h2><p>{_escape(stage["purpose"])}</p></section>'
        f'<section class="detail-panel"><h2>Inputs</h2>{_list(stage["inputs"])}</section>'
        f'<section class="detail-panel"><h2>Outputs</h2>{_list(stage["outputs"])}</section>'
        f'<section class="detail-panel"><h2>Decisions and statuses</h2>{_list(stage["decisions"])}</section>'
        "</div><h2>Claim and failure boundaries</h2>"
        f"{_list(stage['boundaries'])}"
        "<details><summary>Operator commands and implementation links</summary>"
        "<p>Use commands only with the reviewed configuration, immutable source, and owned inputs for the intended site. Placeholders are deliberate.</p>"
        f'<pre><code>{_escape(commands)}</code></pre><div class="callout-links">{subsystem_links}'
        '<a href="../inventory.html">Search implementation inventory</a></div></details>'
        f'<nav class="callout-links" aria-label="Workflow stage navigation">{"".join(previous_next)}</nav>'
    )
    return relative, _page(relative, stage["title"], body, inventory_id)


VIEWER_DRAWER_STYLE = """
    /* Documentation navigation injected by the deterministic atlas builder. */
    .atlas-docs-drawer {
      position: fixed; inset: 0 0 0 auto; z-index: 2147483000;
      width: min(440px, 94vw); height: 100dvh; overflow: auto;
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
    .atlas-docs-switch { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 0 0 14px; }
    .atlas-docs-switch a, .atlas-docs-utility a { display: block; border: 1px solid var(--toolbar-border); border-radius: 8px; padding: 8px 10px; color: var(--toolbar-text); text-decoration: none; background: var(--toolbar-bg); }
    .atlas-docs-switch a[aria-current="page"] { border-color: var(--frontend-stroke); color: var(--frontend-stroke); }
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
    @media print { .atlas-docs-drawer, .atlas-docs-toggle { display: none !important; } }
"""


VIEWER_DRAWER_SCRIPT = """
  <script>
  (() => {
    const drawer = document.getElementById('atlas-docs-drawer');
    const toggle = document.getElementById('atlas-docs-toggle');
    const close = document.getElementById('atlas-docs-close');
    const closeDrawer = (restoreFocus = false) => {
      if (drawer.hidden) return;
      drawer.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
      if (restoreFocus) toggle.focus();
    };
    toggle.addEventListener('click', () => {
      drawer.hidden = false;
      toggle.setAttribute('aria-expanded', 'true');
      close.focus();
    });
    close.addEventListener('click', () => closeDrawer(true));
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !drawer.hidden) {
        event.preventDefault();
        event.stopImmediatePropagation();
        closeDrawer(true);
      }
    }, true);
    new MutationObserver(() => {
      if (document.documentElement.dataset.present === 'true') closeDrawer(false);
    }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-present'] });
  })();
  </script>
"""


def _derive_viewer_home(base: bytes, drawer: str) -> bytes:
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
    toggle = (
        '\n    <button id="atlas-docs-toggle" class="atlas-docs-toggle" type="button" '
        'aria-label="Open documentation" aria-controls="atlas-docs-drawer" '
        'aria-expanded="false">Documentation</button>'
    )
    document = document.replace(
        toolbar_end,
        f"{toggle}{toolbar_end}",
        1,
    )
    if document.count("</body>") != 1:
        raise ValueError("unexpected Archify viewer body; refusing unsafe injection")
    derived = document.replace(
        "</body>", f"{drawer}{VIEWER_DRAWER_SCRIPT}\n</body>", 1
    )
    had_final_newline = derived.endswith("\n")
    derived = "\n".join(line.rstrip() for line in derived.splitlines())
    if had_final_newline:
        derived += "\n"
    return derived.encode("utf-8")


def _drawer_shell(audience: str, title: str, content: str, inventory_id: str) -> str:
    scientist_current = ' aria-current="page"' if audience == "scientist" else ""
    developer_current = ' aria-current="page"' if audience == "developer" else ""
    return (
        '<aside class="atlas-docs-drawer" id="atlas-docs-drawer" aria-label="Documentation" hidden>'
        '<div class="atlas-docs-head"><div><span class="atlas-docs-eyebrow">Documentation</span>'
        f'<h2>{_escape(title)}</h2></div><button class="atlas-docs-close" id="atlas-docs-close" type="button" aria-label="Close documentation">&times;</button></div>'
        '<nav class="atlas-docs-switch" aria-label="Audience">'
        f'<a href="scientist.html"{scientist_current}>Scientist / Operator</a>'
        f'<a href="developer.html"{developer_current}>Developer</a></nav>'
        f"{content}"
        '<div class="atlas-docs-utility"><a href="validation.html">Validation &amp; Evidence</a>'
        '<a href="inventory.html">Search implementation inventory</a></div>'
        f'<p class="atlas-docs-foot">Inventory {_escape(inventory_id)}</p></aside>'
    )


def _scientist_page(
    stages: list[dict[str, Any]], inventory: dict[str, Any], base: bytes
) -> tuple[Path, bytes]:
    relative = Path("scientist.html")
    items = "".join(
        '<li><a href="stages/'
        f'{stage["id"]}.html"><strong><span class="atlas-docs-index">{_escape(stage["number"])}</span>{_escape(stage["title"])}</strong>'
        f'<small>{_escape(stage["summary"])}</small><span class="atlas-docs-maturity">{_escape(stage["maturity"])}</span></a>'
        f'<p class="atlas-docs-warning">{_escape(stage["warning"])}</p></li>'
        for stage in stages
    )
    content = (
        "<p>Use the guided workflow as the primary map. Open a stage below for purpose, inputs, outputs, decisions, claim limits, maturity, and deep operator commands.</p>"
        f'<ol class="atlas-docs-list">{items}</ol>'
        '<section class="atlas-docs-rail"><strong>Cross-cutting localisation and gel evidence</strong>'
        "<p>These observations order search waves; missing evidence is neutral, and apparent gel mass is never ASU total mass.</p>"
        f'<a href="subsystems/{_slug("localisation_gel")}.html">Inspect the evidence contract</a></section>'
        '<section class="atlas-docs-clean-break"><strong>Visible maturity boundaries</strong>'
        "<p>Pass 2 remains unauthorised pending final RG0-RG7 evidence. Depth three is positively qualified by 9ECN; depths four through six remain provisional.</p></section>"
    )
    drawer = _drawer_shell(
        "scientist", "Scientist / Operator", content, inventory["inventory_id"]
    )
    return relative, _derive_viewer_home(base, drawer)


def _developer_page(
    layers: list[dict[str, Any]],
    subsystems: list[dict[str, Any]],
    inventory: dict[str, Any],
    base: bytes,
) -> tuple[Path, bytes]:
    relative = Path("developer.html")
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
        '<section class="atlas-docs-clean-break"><strong>Transitional application authority</strong>'
        "<p><code>phase3_application.nf</code> is the current reviewed Phase III owner while archival <code>main.nf</code> remains the v0.2 route. The accepted large clean break makes Phase III the sole public <code>main.nf</code>, retains <code>prepare_databases.nf</code>, and removes superseded roots, milestone names, aliases, and shims together.</p></section>"
        '<div class="atlas-docs-utility"><a href="external-tools.html">External tool boundaries</a>'
        '<a href="scientist.html">Follow the scientific runtime sequence</a></div>'
    )
    drawer = _drawer_shell(
        "developer", "Developer architecture", content, inventory["inventory_id"]
    )
    return relative, _derive_viewer_home(base, drawer)


def _validation_page(inventory: dict[str, Any]) -> tuple[Path, bytes]:
    relative = Path("validation.html")
    body = (
        '<div class="breadcrumbs"><a href="scientist.html">Scientist / Operator</a> or <a href="developer.html">Developer</a> / Cross-cutting area</div>'
        '<div class="eyebrow">Cross-cutting</div><h1>Validation &amp; Evidence</h1>'
        '<p class="lead">Controls, robustness evidence, provenance checks, and release gates remain separate from normal scientific analyses while supporting both audience views.</p>'
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


def _index_redirect() -> tuple[Path, bytes]:
    relative = Path("index.html")
    content = b"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=scientist.html"><meta name="robots" content="noindex"><title></title><script>location.replace('scientist.html');</script></head><body></body></html>
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
