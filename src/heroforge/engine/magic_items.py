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
from enum import StrEnum

from heroforge.engine.enums import SourceBook


class BodySlot(StrEnum):
    """
    Where an item is worn, and what it competes with.

    The eleven body slots of the Magic Item Compendium, plus
    the three ways an item can occupy none of them: a tool is
    held, a consumable is used up, and a slotless item just
    works.
    """

    NONE = ""
    HEAD = "head"
    FACE = "face"
    THROAT = "throat"
    SHOULDERS = "shoulders"
    BODY = "body"
    TORSO = "torso"
    ARMS = "arms"
    HANDS = "hands"
    RING = "ring"
    WAIST = "waist"
    FEET = "feet"
    SLOTLESS = "slotless"
    TOOL = "tool"
    CONSUMABLE = "consumable"


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
    slot        : Body slot the item occupies.
    cost_gp     : Gold piece cost.
    defenses    : Damage reduction / energy resistance /
                  immunity block (see engine/defenses.py).
    takes_parameter : The item names something chosen when it
                  is made -- a ring of energy resistance picks
                  its energy. `$parameter` in a defenses key
                  or value is replaced with the choice.
    parameter_label : What the choice is, for the UI.
    """

    name: str
    note: str = ""
    effects: list[dict] = field(default_factory=list)
    source_book: SourceBook = SourceBook.SRD
    slot: BodySlot = BodySlot.NONE
    cost_gp: int = 0
    defenses: dict = field(default_factory=dict)
    takes_parameter: bool = False
    parameter_label: str = ""
    # Feats wearing this item confers, each optionally gated on
    # a feat the wearer already has of their own (Gloves of the
    # Balanced Hand grant Improved Two-Weapon Fighting only to
    # someone who already had Two-Weapon Fighting). Derived,
    # never saved.
    grants_feats: list[dict] = field(default_factory=list)


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
