"""
engine/spells.py
----------------
Spell compendium: metadata for all SRD spells regardless
of whether they have stat-modifying effects.

Buff spells (those with BonusEffects) are still loaded
into the BuffRegistry via SpellsLoader.  This module
provides a parallel registry for *all* spells, including
those with no stat effects (damage spells, utility spells,
summons, etc.).

This is used by:
  - Class spell list validation
  - Spell slot/prepared spell tracking
  - UI spell browsing (future)

Public API:
  SpellEntry       — metadata for one spell
  SpellCompendium  — registry of SpellEntry objects
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SpellEntry:
    """Metadata for a single spell."""

    name: str
    school: str = ""
    subschool: str = ""
    descriptor: str = ""
    level: dict[str, int] = field(
        default_factory=dict
    )  # e.g. {"Wizard": 3, "Cleric": 4}
    casting_time: str = ""
    range: str = ""
    duration: str = ""
    saving_throw: str = ""
    spell_resistance: str = ""
    description: str = ""
    source_book: str = "SRD"
    has_buff_effects: bool = False


class SpellCompendium:
    """Registry of SpellEntry objects, keyed by name."""

    def __init__(self) -> None:
        self._entries: dict[str, SpellEntry] = {}

    def register(self, entry: SpellEntry) -> None:
        self._entries[entry.name] = entry

    def get(self, name: str) -> SpellEntry | None:
        return self._entries.get(name)

    def all_entries(self) -> list[SpellEntry]:
        return list(self._entries.values())

    def names(self) -> set[str]:
        return set(self._entries.keys())

    def by_class(self, class_name: str) -> list[SpellEntry]:
        """All spells available to a class."""
        return [e for e in self._entries.values() if class_name in e.level]

    def by_class_and_level(
        self, class_name: str, spell_level: int
    ) -> list[SpellEntry]:
        """Spells for a class at a specific level."""
        return [
            e
            for e in self._entries.values()
            if e.level.get(class_name) == spell_level
        ]

    def __len__(self) -> int:
        return len(self._entries)
