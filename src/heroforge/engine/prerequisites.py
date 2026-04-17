"""
engine/prerequisites.py
-----------------------
Prerequisite checking for feats, prestige classes, and other gated options.

Design principles:
  - Prerequisites operate on *derived character state*, not raw field values.
    "Proficient with Bastard Sword" is a computed capability, not a feat check.
  - The YAML vocabulary is declarative; Python only knows how to evaluate it.
  - DM overrides short-circuit all checks — an overridden target is always
    considered AVAILABLE regardless of whether prereqs are met.
  - Prerequisite trees (feat chains) are walked to produce actionable
    "here is what you are missing" output, not just pass/fail.

Public API:
  PrereqResult        — enum: MET / UNMET / OVERRIDE
  FeatAvailability    — enum: AVAILABLE / TAKEN / OVERRIDE / UNAVAILABLE /
                               CHAIN_PARTIAL
  Prerequisite        — base class; concrete subclasses below
  PrerequisiteChecker — evaluates prerequisites against a Character
  CapabilityChecker   — resolves capability checks (proficiency, etc.)
  UnmetDetail         — structured description of an unmet prerequisite
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

from heroforge.engine.character import Ability
from heroforge.engine.classes import CastType

if TYPE_CHECKING:
    from typing import Any

    from heroforge.engine.character import Character


# ---------------------------------------------------------------------------
# Result enums
# ---------------------------------------------------------------------------


class PrereqResult(enum.Enum):
    MET = "met"
    UNMET = "unmet"
    OVERRIDE = "override"  # DM override active; treat as met


class FeatAvailability(enum.Enum):
    AVAILABLE = "available"  # all prereqs met, not yet taken
    TAKEN = "taken"  # already selected
    OVERRIDE = "override"  # DM override — show distinctly
    UNAVAILABLE = "unavailable"  # hard prereqs not met
    CHAIN_PARTIAL = "chain_partial"  # some prereq feats met, others not


# ---------------------------------------------------------------------------
# Unmet detail
# ---------------------------------------------------------------------------


@dataclass
class UnmetDetail:
    """
    Describes one unmet prerequisite in human-readable form.

    Used for tooltip text ("You need BAB +5 (have +3)") and for the
    CHAIN_PARTIAL state ("You have Point Blank Shot but not Precise Shot").
    """

    description: str
    have: str = ""  # current value, if applicable
    need: str = ""  # required value, if applicable
    is_feat_dep: bool = False  # True if this is a feat chain dependency


# ---------------------------------------------------------------------------
# Prerequisite base and concrete types
# ---------------------------------------------------------------------------


class Prerequisite:
    """
    Base class for all prerequisite types.

    Subclasses implement check(character) → (PrereqResult, list[UnmetDetail]).
    """

    def check(
        self,
        character: "Character",
        checker: "PrerequisiteChecker",
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        raise NotImplementedError


# --- Atomic prerequisites ---------------------------------------------------


@dataclass
class StatPrereq(Prerequisite):
    """character.get(stat_key) >= min_value"""

    stat_key: str
    min_value: int
    label: str = ""  # human-readable name, e.g. "BAB"

    def check(
        self,
        character: Character,
        checker: PrerequisiteChecker,
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        have = character.get(self.stat_key)
        if have >= self.min_value:
            return PrereqResult.MET, []
        display = self.label or self.stat_key
        return PrereqResult.UNMET, [
            UnmetDetail(
                description=f"{display} +{self.min_value} required",
                have=f"+{have}",
                need=f"+{self.min_value}",
            )
        ]


@dataclass
class AbilityPrereq(Prerequisite):
    """ability score >= min_value"""

    ability: Ability
    min_value: int

    def check(
        self,
        character: Character,
        checker: PrerequisiteChecker,
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        have = character.get_ability_score(self.ability)
        if have >= self.min_value:
            return PrereqResult.MET, []
        label = self.ability.upper()
        return PrereqResult.UNMET, [
            UnmetDetail(
                description=f"{label} {self.min_value} required",
                have=str(have),
                need=str(self.min_value),
            )
        ]


@dataclass
class FeatPrereq(Prerequisite):
    """Character must have the named feat."""

    feat_name: str

    def check(
        self,
        character: Character,
        checker: PrerequisiteChecker,
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        if checker.has_feat(character, self.feat_name):
            return PrereqResult.MET, []
        return PrereqResult.UNMET, [
            UnmetDetail(
                description=f"Feat: {self.feat_name}",
                is_feat_dep=True,
            )
        ]


@dataclass
class SkillPrereq(Prerequisite):
    """skill ranks >= min_ranks"""

    skill_name: str
    min_ranks: int

    def check(
        self,
        character: Character,
        checker: PrerequisiteChecker,
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        have = character.skills.get(self.skill_name, 0)
        if have >= self.min_ranks:
            return PrereqResult.MET, []
        return PrereqResult.UNMET, [
            UnmetDetail(
                description=f"{self.skill_name} {self.min_ranks} ranks",
                have=str(have),
                need=str(self.min_ranks),
            )
        ]


@dataclass
class ClassLevelPrereq(Prerequisite):
    """At least min_level levels in class_name."""

    class_name: str
    min_level: int

    def check(
        self,
        character: Character,
        checker: PrerequisiteChecker,
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        have = character.class_level_map.get(self.class_name, 0)
        if have >= self.min_level:
            return PrereqResult.MET, []
        return PrereqResult.UNMET, [
            UnmetDetail(
                description=f"{self.class_name} level {self.min_level}",
                have=str(have),
                need=str(self.min_level),
            )
        ]


@dataclass
class RacePrereq(Prerequisite):
    """Character must be one of the listed races."""

    races: list[str]

    def check(
        self,
        character: Character,
        checker: PrerequisiteChecker,
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        race = getattr(character, "race", "")
        # Also check effective race (after templates)
        eff_race = getattr(character, "_effective_race", race)
        if eff_race in self.races or race in self.races:
            return PrereqResult.MET, []
        options = " or ".join(self.races)
        return PrereqResult.UNMET, [
            UnmetDetail(
                description=f"Race: {options}",
                have=race or "Unknown",
                need=options,
            )
        ]


@dataclass
class AlignmentPrereq(Prerequisite):
    """Character alignment must be in the allowed list."""

    allowed: list[str]  # e.g. ["lawful_good", "neutral_good", "chaotic_good"]

    def check(
        self,
        character: Character,
        checker: PrerequisiteChecker,
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        alignment = getattr(character, "alignment", "")
        if alignment in self.allowed:
            return PrereqResult.MET, []
        options = " or ".join(a.replace("_", " ").title() for a in self.allowed)
        return PrereqResult.UNMET, [
            UnmetDetail(
                description=f"Alignment: {options}",
                have=alignment or "Unknown",
                need=options,
            )
        ]


@dataclass
class ProficiencyPrereq(Prerequisite):
    """
    Character must be proficient with the named weapon.
    Resolved via CapabilityChecker — proficiency can come from race,
    class, feat (EWP), or other special abilities.
    """

    weapon: str  # e.g. "Bastard Sword", "$parameter" for parameterised feats

    def check(
        self,
        character: Character,
        checker: PrerequisiteChecker,
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        weapon = self.weapon
        # Resolve parameter substitution (e.g. Weapon Focus uses the
        # feat's chosen weapon parameter)
        if weapon.startswith("$"):
            param_name = weapon[1:]
            # Resolved by caller passing context; default to no weapon
            weapon = checker._resolve_param(character, param_name) or ""

        if not weapon:
            return PrereqResult.UNMET, [
                UnmetDetail(
                    description="Proficiency with weapon (no weapon specified)"
                )
            ]

        if checker.capabilities.is_proficient(character, weapon):
            return PrereqResult.MET, []
        return PrereqResult.UNMET, [
            UnmetDetail(
                description=f"Proficiency with {weapon}",
                have="not proficient",
                need=f"proficient with {weapon}",
            )
        ]


@dataclass
class SpellcastingPrereq(Prerequisite):
    """Character must be able to cast spells of at least min_level."""

    min_level: int
    cast_type: CastType = CastType.EITHER

    def check(
        self,
        character: Character,
        checker: PrerequisiteChecker,
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        if checker.capabilities.can_cast(
            character, self.min_level, self.cast_type
        ):
            return PrereqResult.MET, []
        type_str = (
            "arcane"
            if self.cast_type == CastType.ARCANE
            else "divine"
            if self.cast_type == CastType.DIVINE
            else "arcane or divine"
        )
        return PrereqResult.UNMET, [
            UnmetDetail(
                description=(
                    f"Ability to cast {type_str}"
                    f" spells of level {self.min_level}+"
                ),
            )
        ]


@dataclass
class ClassFeaturePrereq(Prerequisite):
    """Character must have the named class feature."""

    feature: str
    min_value: str = ""  # e.g. "2d6" for sneak attack; empty = just presence

    def check(
        self,
        character: Character,
        checker: PrerequisiteChecker,
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        if checker.capabilities.has_class_feature(
            character, self.feature, self.min_value
        ):
            return PrereqResult.MET, []
        display = self.feature.replace("_", " ").title()
        if self.min_value:
            display = f"{display} ({self.min_value}+)"
        return PrereqResult.UNMET, [UnmetDetail(description=display)]


@dataclass
class CreatureTypePrereq(Prerequisite):
    """Character's effective creature type must be in allowed list."""

    allowed: list[str]

    def check(
        self,
        character: Character,
        checker: PrerequisiteChecker,
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        ct = checker.capabilities.effective_creature_type(character)
        if ct in self.allowed:
            return PrereqResult.MET, []
        options = " or ".join(self.allowed)
        return PrereqResult.UNMET, [
            UnmetDetail(
                description=f"Creature type: {options}",
                have=ct or "Unknown",
                need=options,
            )
        ]


# --- Compound prerequisites -------------------------------------------------


@dataclass
class AllOfPrereq(Prerequisite):
    """All sub-prerequisites must be met."""

    children: list[Prerequisite]

    def check(
        self,
        character: Character,
        checker: PrerequisiteChecker,
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        all_details: list[UnmetDetail] = []
        for child in self.children:
            result, details = child.check(character, checker)
            if result == PrereqResult.UNMET:
                all_details.extend(details)
        if all_details:
            return PrereqResult.UNMET, all_details
        return PrereqResult.MET, []


@dataclass
class AnyOfPrereq(Prerequisite):
    """At least one sub-prerequisite must be met."""

    children: list[Prerequisite]

    def check(
        self,
        character: Character,
        checker: PrerequisiteChecker,
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        for child in self.children:
            result, _ = child.check(character, checker)
            if result == PrereqResult.MET:
                return PrereqResult.MET, []
        # None met — collect all details
        all_details: list[UnmetDetail] = []
        for child in self.children:
            _, details = child.check(character, checker)
            all_details.extend(details)
        return PrereqResult.UNMET, [
            UnmetDetail(
                description="Any of: "
                + "; ".join(d.description for d in all_details)
            )
        ]


@dataclass
class NoneOfPrereq(Prerequisite):
    """None of the sub-prerequisites may be met (exclusion)."""

    children: list[Prerequisite]

    def check(
        self,
        character: Character,
        checker: PrerequisiteChecker,
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        for child in self.children:
            result, _ = child.check(character, checker)
            if result == PrereqResult.MET:
                return PrereqResult.UNMET, [
                    UnmetDetail(
                        description="Incompatible with current character build"
                    )
                ]
        return PrereqResult.MET, []


# ---------------------------------------------------------------------------
# CapabilityChecker
# ---------------------------------------------------------------------------


class CapabilityChecker:
    """
    Resolves capability checks by walking the character's full state:
    race, class levels, feats, equipment, and templates.

    Each capability method returns bool.  Adding a new source of a
    capability (e.g. a PrC that grants proficiency with exotic weapons)
    means updating the relevant method here and/or adding a hook in the
    class data.
    """

    # Weapons that are martial for all characters with martial proficiency
    # This is a subset; the full list comes from the weapons rules YAML.
    # For now we use a representative set for testing.
    _SIMPLE_WEAPONS: frozenset[str] = frozenset(
        {
            "Dagger",
            "Quarterstaff",
            "Club",
            "Shortspear",
            "Spear",
            "Light Crossbow",
            "Heavy Crossbow",
            "Dart",
            "Sling",
            "Unarmed Strike",
        }
    )

    _MARTIAL_WEAPONS: frozenset[str] = frozenset(
        {
            "Longsword",
            "Shortsword",
            "Greatsword",
            "Handaxe",
            "Battleaxe",
            "Greataxe",
            "Longbow",
            "Shortbow",
            "Longbow, Composite",
            "Shortbow, Composite",
            "Morningstar",
            "Flail",
            "Heavy Flail",
            "Rapier",
            "Warhammer",
            "Falchion",
            "Greatclub",
            "Glaive",
            "Halberd",
            "Lance",
            "Scythe",
        }
    )

    # Classes that grant martial weapon proficiency
    _MARTIAL_CLASSES: frozenset[str] = frozenset(
        {
            "Fighter",
            "Paladin",
            "Ranger",
            "Barbarian",
            "Warblade",
            "Crusader",
            "Swordsage",
        }
    )

    # Classes that grant all simple weapon proficiency
    _SIMPLE_CLASSES: frozenset[str] = frozenset(
        {
            "Cleric",
            "Druid",
            "Rogue",
            "Wizard",
            "Sorcerer",
            "Bard",
            "Monk",
            "Psychic Warrior",
            "Wilder",
            "Psion",
        }
    )

    # Racial weapon familiarity: race → set of weapons treated as martial
    _RACIAL_MARTIAL: dict[str, frozenset[str]] = {
        "Gnome": frozenset({"Gnome Hooked Hammer"}),
        "Dwarf": frozenset({"Dwarven Waraxe", "Dwarven Urgrosh"}),
        "Elf": frozenset(
            {
                "Longsword",
                "Rapier",
                "Longbow",
                "Longbow, Composite",
                "Shortbow",
                "Shortbow, Composite",
            }
        ),
        "Half-Elf": frozenset(
            {
                "Longsword",
                "Rapier",
                "Longbow",
                "Longbow, Composite",
                "Shortbow",
                "Shortbow, Composite",
            }
        ),
        "Halfling": frozenset({"Sling", "Halfling Skiprock"}),
        "Orc": frozenset({"Orc Double Axe"}),
        "Half-Orc": frozenset({"Orc Double Axe"}),
    }

    def is_proficient(self, character: "Character", weapon: str) -> bool:
        """
        Returns True if the character is proficient with the named weapon.

        Checks in order:
          1. Simple weapon → any character is proficient (martial classes,
             simple-only classes, and any non-caster with simple proficiency)
          2. Martial weapon → martial classes, or racial familiarity
          3. Exotic weapon → EWP feat, racial familiarity, or class grant
        """
        class_names = set(character.class_level_map)
        race = getattr(character, "race", "")
        feat_names = {
            f.get("name", "") for f in getattr(character, "feats", [])
        }

        # Simple weapons: proficient if any class grants at least simple
        if weapon in self._SIMPLE_WEAPONS:
            all_classes = self._MARTIAL_CLASSES | self._SIMPLE_CLASSES
            if class_names & all_classes:
                return True
            # Monk unarmed + simple
            if "Monk" in class_names:
                return True

        # Martial weapons: martial class, or racial familiarity
        if weapon in self._MARTIAL_WEAPONS:
            if class_names & self._MARTIAL_CLASSES:
                return True
            racial_martial = self._RACIAL_MARTIAL.get(race, frozenset())
            if weapon in racial_martial:
                return True

        # Racial familiarity: weapon treated as martial by race
        racial_martial = self._RACIAL_MARTIAL.get(race, frozenset())
        if weapon in racial_martial:
            # Counts as martial for this race; need martial class OR
            # just being proficient via racial familiarity alone
            if class_names & self._MARTIAL_CLASSES:
                return True
            # Racial familiarity alone grants proficiency
            return True

        # EWP feat
        ewp_name = f"Exotic Weapon Proficiency ({weapon})"
        if ewp_name in feat_names:
            return True

        # Generic EWP (some feats grant all exotic weapons)
        return "Exotic Weapon Proficiency (all)" in feat_names

    def can_cast(
        self,
        character: "Character",
        min_level: int,
        cast_type: CastType = CastType.EITHER,
    ) -> bool:
        """
        Returns True if the character can cast spells of at least min_level.
        cast_type: "arcane", "divine", or "either".

        Determined from class_levels using known caster classifications.
        Partial casters (Paladin, Ranger) are handled correctly.
        """
        ARCANE_CASTERS = {
            "Wizard",
            "Sorcerer",
            "Bard",
            "Warmage",
            "Duskblade",
            "Hexblade",
            "Wu Jen",
            "Sha'ir",
        }
        DIVINE_CASTERS = {
            "Cleric",
            "Druid",
            "Favored Soul",
            "Shugenja",
            "Spirit Shaman",
        }
        # Partial casters: gain spells starting at level 4 (level 1 spells)
        PARTIAL_ARCANE = {"Beguiler", "Dread Necromancer"}
        PARTIAL_DIVINE = {"Paladin", "Ranger", "Blackguard"}

        class_level_map = character.class_level_map
        class_names = set(class_level_map)

        def highest_spell_level(
            caster_class: str, partial: bool = False
        ) -> int:
            lvl = class_level_map.get(caster_class, 0)
            if lvl == 0:
                return 0
            if partial:
                # Paladin/Ranger: 1st level spells at class level 4
                return max(0, (lvl - 1) // 3)
            # Full caster: 9th level spells at level 17+
            return min(9, (lvl + 1) // 2)

        max_arcane = max(
            (
                highest_spell_level(c)
                for c in ARCANE_CASTERS
                if c in class_names
            ),
            default=0,
        )
        max_arcane = max(
            max_arcane,
            max(
                (
                    highest_spell_level(c, partial=True)
                    for c in PARTIAL_ARCANE
                    if c in class_names
                ),
                default=0,
            ),
        )

        max_divine = max(
            (
                highest_spell_level(c)
                for c in DIVINE_CASTERS
                if c in class_names
            ),
            default=0,
        )
        max_divine = max(
            max_divine,
            max(
                (
                    highest_spell_level(c, partial=True)
                    for c in PARTIAL_DIVINE
                    if c in class_names
                ),
                default=0,
            ),
        )

        if cast_type == CastType.ARCANE:
            return max_arcane >= min_level
        if cast_type == CastType.DIVINE:
            return max_divine >= min_level
        return max(max_arcane, max_divine) >= min_level

    def has_class_feature(
        self,
        character: "Character",
        feature: str,
        min_value: str = "",
    ) -> bool:
        """
        Returns True if the character has the named class feature.

        Feature presence is derived from class levels.  The min_value
        string is used for graduated features (e.g. sneak_attack "2d6").
        """
        class_level_map = character.class_level_map

        if feature == "sneak_attack":
            # Rogue: 1d6 at level 1, +1d6 every 2 levels
            rogue_lvl = class_level_map.get("Rogue", 0)
            # Also Assassin, Ninja, etc. — simplified here
            sneak_dice = (rogue_lvl + 1) // 2
            if not min_value:
                return sneak_dice >= 1
            # Parse "Nd6" format
            try:
                required = int(min_value.replace("d6", ""))
                return sneak_dice >= required
            except ValueError:
                return sneak_dice >= 1

        if feature == "turn_undead":
            return bool(
                class_level_map.keys() & {"Cleric", "Paladin", "Favored Soul"}
            )

        if feature == "wild_shape":
            druid_lvl = class_level_map.get("Druid", 0)
            return druid_lvl >= 5

        if feature == "rage":
            barbarian_lvl = class_level_map.get("Barbarian", 0)
            return barbarian_lvl >= 1

        if feature == "bardic_music":
            return "Bard" in class_level_map

        if feature == "spells":
            # Generic "can cast spells" — any spellcasting class
            return self.can_cast(character, 1, CastType.EITHER)

        # Unknown feature: not present
        return False

    def effective_creature_type(self, character: "Character") -> str:
        """
        Returns the character's effective creature type after templates.
        Falls back to race-derived type, then "Humanoid".
        """
        # Templates can override creature type — checked first
        override = getattr(character, "_creature_type_override", None)
        if override:
            return override

        # Race-derived types
        RACE_TYPES = {
            "Human": "Humanoid",
            "Elf": "Humanoid",
            "Half-Elf": "Humanoid",
            "Dwarf": "Humanoid",
            "Gnome": "Humanoid",
            "Halfling": "Humanoid",
            "Half-Orc": "Humanoid",
            "Orc": "Humanoid",
            "Tiefling": "Outsider",
            "Aasimar": "Outsider",
            "Warforged": "Construct",
            "Gnoll": "Humanoid",
            "Goblin": "Humanoid",
            "Kobold": "Humanoid",
        }
        race = getattr(character, "race", "")
        return RACE_TYPES.get(race, "Humanoid")

    def effective_subtypes(self, character: "Character") -> list[str]:
        """Returns the character's effective creature subtypes."""
        base = []
        race = getattr(character, "race", "")
        if race in {
            "Human",
            "Elf",
            "Half-Elf",
            "Dwarf",
            "Gnome",
            "Halfling",
            "Half-Orc",
            "Orc",
        } and race not in {"Half-Elf", "Half-Orc"}:
            base.append(race)
        template_subtypes = getattr(character, "_template_subtypes", [])
        return base + template_subtypes


# ---------------------------------------------------------------------------
# PrerequisiteChecker
# ---------------------------------------------------------------------------


class PrerequisiteChecker:
    """
    Main facade for prerequisite evaluation.

    Holds references to all registered feat/PrC prerequisite trees and
    evaluates them against a Character.  DM overrides are checked first
    and short-circuit all evaluation.
    """

    def __init__(self) -> None:
        self.capabilities = CapabilityChecker()
        # feat_name → Prerequisite (the root of its prereq tree)
        self._feat_prereqs: dict[str, Prerequisite] = {}
        # prc_name  → (entry_prereq, ongoing_prereq|None)
        self._prc_prereqs: dict[
            str, tuple[Prerequisite, Prerequisite | None]
        ] = {}
        # feat_name → bool (snapshot = only checked at acquisition time)
        self._feat_snapshot: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_feat(
        self,
        feat_name: str,
        prereq: Prerequisite | None,
        snapshot: bool = False,
    ) -> None:
        """
        Register a feat and its prerequisites.
        prereq=None means no prerequisites (always available).
        snapshot=True means prereqs are only checked at acquisition time.
        """
        self._feat_prereqs[feat_name] = prereq
        self._feat_snapshot[feat_name] = snapshot

    def register_prc(
        self,
        prc_name: str,
        entry_prereq: Prerequisite | None,
        ongoing_prereq: Prerequisite | None = None,
    ) -> None:
        self._prc_prereqs[prc_name] = (entry_prereq, ongoing_prereq)

    # ------------------------------------------------------------------
    # Core check
    # ------------------------------------------------------------------

    def check(
        self,
        prereq: Prerequisite | None,
        character: "Character",
        target_name: str = "",
    ) -> tuple[PrereqResult, list[UnmetDetail]]:
        """
        Evaluate a Prerequisite against a character.

        Checks DM override first — if target_name is overridden, returns
        (OVERRIDE, []) without evaluating prereqs.

        prereq=None means no prerequisites; returns MET immediately.
        """
        if target_name and character.has_dm_override(target_name):
            return PrereqResult.OVERRIDE, []

        if prereq is None:
            return PrereqResult.MET, []

        return prereq.check(character, self)

    # ------------------------------------------------------------------
    # Feat availability
    # ------------------------------------------------------------------

    def feat_availability(
        self,
        feat_name: str,
        character: "Character",
    ) -> tuple[FeatAvailability, list[UnmetDetail]]:
        """
        Return (FeatAvailability, unmet_details) for a single feat.

        Priority:
          1. DM override → OVERRIDE
          2. Already taken → TAKEN
          3. No prereqs registered → AVAILABLE
          4. Evaluate prereqs → AVAILABLE / UNAVAILABLE / CHAIN_PARTIAL
        """
        # 1. DM override
        if character.has_dm_override(feat_name):
            return FeatAvailability.OVERRIDE, []

        # 2. Already taken
        if self.has_feat(character, feat_name):
            return FeatAvailability.TAKEN, []

        # 3. No prereqs in registry — not necessarily available; the feat
        #    might just not be loaded yet.  Return AVAILABLE if in registry.
        if feat_name not in self._feat_prereqs:
            return FeatAvailability.AVAILABLE, []

        prereq = self._feat_prereqs[feat_name]

        # 4. Evaluate
        result, details = self.check(prereq, character, feat_name)

        if result == PrereqResult.MET:
            return FeatAvailability.AVAILABLE, []

        # Check if any of the unmet details are feat dependencies
        # (for CHAIN_PARTIAL state)
        feat_deps_unmet = [d for d in details if d.is_feat_dep]
        if feat_deps_unmet:
            # Some feat prereqs unmet — is it a partial chain?
            # CHAIN_PARTIAL if at least one feat in the chain IS met
            all_feat_deps = self._collect_feat_deps(prereq)
            any_met = any(
                self.has_feat(character, fname) for fname in all_feat_deps
            )
            if any_met:
                return FeatAvailability.CHAIN_PARTIAL, details

        return FeatAvailability.UNAVAILABLE, details

    def available_feats(
        self,
        character: "Character",
    ) -> list[tuple[str, FeatAvailability, list[UnmetDetail]]]:
        """
        Evaluate all registered feats and return their availability.
        Returns list of (feat_name, availability, unmet_details).
        """
        results = []
        for feat_name in sorted(self._feat_prereqs.keys()):
            avail, details = self.feat_availability(feat_name, character)
            results.append((feat_name, avail, details))
        return results

    # ------------------------------------------------------------------
    # Prestige class availability
    # ------------------------------------------------------------------

    def prc_availability(
        self,
        prc_name: str,
        character: "Character",
    ) -> tuple[FeatAvailability, list[UnmetDetail]]:
        """
        Return (FeatAvailability, unmet_details) for a prestige class entry.
        Uses FeatAvailability states (same semantics, different domain).
        """
        if character.has_dm_override(prc_name):
            return FeatAvailability.OVERRIDE, []

        # Already entered?
        already_in = prc_name in character.class_level_map
        if already_in:
            return FeatAvailability.TAKEN, []

        if prc_name not in self._prc_prereqs:
            return FeatAvailability.AVAILABLE, []

        entry_prereq, _ = self._prc_prereqs[prc_name]
        result, details = self.check(entry_prereq, character, prc_name)

        if result == PrereqResult.MET:
            return FeatAvailability.AVAILABLE, []

        feat_deps_unmet = [d for d in details if d.is_feat_dep]
        if feat_deps_unmet:
            all_feat_deps = self._collect_feat_deps(entry_prereq)
            any_met = any(
                self.has_feat(character, fname) for fname in all_feat_deps
            )
            if any_met:
                return FeatAvailability.CHAIN_PARTIAL, details

        return FeatAvailability.UNAVAILABLE, details

    # ------------------------------------------------------------------
    # Ongoing prerequisite violations
    # ------------------------------------------------------------------

    def ongoing_violations(
        self,
        character: "Character",
    ) -> list[tuple[str, list[UnmetDetail]]]:
        """
        Check all ongoing prerequisites (PrC continuation reqs, alignment
        feats, etc.) and return list of (target_name, unmet_details) for
        anything that is violated.
        """
        violations: list[tuple[str, list[UnmetDetail]]] = []

        for prc_name, (_, ongoing) in self._prc_prereqs.items():
            if ongoing is None:
                continue
            if prc_name not in character.class_level_map:
                continue
            result, details = self.check(ongoing, character, prc_name)
            if result == PrereqResult.UNMET:
                violations.append((prc_name, details))

        return violations

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def has_feat(self, character: "Character", feat_name: str) -> bool:
        """Returns True if the character has the named feat."""
        return any(
            f.get("name", "") == feat_name
            for f in getattr(character, "feats", [])
        )

    def _resolve_param(self, character: "Character", param_name: str) -> str:
        """
        Resolve a parameter from the character's feat list.
        Used for parameterised prereqs like Weapon Focus($weapon).
        Returns the parameter value or "".
        """
        # Look for the feat whose parameter context we're checking;
        # in practice the caller provides this through the check context.
        # Simplified: return "" — full parameter resolution requires
        # the feat context to be threaded through.
        return ""

    def _collect_feat_deps(self, prereq: Prerequisite | None) -> set[str]:
        """
        Walk a prereq tree and collect all FeatPrereq.feat_name values.
        Used to determine CHAIN_PARTIAL state.
        """
        if prereq is None:
            return set()
        deps: set[str] = set()
        if isinstance(prereq, FeatPrereq):
            deps.add(prereq.feat_name)
        elif isinstance(prereq, (AllOfPrereq, AnyOfPrereq, NoneOfPrereq)):
            for child in prereq.children:
                deps |= self._collect_feat_deps(child)
        return deps


# ---------------------------------------------------------------------------
# YAML → Prerequisite tree builder
# ---------------------------------------------------------------------------


def build_prereq_from_yaml(decl: dict[str, Any]) -> Prerequisite | None:
    """
    Recursively build a Prerequisite tree from a YAML-parsed dict.

    Supports the vocabulary defined in ARCHITECTURE.md:
      stat, ability, feat, skill, class_level, race, alignment,
      proficient_with, can_cast, has_class_feature, creature_type_is,
      all_of, any_of, none_of.

    Returns None if decl is empty or None.
    """
    if not decl:
        return None

    if "all_of" in decl:
        children = [build_prereq_from_yaml(c) for c in decl["all_of"]]
        children = [c for c in children if c is not None]
        return AllOfPrereq(children) if children else None

    if "any_of" in decl:
        children = [build_prereq_from_yaml(c) for c in decl["any_of"]]
        children = [c for c in children if c is not None]
        return AnyOfPrereq(children) if children else None

    if "none_of" in decl:
        children = [build_prereq_from_yaml(c) for c in decl["none_of"]]
        children = [c for c in children if c is not None]
        return NoneOfPrereq(children) if children else None

    if "stat" in decl:
        s = decl["stat"]
        return StatPrereq(
            stat_key=s["key"],
            min_value=s["min"],
            label=s.get("label", ""),
        )

    if "ability" in decl:
        a = decl["ability"] if isinstance(decl["ability"], dict) else decl
        key = a.get("key", "")
        raw = key.replace("_score", "") if "_score" in key else key
        return AbilityPrereq(
            ability=Ability(raw),
            min_value=a["min"],
        )

    if "feat" in decl:
        return FeatPrereq(feat_name=decl["feat"])

    if "skill" in decl:
        s = decl["skill"]
        min_ranks = s.get("min_ranks", s.get("min", 0))
        return SkillPrereq(
            skill_name=s["name"],
            min_ranks=min_ranks,
        )

    if "class_level" in decl:
        c = decl["class_level"]
        return ClassLevelPrereq(class_name=c["class"], min_level=c["min"])

    if "race" in decl:
        races = decl["race"]
        if isinstance(races, str):
            races = [races]
        return RacePrereq(races=races)

    if "alignment" in decl:
        allowed = decl["alignment"]
        if isinstance(allowed, dict):
            allowed = allowed.get("any_of", [])
        elif isinstance(allowed, str):
            allowed = [allowed]
        return AlignmentPrereq(allowed=allowed)

    if "proficient_with" in decl:
        return ProficiencyPrereq(
            weapon=decl["proficient_with"].get("weapon", "")
        )

    if "can_cast" in decl:
        c = decl["can_cast"]
        return SpellcastingPrereq(
            min_level=c.get("spell_level", 1),
            cast_type=CastType(c.get("type", "either")),
        )

    if "has_class_feature" in decl:
        f = decl["has_class_feature"]
        return ClassFeaturePrereq(
            feature=f.get("feature", ""),
            min_value=f.get("min_value", ""),
        )

    if "creature_type_is" in decl:
        ct = decl["creature_type_is"]
        allowed = ct.get("any_of", ct) if isinstance(ct, dict) else [ct]
        if isinstance(allowed, str):
            allowed = [allowed]
        return CreatureTypePrereq(allowed=allowed)

    # Unknown key — skip silently
    return None
