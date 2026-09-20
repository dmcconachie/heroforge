"""
engine/item_properties.py
-------------------------
Special properties on armour, shields and weapons — the
`properties:` list on an equipment entry.

Only properties that apply **permanently** contribute to
stats. A property is wired when its benefit is always on for
the wearer or wielder: greater shadow's +15 competence on
Hide, a speed weapon's extra attack. Everything else is
recognised and described but changes no number, because it
would be wrong most of the time:

  * activated — blinking (1/day), vanishing (2/day),
    mindarmor (3/day), deathward (1/day), animated (on
    command)
  * reactive — arrow deflection
  * conditional on the target — bane, fiendslayer, truedeath,
    illusion bane, revelation
  * conditional on the roll — wounding (on a hit), mind
    cloaking (only against mind-affecting effects), precise
    (only against cover and concealment)

Those belong in the conditional-effects panel when it lands,
not in a bonus pool.

An unrecognised property name is *not* an error: the property
vocabulary is open and books are added piecemeal, so a name
with no definition simply displays and does nothing. Making
it an error needs complete coverage first.

Public API:
  ItemPropertyDefinition  -- one property
  ItemPropertyRegistry    -- case-insensitive lookup
  property_definition()   -- look one up in the loaded rules
  property_pool_entries() -- (pool_key, BonusEntry) pairs for
                             a list of property names
  grants_extra_attack()   -- True if any name is a speed-like
                             property
  doubles_range_increment() -- True if any name is distance
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from heroforge.engine.bonus import BonusEntry


@dataclass(frozen=True)
class ItemPropertyDefinition:
    """One armour, shield or weapon special property."""

    name: str
    # "armor", "shield", "weapon". Advisory: nothing refuses
    # to apply a property to the wrong kind of item, because
    # the books themselves are loose about shields counting
    # as armour.
    applies_to: str = "armor"
    source_book: str = "DMG"
    note: str = ""
    # Permanent stat contributions. Empty for everything that
    # is activated, reactive or conditional.
    effects: tuple[dict, ...] = ()
    # A speed weapon grants one extra attack at full base
    # attack bonus on a full attack. Not a bonus, so not an
    # effect.
    extra_attack: bool = False
    # A distance weapon has double the range increment of
    # other weapons of its kind. Multiplicative, so it cannot
    # be a pool entry either.
    doubles_range_increment: bool = False


class ItemPropertyRegistry:
    """Case-insensitive lookup for item properties."""

    def __init__(self) -> None:
        self._entries: dict[str, ItemPropertyDefinition] = {}

    def register(self, defn: ItemPropertyDefinition) -> None:
        self._entries[defn.name.lower()] = defn

    def get(self, name: str) -> ItemPropertyDefinition | None:
        """
        Look up *name* the way people actually write it.

        The books name grades with a trailing comma -- "Shadow,
        Greater" -- while character files write "greater
        shadow". Parenthetical grades and qualifiers appear
        too: "truedeath (greater)", "bane (undead)". All of
        those resolve to the one definition.
        """
        for candidate in self._candidates(name):
            defn = self._entries.get(candidate)
            if defn is not None:
                return defn
        return None

    @staticmethod
    def _candidates(name: str) -> list[str]:
        key = " ".join(name.lower().split())
        forms = [key]
        # "greater shadow" -> "shadow, greater"
        for grade in ("greater", "improved", "lesser", "least"):
            prefix = grade + " "
            if key.startswith(prefix):
                forms.append(f"{key[len(prefix) :]}, {grade}")
        # drop a parenthetical, then try the same swap again
        if "(" in key:
            bare = key.split("(")[0].strip()
            forms.append(bare)
            inner = key[key.index("(") + 1 :].rstrip(") ").strip()
            if inner in ("greater", "improved", "lesser", "least"):
                forms.append(f"{bare}, {inner}")
        return forms

    def all_properties(self) -> list[ItemPropertyDefinition]:
        return list(self._entries.values())

    def names(self) -> list[str]:
        return sorted(d.name for d in self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)


def property_definition(name: str) -> ItemPropertyDefinition | None:
    """Look up *name* in the loaded rules."""
    from heroforge.rules.rules import get_rules  # cycle; see docs

    return get_rules().item_properties.get(name)


def property_pool_entries(
    names: list[str] | tuple[str, ...],
    character: "object | None" = None,
) -> list[tuple[str, "BonusEntry"]]:
    """
    Expand a list of property names into pool entries.

    Unknown names and properties with no permanent effect
    contribute nothing.
    """
    from heroforge.engine.effects import pool_entries_from_effects

    pairs: list[tuple[str, BonusEntry]] = []
    for name in names or ():
        defn = property_definition(str(name))
        if defn is None or not defn.effects:
            continue
        pairs.extend(
            pool_entries_from_effects(
                [dict(e) for e in defn.effects],
                source_label=f"property:{defn.name}",
                character=character,
            )
        )
    return pairs


def grants_extra_attack(names: list[str] | tuple[str, ...]) -> bool:
    """True if any of *names* is a speed-like property."""
    for name in names or ():
        defn = property_definition(str(name))
        if defn is not None and defn.extra_attack:
            return True
    return False


def doubles_range_increment(
    names: list[str] | tuple[str, ...],
) -> bool:
    """
    True if any of *names* doubles the range increment.

    Doubling at most once however many sources apply, the
    same way threat ranges behave.
    """
    for name in names or ():
        defn = property_definition(str(name))
        if defn is not None and defn.doubles_range_increment:
            return True
    return False
