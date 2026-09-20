"""
engine/defenses.py
------------------
Damage reduction, resistance to energy, and immunity.

None of these is a bonus, so none can live in a BonusPool.
Both DR and energy resistance are *keyed* — DR by what
bypasses it, resistance by which energy — and in both cases
the best single source applies rather than a sum:

  * "If a creature has damage reduction from more than one
    source, the two forms of damage reduction do not stack.
    Instead, the creature gets the benefit of the best damage
    reduction in a given situation." (DMG p. 291)
  * "Multiple sources of resistance to a certain energy type
    don't stack with each other. Only the highest value
    applies to any given attack." (Rules Compendium p. 48)

"In a given situation" is why DR keeps one entry per bypass
rather than collapsing to a single number: DR 2/- and DR
5/magic are both worth knowing, because which one helps
depends on what is swinging.

Immunity to an energy type supersedes resistance to it, so
the resistance entry is dropped rather than shown alongside.

A source declares these with a `defenses:` block:

    defenses:
      damage_reduction:
        - amount: 5          # int, or a formula string
          bypassed_by: magic
      energy_resistance:
        fire: 10
      immunities:
        - disease

Public API:
  DamageReduction         -- one DR entry
  Defenses                -- the aggregate for a character
  best_damage_reduction() -- reduce DR entries per bypass
  collect_defenses()      -- aggregate from every source
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from heroforge.engine.effects import evaluate_formula

if TYPE_CHECKING:
    from heroforge.engine.character import Character

# What DR is written against when nothing bypasses it.
NOTHING = "-"


@dataclass(frozen=True)
class DamageReduction:
    """`amount`/`bypassed_by`, e.g. 5/magic or 2/-."""

    amount: int
    bypassed_by: str = NOTHING

    def __str__(self) -> str:
        return f"{self.amount}/{self.bypassed_by}"


@dataclass(frozen=True)
class Defenses:
    """Everything a character shrugs off, already reduced."""

    damage_reduction: tuple[DamageReduction, ...] = ()
    energy_resistance: dict[str, int] = field(default_factory=dict)
    immunities: tuple[str, ...] = ()


def best_damage_reduction(
    entries: Iterable[DamageReduction],
) -> tuple[DamageReduction, ...]:
    """
    Keep the best entry per bypass type.

    Sorted by bypass so the result is stable for the sheet.
    """
    best: dict[str, int] = {}
    for dr in entries:
        if dr.amount > best.get(dr.bypassed_by, 0):
            best[dr.bypassed_by] = dr.amount
    return tuple(DamageReduction(best[key], key) for key in sorted(best))


def _read_block(
    block: dict,
    character: "Character",
    drs: list[DamageReduction],
    resist: list[tuple[str, int]],
    immune: set[str],
) -> None:
    """Accumulate one `defenses:` declaration."""
    for entry in block.get("damage_reduction", ()) or ():
        raw = entry.get("amount", 0)
        amount = (
            evaluate_formula(raw, character=character)
            if isinstance(raw, str)
            else int(raw)
        )
        if amount > 0:
            drs.append(
                DamageReduction(amount, entry.get("bypassed_by", NOTHING))
            )
    for energy, raw in (block.get("energy_resistance", {}) or {}).items():
        points = (
            evaluate_formula(raw, character=character)
            if isinstance(raw, str)
            else int(raw)
        )
        if points > 0:
            resist.append((str(energy), points))
    immune.update(str(x) for x in block.get("immunities", ()) or ())


def _equipped_property_names(character: "Character") -> list[str]:
    """Every property on every piece the character has on."""
    names: list[str] = []
    for slot in ("armor", "shield"):
        item = character.equipment.get(slot) or {}
        names += list(item.get("properties", []) or [])
    for weapon in character.equipment.get("weapons", []) or []:
        names += list(weapon.get("properties", []) or [])
    return names


def collect_defenses(character: "Character") -> Defenses:
    """
    Aggregate every source of DR, resistance and immunity.

    Sources today are equipped item properties and class
    features. Creature templates carry theirs as display text
    and rings of energy resistance name their energy per
    item, so neither reaches this yet.
    """
    from heroforge.engine.item_properties import property_definition
    from heroforge.rules.rules import get_rules

    drs: list[DamageReduction] = []
    resist: list[tuple[str, int]] = []
    immune: set[str] = set()

    for name in _equipped_property_names(character):
        defn = property_definition(str(name))
        if defn is not None and defn.defenses:
            _read_block(defn.defenses, character, drs, resist, immune)

    classes = get_rules().classes
    for class_name, level in character.class_level_map.items():
        defn = classes.get(class_name)
        if defn is None:
            continue
        for feature in defn.class_features:
            if feature.level <= level and feature.defenses:
                _read_block(feature.defenses, character, drs, resist, immune)

    best_resist: dict[str, int] = {}
    for energy, points in resist:
        if points > best_resist.get(energy, 0):
            best_resist[energy] = points
    # Immunity is total, so a resistance to the same energy
    # adds nothing and would only clutter the sheet.
    for energy in immune:
        best_resist.pop(energy, None)

    return Defenses(
        damage_reduction=best_damage_reduction(drs),
        energy_resistance={k: best_resist[k] for k in sorted(best_resist)},
        immunities=tuple(sorted(immune)),
    )
