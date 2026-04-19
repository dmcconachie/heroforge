"""
engine/equipment.py
-------------------
Equipment system: armor, shields, worn magic items,
and weapons with stat effects wired into the
Character's BonusPools.

Armor contributes:
  - Armor bonus to AC (BonusType.ARMOR)
  - Max DEX bonus cap
  - Armor check penalty to relevant skills
  - Arcane spell failure chance (tracked, not a pool)

Shields contribute:
  - Shield bonus to AC (BonusType.SHIELD)
  - Armor check penalty (stacks with armor ACP)
  - Arcane spell failure chance

Worn magic items (rings, cloaks, belts, etc.) are
permanent — their effects feed directly into pools
via set_source(), NOT through the buff toggle system.

Weapons are data-only — no pool contributions.
Attack/damage bonuses come from ability scores, BAB,
and enhancement bonuses (applied separately).

Public API:
  ArmorDefinition          — data model for armor/shields
  WeaponDefinition         — data model for weapons
  ArmorRegistry            — name-based lookup
  WeaponRegistry           — name-based lookup
  equip_armor()            — wire armor into pools
  unequip_armor()          — remove armor from pools
  equip_shield()           — wire shield into pools
  unequip_shield()         — remove shield from pools
  equip_item()             — wire magic item into pools
  unequip_item()           — remove magic item from pools
  adjust_for_material()    — material ACP/DEX/ASF mods
  equipment_display_name() — build display name
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from heroforge.rules.core.pool_keys import PoolKey

if TYPE_CHECKING:
    from heroforge.engine.character import Character
    from heroforge.engine.magic_items import (
        MagicItemDefinition,
    )


class ArmorCategory(enum.Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"
    SHIELD = "shield"
    TOWER_SHIELD = "tower_shield"


class LoadCategory(enum.Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


_SHIELD_CATS = {
    ArmorCategory.SHIELD,
    ArmorCategory.TOWER_SHIELD,
}


class WeaponCategory(enum.Enum):
    SIMPLE = "simple"
    MARTIAL = "martial"
    EXOTIC = "exotic"


class DamageType(StrEnum):
    SLASHING = "slashing"
    PIERCING = "piercing"
    BLUDGEONING = "bludgeoning"
    BLUDGEONING_AND_PIERCING = "bludgeoning and piercing"
    PIERCING_OR_SLASHING = "piercing or slashing"


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
    damage_type: DamageType | str = ""
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
            d for d in self._entries.values() if d.category not in _SHIELD_CATS
        ]

    def all_shields(self) -> list[ArmorDefinition]:
        return [d for d in self._entries.values() if d.category in _SHIELD_CATS]

    def all_entries(self) -> list[ArmorDefinition]:
        return list(self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)


@dataclass(frozen=True)
class MaterialDefinition:
    """Armor/shield material with stat adjustments."""

    name: str
    acp_adjust: int = 0  # toward 0 (positive)
    max_dex_adjust: int = 0
    asf_adjust: int = 0  # negative = less failure
    armor_bonus_adjust: int = 0  # typically 0 or -1
    category_shift: int = 0  # -1 = one lighter
    includes_masterwork: bool = False
    note: str = ""


class MaterialRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, MaterialDefinition] = {}

    def register(self, defn: MaterialDefinition) -> None:
        self._entries[defn.name.lower()] = defn

    def get(self, name: str) -> MaterialDefinition | None:
        return self._entries.get(name.lower())

    def all_materials(
        self,
    ) -> list[MaterialDefinition]:
        return list(self._entries.values())

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
# Material adjustments
# -------------------------------------------------------


def adjust_for_material(
    acp: int,
    max_dex: int,
    asf: int,
    material: str | MaterialDefinition,
) -> tuple[int, int, int]:
    """
    Return (acp, max_dex, asf) adjusted for material.

    *material* can be a MaterialDefinition or a string
    (looked up in the module-level registry).
    """
    mat = _resolve_material(material)
    if mat is None:
        return acp, max_dex, asf
    if mat.acp_adjust:
        acp = min(acp + mat.acp_adjust, 0)
    if mat.max_dex_adjust and max_dex >= 0:
        max_dex += mat.max_dex_adjust
    if mat.asf_adjust:
        asf = max(asf + mat.asf_adjust, 0)
    return acp, max_dex, asf


# Fallback registry for when AppState isn't available.
_material_registry: MaterialRegistry | None = None


def set_material_registry(
    reg: MaterialRegistry,
) -> None:
    """Set the module-level material registry."""
    global _material_registry  # noqa: PLW0603
    _material_registry = reg


def _resolve_material(
    material: str | MaterialDefinition,
) -> MaterialDefinition | None:
    if isinstance(material, MaterialDefinition):
        return material
    if not material:
        return None
    if _material_registry is not None:
        return _material_registry.get(material)
    return None


# -------------------------------------------------------
# Equip / unequip helpers
# -------------------------------------------------------

_ARMOR_SRC = "equip:armor"
_SHIELD_SRC = "equip:shield"


def equip_armor(
    character: Character,
    armor: ArmorDefinition,
    enhancement: int = 0,
    material: str = "",
    masterwork: bool = False,
) -> None:
    """Wire armor bonuses into Character pools."""
    from heroforge.engine.bonus import (
        BonusEntry,
        BonusType,
    )

    acp = armor.armor_check_penalty
    max_dex = armor.max_dex_bonus
    asf = armor.arcane_spell_failure
    armor_bonus = armor.armor_bonus
    mat_def = _resolve_material(material)
    if mat_def is not None:
        acp, max_dex, asf = adjust_for_material(acp, max_dex, asf, mat_def)
        armor_bonus = max(0, armor_bonus + mat_def.armor_bonus_adjust)
    # Masterwork reduces ACP by 1, but special
    # materials that include_masterwork already
    # account for this in their acp_adjust.
    mat_is_mw = mat_def.includes_masterwork if mat_def else False
    if (enhancement > 0 or masterwork) and not mat_is_mw:
        acp = min(acp + 1, 0)

    total_ac = armor_bonus + enhancement

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
        "category": armor.category.value,
        "max_dex_bonus": max_dex,
        "armor_check_penalty": acp,
        "arcane_spell_failure": asf,
        "enhancement": enhancement,
        "material": material,
    }

    # Push ACP into skill pools
    _apply_acp(character, _ARMOR_SRC, acp)

    # Speed penalty from medium/heavy armor
    _apply_armor_speed(character, armor, material)

    character._graph.invalidate("ac")
    character._graph.invalidate("speed")
    character.on_change.notify({"ac", "equipment", "speed"})


def unequip_armor(character: Character) -> None:
    """Remove armor bonuses from Character pools."""
    pool = character._pools.get("ac")
    if pool is not None:
        pool.clear_source(_ARMOR_SRC)

    character.equipment.pop("armor", None)
    _clear_acp(character, _ARMOR_SRC)

    # Remove speed penalty
    sp = character._pools.get("speed")
    if sp is not None:
        sp.clear_source(_ARMOR_SRC)

    character._graph.invalidate("ac")
    character._graph.invalidate("speed")
    character.on_change.notify({"ac", "equipment", "speed"})


def equip_shield(
    character: Character,
    shield: ArmorDefinition,
    enhancement: int = 0,
    material: str = "",
    masterwork: bool = False,
) -> None:
    """Wire shield bonuses into Character pools."""
    from heroforge.engine.bonus import (
        BonusEntry,
        BonusType,
    )

    acp = shield.armor_check_penalty
    asf = shield.arcane_spell_failure
    max_dex = shield.max_dex_bonus
    mat_def = _resolve_material(material)
    if mat_def is not None:
        acp, max_dex, asf = adjust_for_material(acp, max_dex, asf, mat_def)
    mat_is_mw = mat_def.includes_masterwork if mat_def else False
    if (enhancement > 0 or masterwork) and not mat_is_mw:
        acp = min(acp + 1, 0)

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
        "armor_check_penalty": acp,
        "arcane_spell_failure": asf,
        "enhancement": enhancement,
        "material": material,
    }

    _apply_acp(character, _SHIELD_SRC, acp)

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


_LIGHT_CATS = {ArmorCategory.LIGHT}
_MEDIUM_CATS = {ArmorCategory.MEDIUM}
_HEAVY_CATS = {ArmorCategory.HEAVY}

# 3.5e: medium/heavy → 30→20, 20→15.
# Mithral shifts category one lighter.
_SPEED_PENALTY = {30: -10, 20: -5}


_CAT_ORDER = [
    ArmorCategory.LIGHT,
    ArmorCategory.MEDIUM,
    ArmorCategory.HEAVY,
]


def _effective_category(cat: ArmorCategory, material: str) -> ArmorCategory:
    """Category after material's category_shift."""
    mat = _resolve_material(material)
    if mat is None or mat.category_shift == 0:
        return cat
    if cat not in _CAT_ORDER:
        return cat  # shields don't shift
    idx = _CAT_ORDER.index(cat)
    idx = max(0, min(len(_CAT_ORDER) - 1, idx + mat.category_shift))
    return _CAT_ORDER[idx]


