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

import cattrs
from cattrs.gen import make_dict_structure_fn, override

from heroforge.engine.classes import (
    ClassDefinition,
    ClassFeature,
    SpellcastingInfo,
)
from heroforge.engine.domains import DomainDefinition
from heroforge.engine.equipment import (
    ArmorDefinition,
    WeaponDefinition,
)
from heroforge.engine.persistence import (
    ArmorSlotEntry,
    CharLevelEntry,
)
from heroforge.engine.spells import SpellEntry

converter = cattrs.Converter(forbid_extra_keys=True)


# ---------------------------------------------------
# Enums: cattrs handles string -> enum by value
# automatically with forbid_extra_keys=True.
# No custom hooks needed.
# ---------------------------------------------------

# ---------------------------------------------------
# Simple dataclasses: cattrs auto-structures these
# with forbid_extra_keys. No hooks needed for:
#   SkillDefinition, ConditionDefinition,
#   MagicItemDefinition, RaceAbilityMod,
#   RaceDefinition, SaveProgressions
# ---------------------------------------------------

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


def _structure_domain(val: object, _: type) -> DomainDefinition:
    if not isinstance(val, dict):
        msg = f"Cannot structure {type(val)} as DomainDefinition"
        raise TypeError(msg)
    spells_raw = val.get("domain_spells", {})
    domain_spells = {int(k): str(v) for k, v in spells_raw.items()}
    return DomainDefinition(
        name=val["name"],
        granted_power=val.get("granted_power", ""),
        domain_spells=domain_spells,
    )


converter.register_structure_hook(
    DomainDefinition,
    _structure_domain,
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

# CharLevelEntry: YAML uses "class" but Python uses
# "class_" (reserved word).
converter.register_structure_hook(
    CharLevelEntry,
    make_dict_structure_fn(
        CharLevelEntry,
        converter,
        class_=override(rename="class"),
    ),
)

# EquipmentSection: armor/shield are optional
# (None if absent). cattrs needs a hint for
# ArmorSlotEntry | None.


def _structure_armor_slot(val: object, _: type) -> ArmorSlotEntry | None:
    if val is None:
        return None
    if isinstance(val, ArmorSlotEntry):
        return val
    if isinstance(val, dict):
        if not val:
            return None  # empty dict = no item
        return converter.structure(val, ArmorSlotEntry)
    return None


converter.register_structure_hook(
    ArmorSlotEntry | None,
    _structure_armor_slot,
)
