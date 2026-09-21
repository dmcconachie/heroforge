"""
engine/proficiency.py
---------------------
Who is proficient with what, and what it costs when they are
not.

A character's proficiencies are the union of what every class
they have levels in grants, what their race grants, and what
proficiency feats they have taken. Nothing is stored on the
character: proficiency is derived, so dropping a class or an
item drops the proficiency with it.

Penalties (PHB p. 122 for armor, p. 113 for weapons):

  * Armor or a shield the character is not proficient with
    applies its own armor check penalty to attack rolls and to
    every Strength- and Dexterity-based ability and skill
    check. In practice that *extends* the penalised list by
    Open Lock, Ride and Use Rope (Rules Compendium p. 14) —
    a skill that already carries an armor check penalty takes
    it once, not twice. Armor and shield nonproficiency stack
    with each other, as the two armor check penalties
    themselves do.
  * A weapon the character is not proficient with costs -4 on
    attack rolls with that weapon.

The weapon penalty is applied per weapon in engine/weapons.py,
because that is where a weapon's own pool lives. The armor and
shield penalties are global and are installed here.

Note on imports: the three `get_rules` imports in this module
are deliberately deferred to function scope. `rules.rules`
imports `engine.classes` at module scope, so a top-level
import here closes a cycle. That inversion is a real design
problem, written up in
docs/plans/engine-rules-import-cycle.md; every other import
in this module is at the top where it belongs.

Public API:
  Proficiencies              -- what one source grants
  character_proficiencies()  -- the union for a character
  is_proficient_with_weapon()
  is_proficient_with_armor()
  is_proficient_with_shield()
  refresh_proficiency_penalties()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from heroforge.engine.bonus import BonusEntry, BonusType
from heroforge.engine.classes import Proficiencies
from heroforge.engine.enums import (
    Ability,
    ArmorCategory,
    WeaponCategory,
)
from heroforge.rules.core.pool_keys import PoolKey

if TYPE_CHECKING:
    from heroforge.engine.character import Character
    from heroforge.engine.equipment import (
        ArmorDefinition,
        WeaponDefinition,
    )

ARMOR_SRC = "nonproficient_armor"
SHIELD_SRC = "nonproficient_shield"

# What a feat grants. Armor Proficiency (Heavy) grants only
# heavy: the chain is enforced by the feats' prerequisites,
# not by implication here.
_ARMOR_FEATS: dict[str, ArmorCategory] = {
    "Armor Proficiency (Light)": ArmorCategory.LIGHT,
    "Armor Proficiency (Medium)": ArmorCategory.MEDIUM,
    "Armor Proficiency (Heavy)": ArmorCategory.HEAVY,
}

_CATEGORY_FEATS = {
    "Simple Weapon Proficiency": "simple",
    "Martial Weapon Proficiency": "martial",
    "Exotic Weapon Proficiency": "exotic",
}


@dataclass
class _Merged:
    armor: set[ArmorCategory] = field(default_factory=set)
    shields: bool = False
    tower_shields: bool = False
    weapons: set[WeaponCategory] = field(default_factory=set)
    weapon_names: set[str] = field(default_factory=set)
    weapon_familiarity: set[str] = field(default_factory=set)

    def add(self, p: Proficiencies) -> None:
        self.armor |= set(p.armor)
        self.shields = self.shields or p.shields
        self.tower_shields = self.tower_shields or p.tower_shields
        self.weapons |= set(p.weapons)
        self.weapon_names |= set(p.weapon_names)
        self.weapon_familiarity |= set(p.weapon_familiarity)


def character_proficiencies(character: "Character") -> _Merged:
    """Union of class, race and feat proficiencies."""
    from heroforge.rules.rules import get_rules  # cycle; see above

    rules = get_rules()
    merged = _Merged()

    for class_name in character.class_level_map:
        defn = rules.classes.get(class_name)
        if defn is not None and defn.proficiencies is not None:
            merged.add(defn.proficiencies)

    race = rules.races.get(character.race) if character.race else None
    if race is not None:
        merged.weapon_names |= set(race.weapon_proficiencies)
        merged.weapon_familiarity |= set(race.weapon_familiarity)

    for entry in character.feats:
        name = entry.get("name", "")
        if name in _ARMOR_FEATS:
            merged.armor.add(_ARMOR_FEATS[name])
        elif name == "Shield Proficiency":
            merged.shields = True
        elif name == "Tower Shield Proficiency":
            merged.tower_shields = True
        elif name in _CATEGORY_FEATS:
            # Simple Weapon Proficiency covers the whole
            # category; the martial and exotic feats name one
            # weapon each.
            param = entry.get("parameter")
            if _CATEGORY_FEATS[name] == "simple" and not param:
                merged.weapons.add(WeaponCategory.SIMPLE)
            elif param:
                merged.weapon_names.add(param)

    return merged


def is_proficient_with_weapon(
    character: "Character",
    weapon: "WeaponDefinition | None",
) -> bool:
    """True if *character* may use *weapon* without the -4."""
    if weapon is None:
        return True
    merged = character_proficiencies(character)
    if weapon.name in merged.weapon_names:
        return True
    category = weapon.category.value
    # Weapon familiarity moves an exotic weapon into the
    # martial category for this character (PHB p. 15).
    if category == "exotic" and weapon.name in merged.weapon_familiarity:
        category = "martial"
    return category in merged.weapons


def is_proficient_with_armor(
    character: "Character",
    armor: "ArmorDefinition | None",
) -> bool:
    if armor is None:
        return True
    return armor.category.value in character_proficiencies(character).armor


def is_proficient_with_shield(
    character: "Character",
    shield: "ArmorDefinition | None",
) -> bool:
    if shield is None:
        return True
    merged = character_proficiencies(character)
    if shield.category.value == "tower_shield":
        return merged.tower_shields
    return merged.shields


def _newly_penalised_skill_pools() -> list[str]:
    """
    The STR/DEX skills nonproficiency *adds* to the penalised
    list.

    Rules Compendium p. 14: the penalty reaches attack rolls
    and all STR- and DEX-based checks, which "effectively adds
    Open Lock, Ride, and Use Rope to the list of penalized
    skills". It extends the list rather than applying a second
    penalty, so skills that already carry an armor check
    penalty of their own are excluded here — including Swim,
    which takes the normal penalty twice over and no more.
    """
    from heroforge.rules.rules import get_rules  # cycle; see above

    return [
        sd.pool_key
        for sd in get_rules().skills.all_skills()
        if sd.ability in (Ability.STR, Ability.DEX) and not sd.armor_check
    ]


def refresh_proficiency_penalties(character: "Character") -> None:
    """
    Install (or clear) the armor and shield nonproficiency
    penalties on attack rolls and STR/DEX skills.

    Idempotent: recomputes both sources from scratch, so it is
    safe to call whenever equipment, class levels or feats
    change.
    """
    from heroforge.rules.rules import get_rules  # cycle; see above

    rules = get_rules()
    targets = [PoolKey.ATTACK_ALL, *_newly_penalised_skill_pools()]

    for slot, src in (("armor", ARMOR_SRC), ("shield", SHIELD_SRC)):
        item = character.equipment.get(slot) or {}
        key = item.get("name") or item.get("base", "")
        defn = rules.armor.get(key) if key else None
        if defn is None:
            penalty = 0
        elif slot == "armor":
            ok = is_proficient_with_armor(character, defn)
            penalty = 0 if ok else item.get("armor_check_penalty", 0)
        else:
            ok = is_proficient_with_shield(character, defn)
            penalty = 0 if ok else item.get("armor_check_penalty", 0)

        for key in targets:
            pool = character._pools.get(key)
            if pool is None:
                continue
            if penalty >= 0:
                pool.clear_source(src)
            else:
                pool.set_source(
                    src,
                    [
                        BonusEntry(
                            value=penalty,
                            bonus_type=BonusType.UNTYPED,
                            source=src,
                        )
                    ],
                )
    character._graph.invalidate("attack_melee")
    character._graph.invalidate("attack_ranged")
