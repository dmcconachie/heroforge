"""
engine/classes.py
-----------------
ClassDefinition and related types for D&D 3.5e
character classes, plus BAB/save progression helpers.

Public API:
  CastType          -- enum: ARCANE / DIVINE / EITHER
  SpellPreparation  -- enum: PREPARED / SPONTANEOUS
  BABProgression    -- enum: FULL / MEDIUM / POOR
  SaveProgression   -- enum: GOOD / POOR
  SaveProgressions  -- fort/ref/will bundle
  ClassFeature      -- one feature at a specific level
  SpellcastingInfo  -- spellcasting metadata
  ClassDefinition   -- complete class description
  ClassRegistry     -- lookup by name
  bab_at_level()    -- compute BAB at a given level
  save_at_level()   -- compute base save at a level
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from heroforge.engine.character import Ability

if TYPE_CHECKING:
    from heroforge.engine.character import (
        ClassLevel,
    )


# -----------------------------------------------------------
# Enumerations
# -----------------------------------------------------------


class CastType(StrEnum):
    ARCANE = "arcane"
    DIVINE = "divine"
    EITHER = "either"


class SpellPreparation(StrEnum):
    PREPARED = "prepared"
    SPONTANEOUS = "spontaneous"


class BABProgression(enum.Enum):
    FULL = "full"
    MEDIUM = "medium"
    POOR = "poor"


class SaveProgression(enum.Enum):
    GOOD = "good"
    POOR = "poor"


# -----------------------------------------------------------
# Progression helpers
# -----------------------------------------------------------


def bab_at_level(progression: BABProgression, level: int) -> int:
    """Compute cumulative BAB for one class."""
    if level <= 0:
        return 0
    if progression == BABProgression.FULL:
        return level
    if progression == BABProgression.MEDIUM:
        return math.floor(level * 3 / 4)
    return math.floor(level / 2)


def save_at_level(progression: SaveProgression, level: int) -> int:
    """Compute base save for one class."""
    if level <= 0:
        return 0
    if progression == SaveProgression.GOOD:
        return 2 + math.floor(level / 2)
    return math.floor(level / 3)


# -----------------------------------------------------------
# ClassFeature
# -----------------------------------------------------------


@dataclass(frozen=True)
class ClassFeature:
    """One class feature at a specific level."""

    level: int
    feature: str
    description: str
    buff_name: str = ""
    effects: tuple[dict, ...] = ()
    note: str = ""
    requires_caster_level: bool = False
    mutually_exclusive_with: tuple[str, ...] = ()


# -----------------------------------------------------------
# SpellcastingInfo
# -----------------------------------------------------------


@dataclass
class SpellcastingInfo:
    """Spellcasting metadata for a class."""

    cast_type: CastType
    stat: Ability
    preparation: SpellPreparation
    max_spell_level: int  # 4 or 9
    starts_at_level: int  # 1 or 4


# -----------------------------------------------------------
# SaveProgressions
# -----------------------------------------------------------


@dataclass
class SaveProgressions:
    """Fort/Ref/Will save progression bundle."""

    fort: SaveProgression = SaveProgression.POOR
    ref: SaveProgression = SaveProgression.POOR
    will: SaveProgression = SaveProgression.POOR


# -----------------------------------------------------------
# ClassDefinition
# -----------------------------------------------------------


@dataclass
class ClassDefinition:
    """Complete description of a character class."""

    name: str
    source_book: str = "PHB"
    hit_die: int = 8
    bab_progression: BABProgression = BABProgression.MEDIUM
    save_progressions: SaveProgressions = field(
        default_factory=SaveProgressions
    )
    skills_per_level: int = 2
    class_skills: list[str] = field(default_factory=list)
    spellcasting: SpellcastingInfo | None = None
    class_features: list[ClassFeature] = field(default_factory=list)
    max_level: int = 20
    is_prestige: bool = False
    entry_prerequisites: Any = None
    ongoing_prerequisites: Any = None

    def bab_contribution(self, level: int) -> int:
        return bab_at_level(self.bab_progression, level)

    def fort_contribution(self, level: int) -> int:
        return save_at_level(self.save_progressions.fort, level)

    def ref_contribution(self, level: int) -> int:
        return save_at_level(self.save_progressions.ref, level)

    def will_contribution(self, level: int) -> int:
        return save_at_level(self.save_progressions.will, level)

    def make_class_level(
        self,
        level: int,
        hp_rolls: list[int] | None = None,
    ) -> "ClassLevel":
        from heroforge.engine.character import (
            ClassLevel,
        )

        if hp_rolls is None:
            hp_rolls = [self.hit_die] * level
        return ClassLevel(
            class_name=self.name,
            level=level,
            hp_rolls=hp_rolls,
            bab_contribution=self.bab_contribution(level),
            fort_contribution=self.fort_contribution(level),
            ref_contribution=self.ref_contribution(level),
            will_contribution=self.will_contribution(level),
        )

    def features_at_level(self, level: int) -> list[ClassFeature]:
        return [f for f in self.class_features if f.level == level]

    def features_up_to_level(self, level: int) -> list[ClassFeature]:
        return [f for f in self.class_features if f.level <= level]


# -----------------------------------------------------------
# ClassRegistry
# -----------------------------------------------------------


class ClassRegistry:
    """Central lookup for ClassDefinitions."""

    def __init__(self) -> None:
        self._defs: dict[str, ClassDefinition] = {}

    def register(
        self,
        defn: ClassDefinition,
        overwrite: bool = False,
    ) -> None:
        if defn.name in self._defs and not overwrite:
            raise ValueError(
                f"ClassDefinition {defn.name!r} already registered."
            )
        self._defs[defn.name] = defn

    def get(self, name: str) -> ClassDefinition | None:
        return self._defs.get(name)

    def require(self, name: str) -> ClassDefinition:
        defn = self._defs.get(name)
        if defn is None:
            raise KeyError(f"No ClassDefinition for {name!r}.")
        return defn

    def all_names(self) -> list[str]:
        return sorted(self._defs.keys())

    def __len__(self) -> int:
        return len(self._defs)

    def __contains__(self, name: str) -> bool:
        return name in self._defs
