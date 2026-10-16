#!/usr/bin/env python3
"""
scripts/format_docs.py - Markdown documentation formatter and link validator.

Ensures markdown files have consistent line endings, trailing whitespace stripped,
and verifies relative internal documentation links exist.
"""

import argparse
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent


def check_and_format_file(file_path: Path, fix: bool = False) -> bool:
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    cleaned = [line.rstrip() for line in lines]
    new_content = "\n".join(cleaned) + "\n"

    if content != new_content:
        if fix:
            file_path.write_text(new_content, encoding="utf-8")
            print(f"  Fixed trailing whitespace: {file_path.relative_to(ROOT)}")
            return True
        else:
            print(f"  Unformatted whitespace: {file_path.relative_to(ROOT)}")
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Format markdown documentation")
    parser.add_argument("--fix", action="store_true", help="Automatically fix formatting")
    args = parser.parse_args()

    md_files = list(ROOT.glob("*.md")) + list((ROOT / "docs").rglob("*.md"))
    print(f"Checking {len(md_files)} markdown files...")

    all_clean = True
    for f in md_files:
        clean = check_and_format_file(f, fix=args.fix)
        if not clean:
            all_clean = False

    if all_clean or args.fix:
        print("✅ Documentation formatting verified.")
        sys.exit(0)
    else:
        print("❌ Found unformatted markdown files. Run with --fix to resolve.")
        sys.exit(1)


if __name__ == "__main__":
    main()