def _apply_armor_speed(
    character: Character,
    armor: ArmorDefinition,
    material: str,
) -> None:
    """Push speed penalty for medium/heavy armor."""
    from heroforge.engine.bonus import (
        BonusEntry,
        BonusType,
    )

    eff_cat = _effective_category(armor.category, material)
    if eff_cat in _LIGHT_CATS or eff_cat == ArmorCategory.LIGHT:
        # Light armor: no speed penalty
        sp = character._pools.get("speed")
        if sp is not None:
            sp.clear_source(_ARMOR_SRC)
        return

    base_speed = character._race_base_speed
    penalty = _SPEED_PENALTY.get(base_speed, -10)

    sp = character._pools.get("speed")
    if sp is not None:
        sp.set_source(
            _ARMOR_SRC,
            [
                BonusEntry(
                    value=penalty,
                    bonus_type=BonusType.UNTYPED,
                    source=_ARMOR_SRC,
                )
            ],
        )


# SRD: these skills take ACP.  Swim takes double.
_ACP_SKILLS: frozenset[PoolKey] = frozenset(
    {
        PoolKey.SKILL_BALANCE,
        PoolKey.SKILL_CLIMB,
        PoolKey.SKILL_ESCAPE_ARTIST,
        PoolKey.SKILL_HIDE,
        PoolKey.SKILL_JUMP,
        PoolKey.SKILL_MOVE_SILENTLY,
        PoolKey.SKILL_SLEIGHT_OF_HAND,
        PoolKey.SKILL_TUMBLE,
    }
)
_ACP_DOUBLE_SKILLS: frozenset[PoolKey] = frozenset({PoolKey.SKILL_SWIM})


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

    for key in _ACP_SKILLS:
        pool = character._pools.get(key)
        if pool is not None:
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
    for key in _ACP_DOUBLE_SKILLS:
        pool = character._pools.get(key)
        if pool is not None:
            pool.set_source(
                source,
                [
                    BonusEntry(
                        value=penalty * 2,
                        bonus_type=BonusType.UNTYPED,
                        source=source,
                    )
                ],
            )


