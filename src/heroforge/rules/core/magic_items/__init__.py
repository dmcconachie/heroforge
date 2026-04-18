"""
magic_items/__init__.py
-------------------------
Aggregates per-slot SRD magic-item StrEnums
into a single KnownCoreMagicItem.
"""

from __future__ import annotations

from enum import StrEnum

from heroforge.rules.core.magic_items.head import (
    KnownCoreMagicItemHead,
)
from heroforge.rules.core.magic_items.face import (
    KnownCoreMagicItemFace,
)
from heroforge.rules.core.magic_items.throat import (
    KnownCoreMagicItemThroat,
)
from heroforge.rules.core.magic_items.shoulders import (
    KnownCoreMagicItemShoulders,
)
from heroforge.rules.core.magic_items.body import (
    KnownCoreMagicItemBody,
)
from heroforge.rules.core.magic_items.torso import (
    KnownCoreMagicItemTorso,
)
from heroforge.rules.core.magic_items.arms import (
    KnownCoreMagicItemArms,
)
from heroforge.rules.core.magic_items.hands import (
    KnownCoreMagicItemHands,
)
from heroforge.rules.core.magic_items.ring import (
    KnownCoreMagicItemRing,
)
from heroforge.rules.core.magic_items.waist import (
    KnownCoreMagicItemWaist,
)
from heroforge.rules.core.magic_items.feet import (
    KnownCoreMagicItemFeet,
)
from heroforge.rules.core.magic_items.slotless import (
    KnownCoreMagicItemSlotless,
)
from heroforge.rules.core.magic_items.tool import (
    KnownCoreMagicItemTool,
)
from heroforge.rules.core.magic_items.consumable import (
    KnownCoreMagicItemConsumable,
)


def _combine(
    name: str, *sources: type[StrEnum]
) -> type[StrEnum]:
    members: dict[str, str] = {}
    for src in sources:
        for m in src:
            members[m.name] = m.value
    return StrEnum(name, members)


KnownCoreMagicItem = _combine(
    "KnownCoreMagicItem",
    KnownCoreMagicItemHead,
    KnownCoreMagicItemFace,
    KnownCoreMagicItemThroat,
    KnownCoreMagicItemShoulders,
    KnownCoreMagicItemBody,
    KnownCoreMagicItemTorso,
    KnownCoreMagicItemArms,
    KnownCoreMagicItemHands,
    KnownCoreMagicItemRing,
    KnownCoreMagicItemWaist,
    KnownCoreMagicItemFeet,
    KnownCoreMagicItemSlotless,
    KnownCoreMagicItemTool,
    KnownCoreMagicItemConsumable,
)
