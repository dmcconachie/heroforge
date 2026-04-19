#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pypdf>=5.0"]
# ///
"""
rules-lookup/scripts/lookup.py
-------------------------------
Search D&D 3.5 PDFs at ~/DnD/3.5 Books/ for a term.

First invocation per PDF extracts text to a cache
directory; subsequent calls are fast.

Usage:
  lookup.py "Crystal Mask of Insight"
  lookup.py --book "Magic Item" "Phoenix Cloak"
  lookup.py --list-books
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BOOKS_DIR = Path.home() / "DnD" / "3.5 Books"
CACHE_DIR = Path.home() / ".cache" / "heroforge-rules-lookup"


def _extract_pdf(pdf: Path) -> list[str]:
    """Return per-page text, caching to CACHE_DIR."""
    cache = CACHE_DIR / f"{pdf.stem}.json"
    if cache.exists() and cache.stat().st_mtime >= pdf.stat().st_mtime:
        with open(cache) as f:
            return json.load(f)

    from pypdf import PdfReader

    print(f"  extracting {pdf.name}...", file=sys.stderr)
    reader = PdfReader(str(pdf))
    pages = [p.extract_text() or "" for p in reader.pages]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache, "w") as f:
        json.dump(pages, f)
    return pages


def _iter_pdfs(book_filter: str | None) -> list[Path]:
    pdfs = sorted(BOOKS_DIR.rglob("*.pdf"))
    if book_filter:
        bf = book_filter.lower()
        pdfs = [p for p in pdfs if bf in p.name.lower()]
    return pdfs


def list_books() -> int:
    for p in _iter_pdfs(None):
        rel = p.relative_to(BOOKS_DIR)
        print(rel)
    return 0


def search(
    term: str,
    book_filter: str | None,
    context: int,
    max_hits: int,
) -> int:
    pdfs = _iter_pdfs(book_filter)
    if not pdfs:
        print(f"No PDFs matched in {BOOKS_DIR}", file=sys.stderr)
        return 1

    pattern = re.compile(re.escape(term), re.IGNORECASE)
    total = 0

    for pdf in pdfs:
        pages = _extract_pdf(pdf)
        for page_num, text in enumerate(pages, start=1):
            if not pattern.search(text):
                continue
            total += 1
            print(f"\n=== {pdf.name} · page {page_num} ===")
            print(_snippet(text, pattern, context))
            if total >= max_hits:
                print(
                    f"\n(stopped at {max_hits} hits; "
                    "use --max to see more)",
                    file=sys.stderr,
                )
                return 0

    if total == 0:
        print(f"No matches for {term!r}", file=sys.stderr)
        return 2
    return 0


def _snippet(
    text: str,
    pattern: re.Pattern[str],
    context_lines: int,
) -> str:
    """Return lines around each match, with match lines highlighted."""
    lines = text.splitlines()
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if pattern.search(line):
            for j in range(
                max(0, i - context_lines),
                min(len(lines), i + context_lines + 1),
            ):
                keep.add(j)

    out: list[str] = []
    prev = -2
    for i in sorted(keep):
        if i > prev + 1:
            out.append("  ...")
        out.append(f"  {lines[i]}")
        prev = i
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Search D&D 3.5 PDFs for a term.",
    )
    ap.add_argument("term", nargs="?", help="Term to search for")
    ap.add_argument(
        "--book",
        help="Filter to books whose filename contains this substring",
    )
    ap.add_argument(
        "--context",
        type=int,
        default=3,
        help="Lines of context around each match (default: 3)",
    )
    ap.add_argument(
        "--max",
        type=int,
        default=10,
        dest="max_hits",
        help="Stop after N hits (default: 10)",
    )
    ap.add_argument(
        "--list-books",
        action="store_true",
        help="List available PDF books and exit",
    )
    args = ap.parse_args()

    if args.list_books:
        return list_books()
    if not args.term:
        ap.error("term is required unless --list-books")
    return search(args.term, args.book, args.context, args.max_hits)


if __name__ == "__main__":
    raise SystemExit(main())
