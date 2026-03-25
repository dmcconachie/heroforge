"""
rules/schema.py
---------------
Central cattrs converter for YAML → dataclass structuring.

All enum coercion, custom type hooks, and
``forbid_extra_keys`` configuration live here.
Loaders call ``converter.structure(decl, SomeClass)``
instead of manually extracting fields with
``decl.get()``.

Public API:
  converter  — pre-configured cattrs.Converter
"""

from __future__ import annotations

import enum

import cattrs

from heroforge.engine.bonus import BonusType
from heroforge.engine.classes_races import (
    BABProgression,
    ClassDefinition,
    ClassFeature,
    DomainDefinition,
    RaceAbilityMod,
    RaceDefinition,
    SaveProgression,
    SaveProgressions,
    SpellcastingInfo,
)
from heroforge.engine.conditions import ConditionDefinition
from heroforge.engine.equipment import (
    ArmorCategory,
    ArmorDefinition,
    WeaponCategory,
    WeaponDefinition,
)
from heroforge.engine.feats import FeatKind
from heroforge.engine.magic_items import MagicItemDefinition
from heroforge.engine.skills import SkillDefinition
from heroforge.engine.spells import SpellEntry

converter = cattrs.Converter(
    forbid_extra_keys=True,
)


def _fields_of(cls: type) -> set[str]:
    """
    Return init field names for a dataclass.

    Only fields with ``init=True`` are included —
    derived fields (``init=False``) are excluded
    since they don't come from YAML.
    """
    from dataclasses import fields

    return {f.name for f in fields(cls) if f.init}


def _forbid_extra(
    val: dict,
    cls_or_keys: type | set[str],
    label: str,
) -> None:
    """
    Raise if *val* has keys not in the dataclass.

    *cls_or_keys* is either a dataclass type (fields
    are extracted automatically) or an explicit set.
    """
    if isinstance(cls_or_keys, set):
        allowed = cls_or_keys
    else:
        allowed = _fields_of(cls_or_keys)
    extra = set(val) - allowed
    if extra:
        msg = f"{label}: unknown keys {sorted(extra)}"
        raise Exception(msg)  # noqa: TRY002


# -------------------------------------------------------
# Enum hooks: string → enum by value
# -------------------------------------------------------
# cattrs handles standard enums out of the box when
# the value matches, but we register explicit hooks
# for clarity and better error messages.

_ENUM_TYPES: list[type[enum.Enum]] = [
    BABProgression,
    SaveProgression,
    BonusType,
    ArmorCategory,
    WeaponCategory,
    FeatKind,
]

for _enum_cls in _ENUM_TYPES:

    def _make_hook(
        cls: type[enum.Enum],
    ) -> cattrs.SimpleStructureHook:
        def hook(val: object, _: type) -> enum.Enum:
            if isinstance(val, cls):
                return val
            return cls(val)

        return hook

    converter.register_structure_hook(_enum_cls, _make_hook(_enum_cls))


# -------------------------------------------------------
# SaveProgressions: {fort: "good", ...} → dataclass
# -------------------------------------------------------
def _structure_save_progressions(val: object, _: type) -> SaveProgressions:
    if isinstance(val, SaveProgressions):
        return val
    if not isinstance(val, dict):
        return SaveProgressions()
    return SaveProgressions(
        fort=SaveProgression(val.get("fort", "poor")),
        ref=SaveProgression(val.get("ref", "poor")),
        will=SaveProgression(val.get("will", "poor")),
    )


converter.register_structure_hook(
    SaveProgressions,
    _structure_save_progressions,
)


# -------------------------------------------------------
# SpellcastingInfo | None: null → None, dict → obj
# -------------------------------------------------------
def _structure_spellcasting(val: object, _: type) -> SpellcastingInfo | None:
    if val is None:
        return None
    if isinstance(val, SpellcastingInfo):
        return val
    if not isinstance(val, dict):
        return None
    return SpellcastingInfo(
        cast_type=val.get("cast_type", "arcane"),
        stat=val.get("stat", "int"),
        preparation=val.get("preparation", "prepared"),
        max_spell_level=int(val.get("max_spell_level", 9)),
        starts_at_level=int(val.get("starts_at_level", 1)),
    )


