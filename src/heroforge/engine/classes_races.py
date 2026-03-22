"""
engine/classes_races.py
-----------------------
ClassDefinition and RaceDefinition data models, plus helper functions
for computing BAB/save progressions from class data.

These models are populated by ClassesLoader and RacesLoader (in loader.py)
and used by the Character to set up class levels and racial bonuses.

Public API:
  BABProgression        — enum: FULL / MEDIUM / POOR
  SaveProgression       — enum: GOOD / POOR
  ClassFeature          — one feature granted at a specific level
  SpellcastingInfo      — spellcasting metadata for a class
  ClassDefinition       — complete class description
  ClassRegistry         — lookup by name
  RaceDefinition        — complete race description
  RaceRegistry          — lookup by name
  bab_at_level()        — compute BAB for a class at a given level
  save_at_level()       — compute base save bonus at a given level
  apply_race()          — wire racial ability bonuses into Character
  remove_race()         — undo racial ability bonuses
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from heroforge.engine.bonus import BonusEntry, BonusType

if TYPE_CHECKING:
    from typing import Any

    from heroforge.engine.character import (
        Character,
        ClassLevel,
    )


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class BABProgression(enum.Enum):
    FULL = "full"  # +1 per level  (Fighter, Paladin, etc.)
    MEDIUM = "medium"  # +3/4 per level (Cleric, Rogue, etc.)
    POOR = "poor"  # +1/2 per level (Wizard, Sorcerer, etc.)


class SaveProgression(enum.Enum):
    GOOD = "good"  # base = 2 + floor(level / 2)
    POOR = "poor"  # base = floor(level / 3)


# ---------------------------------------------------------------------------
# Progression helpers
# ---------------------------------------------------------------------------


def bab_at_level(progression: BABProgression, level: int) -> int:
    """
    Compute cumulative BAB for a single class at a given level.

    Full:   1 per level → level
    Medium: floor(level * 3 / 4)
    Poor:   floor(level / 2)
    """
    if level <= 0:
        return 0
    if progression == BABProgression.FULL:
        return level
    if progression == BABProgression.MEDIUM:
        return math.floor(level * 3 / 4)
    return math.floor(level / 2)  # POOR


def save_at_level(progression: SaveProgression, level: int) -> int:
    """
    Compute base save bonus for a single class at a given level.

    Good: 2 + floor(level / 2)
    Poor: floor(level / 3)
    """
    if level <= 0:
        return 0
    if progression == SaveProgression.GOOD:
        return 2 + math.floor(level / 2)
    return math.floor(level / 3)  # POOR


# ---------------------------------------------------------------------------
# ClassFeature
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassFeature:
    """One class feature granted at a specific level."""

    level: int
    feature: str  # machine key (e.g. "sneak_attack")
    description: str  # human-readable display text


# ---------------------------------------------------------------------------
# SpellcastingInfo
# ---------------------------------------------------------------------------


@dataclass
class SpellcastingInfo:
    """Spellcasting metadata for a class."""

    cast_type: str  # "arcane" or "divine"
    stat: str  # "int", "wis", or "cha"
    preparation: str  # "prepared" or "spontaneous"
    max_spell_level: int  # 4 for Paladin/Ranger, 9 for full casters
    starts_at_level: int  # 1 for most, 4 for Paladin/Ranger


# ---------------------------------------------------------------------------
# ClassDefinition
# ---------------------------------------------------------------------------


@dataclass
class ClassDefinition:
    """
    Complete description of a character class.

    Used by the character loader to populate ClassLevel contributions
    (BAB, save bonuses) from just the class name and level.
    """

    name: str
    source_book: str = "PHB"
    hit_die: int = 8  # numeric die size
    bab_progression: BABProgression = BABProgression.MEDIUM
    fort_progression: SaveProgression = SaveProgression.POOR
    ref_progression: SaveProgression = SaveProgression.POOR
    will_progression: SaveProgression = SaveProgression.POOR
    skills_per_level: int = 2
    class_skills: list[str] = field(default_factory=list)
    spellcasting: SpellcastingInfo | None = None
    class_features: list[ClassFeature] = field(default_factory=list)
    favored_by: list[str] = field(default_factory=list)
    # Prestige class fields
    max_level: int = 20
    is_prestige: bool = False
    entry_prerequisites: Any = None
    ongoing_prerequisites: Any = None

    def bab_contribution(self, level: int) -> int:
        return bab_at_level(self.bab_progression, level)

    def fort_contribution(self, level: int) -> int:
        return save_at_level(self.fort_progression, level)

    def ref_contribution(self, level: int) -> int:
        return save_at_level(self.ref_progression, level)

    def will_contribution(self, level: int) -> int:
        return save_at_level(self.will_progression, level)

    def make_class_level(
        self, level: int, hp_rolls: list[int] | None = None
    ) -> ClassLevel:
        """Build a ClassLevel object for this class at the given level."""
        from heroforge.engine.character import ClassLevel

        if hp_rolls is None:
            # Default to max HP for now; real chargen rolls dice
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
        """Return features gained exactly at the given level."""
        return [f for f in self.class_features if f.level == level]

    def features_up_to_level(self, level: int) -> list[ClassFeature]:
        """Return all features gained up to and including the given level."""
        return [f for f in self.class_features if f.level <= level]


# ---------------------------------------------------------------------------
# ClassRegistry
# ---------------------------------------------------------------------------


class ClassRegistry:
    """Central lookup for ClassDefinitions."""

    def __init__(self) -> None:
        self._defs: dict[str, ClassDefinition] = {}

    def register(self, defn: ClassDefinition, overwrite: bool = False) -> None:
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
            raise KeyError(f"No ClassDefinition registered for {name!r}.")
        return defn

    def all_names(self) -> list[str]:
        return sorted(self._defs.keys())

    def __len__(self) -> int:
        return len(self._defs)

    def __contains__(self, name: str) -> bool:
        return name in self._defs


# ---------------------------------------------------------------------------
# RaceDefinition
# ---------------------------------------------------------------------------


@dataclass
class RaceAbilityMod:
    """One racial ability score modifier."""

    ability: str  # "str", "dex", etc.
    value: int
    bonus_type: BonusType = BonusType.UNTYPED


@dataclass
class RaceDefinition:
    """
    Complete description of a playable race.

    Ability modifiers are applied to the character's stat pools when
    apply_race() is called.  Size bonuses (Small vs Medium) are handled
    by the size_mod pool.
    """

    name: str
    source_book: str = "PHB"
    creature_type: str = "Humanoid"
    subtypes: list[str] = field(default_factory=list)
    size: str = "Medium"  # Small | Medium | Large
    base_speed: int = 30
    ability_modifiers: list[RaceAbilityMod] = field(default_factory=list)
    favored_class: str = "any"
    la: int = 0
    racial_traits: list[str] = field(default_factory=list)
    languages_auto: list[str] = field(default_factory=list)
    languages_bonus: list[str] = field(default_factory=list)
    weapon_familiarity: list[str] = field(default_factory=list)
    low_light_vision: bool = False
    darkvision: int = 0  # feet; 0 = none

    @property
    def size_modifier(self) -> int:
        """Attack/AC size modifier: Small=+1, Medium=0, Large=-1."""
        if self.size == "Small":
            return 1
        if self.size == "Large":
            return -1
        return 0

    @property
    def hide_modifier(self) -> int:
        """Hide check size modifier: Small=+4, Large=-4."""
        if self.size == "Small":
            return 4
        if self.size == "Large":
            return -4
        return 0


# ---------------------------------------------------------------------------
# RaceRegistry
# ---------------------------------------------------------------------------


class RaceRegistry:
    """Central lookup for RaceDefinitions."""

    def __init__(self) -> None:
        self._defs: dict[str, RaceDefinition] = {}

    def register(self, defn: RaceDefinition, overwrite: bool = False) -> None:
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
            raise KeyError(f"No RaceDefinition registered for {name!r}.")
        return defn

    def all_names(self) -> list[str]:
        return sorted(self._defs.keys())

    def __len__(self) -> int:
        return len(self._defs)

    def __contains__(self, name: str) -> bool:
        return name in self._defs


# ---------------------------------------------------------------------------
# apply_race / remove_race
# ---------------------------------------------------------------------------

_RACE_SOURCE_KEY = "race:ability_mods"
_RACE_SPEED_KEY = "race:speed"


def apply_race(defn: RaceDefinition, character: "Character") -> None:
    """
    Apply a race's ability score modifiers and base speed to a Character.

    Also sets character.race and configures the base speed.
    Idempotent: calling again with the same race overwrites (no doubling).
    """
    character.race = defn.name

    # --- Ability score bonuses -------------------------------------------
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

    # --- Base speed ------------------------------------------------------
    # Store the race's base speed on the character for the speed node's
    # compute delegate to pick up.
    character._race_base_speed = defn.base_speed
    character._graph.invalidate_pool("speed")
    character._graph.invalidate("speed")

    # --- Creature type and subtypes --------------------------------------
    # Only set if not already overridden by a template
    if not getattr(character, "_creature_type_override", None):
        character._race_creature_type = defn.creature_type

    existing_subs = list(getattr(character, "_race_subtypes", []))
    for sub in defn.subtypes:
        if sub not in existing_subs:
            existing_subs.append(sub)
    character._race_subtypes = existing_subs

    # Notify affected stats
    affected = {
        f"{ab}_score" for ab in ("str", "dex", "con", "int", "wis", "cha")
    }
    affected.add("speed")
    character._notify(affected)


def remove_race(defn: RaceDefinition, character: "Character") -> None:
    """
    Remove a race's ability score modifiers from a Character.
    Idempotent: safe to call if the race isn't applied.
    """
    for mod in defn.ability_modifiers:
        pool_key = f"{mod.ability}_score"
        pool = character.get_pool(pool_key)
        if pool is not None:
            pool.clear_source(_RACE_SOURCE_KEY)
            character._graph.invalidate_pool(pool_key)

    character._race_base_speed = 30  # reset to default
    character._graph.invalidate("speed")
    character.race = ""

    affected = {
        f"{ab}_score" for ab in ("str", "dex", "con", "int", "wis", "cha")
    }
    affected.add("speed")
    character._notify(affected)


# ---------------------------------------------------------------------------
# YAML builders
# ---------------------------------------------------------------------------


def build_class_from_yaml(decl: dict) -> ClassDefinition:
    """Build a ClassDefinition from a YAML-parsed dict."""

    # Parse hit die: "d8" → 8
    hit_die_str = str(decl.get("hit_die", "d8"))
    hit_die = int(hit_die_str.replace("d", "").strip())

    bab_str = decl.get("bab_progression", "medium")
    bab = BABProgression(bab_str)

    saves = decl.get("save_progressions", {})
    fort = SaveProgression(saves.get("fort", "poor"))
    ref = SaveProgression(saves.get("ref", "poor"))
    will = SaveProgression(saves.get("will", "poor"))

    spellcasting = None
    sc = decl.get("spellcasting")
    if sc:
        spellcasting = SpellcastingInfo(
            cast_type=sc.get("type", "arcane"),
            stat=sc.get("stat", "int"),
            preparation=sc.get("preparation", "prepared"),
            max_spell_level=int(sc.get("max_spell_level", 9)),
            starts_at_level=int(sc.get("starts_at_level", 1)),
        )

    features = [
        ClassFeature(
            level=f["level"],
            feature=f["feature"],
            description=f.get("description", ""),
        )
        for f in decl.get("class_features", [])
    ]

    return ClassDefinition(
        name=decl["name"],
        source_book=decl.get("source_book", "PHB"),
        hit_die=hit_die,
        bab_progression=bab,
        fort_progression=fort,
        ref_progression=ref,
        will_progression=will,
        skills_per_level=int(decl.get("skills_per_level", 2)),
        class_skills=decl.get("class_skills", []),
        spellcasting=spellcasting,
        class_features=features,
        favored_by=decl.get("favored_by", []),
        max_level=int(decl.get("max_level", 20)),
        is_prestige=bool(decl.get("is_prestige", False)),
    )


def build_race_from_yaml(decl: dict) -> RaceDefinition:
    """Build a RaceDefinition from a YAML-parsed dict."""

    ability_mods = []
    for amod in decl.get("ability_modifiers", []):
        bt_str = amod.get("bonus_type", "untyped")
        try:
            bt = BonusType(bt_str)
        except ValueError:
            bt = BonusType.UNTYPED
        ability_mods.append(
            RaceAbilityMod(
                ability=amod["ability"],
                value=int(amod["value"]),
                bonus_type=bt,
            )
        )

    languages = decl.get("languages", {})

    return RaceDefinition(
        name=decl["name"],
        source_book=decl.get("source_book", "PHB"),
        creature_type=decl.get("creature_type", "Humanoid"),
        subtypes=decl.get("subtypes", []),
        size=decl.get("size", "Medium"),
        base_speed=int(decl.get("base_speed", 30)),
        ability_modifiers=ability_mods,
        favored_class=decl.get("favored_class", "any"),
        la=int(decl.get("la", 0)),
        racial_traits=decl.get("racial_traits", []),
        languages_auto=languages.get("automatic", []),
        languages_bonus=languages.get("bonus", []),
        weapon_familiarity=decl.get("weapon_familiarity", []),
        low_light_vision=bool(decl.get("low_light_vision", False)),
        darkvision=int(decl.get("darkvision", 0)),
    )
