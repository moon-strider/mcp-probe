"""Keep the public check catalog and local documentation links synchronized."""

from __future__ import annotations

import argparse
import pathlib
import re

from mcp_probe.cli import check_catalog

ROOT = pathlib.Path(__file__).resolve().parents[1]
START = "<!-- generated checks start -->"
END = "<!-- generated checks end -->"


def table() -> str:
    lines = ["| Suite | Check | Severity | Description |", "| --- | --- | --- | --- |"]
    for item in check_catalog():
        lines.append(f"| {item['suite']} | `{item['id']}` | {item['severity']} | {item['description']} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    catalog = ROOT / "docs/checks.md"
    text = catalog.read_text()
    before, rest = text.split(START)
    _, after = rest.split(END)
    expected = before + START + "\n\n" + table() + "\n\n" + END + after
    if args.write:
        catalog.write_text(expected)
    else:
        assert text == expected, "Run python scripts/check_docs.py --write"
    files = [*ROOT.glob("*.md"), *(ROOT / "docs").glob("*.md")]
    for path in files:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            relative = target.split("#", 1)[0]
            assert (path.parent / relative).exists(), f"Broken link in {path.name}: {target}"
    print(f"Checked {len(check_catalog())} catalog entries and links in {len(files)} documents")


if __name__ == "__main__":
    main()
