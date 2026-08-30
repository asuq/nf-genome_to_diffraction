# Documentation atlas

The atlas is a private, offline, deterministic documentation tree for the
current source and frozen releases. It has separate Scientist / Operator and
Developer entry portals plus a first-class Validation & Evidence portal. The
portals converge on shared subsystem pages.

## Source and generated content

- `sources/` contains curated subsystem metadata and Archify specifications.
- `generated/` contains deterministic machine-readable repository inventory.
- `current/` contains committed deterministic HTML for the active source.
- release snapshots will be frozen under `releases/<version>/`.

Run `pixi run docs-atlas-inventory` to regenerate the executable inventory and
`pixi run docs-atlas-check` to reject stale committed output. The final release
gate will also validate every link, schema, example, diagram and wheel-content
boundary.

Private unknown-crystal inputs and generated scientific reports are not part of
the committed atlas.
