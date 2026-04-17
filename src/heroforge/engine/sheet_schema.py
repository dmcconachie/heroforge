"""
engine/sheet_schema.py
----------------------
Dataclasses describing the computed character-sheet
output. Every field is typed; closed vocabularies use
enums (Ability, Alignment, Save, Size, BonusType,
KnownRace, KnownClass, KnownSkill, CastType,
SpellPreparation). `str` is reserved for genuinely
open vocabularies (parameterised feat display text,
composed equipment names, free-form class-feature
description strings).

Serialisation: `converter.unstructure(sheet)` from
`heroforge.rules.schema` — the cattrs StrEnum→str hook
and the per-dataclass "omit default" hooks produce
compact YAML with no `!!python/object/apply:` leaks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from heroforge.engine.bonus import BonusType
from heroforge.engine.character import (
    Ability,
    Alignment,
    Save,
    Size,
)
from heroforge.engine.classes import (
    CastType,
    SpellPreparation,
)
from heroforge.rules.known import (
    KnownClass,
    KnownMagicItem,
    KnownRace,
    KnownSkill,
)

# ---------------------------------------------------
# Identity
# ---------------------------------------------------


@dataclass
class SheetIdentity:
    name: str
    race: KnownRace
    class_str: str
    level: int
    alignment: Alignment
    deity: str
    size: Size


# ---------------------------------------------------
# Ability scores
# ---------------------------------------------------


@dataclass
class AbilityEntry:
    base: int
    score: int
    mod: int
    level_bumps: int | None = None
    inherent: int | None = None
    typed: dict[BonusType, int] = field(default_factory=dict)


# ---------------------------------------------------
# Generic breakdown used for combat stats, saves,
# attack rolls, skills — anything with a base value,
# ability-mod contributions, a size modifier, typed
# bonus stacking, and a final total.
# ---------------------------------------------------


@dataclass
class Breakdown:
    total: int
    base: int | None = None
    ability: dict[Ability, int] = field(default_factory=dict)
    size: int | None = None
    typed: dict[BonusType, int] = field(default_factory=dict)


# ---------------------------------------------------
# Combat
# ---------------------------------------------------


@dataclass
class CombatSection:
    ac: Breakdown
    touch_ac: int
    flatfooted_ac: int
    hp_max: Breakdown
    bab: Breakdown
    initiative: Breakdown
    speed: Breakdown
    sr: int
    saves: dict[Save, Breakdown]
    attack_melee: Breakdown
    attack_ranged: Breakdown
    damage_melee: Breakdown
    grapple: Breakdown


@dataclass
class Iteratives:
    melee: list[int]
    ranged: list[int]


# ---------------------------------------------------
# Skills
# ---------------------------------------------------


@dataclass
class SkillEntry:
    total: int
    ability_mod: int
    ranks: int | None = None
    synergy: int | None = None
    armor_penalty: int | None = None
    speed_mod: int | None = None
    typed: dict[BonusType, int] = field(default_factory=dict)


# ---------------------------------------------------
# Carrying capacity
# ---------------------------------------------------


@dataclass
class CarryingCapacity:
    light: int
    medium: int
    heavy: int


# ---------------------------------------------------
# Spellcasting
# ---------------------------------------------------


@dataclass
class SpellcastingEntry:
    caster_level: int
    key_ability: Ability
    cast_type: CastType
    preparation: SpellPreparation
    slots_per_day: list[int | None]
    spell_save_dc: dict[int, int] = field(default_factory=dict)
    spells_known_count: list[int | None] | None = None
    spells_known: dict[int, list[str]] | None = None


# ---------------------------------------------------
# Equipment
# ---------------------------------------------------


@dataclass
class ArmorDisplay:
    name: str
    acp: int = 0
    max_dex: int | None = None
    asf: int | None = None
    properties: list[str] = field(default_factory=list)


@dataclass
class WeaponDisplay:
    name: str
    damage_dice: str = ""
    crit_range: str = ""
    crit_mult: str = ""
    range_inc: int | None = None
    damage_types: list[str] = field(default_factory=list)
    weapon_type: str = ""
    weight: float | None = None
    properties: list[str] = field(default_factory=list)


@dataclass
class EquipmentSection:
    armor: ArmorDisplay | None = None
    shield: ArmorDisplay | None = None
    worn: list[KnownMagicItem] = field(default_factory=list)
    weapons: list[WeaponDisplay] = field(default_factory=list)


# ---------------------------------------------------
# Top-level sheet
# ---------------------------------------------------


@dataclass
class Sheet:
    identity: SheetIdentity
    abilities: dict[Ability, AbilityEntry]
    combat: CombatSection
    attack_iteratives: Iteratives
    skills: dict[KnownSkill, SkillEntry]
    carrying_capacity: CarryingCapacity
    feats: list[str] = field(default_factory=list)
    class_features: list[str] = field(default_factory=list)
    spellcasting: dict[KnownClass, SpellcastingEntry] = field(
        default_factory=dict,
    )
    special_qualities: list[str] = field(default_factory=list)
    equipment: EquipmentSection = field(default_factory=EquipmentSection)
