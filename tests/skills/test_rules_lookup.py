"""
tests/skills/test_rules_lookup.py
----------------------------------
Unit tests for the rules-lookup skill's matching logic.

The lookup script lives at
``.claude/skills/rules-lookup/scripts/lookup.py``. We load it
via importlib so the dot-prefixed directory doesn't trip
pytest's default discovery, then exercise the matching helpers
in isolation (no PDFs, no pypdf dependency at test time).

These tests guard the apostrophe-tolerance fix: PDF text
extraction often turns ``'`` into ``’`` (right single
quotation mark) or strips it entirely. The lookup script must
match across these forms so audit subagents don't conclude
"feat doesn't exist" when only the punctuation differs.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

LOOKUP_PATH = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "skills"
    / "rules-lookup"
    / "scripts"
    / "lookup.py"
)


def _load_lookup() -> ModuleType:
    """Import the standalone uv-script as a Python module."""
    spec = importlib.util.spec_from_file_location("rules_lookup", LOOKUP_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rules_lookup"] = mod
    spec.loader.exec_module(mod)
    return mod


# --- _normalize_for_search ------------------------------------


def test_normalize_lowercases() -> None:
    lookup = _load_lookup()
    assert lookup._normalize_for_search("PHOENIX") == "phoenix"


def test_normalize_strips_ascii_apostrophe() -> None:
    lookup = _load_lookup()
    assert lookup._normalize_for_search("Lion's") == "lions"


def test_normalize_strips_curly_right_quote() -> None:
    lookup = _load_lookup()
    assert lookup._normalize_for_search("Lion’s") == "lions"


def test_normalize_strips_curly_left_quote() -> None:
    lookup = _load_lookup()
    assert lookup._normalize_for_search("Lion‘s") == "lions"


def test_normalize_strips_modifier_letter_apostrophe() -> None:
    lookup = _load_lookup()
    assert lookup._normalize_for_search("Lionʼs") == "lions"


def test_normalize_idempotent_on_clean_text() -> None:
    lookup = _load_lookup()
    assert lookup._normalize_for_search("lions pounce") == "lions pounce"


def test_normalize_keeps_other_punctuation() -> None:
    lookup = _load_lookup()
    # parentheses, plus signs, commas remain so multi-token
    # entries like "Crystal of Mind Cloaking, Greater" still
    # search literally for the comma.
    assert (
        lookup._normalize_for_search("Belt of Magnificence +6")
        == "belt of magnificence +6"
    )


# --- _find_matches --------------------------------------------


def test_find_matches_curly_apostrophe_in_text() -> None:
    """User searches with ASCII apostrophe; PDF rendered curly."""
    lookup = _load_lookup()
    pages = ["", "LION’S POUNCE [WILD]\nWhen you charge..."]
    assert lookup._find_matches(pages, "Lion's Pounce") == [2]


def test_find_matches_stripped_apostrophe_in_text() -> None:
    """User searches with ASCII apostrophe; PDF dropped it."""
    lookup = _load_lookup()
    pages = ["Lions Pounce is described here."]
    assert lookup._find_matches(pages, "Lion's Pounce") == [1]


def test_find_matches_ascii_apostrophe_in_text() -> None:
    """Both ASCII (regression check)."""
    lookup = _load_lookup()
    pages = ["Lion's Pounce is described here."]
    assert lookup._find_matches(pages, "Lion's Pounce") == [1]


def test_find_matches_term_without_apostrophe_finds_apostrophe_text() -> None:
    """User searches without apostrophe; PDF has curly."""
    lookup = _load_lookup()
    pages = ["Lion’s Pounce"]
    assert lookup._find_matches(pages, "Lions Pounce") == [1]


def test_find_matches_multiple_pages() -> None:
    lookup = _load_lookup()
    pages = [
        "intro",
        "no match here",
        "Lion’s Pounce",
        "another match Lions Pounce",
    ]
    assert lookup._find_matches(pages, "Lion's Pounce") == [3, 4]


def test_find_matches_no_match_returns_empty() -> None:
    lookup = _load_lookup()
    assert lookup._find_matches(["Phoenix Cloak"], "Nonexistent") == []


def test_find_matches_case_insensitive() -> None:
    lookup = _load_lookup()
    assert lookup._find_matches(["lion's pounce"], "LION'S POUNCE") == [1]


def test_find_matches_unaffected_when_no_apostrophe_anywhere() -> None:
    """Plain term + plain text continues to work as before."""
    lookup = _load_lookup()
    assert lookup._find_matches(["Phoenix Cloak"], "Phoenix Cloak") == [1]


# --- _snippet -------------------------------------------------


def test_snippet_preserves_original_apostrophes() -> None:
    """Output must show original (un-normalized) text for citation."""
    lookup = _load_lookup()
    text = "Some context.\nLion’s Pounce: when you charge...\nMore context."
    pattern = lookup._compile_pattern("Lion's Pounce")
    out = lookup._snippet(text, pattern, context_lines=1)
    assert "Lion’s" in out
    # the normalized form should never leak into output
    assert "Lions Pounce" not in out


def test_snippet_empty_when_no_match() -> None:
    lookup = _load_lookup()
    pattern = lookup._compile_pattern("Nonexistent")
    out = lookup._snippet("Phoenix Cloak\nrandom text", pattern, 1)
    assert out == ""