converter.register_structure_hook(
    SpellcastingInfo | None,
    _structure_spellcasting,
)


# -------------------------------------------------------
# ClassFeature: straightforward frozen dataclass
# -------------------------------------------------------
def _structure_class_feature(val: object, _: type) -> ClassFeature:
    if isinstance(val, ClassFeature):
        return val
    if isinstance(val, dict):
        _forbid_extra(val, ClassFeature, "class_feature")
        me_raw = val.get("mutually_exclusive_with", [])
        return ClassFeature(
            level=val["level"],
            feature=val["feature"],
            description=val.get("description", ""),
            buff_name=val.get("buff_name", ""),
            effects=tuple(val.get("effects", [])),
            note=val.get("note", ""),
            requires_caster_level=bool(val.get("requires_caster_level", False)),
            mutually_exclusive_with=tuple(me_raw),
        )
    msg = f"Cannot structure {val!r} as ClassFeature"
    raise cattrs.ClassValidationError(msg, [], ClassFeature)


converter.register_structure_hook(
    ClassFeature,
    _structure_class_feature,
)

# -------------------------------------------------------
# ClassDefinition: custom hook to handle prerequisites
# (which are Any-typed and should pass through as-is)
# -------------------------------------------------------


def _structure_class_definition(val: object, _: type) -> ClassDefinition:
    if not isinstance(val, dict):
        msg = f"Cannot structure {type(val)} as ClassDefinition"
        raise TypeError(msg)
    _forbid_extra(val, ClassDefinition, val.get("name", "?"))
    return ClassDefinition(
        name=val["name"],
        source_book=val.get("source_book", "PHB"),
        hit_die=int(val.get("hit_die", 8)),
        bab_progression=converter.structure(
            val.get("bab_progression", "medium"),
            BABProgression,
        ),
        save_progressions=converter.structure(
            val.get("save_progressions", {}),
            SaveProgressions,
        ),
        skills_per_level=int(val.get("skills_per_level", 2)),
        class_skills=val.get("class_skills", []),
        spellcasting=_structure_spellcasting(
            val.get("spellcasting"), type(None)
        ),
        class_features=[
            converter.structure(f, ClassFeature)
            for f in val.get("class_features", [])
        ],
        max_level=int(val.get("max_level", 20)),
        is_prestige=bool(val.get("is_prestige", False)),
        # Pass through as raw dicts — prerequisite
        # tree building is handled separately by the
        # loader.
        entry_prerequisites=val.get("entry_prerequisites"),
        ongoing_prerequisites=val.get("ongoing_prerequisites"),
    )


converter.register_structure_hook(
    ClassDefinition,
    _structure_class_definition,
)


# -------------------------------------------------------
# DomainDefinition: string keys → int for domain_spells
# -------------------------------------------------------
def _structure_domain_definition(val: object, _: type) -> DomainDefinition:
    if not isinstance(val, dict):
        msg = f"Cannot structure {type(val)} as DomainDefinition"
        raise TypeError(msg)
    _forbid_extra(
        val,
        {"name", "granted_power", "domain_spells"},
        val.get("name", "?"),
    )
    spells_raw = val.get("domain_spells", {})
    domain_spells = {int(k): str(v) for k, v in spells_raw.items()}
    return DomainDefinition(
        name=val["name"],
        granted_power=val.get("granted_power", ""),
        domain_spells=domain_spells,
    )


converter.register_structure_hook(
    DomainDefinition,
    _structure_domain_definition,
)

# -------------------------------------------------------
# ArmorDefinition: weight needs float coercion
# -------------------------------------------------------


