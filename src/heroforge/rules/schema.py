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
    SaveProgression,
    SaveProgressions,
    SpellcastingInfo,
)
from heroforge.engine.equipment import (
    ArmorCategory,
    WeaponCategory,
)
from heroforge.engine.feats import FeatKind

converter = cattrs.Converter(
    forbid_extra_keys=True,
)


def _forbid_extra(
    val: dict,
    allowed: set[str],
    label: str,
) -> None:
    """Raise if *val* has keys not in *allowed*."""
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
_CLASS_FEATURE_KEYS = {
    "level",
    "feature",
    "description",
}


def _structure_class_feature(val: object, _: type) -> ClassFeature:
    if isinstance(val, ClassFeature):
        return val
    if isinstance(val, dict):
        _forbid_extra(
            val,
            _CLASS_FEATURE_KEYS,
            "class_feature",
        )
        return ClassFeature(
            level=val["level"],
            feature=val["feature"],
            description=val.get("description", ""),
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
_CLASS_KEYS = {
    "name",
    "source_book",
    "hit_die",
    "bab_progression",
    "save_progressions",
    "skills_per_level",
    "class_skills",
    "spellcasting",
    "class_features",
    "max_level",
    "is_prestige",
    "entry_prerequisites",
    "ongoing_prerequisites",
}


def _structure_class_definition(val: object, _: type) -> ClassDefinition:
    if not isinstance(val, dict):
        msg = f"Cannot structure {type(val)} as ClassDefinition"
        raise TypeError(msg)
    _forbid_extra(val, _CLASS_KEYS, val.get("name", "?"))
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
