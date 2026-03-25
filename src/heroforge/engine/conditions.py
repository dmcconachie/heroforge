"""
engine/conditions.py
--------------------
Domain model for D&D 3.5e status conditions.

ConditionDefinition is a lightweight dataclass holding
the condition's name, note, raw effect dicts, and source
book.  The ConditionLoader (in rules/loader.py) reads
conditions_srd.yaml, creates ConditionDefinitions, and
also registers a corresponding BuffDefinition in the
BuffRegistry so existing buff-toggle UI keeps working.

Public API:
  ConditionDefinition  — frozen dataclass
  ConditionRegistry    — name-based lookup
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConditionDefinition:
    """
    One SRD condition (e.g. Shaken, Prone).

    Attributes
    ----------
    name        : Display name, also the lookup key.
    note        : One-line description shown in the UI.
    effects     : Raw effect dicts (target, bonus_type,
                  value).  Passed through to
                  build_buff_from_effects() by the loader.
    source_book : Rulebook abbreviation (default "SRD").
    """

    name: str
    note: str = ""
    effects: list[dict] = field(default_factory=list)
    source_book: str = "SRD"
    requires_caster_level: bool = False


class ConditionRegistry:
    """
    Central lookup for loaded ConditionDefinitions.

    Read-only after startup.
    """

    def __init__(self) -> None:
        self._entries: dict[str, ConditionDefinition] = {}

    def register(self, defn: ConditionDefinition) -> None:
        self._entries[defn.name] = defn

    def get(self, name: str) -> ConditionDefinition | None:
        return self._entries.get(name)

    def all_conditions(self) -> list[ConditionDefinition]:
        return list(self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)
