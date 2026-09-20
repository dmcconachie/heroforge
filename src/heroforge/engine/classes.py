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
from typing import Any

from heroforge.engine.enums import Ability

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
class Proficiencies:
    """
    What one source (a class, a race) grants proficiency with.

    ``weapons`` names whole categories; ``weapon_names`` names
    individual weapons, which is how the wizard's short list
    and the monk's special weapons are expressed.

    This lives here rather than in engine/proficiency.py so
    that module can stay a consumer of the rules registry
    without ClassDefinition having to import it. See
    docs/plans/engine-rules-import-cycle.md.
    """

    armor: tuple[str, ...] = ()
    shields: bool = False
    tower_shields: bool = False
    weapons: tuple[str, ...] = ()
    weapon_names: tuple[str, ...] = ()
    # Exotic weapons this source lets the character treat as
    # martial (dwarven waraxe for a dwarf). Not the same rule
    # as proficiency: familiarity only reclassifies, so a
    # character still needs martial proficiency to use it.
    weapon_familiarity: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClassFeature:
    """One class feature at a specific level."""

    level: int
    feature: str
    description: str
    # Feats this feature confers (e.g. the Swashbuckler's
    # Weapon Finesse). Materialised as derived feats, so they
    # count for prerequisites and per-weapon lines but are never
    # written to the character file.
    grants_feats: tuple[dict, ...] = ()
    buff_name: str = ""
    effects: tuple[dict, ...] = ()
    note: str = ""
    requires_caster_level: bool = False
    mutually_exclusive_with: tuple[str, ...] = ()
    # Gate keys (KnownCoreGate values) governing when this
    # feature's effects contribute. Empty = unconditional.
    # Only meaningful for passive features (buff_name=="")
    # today.
    gate: tuple[str, ...] = ()
    # Uses per day: {"max": "<formula>", "unit": "use"}.
    # The formula is evaluated per character, so a feature
    # that scales with level or an ability has one entry
    # rather than one per level.
    uses: dict[str, str] | None = None
    # Named numbers the player needs at the table, as
    # formulas: {"attack": "max(0, cha_mod)", "damage":
    # "paladin_level"}.
    values: dict[str, str] = field(default_factory=dict)
    # Damage reduction, resistance to energy and immunity.
    # See engine/defenses.py for the shape.
    defenses: dict = field(default_factory=dict)
    # The feature attaches to one thing the character picks.
    # "weapon" is the only kind so far: an occult slayer bonds
    # one weapon. The designation is written on the weapon
    # slot, where "which one" is unambiguous even between two
    # identical daggers.
    designates: str = ""
    # A condition the engine cannot evaluate because it is
    # about the *target*, not the character — insightful
    # strike only applies to creatures that can be critically
    # hit. Recorded as text so the sheet can say so.
    when: str = ""


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
    # Weapon and armor proficiency the class grants. None means
    # "not stated": base classes must declare a block, because
    # an omission would silently make every character of that
    # class nonproficient with everything.
    proficiencies: Proficiencies | None = None
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
