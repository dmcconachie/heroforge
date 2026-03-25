"""
engine/magic_items.py
---------------------
Domain model for D&D 3.5e magic items.

MagicItemDefinition is a lightweight dataclass holding
the item's name, note, raw effect dicts, source book,
slot, and cost.  The MagicItemLoader (in rules/loader.py)
reads magic_items.yaml, creates MagicItemDefinitions,
and also registers a corresponding BuffDefinition in the
BuffRegistry so existing buff-toggle UI keeps working.

Public API:
  MagicItemDefinition  — frozen dataclass
  MagicItemRegistry    — name-based lookup
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MagicItemDefinition:
    """
    One SRD magic item (e.g. Ring of Protection +2).

    Attributes
    ----------
    name        : Display name, also the lookup key.
    note        : One-line description shown in the UI.
    effects     : Raw effect dicts (target, bonus_type,
                  value).  Passed through to
                  build_buff_from_effects() by the loader.
    source_book : Rulebook abbreviation (default "SRD").
    slot        : Equipment slot (e.g. "ring", "cloak").
    cost_gp     : Gold piece cost.
    """

    name: str
    note: str = ""
    effects: list[dict] = field(default_factory=list)
    source_book: str = "SRD"
    slot: str = ""
    cost_gp: int = 0


class MagicItemRegistry:
    """
    Central lookup for loaded MagicItemDefinitions.

    Read-only after startup.
    """

    def __init__(self) -> None:
        self._entries: dict[str, MagicItemDefinition] = {}

    def register(self, defn: MagicItemDefinition) -> None:
        self._entries[defn.name] = defn

    def get(self, name: str) -> MagicItemDefinition | None:
        return self._entries.get(name)

    def all_items(
        self,
    ) -> list[MagicItemDefinition]:
        return list(self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)
