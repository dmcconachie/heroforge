"""
feats.py
Feats from Complete Mage.
"""

from __future__ import annotations

from enum import StrEnum


class KnownCompleteMageFeat(StrEnum):
    METAMAGIC_SCHOOL_FOCUS_ABJURATION = "Metamagic School Focus (Abjuration)"
    METAMAGIC_SCHOOL_FOCUS_CONJURATION = "Metamagic School Focus (Conjuration)"
    METAMAGIC_SCHOOL_FOCUS_DIVINATION = "Metamagic School Focus (Divination)"
    METAMAGIC_SCHOOL_FOCUS_ENCHANTMENT = "Metamagic School Focus (Enchantment)"
    METAMAGIC_SCHOOL_FOCUS_EVOCATION = "Metamagic School Focus (Evocation)"
    METAMAGIC_SCHOOL_FOCUS_ILLUSION = "Metamagic School Focus (Illusion)"
    METAMAGIC_SCHOOL_FOCUS_NECROMANCY = "Metamagic School Focus (Necromancy)"
    METAMAGIC_SCHOOL_FOCUS_TRANSMUTATION = (
        "Metamagic School Focus (Transmutation)"
    )
    RETRIBUTIVE_SPELL = "Retributive Spell"
