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

from heroforge.rules.combine_str_enum import combine
from heroforge.rules.core.armor import KnownCoreArmor
from heroforge.rules.core.buffs import KnownCoreBuff
from heroforge.rules.core.classes import KnownCoreClass
from heroforge.rules.core.conditions_srd import KnownCoreCondition
from heroforge.rules.core.domains import KnownCoreDomain
from heroforge.rules.core.feats import KnownCoreFeat
from heroforge.rules.core.gates import KnownCoreGate
from heroforge.rules.core.magic_items import KnownCoreMagicItem
from heroforge.rules.core.materials import KnownCoreMaterial
from heroforge.rules.core.races import KnownCoreRace
from heroforge.rules.core.skills import KnownCoreSkill
from heroforge.rules.core.templates import KnownCoreTemplate
from heroforge.rules.core.weapons import KnownCoreWeapon
from heroforge.rules.custom.classes import KnownCustomClass
from heroforge.rules.custom.feats import KnownCustomFeat
from heroforge.rules.custom.magic_items import KnownCustomMagicItem
from heroforge.rules.custom.materials import KnownCustomMaterial

# --- Combined enums from rule sources --------------

KnownRace = combine("KnownRace", KnownCoreRace)
KnownClass = combine("KnownClass", KnownCoreClass, KnownCustomClass)
KnownFeat = combine("KnownFeat", KnownCoreFeat, KnownCustomFeat)
KnownSkill = combine("KnownSkill", KnownCoreSkill)
KnownBuff = combine("KnownBuff", KnownCoreBuff)
KnownTemplate = combine("KnownTemplate", KnownCoreTemplate)
KnownArmor = combine("KnownArmor", KnownCoreArmor)
KnownWeapon = combine("KnownWeapon", KnownCoreWeapon)
KnownMagicItem = combine(
    "KnownMagicItem", KnownCoreMagicItem, KnownCustomMagicItem
)
KnownMaterial = combine("KnownMaterial", KnownCoreMaterial, KnownCustomMaterial)
KnownDomain = combine("KnownDomain", KnownCoreDomain)
KnownCondition = combine("KnownCondition", KnownCoreCondition)
KnownGate = combine("KnownGate", KnownCoreGate)
