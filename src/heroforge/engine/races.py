"""
engine/races.py
---------------
RaceDefinition and related types for D&D 3.5e
playable races.

Public API:
  RaceAbilityMod   -- one racial ability modifier
  RaceDefinition   -- complete race description
  RaceRegistry     -- lookup by name
  apply_race()     -- wire racial bonuses into Character
  remove_race()    -- undo racial bonuses
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from heroforge.engine.bonus import (
    BonusEntry,
    BonusType,
)

if TYPE_CHECKING:
    from heroforge.engine.character import Character


# -----------------------------------------------------------
# RaceAbilityMod
# -----------------------------------------------------------


@dataclass
class RaceAbilityMod:
    """One racial ability score modifier."""

    ability: str  # "str", "dex", etc.
    value: int
    bonus_type: BonusType = BonusType.UNTYPED


# -----------------------------------------------------------
# RaceDefinition
# -----------------------------------------------------------


@dataclass
class RaceDefinition:
    """Complete description of a playable race."""

    name: str
    source_book: str = "PHB"
    creature_type: str = "Humanoid"
    subtypes: list[str] = field(default_factory=list)
    size: str = "Medium"
    base_speed: int = 30
    ability_modifiers: list[RaceAbilityMod] = field(default_factory=list)
    favored_class: str = "any"
    la: int = 0
    racial_traits: list[str] = field(default_factory=list)
    languages_auto: list[str] = field(default_factory=list)
    languages_bonus: list[str] = field(default_factory=list)
    weapon_familiarity: list[str] = field(default_factory=list)
    low_light_vision: bool = False
    darkvision: int = 0

    @property
    def size_modifier(self) -> int:
        if self.size == "Small":
            return 1
        if self.size == "Large":
            return -1
        return 0

    @property
    def hide_modifier(self) -> int:
        if self.size == "Small":
            return 4
        if self.size == "Large":
            return -4
        return 0


# -----------------------------------------------------------
# RaceRegistry
# -----------------------------------------------------------


class RaceRegistry:
    """Central lookup for RaceDefinitions."""

    def __init__(self) -> None:
        self._defs: dict[str, RaceDefinition] = {}

    def register(
        self,
        defn: RaceDefinition,
        overwrite: bool = False,
    ) -> None:
        if defn.name in self._defs and not overwrite:
            raise ValueError(
                f"RaceDefinition {defn.name!r} already registered."
            )
        self._defs[defn.name] = defn

    def get(self, name: str) -> RaceDefinition | None:
        return self._defs.get(name)

    def require(self, name: str) -> RaceDefinition:
        defn = self._defs.get(name)
        if defn is None:
            raise KeyError(f"No RaceDefinition for {name!r}.")
        return defn

    def all_names(self) -> list[str]:
        return sorted(self._defs.keys())

    def __len__(self) -> int:
        return len(self._defs)

    def __contains__(self, name: str) -> bool:
        return name in self._defs


# -----------------------------------------------------------
# apply_race / remove_race
# -----------------------------------------------------------

_RACE_SOURCE_KEY = "race:ability_mods"
_RACE_SPEED_KEY = "race:speed"


def apply_race(defn: RaceDefinition, character: "Character") -> None:
    """
    Apply a race's ability modifiers and base speed.
    Idempotent.
    """
    character.race = defn.name

    for mod in defn.ability_modifiers:
        pool_key = f"{mod.ability}_score"
        pool = character.get_pool(pool_key)
        if pool is None:
            continue
        entry = BonusEntry(
            value=mod.value,
            bonus_type=mod.bonus_type,
            source=defn.name,
        )
        pool.set_source(_RACE_SOURCE_KEY, [entry])
        character._graph.invalidate_pool(pool_key)

    character._race_size = defn.size
    character._race_base_speed = defn.base_speed
    character._graph.invalidate_pool("speed")
    character._graph.invalidate("speed")

    if not getattr(character, "_creature_type_override", None):
        character._race_creature_type = defn.creature_type

    existing_subs = list(getattr(character, "_race_subtypes", []))
    for sub in defn.subtypes:
        if sub not in existing_subs:
            existing_subs.append(sub)
    character._race_subtypes = existing_subs
    character._race_favored_class = defn.favored_class

    character._graph.invalidate("ac")
    character._graph.invalidate("attack_melee")
    character._graph.invalidate("attack_ranged")

    affected = {
        f"{ab}_score"
        for ab in (
            "str",
            "dex",
            "con",
            "int",
            "wis",
            "cha",
        )
    }
    affected |= {
        "speed",
        "ac",
        "attack_melee",
        "attack_ranged",
    }
    character._notify(affected)


def remove_race(defn: RaceDefinition, character: "Character") -> None:
    """Remove a race's ability modifiers. Idempotent."""
    for mod in defn.ability_modifiers:
        pool_key = f"{mod.ability}_score"
        pool = character.get_pool(pool_key)
        if pool is not None:
            pool.clear_source(_RACE_SOURCE_KEY)
            character._graph.invalidate_pool(pool_key)

    character._race_base_speed = 30
    character._race_size = "Medium"
    character._graph.invalidate("speed")
    character.race = ""

    affected = {
        f"{ab}_score"
        for ab in (
            "str",
            "dex",
            "con",
            "int",
            "wis",
            "cha",
        )
    }
    affected.add("speed")
    character._notify(affected)
