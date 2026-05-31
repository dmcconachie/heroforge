"""
engine/deities.py
-----------------
Deity definitions for D&D 3.5e (Living Greyhawk roster).

Public API:
  DeityDefinition  -- a deity with alignment, favored weapon, domains
  DeityRegistry    -- lookup by name
"""

from __future__ import annotations

from dataclasses import dataclass, field

from heroforge.engine.enums import Alignment


@dataclass(frozen=True)
class DeityDefinition:
    """A deity: alignment, favored weapon, and available domains."""

    name: str
    alignment: Alignment
    favored_weapon: str = ""
    domains: list[str] = field(default_factory=list)


class DeityRegistry:
    """Name-based lookup for deity definitions."""

    def __init__(self) -> None:
        self._entries: dict[str, DeityDefinition] = {}

    def register(self, defn: DeityDefinition) -> None:
        self._entries[defn.name] = defn

    def get(self, name: str) -> DeityDefinition | None:
        return self._entries.get(name)

    def all_deities(self) -> list[DeityDefinition]:
        return list(self._entries.values())

    def names(self) -> list[str]:
        return sorted(self._entries.keys())

    def __len__(self) -> int:
        return len(self._entries)
