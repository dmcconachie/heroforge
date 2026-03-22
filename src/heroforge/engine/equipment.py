"""
engine/equipment.py
-------------------
Equipment system: armor, shields, and weapons with
stat effects wired into the Character's BonusPools.

Armor contributes:
  - Armor bonus to AC (BonusType.ARMOR)
  - Max DEX bonus cap
  - Armor check penalty to relevant skills
  - Arcane spell failure chance (tracked, not a pool)

Shields contribute:
  - Shield bonus to AC (BonusType.SHIELD)
  - Armor check penalty (stacks with armor ACP)
  - Arcane spell failure chance

Weapons are data-only — no pool contributions.
Attack/damage bonuses come from ability scores, BAB,
and enhancement bonuses (applied separately).

Public API:
  ArmorDefinition   — data model for armor/shields
  WeaponDefinition  — data model for weapons
  ArmorRegistry     — name-based lookup
  WeaponRegistry    — name-based lookup
  equip_armor()     — wire armor into Character pools
  unequip_armor()   — remove armor from Character pools
  equip_shield()    — wire shield into Character pools
  unequip_shield()  — remove shield from pools
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from heroforge.engine.character import Character


class ArmorCategory(enum.Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"
    SHIELD = "shield"


class WeaponCategory(enum.Enum):
    SIMPLE = "simple"
    MARTIAL = "martial"
    EXOTIC = "exotic"


@dataclass(frozen=True)
class ArmorDefinition:
    name: str
    category: ArmorCategory
    armor_bonus: int
    max_dex_bonus: int  # -1 = no cap
    armor_check_penalty: int  # 0 or negative
    arcane_spell_failure: int  # percentage 0-100
    speed_30: int  # speed when base is 30
    speed_20: int  # speed when base is 20
    weight: float = 0.0
    cost_gp: int = 0
    special: str = ""


@dataclass(frozen=True)
class WeaponDefinition:
    name: str
    category: WeaponCategory
    damage_dice: str  # e.g. "1d8", "2d6"
    critical_range: int = 20  # threat range start
    critical_multiplier: int = 2
    damage_type: str = ""  # slash/pierce/bludgeon
    range_increment: int = 0  # 0 = melee
    weight: float = 0.0
    cost_gp: int = 0
    is_ranged: bool = False
    special: str = ""


class ArmorRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, ArmorDefinition] = {}

    def register(self, defn: ArmorDefinition) -> None:
        self._entries[defn.name] = defn

    def get(self, name: str) -> ArmorDefinition | None:
        return self._entries.get(name)

    def all_armor(self) -> list[ArmorDefinition]:
        return [
            d
            for d in self._entries.values()
            if d.category != ArmorCategory.SHIELD
        ]

    def all_shields(self) -> list[ArmorDefinition]:
        return [
            d
            for d in self._entries.values()
            if d.category == ArmorCategory.SHIELD
        ]

    def __len__(self) -> int:
        return len(self._entries)


class WeaponRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, WeaponDefinition] = {}

    def register(self, defn: WeaponDefinition) -> None:
        self._entries[defn.name] = defn

    def get(self, name: str) -> WeaponDefinition | None:
        return self._entries.get(name)

    def all_weapons(self) -> list[WeaponDefinition]:
        return list(self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)


# -------------------------------------------------------
# Equip / unequip helpers
# -------------------------------------------------------

_ARMOR_SRC = "equip:armor"
_SHIELD_SRC = "equip:shield"


def equip_armor(
    character: Character,
    armor: ArmorDefinition,
    enhancement: int = 0,
) -> None:
    """Wire armor bonuses into Character pools."""
    from heroforge.engine.bonus import (
        BonusEntry,
        BonusType,
    )

    total_ac = armor.armor_bonus + enhancement

    # AC bonus
    pool = character._pools.get("ac")
    if pool is not None:
        pool.set_source(
            _ARMOR_SRC,
            [
                BonusEntry(
                    value=total_ac,
                    bonus_type=BonusType.ARMOR,
                    source=_ARMOR_SRC,
                )
            ],
        )

    # Store armor data for max DEX and ACP
    character.equipment["armor"] = {
        "name": armor.name,
        "max_dex_bonus": armor.max_dex_bonus,
        "armor_check_penalty": (armor.armor_check_penalty),
        "arcane_spell_failure": (armor.arcane_spell_failure),
        "enhancement": enhancement,
    }

    # Push ACP into skill pools
    _apply_acp(
        character,
        _ARMOR_SRC,
        armor.armor_check_penalty,
    )

    character._graph.invalidate("ac")
    character.on_change.notify({"ac", "equipment"})


def unequip_armor(character: Character) -> None:
    """Remove armor bonuses from Character pools."""
    pool = character._pools.get("ac")
    if pool is not None:
        pool.clear_source(_ARMOR_SRC)

    character.equipment.pop("armor", None)
    _clear_acp(character, _ARMOR_SRC)

    character._graph.invalidate("ac")
    character.on_change.notify({"ac", "equipment"})


def equip_shield(
    character: Character,
    shield: ArmorDefinition,
    enhancement: int = 0,
) -> None:
    """Wire shield bonuses into Character pools."""
    from heroforge.engine.bonus import (
        BonusEntry,
        BonusType,
    )

    total_ac = shield.armor_bonus + enhancement

    pool = character._pools.get("ac")
    if pool is not None:
        pool.set_source(
            _SHIELD_SRC,
            [
                BonusEntry(
                    value=total_ac,
                    bonus_type=BonusType.SHIELD,
                    source=_SHIELD_SRC,
                )
            ],
        )

    character.equipment["shield"] = {
        "name": shield.name,
        "armor_check_penalty": (shield.armor_check_penalty),
        "arcane_spell_failure": (shield.arcane_spell_failure),
        "enhancement": enhancement,
    }

    _apply_acp(
        character,
        _SHIELD_SRC,
        shield.armor_check_penalty,
    )

    character._graph.invalidate("ac")
    character.on_change.notify({"ac", "equipment"})


def unequip_shield(character: Character) -> None:
    """Remove shield bonuses from Character pools."""
    pool = character._pools.get("ac")
    if pool is not None:
        pool.clear_source(_SHIELD_SRC)

    character.equipment.pop("shield", None)
    _clear_acp(character, _SHIELD_SRC)

    character._graph.invalidate("ac")
    character.on_change.notify({"ac", "equipment"})


def _apply_acp(
    character: Character,
    source: str,
    penalty: int,
) -> None:
    """Push armor check penalty into skill pools."""
    if penalty >= 0:
        return
    from heroforge.engine.bonus import (
        BonusEntry,
        BonusType,
    )

    for key, pool in character._pools.items():
        if not key.startswith("skill_"):
            continue
        # Only apply to armor-check skills
        # The pool key pattern is skill_<name>
        pool.set_source(
            source,
            [
                BonusEntry(
                    value=penalty,
                    bonus_type=BonusType.UNTYPED,
                    source=source,
                )
            ],
        )


def _clear_acp(character: Character, source: str) -> None:
    """Remove ACP from all skill pools."""
    for key, pool in character._pools.items():
        if key.startswith("skill_"):
            pool.clear_source(source)
