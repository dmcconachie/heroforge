"""
rules/schema.py
---------------
Central cattrs converter for YAML -> dataclass
structuring.

All type hooks and ``forbid_extra_keys`` config
live here. Loaders call
``converter.structure(decl, SomeClass)`` instead
of manually extracting fields.

Public API:
  converter  -- pre-configured cattrs.Converter
"""

from __future__ import annotations

from enum import StrEnum

import cattrs
from cattrs.gen import (
    make_dict_structure_fn,
    make_dict_unstructure_fn,
    override,
)

from heroforge.engine.acfs import AcfDefinition
from heroforge.engine.bonus import BonusType
from heroforge.engine.classes import (
    ClassDefinition,
    ClassFeature,
    SpellcastingInfo,
)
from heroforge.engine.deities import DeityDefinition
from heroforge.engine.domains import DomainDefinition, DomainResource
from heroforge.engine.enums import Ability, Alignment
from heroforge.engine.equipment import (
    ArmorDefinition,
    DamageType,
    WeaponDefinition,
)
from heroforge.engine.persistence import (
    ArmorSlotEntry,
    CharLevelEntry,
)
from heroforge.engine.sheet_schema import (
    AbilityEntry,
    ArmorDisplay,
    Breakdown,
    CarryingCapacity,
    ClassFeatureEntry,
    CombatSection,
    DomainEntry,
    FeatureUses,
    Iteratives,
    ResourceEntry,
    Sheet,
    SheetIdentity,
    SkillEntry,
    SpellcastingEntry,
    WeaponDisplay,
)
from heroforge.engine.sheet_schema import (
    EquipmentSection as SheetEquipmentSection,
)
from heroforge.engine.skills import SkillDefinition
from heroforge.engine.spells import SpellEntry
from heroforge.rules.known import KnownMaterial

converter = cattrs.Converter(forbid_extra_keys=True)


# ---------------------------------------------------
# Enums: cattrs handles string -> enum by value
# automatically with forbid_extra_keys=True.
# No custom hooks needed.
# ---------------------------------------------------

# ---------------------------------------------------
# Simple dataclasses: cattrs auto-structures these
# with forbid_extra_keys. No hooks needed for:
#   ConditionDefinition, MagicItemDefinition,
#   RaceAbilityMod, RaceDefinition, SaveProgressions
# ---------------------------------------------------

# ---------------------------------------------------
# SkillDefinition: ability "none" → None,
# otherwise Ability enum.
# ---------------------------------------------------


def _structure_ability_or_none(v: object, _: type) -> Ability | None:
    if v is None or v == "none":
        return None
    return Ability(v)


converter.register_structure_hook(
    SkillDefinition,
    make_dict_structure_fn(
        SkillDefinition,
        converter,
        ability=override(
            struct_hook=_structure_ability_or_none,
        ),
    ),
)

# ---------------------------------------------------
# float coercion: ArmorDefinition.weight,
# WeaponDefinition.weight
# ---------------------------------------------------

converter.register_structure_hook(
    ArmorDefinition,
    make_dict_structure_fn(
        ArmorDefinition,
        converter,
        weight=override(struct_hook=lambda v, _: float(v)),
    ),
)

# DamageType | str: pass through as-is.


def _structure_damage_type_or_str(val: object, _: type) -> DamageType | str:
    if isinstance(val, DamageType):
        return val
    if isinstance(val, str) and val:
        try:
            return DamageType(val)
        except ValueError:
            return val
    return str(val) if val is not None else ""


converter.register_structure_hook(
    DamageType | str,
    _structure_damage_type_or_str,
)

converter.register_structure_hook(
    WeaponDefinition,
    make_dict_structure_fn(
        WeaponDefinition,
        converter,
        weight=override(struct_hook=lambda v, _: float(v)),
    ),
)

# ---------------------------------------------------
# ClassFeature: effects and mutually_exclusive_with
# are tuples in the dataclass but lists in YAML.
# ---------------------------------------------------

converter.register_structure_hook(
    ClassFeature,
    make_dict_structure_fn(
        ClassFeature,
        converter,
        effects=override(struct_hook=lambda v, _: tuple(v or [])),
        mutually_exclusive_with=override(
            struct_hook=lambda v, _: tuple(v or [])
        ),
    ),
)

# ---------------------------------------------------
# SpellcastingInfo | None: null -> None
# ---------------------------------------------------


