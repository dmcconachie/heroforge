"""
engine/gates.py
---------------
Equipment-state gate predicates. A gate is a named
predicate Callable[[Character], bool] that decides when
an effect applies (Barbarian fast movement only when not
in heavy armor, Duelist canny defense only when
unarmored, etc.).

Each gate key corresponds to a KnownCoreGate enum member
(rules/core/gates.py). Adding a new gate requires:

    1. Adding the member to KnownCoreGate.
    2. Registering its Python predicate in
       GATE_PREDICATES below.

The test suite's rules-loading congruence checks will
catch drift between enum members and the dispatch table.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from heroforge.engine.equipment import ArmorCategory, LoadCategory
from heroforge.rules.core.gates import KnownCoreGate

if TYPE_CHECKING:
    from heroforge.engine.character import Character


def _not_heavy_armor(c: "Character") -> bool:
    cat = c.equipped_armor_category()
    return cat is None or cat != ArmorCategory.HEAVY


def _not_heavy_load(c: "Character") -> bool:
    return c.current_load_category() != LoadCategory.HEAVY


GATE_PREDICATES: dict[KnownCoreGate, Callable[["Character"], bool]] = {
    KnownCoreGate.NOT_HEAVY_ARMOR: _not_heavy_armor,
    KnownCoreGate.NOT_HEAVY_LOAD: _not_heavy_load,
}


def make_condition(
    gates: list[str] | tuple[str, ...] | None,
) -> Callable[["Character"], bool] | None:
    """
    Compose a condition lambda from a list of gate keys.

    Returns None when `gates` is empty/None — callers
    should treat this as "unconditionally active." All
    gates in the list must hold (AND semantics).

    Raises KeyError on an unknown gate name — loader-time
    validation should catch these before any character
    evaluation happens.
    """
    if not gates:
        return None

    resolved: list[Callable[["Character"], bool]] = []
    for g in gates:
        # Coerce strings to enum members; raise on unknown.
        key = g if isinstance(g, KnownCoreGate) else KnownCoreGate(g)
        pred = GATE_PREDICATES[key]
        resolved.append(pred)

    def _composite(c: "Character") -> bool:
        return all(pred(c) for pred in resolved)

    return _composite
