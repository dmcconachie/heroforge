"""
engine/enums.py
---------------
Leaf StrEnums for D&D 3.5 vocabulary: ability scores, saves,
alignment, creature size. Kept in their own module with no
upstream dependencies so any module can import them without
pulling in Character / the stat graph / rules loading.
"""

from __future__ import annotations

from enum import StrEnum


class Ability(StrEnum):
    STR = "str"
    DEX = "dex"
    CON = "con"
    INT = "int"
    WIS = "wis"
    CHA = "cha"


class Alignment(StrEnum):
    LAWFUL_GOOD = "lawful_good"
    LAWFUL_NEUTRAL = "lawful_neutral"
    LAWFUL_EVIL = "lawful_evil"
    NEUTRAL_GOOD = "neutral_good"
    NEUTRAL = "neutral"
    NEUTRAL_EVIL = "neutral_evil"
    CHAOTIC_GOOD = "chaotic_good"
    CHAOTIC_NEUTRAL = "chaotic_neutral"
    CHAOTIC_EVIL = "chaotic_evil"


class Save(StrEnum):
    FORT = "fort"
    REF = "ref"
    WILL = "will"


class Size(StrEnum):
    FINE = "Fine"
    DIMINUTIVE = "Diminutive"
    TINY = "Tiny"
    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"
    HUGE = "Huge"
    GARGANTUAN = "Gargantuan"
    COLOSSAL = "Colossal"


SAVE_ABILITY: dict[Save, Ability] = {
    Save.FORT: Ability.CON,
    Save.REF: Ability.DEX,
    Save.WILL: Ability.WIS,
}


class School(StrEnum):
    """
    The eight schools of magic (PHB p. 57).

    Universal is deliberately absent: it is not a school for
    specialization purposes and can be neither chosen nor
    prohibited.
    """

    ABJURATION = "Abjuration"
    CONJURATION = "Conjuration"
    DIVINATION = "Divination"
    ENCHANTMENT = "Enchantment"
    EVOCATION = "Evocation"
    ILLUSION = "Illusion"
    NECROMANCY = "Necromancy"
    TRANSMUTATION = "Transmutation"