def _structure_spellcasting(val: object, _: type) -> SpellcastingInfo | None:
    if val is None:
        return None
    if isinstance(val, SpellcastingInfo):
        return val
    if isinstance(val, dict):
        return converter.structure(val, SpellcastingInfo)
    return None


converter.register_structure_hook(
    SpellcastingInfo | None,
    _structure_spellcasting,
)

# ---------------------------------------------------
# ClassDefinition: entry_prerequisites and
# ongoing_prerequisites are raw dicts (Any) that
# pass through for the loader to interpret.
# ---------------------------------------------------

converter.register_structure_hook(
    ClassDefinition,
    make_dict_structure_fn(
        ClassDefinition,
        converter,
        entry_prerequisites=override(struct_hook=lambda v, _: v),
        ongoing_prerequisites=override(struct_hook=lambda v, _: v),
    ),
)

# ---------------------------------------------------
# DomainDefinition: domain_spells keys are ints
# but YAML loads them as ints already. The only
# issue is that cattrs expects dict[int, str] and
# YAML gives dict[int, str] — this works. But we
# need a hook because the dataclass has only 2
# fields and forbid_extra_keys would reject the
# name field injected by the loader.
# ---------------------------------------------------


_ACF_KEYS = frozenset(
    {
        "name",
        "source_book",
        "classes",
        "levels",
        "requires",
        "replaces",
        "grants",
        "note",
    }
)


def _structure_acf(val: object, _: type) -> AcfDefinition:
    if not isinstance(val, dict):
        msg = f"Cannot structure {type(val)} as AcfDefinition"
        raise TypeError(msg)
    unknown = sorted(set(val) - _ACF_KEYS)
    if unknown:
        msg = f"Unknown ACF key(s): {', '.join(unknown)}"
        raise ValueError(msg)
    return AcfDefinition(
        name=str(val["name"]),
        source_book=str(val.get("source_book", "")),
        classes=tuple(val.get("classes", ())),
        levels=tuple(int(x) for x in val.get("levels", ())),
        requires=dict(val.get("requires", {})),
        replaces=dict(val.get("replaces", {})),
        grants=dict(val.get("grants", {})),
        note=str(val.get("note", "")),
    )


converter.register_structure_hook(AcfDefinition, _structure_acf)


_DOMAIN_KEYS = frozenset(
    {
        "name",
        "granted_power",
        "domain_spells",
        "class_skills",
        "resource",
    }
)
_RESOURCE_KEYS = frozenset({"name", "max_formula", "unit", "effects"})


def _structure_domain(val: object, _: type) -> DomainDefinition:
    if not isinstance(val, dict):
        msg = f"Cannot structure {type(val)} as DomainDefinition"
        raise TypeError(msg)
    # This hook bypasses the converter's forbid_extra_keys, so it
    # must reject unknown keys itself — otherwise a typo in
    # domains.yaml is silently dropped.
    unknown = sorted(set(val) - _DOMAIN_KEYS)
    if unknown:
        msg = f"Unknown domain key(s): {', '.join(unknown)}"
        raise ValueError(msg)
    spells_raw = val.get("domain_spells", {})
    domain_spells = {int(k): str(v) for k, v in spells_raw.items()}
    return DomainDefinition(
        name=val["name"],
        granted_power=val.get("granted_power", ""),
        domain_spells=domain_spells,
        class_skills=list(val.get("class_skills", [])),
        resource=_structure_domain_resource(val.get("resource")),
    )


def _structure_domain_resource(raw: object) -> DomainResource | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        msg = f"Domain resource must be a mapping, got {type(raw)}"
        raise TypeError(msg)
    unknown = sorted(set(raw) - _RESOURCE_KEYS)
    if unknown:
        msg = f"Unknown domain resource key(s): {', '.join(unknown)}"
        raise ValueError(msg)
    return DomainResource(
        name=str(raw["name"]),
        max_formula=str(raw.get("max_formula", "1")),
        unit=str(raw.get("unit", "use")),
        effects=tuple(raw.get("effects", ())),
    )


converter.register_structure_hook(
    DomainDefinition,
    _structure_domain,
)


# ---------------------------------------------------
# DeityDefinition: name is injected by the loader and
# alignment is an Alignment enum; structure explicitly.
# ---------------------------------------------------