def _clear_acp(character: Character, source: str) -> None:
    """Remove ACP from affected skill pools."""
    for key in _ACP_SKILLS | _ACP_DOUBLE_SKILLS:
        pool = character._pools.get(key)
        if pool is not None:
            pool.clear_source(source)


# -------------------------------------------------------
# Worn magic items
# -------------------------------------------------------

_MULTI_TARGET_EXPANSIONS: dict[PoolKey, list[PoolKey]] = {
    PoolKey.ATTACK_ALL: [PoolKey.ATTACK_MELEE, PoolKey.ATTACK_RANGED],
    PoolKey.DAMAGE_ALL: [PoolKey.DAMAGE_MELEE, PoolKey.DAMAGE_RANGED],
}


def equip_item(
    character: Character,
    item: "MagicItemDefinition",
) -> None:
    """
    Wire a worn magic item's effects into pools.

    Items are permanent — they use set_source() directly,
    NOT the buff toggle system.

    Each effect may carry a `gate: [...]` list (same
    gate vocabulary as class features). Gated effects
    attach a condition lambda to their BonusEntry so the
    pool's aggregate() skips them when the gate is off.
    """
    from heroforge.engine.effects import (
        pool_entries_from_effects,
    )
    from heroforge.engine.gates import make_condition

    if not item.effects:
        return

    source_key = f"item:{item.name}"

    pool_entries: dict[str, list] = {}
    for eff_decl in item.effects:
        gate = eff_decl.get("gate") or []
        condition = make_condition(tuple(gate))
        pairs = pool_entries_from_effects(
            effects_raw=[eff_decl],
            source_label=item.name,
            character=character,
            condition=condition,
        )
        for tgt, entry in pairs:
            pool_entries.setdefault(tgt, []).append(entry)

    affected: set[str] = set()
    for pool_key, entries in pool_entries.items():
        pool = character._pools.get(pool_key)
        if pool is None:
            continue
        pool.set_source(source_key, entries)
        affected.add(pool_key)

    for pk in affected:
        character._graph.invalidate_pool(pk)
    # The item may have contributed to a derived pool
    # (e.g. Monk's Belt → effective_monk_level_ac). Those
    # consumers need refreshing so their cached values see
    # the new pool sum.
    character._refresh_derived_pool_consumers()
    if affected:
        character.on_change.notify(affected | {"equipment"})


def unequip_item(
    character: Character,
    item_name: str,
) -> None:
    """Remove a worn magic item's effects."""
    source_key = f"item:{item_name}"
    affected: set[str] = set()
    for pool in character._pools.values():
        if source_key in pool._sources:
            pool.clear_source(source_key)
            affected.add(pool.stat_key)
    for pk in affected:
        character._graph.invalidate_pool(pk)
    character._refresh_derived_pool_consumers()
    if affected:
        character.on_change.notify(affected | {"equipment"})


# -------------------------------------------------------
# Display name helpers
# -------------------------------------------------------


def equipment_display_name(
    base: str,
    enhancement: int = 0,
    material: str = "",
    masterwork: bool = False,
    name: str = "",
) -> str:
    """
    Build a display name from equipment parts.

    Examples:
      base="Lance", enhancement=1
        → "+1 Lance"
      base="Lance", enhancement=1, material="Bronzewood"
        → "+1 Bronzewood Lance"
      base="Longsword", masterwork=True
        → "Masterwork Longsword"
      base="Full Plate", enhancement=1, material="Mithral"
        → "+1 Mithral Full Plate"
      name="+1 Flaming Longsword" (explicit override)
        → "+1 Flaming Longsword"
    """
    if name:
        return name
    parts: list[str] = []
    if enhancement > 0:
        parts.append(f"+{enhancement}")
    elif masterwork:
        parts.append("Masterwork")
    if material:
        parts.append(material)
    parts.append(base)
    return " ".join(parts)
