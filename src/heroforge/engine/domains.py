"""
engine/domains.py
-----------------
Cleric domain definitions for D&D 3.5e.

Public API:
  DomainDefinition  -- domain with spells
  DomainRegistry    -- lookup by name
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DomainDefinition:
    """A cleric domain with granted power and spells."""

    name: str
    granted_power: str = ""
    domain_spells: dict[int, str] = field(
        default_factory=dict
    )  # level 1-9 -> spell name


class DomainRegistry:
    """Name-based lookup for domain definitions."""

    def __init__(self) -> None:
        self._entries: dict[str, DomainDefinition] = {}

    def register(self, defn: DomainDefinition) -> None:
        self._entries[defn.name] = defn

    def get(self, name: str) -> DomainDefinition | None:
        return self._entries.get(name)

    def all_domains(self) -> list[DomainDefinition]:
        return list(self._entries.values())

    def names(self) -> list[str]:
        return sorted(self._entries.keys())

    def __len__(self) -> int:
        return len(self._entries)