def _structure_deity(val: object, _: type) -> DeityDefinition:
    if not isinstance(val, dict):
        msg = f"Cannot structure {type(val)} as DeityDefinition"
        raise TypeError(msg)
    return DeityDefinition(
        name=val["name"],
        alignment=Alignment(val["alignment"]),
        favored_weapon=val.get("favored_weapon", ""),
        domains=list(val.get("domains", [])),
    )


converter.register_structure_hook(
    DeityDefinition,
    _structure_deity,
)

# ---------------------------------------------------
# SpellEntry: level dict needs str keys coerced,
# and effects/mutually_exclusive_with need defaults.
# ---------------------------------------------------

converter.register_structure_hook(
    SpellEntry,
    make_dict_structure_fn(
        SpellEntry,
        converter,
        level=override(
            struct_hook=lambda v, _: (
                {str(k): int(val) for k, val in v.items()}
                if isinstance(v, dict)
                else {}
            ),
        ),
    ),
)


# ---------------------------------------------------
# Character YAML schema hooks
# ---------------------------------------------------

# CharLevelEntry: YAML "class" → Python "class_".
converter.register_structure_hook(
    CharLevelEntry,
    make_dict_structure_fn(
        CharLevelEntry,
        converter,
        class_=override(rename="class"),
    ),
)

# ArmorSlotEntry | None: empty dict = no item.


def _structure_armor_slot(val: object, _: type) -> ArmorSlotEntry | None:
    if val is None:
        return None
    if isinstance(val, ArmorSlotEntry):
        return val
    if isinstance(val, dict):
        if not val:
            return None
        return converter.structure(val, ArmorSlotEntry)
    return None


converter.register_structure_hook(
    ArmorSlotEntry | None,
    _structure_armor_slot,
)

# KnownMaterial | None: absent = None.


def _structure_material(val: object, _: type) -> KnownMaterial | None:
    if val is None or val == "":
        return None
    if isinstance(val, KnownMaterial):
        return val
    return KnownMaterial(val)


converter.register_structure_hook(
    KnownMaterial | None,
    _structure_material,
)

# Ability | None: absent = None.


def _structure_ability_or_none(val: object, _: type) -> Ability | None:
    if val is None or val == "":
        return None
    if isinstance(val, Ability):
        return val
    return Ability(val)


converter.register_structure_hook(
    Ability | None,
    _structure_ability_or_none,
)


# ---------------------------------------------------
# Unstructure hooks (CharFile → plain dict for YAML)
# ---------------------------------------------------

# StrEnums → plain str for YAML output.
converter.register_unstructure_hook(
    StrEnum,
    lambda v: str(v),
)

# CharLevelEntry: Python "class_" → YAML "class".
converter.register_unstructure_hook(
    CharLevelEntry,
    make_dict_unstructure_fn(
        CharLevelEntry,
        converter,
        class_=override(rename="class"),
    ),
)

# CharFile: use converter.unstructure() directly.
# The default unstructure for dataclasses works;
# StrEnum hook handles all enum→str conversion.

# FeatEntry: no special hook needed beyond
# forbid_extra_keys, but cattrs needs to know
# how to structure KnownFeat from strings
# (handled automatically by StrEnum).


# ---------------------------------------------------
# BonusType (plain enum.Enum, not StrEnum): use
# its .value string for YAML output.
# ---------------------------------------------------
converter.register_unstructure_hook(
    BonusType,
    lambda v: v.value,
)


# ---------------------------------------------------
# Sheet dataclasses: omit fields equal to their
# default value. Gives compact YAML (optional
# level_bumps, inherent, size, base, etc. disappear
# when unset) while required fields (totals, scores)
# are always emitted.
# ---------------------------------------------------


def _register_sheet_omit_default(cls: type) -> None:
    converter.register_unstructure_hook(
        cls,
        make_dict_unstructure_fn(
            cls,
            converter,
            _cattrs_omit_if_default=True,
        ),
    )


# Order matters: cattrs codegens the hook for a
# container class by inspecting what's already
# registered for its fields, so leaf dataclasses
# must be registered before the aggregates that
# embed them.
for _sheet_cls in (
    AbilityEntry,
    Breakdown,
    SkillEntry,
    SpellcastingEntry,
    DomainEntry,
    ResourceEntry,
    FeatureUses,
    ClassFeatureEntry,
    ArmorDisplay,
    WeaponDisplay,
    SheetIdentity,
    Iteratives,
    CarryingCapacity,
    SheetEquipmentSection,
    CombatSection,
    Sheet,
):
    _register_sheet_omit_default(_sheet_cls)
