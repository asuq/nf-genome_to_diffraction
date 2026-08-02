"""Check essential and operational Markdown documentation links."""

import re
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
MARKDOWN_LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")


def main() -> int:
    """Validate local links in essential and operational Markdown files."""

    errors: list[str] = []
    for forbidden in ("prompts", "scaffold", "CODEX_START_HERE.md"):
        if (REPOSITORY / forbidden).exists():
            errors.append(f"untracked handoff path must be absent: {forbidden}")

    markdown_files = [
        REPOSITORY / "README.md",
        REPOSITORY / "AGENTS.md",
        REPOSITORY / "CHANGELOG.md",
    ]
    docs_root = REPOSITORY / "docs"
    docs_index = docs_root / "README.md"
    if not docs_index.is_file():
        errors.append("missing operational documentation index: docs/README.md")
    if docs_root.is_dir():
        markdown_files.extend(sorted(docs_root.rglob("*.md")))
    for markdown_path in markdown_files:
        if not markdown_path.is_file():
            errors.append(f"missing essential file: {markdown_path.name}")
            continue
        source = markdown_path.read_text(encoding="utf-8")
        for target in MARKDOWN_LINK.findall(source):
            if target.startswith(("http://", "https://", "#")):
                continue
            local_target = target.split("#", maxsplit=1)[0]
            resolved = (markdown_path.parent / local_target).resolve()
            if not resolved.exists():
                errors.append(f"{markdown_path.name}: broken local link: {target}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Essential and operational Markdown links are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