def _structure_armor_definition(val: object, _: type) -> ArmorDefinition:
    if not isinstance(val, dict):
        msg = f"Cannot structure {type(val)} as ArmorDefinition"
        raise TypeError(msg)
    _forbid_extra(val, ArmorDefinition, val.get("name", "?"))
    return ArmorDefinition(
        name=val["name"],
        category=converter.structure(
            val.get("category", "light"),
            ArmorCategory,
        ),
        armor_bonus=val.get("armor_bonus", 0),
        max_dex_bonus=val.get("max_dex_bonus", -1),
        armor_check_penalty=val.get("armor_check_penalty", 0),
        arcane_spell_failure=val.get("arcane_spell_failure", 0),
        speed_30=val.get("speed_30", 30),
        speed_20=val.get("speed_20", 20),
        weight=float(val.get("weight", 0)),
        cost_gp=val.get("cost_gp", 0),
        special=val.get("special", ""),
    )


converter.register_structure_hook(
    ArmorDefinition,
    _structure_armor_definition,
)

# -------------------------------------------------------
# WeaponDefinition: weight float, is_ranged bool
# -------------------------------------------------------


def _structure_weapon_definition(val: object, _: type) -> WeaponDefinition:
    if not isinstance(val, dict):
        msg = f"Cannot structure {type(val)} as WeaponDefinition"
        raise TypeError(msg)
    _forbid_extra(val, WeaponDefinition, val.get("name", "?"))
    return WeaponDefinition(
        name=val["name"],
        category=converter.structure(
            val.get("category", "simple"),
            WeaponCategory,
        ),
        damage_dice=val.get("damage_dice", "1d4"),
        critical_range=val.get("critical_range", 20),
        critical_multiplier=val.get("critical_multiplier", 2),
        damage_type=val.get("damage_type", ""),
        range_increment=val.get("range_increment", 0),
        weight=float(val.get("weight", 0)),
        cost_gp=val.get("cost_gp", 0),
        is_ranged=bool(val.get("is_ranged", False)),
        special=val.get("special", ""),
    )


converter.register_structure_hook(
    WeaponDefinition,
    _structure_weapon_definition,
)

# -------------------------------------------------------
# SkillDefinition: straightforward frozen dataclass
# -------------------------------------------------------


def _structure_skill_definition(val: object, _: type) -> SkillDefinition:
    if not isinstance(val, dict):
        msg = f"Cannot structure {type(val)} as SkillDefinition"
        raise TypeError(msg)
    _forbid_extra(val, SkillDefinition, val.get("name", "?"))
    return SkillDefinition(
        name=val["name"],
        key=val["key"],
        ability=val["ability"],
        trained_only=bool(val.get("trained_only", False)),
        armor_check=bool(val.get("armor_check", False)),
        synergies=val.get("synergies", []),
        description=val.get("description", ""),
    )


converter.register_structure_hook(
    SkillDefinition,
    _structure_skill_definition,
)

# -------------------------------------------------------
# SpellEntry: straightforward frozen dataclass
# -------------------------------------------------------


def _structure_spell_entry(val: object, _: type) -> SpellEntry:
    if not isinstance(val, dict):
        msg = f"Cannot structure {type(val)} as SpellEntry"
        raise TypeError(msg)
    _forbid_extra(val, SpellEntry, val.get("name", "?"))
    level_raw = val.get("level", {})
    if isinstance(level_raw, dict):
        level = {str(k): int(v) for k, v in level_raw.items()}
    else:
        level = {}
    mew = val.get("mutually_exclusive_with", [])
    return SpellEntry(
        name=val["name"],
        school=val.get("school", ""),
        subschool=val.get("subschool", ""),
        descriptor=val.get("descriptor", ""),
        level=level,
        casting_time=val.get("casting_time", ""),
        range=val.get("range", ""),
        duration=val.get("duration", ""),
        saving_throw=val.get("saving_throw", ""),
        spell_resistance=val.get("spell_resistance", ""),
        description=val.get("description", ""),
        source_book=val.get("source_book", "SRD"),
        effects=val.get("effects", []),
        note=val.get("note", ""),
        requires_caster_level=bool(val.get("requires_caster_level", False)),
        mutually_exclusive_with=mew,
        condition_key=val.get("condition_key", ""),
        applies_condition=val.get("applies_condition", ""),
    )


