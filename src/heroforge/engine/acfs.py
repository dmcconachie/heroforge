"""
engine/acfs.py
--------------
Alternative class features (ACFs).

An ACF trades a standard class feature for a different one
(Complete Mage p. 31, and the same format in Complete Champion,
Cityscape and Dragon Magic). Racial substitution levels are the
same shape with a race requirement attached, so they use this
mechanism rather than a parallel one.

What a `replaces:` block can express, drawn from the published
ACFs, in rough order of how common it is:

  feature   — a class feature key, optionally templated on the
              level the ACF was taken at (``bonus_feat_{level}``).
              Covers the great majority, including every racial
              substitution level, because each replaceable slot
              already has its own key in the class YAML.
  spell_slots_per_level / prohibited_schools
            — numeric allotments that are not class features at
              all. Focused Specialist needs both.

Proficiencies and selection-style replacements (a ranger's
favored enemy) also appear in print but have no consumer yet, so
they are deliberately absent rather than guessed at.

Public API:
  AcfDefinition           -- one ACF
  AcfRegistry             -- lookup by name
  validate_acf_selection  -- raises on an illegal pick
  replaced_feature_keys   -- class feature keys to suppress
  acf_slot_deltas         -- (general, specialty) per spell level
  extra_prohibited_schools
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from heroforge.engine.enums import SourceBook

if TYPE_CHECKING:
    from heroforge.engine.character import Character


@dataclass(frozen=True)
class AcfDefinition:
    """One alternative class feature."""

    name: str
    source_book: SourceBook = SourceBook.NONE
    # Classes that may take it; several appear in print
    # ("Cleric or paladin").
    classes: tuple[str, ...] = ()
    # Levels at which it may be taken. More than one means the
    # player chooses, as with a fighter bonus feat at any even
    # level.
    levels: tuple[int, ...] = ()
    requires: dict[str, Any] = field(default_factory=dict)
    replaces: dict[str, Any] = field(default_factory=dict)
    grants: dict[str, Any] = field(default_factory=dict)
    note: str = ""


class AcfRegistry:
    """Name-based lookup for ACF definitions."""

    def __init__(self) -> None:
        self._entries: dict[str, AcfDefinition] = {}

    def register(self, defn: AcfDefinition) -> None:
        self._entries[defn.name] = defn

    def get(self, name: str) -> AcfDefinition | None:
        return self._entries.get(name)

    def all_acfs(self) -> list[AcfDefinition]:
        return list(self._entries.values())

    def names(self) -> list[str]:
        return sorted(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


# -----------------------------------------------------------
# Validation
# -----------------------------------------------------------


def _check_requirements(
    character: "Character",
    defn: AcfDefinition,
) -> None:
    requires = defn.requires or {}
    if requires.get("specialist") and character.specialization is None:
        msg = f"{defn.name} requires a specialist wizard."
        raise ValueError(msg)
    race = requires.get("race")
    if race is not None and character.race != race:
        msg = f"{defn.name} requires race {race}, got {character.race!r}."
        raise ValueError(msg)


def validate_acf_selection(
    character: "Character",
    defn: AcfDefinition,
    level: int,
) -> None:
    """Raise ValueError if this character cannot take this ACF."""
    held = set(character.class_level_map)
    eligible = [cn for cn in defn.classes if cn in held]
    if defn.classes and not eligible:
        msg = (
            f"{defn.name} requires one of {list(defn.classes)}; "
            f"character has {sorted(held)}."
        )
        raise ValueError(msg)
    if defn.levels and level not in defn.levels:
        msg = (
            f"{defn.name} is not offered at level {level} "
            f"(offered at {list(defn.levels)})."
        )
        raise ValueError(msg)
    if eligible and all(
        character.class_level_map.get(cn, 0) < level for cn in eligible
    ):
        msg = (
            f"{defn.name} taken at level {level}, but the character "
            f"has no qualifying class at that level."
        )
        raise ValueError(msg)
    _check_requirements(character, defn)


# -----------------------------------------------------------
# Effects
# -----------------------------------------------------------


def _selected(character: "Character") -> list[tuple[AcfDefinition, int]]:
    from heroforge.rules.rules import get_rules

    registry = get_rules().acfs
    out: list[tuple[AcfDefinition, int]] = []
    for entry in getattr(character, "acfs", []):
        defn = registry.get(entry.get("name", ""))
        if defn is not None:
            out.append((defn, int(entry.get("level", 0))))
    return out


def replaced_feature_keys(character: "Character") -> set[str]:
    """
    Class feature keys suppressed by the character's ACFs.

    A `feature:` value may template the level it was taken at, so
    one entry covers a bonus feat slot at any of several levels.
    """
    keys: set[str] = set()
    for defn, level in _selected(character):
        template = defn.replaces.get("feature")
        if template:
            keys.add(str(template).format(level=level))
    return keys


def acf_slot_deltas(character: "Character") -> tuple[int, int]:
    """
    Per-spell-level slot adjustments from ACFs.

    Returns (general, specialty): general is negative when slots
    are given up, specialty positive when extra specialty slots
    are granted.
    """
    general = 0
    specialty = 0
    for defn, _level in _selected(character):
        general -= int(defn.replaces.get("spell_slots_per_level", 0))
        specialty += int(defn.grants.get("specialty_slots_per_level", 0))
    return general, specialty


def extra_prohibited_schools(character: "Character") -> int:
    """Additional prohibited schools demanded by ACFs."""
    return sum(
        int(defn.replaces.get("prohibited_schools", 0))
        for defn, _level in _selected(character)
    )
