"""
rules/known.py
--------------
Combined KnownXxx StrEnums across all rule sources.

Per-book auto-discovery: each top-level subdirectory of
``rules/`` (a "book") may expose a Python StrEnum module per
category. Categories that vary across books (feats, classes,
magic items, materials) are discovered dynamically — adding a
splatbook folder that follows the naming convention needs no
edits here.

Naming convention for per-book modules:
    rules/<book>/<category>.py exporting
    Known<BookCamelCase><CategorySingular>

Examples:
    core/feats.py            -> KnownCoreFeat
    custom/classes.py        -> KnownCustomClass
    complete_warrior/feats.py -> KnownCompleteWarriorFeat

Core-only categories (armor, weapons, races, etc.) are imported
explicitly below.

The congruence test in rules/test/known_test.py catches drift
between these enums and the live registries.
"""

from __future__ import annotations

import importlib
from enum import StrEnum

from heroforge.rules.combine_str_enum import combine
from heroforge.rules.core.armor import KnownCoreArmor
from heroforge.rules.core.buffs import KnownCoreBuff
from heroforge.rules.core.conditions_srd import KnownCoreCondition
from heroforge.rules.core.domains import KnownCoreDomain
from heroforge.rules.core.gates import KnownCoreGate
from heroforge.rules.core.races import KnownCoreRace
from heroforge.rules.core.skills import KnownCoreSkill
from heroforge.rules.core.templates import KnownCoreTemplate
from heroforge.rules.core.weapons import KnownCoreWeapon
from heroforge.rules.rules import book_dirs

# Per-book category -> the singular CamelCase suffix of its
# Known* StrEnum class. e.g. "feats" -> a class named
# "Known<Book>Feat" is expected in the module.
_PER_BOOK_CATEGORIES: dict[str, str] = {
    "feats": "Feat",
    "classes": "Class",
    "magic_items": "MagicItem",
    "materials": "Material",
}


def _book_camel(book: str) -> str:
    """``"complete_warrior"`` -> ``"CompleteWarrior"``."""
    return "".join(part.capitalize() for part in book.split("_"))


def _collect(category: str) -> list[type[StrEnum]]:
    """
    Return every per-book Known* StrEnum for ``category``,
    in book load order. Books that don't define the category
    are silently skipped.
    """
    suffix = _PER_BOOK_CATEGORIES[category]
    out: list[type[StrEnum]] = []
    for book in book_dirs():
        try:
            mod = importlib.import_module(f"heroforge.rules.{book}.{category}")
        except ImportError:
            continue
        cls_name = f"Known{_book_camel(book)}{suffix}"
        cls = getattr(mod, cls_name, None)
        if cls is not None:
            out.append(cls)
    return out


# --- Combined enums --------------------------------------------

# Core-only categories (no splatbook variants).
KnownArmor = combine("KnownArmor", KnownCoreArmor)
KnownBuff = combine("KnownBuff", KnownCoreBuff)
KnownCondition = combine("KnownCondition", KnownCoreCondition)
KnownDomain = combine("KnownDomain", KnownCoreDomain)
KnownGate = combine("KnownGate", KnownCoreGate)
KnownRace = combine("KnownRace", KnownCoreRace)
KnownSkill = combine("KnownSkill", KnownCoreSkill)
KnownTemplate = combine("KnownTemplate", KnownCoreTemplate)
KnownWeapon = combine("KnownWeapon", KnownCoreWeapon)

# Per-book categories: discovered across every book directory.
KnownClass = combine("KnownClass", *_collect("classes"))
KnownFeat = combine("KnownFeat", *_collect("feats"))
KnownMagicItem = combine("KnownMagicItem", *_collect("magic_items"))
KnownMaterial = combine("KnownMaterial", *_collect("materials"))
