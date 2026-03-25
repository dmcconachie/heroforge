"""
engine/spells.py
----------------
Spell compendium: the single source of truth for all
spells.

Each SpellEntry holds metadata (school, level, duration)
and optionally inline stat effects.  The spell loader
registers every spell in the SpellCompendium, and those
with effects also get a BuffDefinition in the
BuffRegistry.

Spells that simply apply a standard condition (e.g.
Doom → Shaken) use ``applies_condition`` instead of
``effects`` — the condition is what appears in the
buff panel, not the spell.

Public API:
  SpellEntry       — metadata + optional effects
  SpellCompendium  — registry of SpellEntry objects
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SpellEntry:
    """Single source of truth for one spell."""

    name: str
    school: str = ""
    subschool: str = ""
    descriptor: str = ""
    level: dict[str, int] = field(default_factory=dict)
    casting_time: str = ""
    range: str = ""
    duration: str = ""
    saving_throw: str = ""
    spell_resistance: str = ""
    description: str = ""
    source_book: str = "SRD"
    # Buff effects (registered in BuffRegistry):
    effects: list[dict] = field(default_factory=list)
    note: str = ""
    requires_caster_level: bool = False
    mutually_exclusive_with: list[str] = field(default_factory=list)
    condition_key: str = ""
    # If the spell just applies a condition, name it
    # here instead of using effects:
    applies_condition: str = ""


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
