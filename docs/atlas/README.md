# Documentation atlas

The atlas is a private, offline, deterministic documentation tree for the
current source and frozen releases. Its surfaced homes are
`current/scientist.html` and `current/developer.html`. Validation & Evidence is
a secondary cross-cutting area linked from both homes. The homes converge on
shared workflow-stage, subsystem, module, contract, and inventory pages.
Each surfaced home is a full Archify viewer, not a page containing an embedded
viewer. The atlas builder deterministically derives it from the corresponding
frozen artifact and injects a toolbar button plus an integrated documentation
drawer. Diagram theme, guided views, semantic search/focus, presentation, and
export remain owned by the unmodified Archify runtime.

`current/index.html` is an internal compatibility redirect only. It immediately
opens `scientist.html`, contains no visible interface, and is never linked from
generated navigation.

## Source and generated content

- `sources/` contains curated portal/subsystem metadata and frozen Archify
  specifications.
- `generated/` contains deterministic machine-readable repository inventory.
- `current/` contains committed deterministic HTML for the active source,
  including the two Archify deliverables under `current/diagrams/`.
- release snapshots will be frozen under `releases/<version>/`.

The Archify HTML files under `current/diagrams/` are frozen base deliverables.
The atlas generator does not rerender or rewrite them; it requires them,
includes their exact bytes in `current/manifest.json`, then injects only the
documentation controls into derived `scientist.html` and `developer.html`
outputs. A base-diagram or injection change is therefore visible to the
freshness check. Rerender a base diagram from its matching source specification
with the Archify validation/delivery workflow before rebuilding the atlas.

Run `pixi run docs-atlas-inventory` to regenerate the executable inventory and
`pixi run docs-atlas-check` to reject stale committed output. Open
`current/scientist.html` or `current/developer.html` directly when reviewing the
prototype. The final release
gate will also validate every link, schema, example, diagram and wheel-content
boundary.

Private unknown-crystal inputs and generated scientific reports are not part of
the committed atlas.
