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
from enum import StrEnum
from typing import TYPE_CHECKING

from heroforge.engine.effects import evaluate_formula
from heroforge.engine.item_properties import property_definition

if TYPE_CHECKING:
    from heroforge.engine.character import Character


class EnergyType(StrEnum):
    """
    The five energy types damage can be dealt as.

    "resistance 10 to acid, cold, electricity, fire, and sonic
    damage" -- 3.0 to 3.5 update booklet, p. 17.
    """

    ACID = "acid"
    COLD = "cold"
    ELECTRICITY = "electricity"
    FIRE = "fire"
    SONIC = "sonic"


class DrBypass(StrEnum):
    """
    What a weapon must be for DR not to apply.

    NOTHING is the "-" of "DR 2/-": no weapon bypasses it.

    Printed DR is sometimes a combination -- "10/magic and
    silver", "15/cold iron or good" -- but only the atoms are
    a closed set, so only the atoms are enumerated. Nothing in
    the rules files needs a combination yet; the day one does
    is the day to add a type that can hold one, rather than
    reopening this to arbitrary text.
    """

    NOTHING = "-"
    MAGIC = "magic"
    EPIC = "epic"
    SILVER = "silver"
    COLD_IRON = "cold iron"
    ADAMANTINE = "adamantine"
    GOOD = "good"
    EVIL = "evil"
    LAWFUL = "lawful"
    CHAOTIC = "chaotic"
    BLUDGEONING = "bludgeoning"
    PIERCING = "piercing"
    SLASHING = "slashing"


@dataclass(frozen=True)
class DamageReduction:
    """`amount`/`bypassed_by`, e.g. 5/magic or 2/-."""

    amount: int
    bypassed_by: DrBypass = DrBypass.NOTHING

    def __str__(self) -> str:
        return f"{self.amount}/{self.bypassed_by.value}"


@dataclass(frozen=True)
class Defenses:
    """Everything a character shrugs off, already reduced."""

    damage_reduction: tuple[DamageReduction, ...] = ()
    energy_resistance: dict[EnergyType, int] = field(default_factory=dict)
    immunities: tuple[str, ...] = ()
    # Percentage chance to negate a critical hit or sneak
    # attack. Neither a bonus nor a reduction, but a
    # defensive number the player needs. Best source wins.
    fortification: int = 0


def best_damage_reduction(
    entries: Iterable[DamageReduction],
) -> tuple[DamageReduction, ...]:
    """
    Keep the best entry per bypass type.

    Sorted by bypass so the result is stable for the sheet.
    """
    best: dict[DrBypass, int] = {}
    for dr in entries:
        if dr.amount > best.get(dr.bypassed_by, 0):
            best[dr.bypassed_by] = dr.amount
    return tuple(DamageReduction(best[key], key) for key in sorted(best))


PARAMETER = "$parameter"


def _substitute(token: str, parameter: str) -> str:
    """
    Replace `$parameter` with the item's chosen argument.

    A ring of energy resistance picks its energy when it is
    made, so its declaration says `$parameter: 10` rather
    than naming one.
    """
    return parameter if token == PARAMETER else token


def _read_block(
    block: dict,
    character: "Character",
    drs: list[DamageReduction],
    resist: list[tuple[EnergyType, int]],
    immune: set[str],
    fortify: list[int],
    parameter: str = "",
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
                DamageReduction(
                    amount,
                    DrBypass(
                        _substitute(
                            entry.get("bypassed_by", DrBypass.NOTHING),
                            parameter,
                        )
                    ),
                )
            )
    for energy, raw in (block.get("energy_resistance", {}) or {}).items():
        points = (
            evaluate_formula(raw, character=character)
            if isinstance(raw, str)
            else int(raw)
        )
        if points > 0:
            resist.append(
                (EnergyType(_substitute(str(energy), parameter)), points)
            )
    immune.update(
        _substitute(str(x), parameter)
        for x in block.get("immunities", ()) or ()
    )
    raw = block.get("fortification", 0)
    if raw:
        fortify.append(
            evaluate_formula(raw, character=character)
            if isinstance(raw, str)
            else int(raw)
        )


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

    Sources are equipped item properties, the armour's
    material, worn magic items, creature templates and class
    features.
    """
    # Only get_rules has to be deferred: engine <- rules is a
    # cycle. See docs/plans/engine-rules-import-cycle.md.
    from heroforge.rules.rules import get_rules

    drs: list[DamageReduction] = []
    resist: list[tuple[EnergyType, int]] = []
    immune: set[str] = set()
    fortify: list[int] = []

    for name in _equipped_property_names(character):
        defn = property_definition(str(name))
        if defn is not None and defn.defenses:
            _read_block(defn.defenses, character, drs, resist, immune, fortify)

    rules = get_rules()

    armor = character.equipment.get("armor") or {}
    material = rules.materials.get(armor.get("material", ""))
    if material is not None and material.armor_damage_reduction:
        amount = material.armor_damage_reduction.get(
            armor.get("category", ""), 0
        )
        if amount > 0:
            drs.append(DamageReduction(amount, DrBypass.NOTHING))

    for entry in character.equipment.get("worn", []) or []:
        item = rules.magic_items.get(entry["name"])
        if item is not None and item.defenses:
            _read_block(
                item.defenses,
                character,
                drs,
                resist,
                immune,
                fortify,
                entry.get("parameter", ""),
            )

    for application in character.templates or ():
        template = rules.templates.get(application.template_name)
        if template is not None and template.defenses:
            _read_block(
                template.defenses,
                character,
                drs,
                resist,
                immune,
                fortify,
            )

    classes = rules.classes
    for class_name, level in character.class_level_map.items():
        defn = classes.get(class_name)
        if defn is None:
            continue
        for feature in defn.class_features:
            if feature.level <= level and feature.defenses:
                _read_block(
                    feature.defenses,
                    character,
                    drs,
                    resist,
                    immune,
                    fortify,
                )

    best_resist: dict[EnergyType, int] = {}
    for energy, points in resist:
        if points > best_resist.get(energy, 0):
            best_resist[energy] = points
    # Immunity is total, so a resistance to the same energy
    # adds nothing and would only clutter the sheet. Only some
    # immunities name an energy — poison and sleep have no
    # resistance entry to drop.
    for name in immune & {e.value for e in EnergyType}:
        best_resist.pop(EnergyType(name), None)

    return Defenses(
        damage_reduction=best_damage_reduction(drs),
        energy_resistance={k: best_resist[k] for k in sorted(best_resist)},
        immunities=tuple(sorted(immune)),
        fortification=max(fortify, default=0),
    )