converter.register_structure_hook(
    SpellEntry,
    _structure_spell_entry,
)

# -------------------------------------------------------
# RaceAbilityMod: {ability, value, bonus_type}
# -------------------------------------------------------


def _structure_race_ability_mod(val: object, _: type) -> RaceAbilityMod:
    if isinstance(val, RaceAbilityMod):
        return val
    if not isinstance(val, dict):
        msg = f"Expected dict for RaceAbilityMod, got {type(val)}"
        raise TypeError(msg)
    _forbid_extra(val, RaceAbilityMod, "ability_modifier")
    bt_str = val.get("bonus_type", "untyped")
    try:
        bt = BonusType(bt_str)
    except ValueError:
        bt = BonusType.UNTYPED
    return RaceAbilityMod(
        ability=val["ability"],
        value=int(val["value"]),
        bonus_type=bt,
    )


converter.register_structure_hook(
    RaceAbilityMod,
    _structure_race_ability_mod,
)

# -------------------------------------------------------
# RaceDefinition
# -------------------------------------------------------


def _structure_race_definition(val: object, _: type) -> RaceDefinition:
    if not isinstance(val, dict):
        msg = f"Expected dict for RaceDefinition, got {type(val)}"
        raise TypeError(msg)
    _forbid_extra(val, RaceDefinition, val.get("name", "?"))
    return RaceDefinition(
        name=val["name"],
        source_book=val.get("source_book", "PHB"),
        creature_type=val.get("creature_type", "Humanoid"),
        subtypes=val.get("subtypes", []),
        size=val.get("size", "Medium"),
        base_speed=int(val.get("base_speed", 30)),
        ability_modifiers=[
            converter.structure(am, RaceAbilityMod)
            for am in val.get("ability_modifiers", [])
        ],
        favored_class=val.get("favored_class", "any"),
        la=int(val.get("la", 0)),
        racial_traits=val.get("racial_traits", []),
        languages_auto=val.get("languages_auto", []),
        languages_bonus=val.get("languages_bonus", []),
        weapon_familiarity=val.get("weapon_familiarity", []),
        low_light_vision=bool(val.get("low_light_vision", False)),
        darkvision=int(val.get("darkvision", 0)),
    )


converter.register_structure_hook(
    RaceDefinition,
    _structure_race_definition,
)

# -------------------------------------------------------
# ConditionDefinition: frozen dataclass
# -------------------------------------------------------


def _structure_condition_definition(
    val: object,
    _: type,
) -> ConditionDefinition:
    if not isinstance(val, dict):
        msg = f"Cannot structure {type(val)} as ConditionDefinition"
        raise TypeError(msg)
    _forbid_extra(
        val,
        ConditionDefinition,
        val.get("name", "?"),
    )
    return ConditionDefinition(
        name=val["name"],
        note=val.get("note", ""),
        effects=val.get("effects", []),
        source_book=val.get("source_book", "SRD"),
        requires_caster_level=bool(val.get("requires_caster_level", False)),
    )


converter.register_structure_hook(
    ConditionDefinition,
    _structure_condition_definition,
)

# -------------------------------------------------------
# MagicItemDefinition: frozen dataclass
# -------------------------------------------------------


def _structure_magic_item_definition(
    val: object,
    _: type,
) -> MagicItemDefinition:
    if not isinstance(val, dict):
        msg = f"Cannot structure {type(val)} as MagicItemDefinition"
        raise TypeError(msg)
    _forbid_extra(
        val,
        MagicItemDefinition,
        val.get("name", "?"),
    )
    return MagicItemDefinition(
        name=val["name"],
        note=val.get("note", ""),
        effects=val.get("effects", []),
        source_book=val.get("source_book", "SRD"),
        slot=val.get("slot", ""),
        cost_gp=int(val.get("cost_gp", 0)),
    )


converter.register_structure_hook(
    MagicItemDefinition,
    _structure_magic_item_definition,
)
