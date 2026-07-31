"""Check essential tracked Markdown and enforce the no-doc-tree policy."""

import re
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
MARKDOWN_LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")


def main() -> int:
    """Validate local links in essential Markdown files."""

    errors: list[str] = []
    for forbidden in ("docs", "prompts", "scaffold", "CODEX_START_HERE.md"):
        if (REPOSITORY / forbidden).exists():
            errors.append(f"untracked documentation path must be absent: {forbidden}")

    markdown_files = [
        REPOSITORY / "README.md",
        REPOSITORY / "AGENTS.md",
        REPOSITORY / "CHANGELOG.md",
    ]
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
    print("Essential Markdown files and documentation policy are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
