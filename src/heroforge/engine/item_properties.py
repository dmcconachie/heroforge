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
  adjust_for_properties() -- apply armour-stat adjustments
  grants_extra_attack()   -- True if any name is a speed-like
                             property
  doubles_range_increment() -- True if any name is distance
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from heroforge.engine.effects import pool_entries_from_effects

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
    # Damage reduction, resistance to energy and immunity.
    # See engine/defenses.py for the shape.
    defenses: dict = field(default_factory=dict)
    # Adjustments to the armour's own figures, with the same
    # sign convention as MaterialDefinition: acp_adjust is
    # positive toward zero, asf_adjust negative for less
    # failure. Nimbleness is the reason these exist -- it
    # raises max Dex and cuts the check penalty, which is not
    # a bonus and cannot be a pool entry.
    acp_adjust: int = 0
    max_dex_adjust: int = 0
    asf_adjust: int = 0
    # The property names an argument the books leave open, so
    # "<name> <argument>" resolves to it. Bane is the only
    # one: its designated foe is any creature type or subtype.
    takes_parameter: bool = False


class ItemPropertyRegistry:
    """Case-insensitive lookup for item properties."""

    def __init__(self) -> None:
        self._entries: dict[str, ItemPropertyDefinition] = {}

    def register(self, defn: ItemPropertyDefinition) -> None:
        self._entries[defn.name] = defn

    def get(self, name: str) -> ItemPropertyDefinition | None:
        """
        Look up *name*.

        There is one canonical spelling per property -- the
        book's own, grade included, as in "Shadow, Greater"
        and "Truedeath Crystal, Least" -- and only that
        spelling resolves. Whitespace is normalised; nothing
        else is.

        The single exception is a property that takes an
        argument. Bane designates a creature type, which is
        unbounded, so `Bane` is declared `takes_parameter`
        and "Bane Undead" resolves to it. That is one named
        mechanism, not an open field of aliases.
        """
        key = " ".join(name.split())
        defn = self._entries.get(key)
        if defn is not None:
            return defn
        head = key.split(" ")[0] if key else ""
        defn = self._entries.get(head)
        if defn is not None and defn.takes_parameter:
            return defn
        return None

    def parameter_of(self, name: str) -> str:
        """
        The argument in a parameterised property's name, e.g.
        "Undead" from "Bane Undead". Empty for anything else.
        """
        key = " ".join(name.split())
        if key in self._entries:
            return ""
        head = key.split(" ")[0] if key else ""
        defn = self._entries.get(head)
        if defn is not None and defn.takes_parameter:
            return key[len(head) :].strip()
        return ""

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


def adjust_for_properties(
    acp: int,
    max_dex: int,
    asf: int,
    names: list[str] | tuple[str, ...],
) -> tuple[int, int, int]:
    """
    Apply every named property's armour-stat adjustments.

    Mirrors ``equipment.adjust_for_material``: the check
    penalty moves toward zero and never past it, and a
    max Dex of -1 means uncapped and stays that way.
    """
    for name in names or ():
        defn = property_definition(str(name))
        if defn is None:
            continue
        if defn.acp_adjust:
            acp = min(acp + defn.acp_adjust, 0)
        if defn.max_dex_adjust and max_dex >= 0:
            max_dex += defn.max_dex_adjust
        if defn.asf_adjust:
            asf = max(asf + defn.asf_adjust, 0)
    return acp, max_dex, asf


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
