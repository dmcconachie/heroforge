"""
rules/known.py
--------------
Combined KnownXxx StrEnums across all rule sources.

To add a splatbook:
1. Create rules/<book>/<category>.py with a StrEnum
2. Merge its members into the corresponding
   _combine() call below.
3. The congruence test catches any drift.
"""

from __future__ import annotations

from enum import StrEnum

from heroforge.rules.core.armor import KnownCoreArmor
from heroforge.rules.core.buffs import KnownCoreBuff
from heroforge.rules.core.classes import KnownCoreClass
from heroforge.rules.core.conditions_srd import KnownCoreCondition
from heroforge.rules.core.domains import KnownCoreDomain
from heroforge.rules.core.feats import KnownCoreFeat
from heroforge.rules.core.magic_items import KnownCoreMagicItem
from heroforge.rules.core.materials import KnownCoreMaterial
from heroforge.rules.custom.magic_items import KnownCustomMagicItem
from heroforge.rules.core.races import KnownCoreRace
from heroforge.rules.core.skills import KnownCoreSkill
from heroforge.rules.core.templates import KnownCoreTemplate
from heroforge.rules.core.weapons import KnownCoreWeapon


def _combine(name: str, *sources: type[StrEnum]) -> type[StrEnum]:
    members: dict[str, str] = {}
    for src in sources:
        for m in src:
            members[m.name] = m.value
    return StrEnum(name, members)


# --- Combined enums from rule sources --------------

KnownRace = _combine("KnownRace", KnownCoreRace)
KnownClass = _combine("KnownClass", KnownCoreClass)
KnownFeat = _combine("KnownFeat", KnownCoreFeat)
KnownSkill = _combine("KnownSkill", KnownCoreSkill)
KnownBuff = _combine("KnownBuff", KnownCoreBuff)
KnownTemplate = _combine("KnownTemplate", KnownCoreTemplate)
KnownArmor = _combine("KnownArmor", KnownCoreArmor)
KnownWeapon = _combine("KnownWeapon", KnownCoreWeapon)
KnownMagicItem = _combine(
    "KnownMagicItem", KnownCoreMagicItem, KnownCustomMagicItem
)
KnownMaterial = _combine("KnownMaterial", KnownCoreMaterial)
KnownDomain = _combine("KnownDomain", KnownCoreDomain)
KnownCondition = _combine("KnownCondition", KnownCoreCondition)
