"""
Which book a rules entry came from.

The set of books is closed, so `source_book` is an enum. It
had been free text, and the data drifted: the Magic Item
Compendium was written both as "MIC" and as "Magic Item
Compendium", so `by_source_book` returned half its entries
for either spelling.
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest
import yaml
from cattrs.errors import ClassValidationError

from heroforge.engine.enums import SourceBook
from heroforge.engine.magic_items import MagicItemDefinition
from heroforge.rules.rules import get_rules
from heroforge.rules.schema import converter

RULES_DIR = Path(__file__).parent.parent.parent / "rules"


def _declared_books() -> set[str]:
    """Every source_book spelling in every rules file."""
    found: set[str] = set()
    for path in glob.glob(str(RULES_DIR / "**" / "*.yaml"), recursive=True):
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        stack = [raw]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if isinstance(node.get("source_book"), str):
                    found.add(node["source_book"])
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return found


class TestTheVocabulary:
    def test_every_spelling_in_the_rules_is_a_member(self) -> None:
        unknown = _declared_books() - {b.value for b in SourceBook}
        assert unknown == set()

    def test_one_spelling_per_book(self) -> None:
        """
        Regression: "MIC" and "Magic Item Compendium" were
        both in use for the same book.
        """
        declared = _declared_books()
        assert "Magic Item Compendium" not in declared
        assert "MIC" in declared

    def test_an_unknown_book_is_refused_at_load(self) -> None:
        with pytest.raises(ClassValidationError):
            converter.structure(
                {"name": "Boots of Nowhere", "source_book": "Book of Vile"},
                MagicItemDefinition,
            )


class TestLoadedEntries:
    def test_magic_items_carry_the_enum(self) -> None:
        for defn in get_rules().magic_items.all_items():
            assert isinstance(defn.source_book, SourceBook), defn.name

    def test_the_compendium_items_are_all_found_together(self) -> None:
        """
        The split spelling meant a search for MIC items
        silently missed the ones written out in full.
        """
        items = [
            d
            for d in get_rules().magic_items.all_items()
            if d.source_book is SourceBook.MIC
        ]
        assert len(items) > 25
