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


class CreatureType(StrEnum):
    """
    The fifteen creature types (Monster Manual, p. 305-317).

    Compared exactly wherever a prerequisite is gated on type,
    so the spelling has to be the book's.
    """

    ABERRATION = "Aberration"
    ANIMAL = "Animal"
    CONSTRUCT = "Construct"
    DRAGON = "Dragon"
    ELEMENTAL = "Elemental"
    FEY = "Fey"
    GIANT = "Giant"
    HUMANOID = "Humanoid"
    MAGICAL_BEAST = "Magical Beast"
    MONSTROUS_HUMANOID = "Monstrous Humanoid"
    OOZE = "Ooze"
    OUTSIDER = "Outsider"
    PLANT = "Plant"
    UNDEAD = "Undead"
    VERMIN = "Vermin"


class CreatureSubtype(StrEnum):
    """
    Subtypes a race or template can carry.

    The Monster Manual's generic subtypes (p. 310-313) plus
    the racial ones races.yaml grants. Splatbooks add more --
    a new one belongs here rather than as loose text, because
    prerequisites match subtypes exactly.
    """

    AIR = "Air"
    AQUATIC = "Aquatic"
    AUGMENTED = "Augmented"
    CHAOTIC = "Chaotic"
    COLD = "Cold"
    EARTH = "Earth"
    EVIL = "Evil"
    EXTRAPLANAR = "Extraplanar"
    FIRE = "Fire"
    GOOD = "Good"
    INCORPOREAL = "Incorporeal"
    LAWFUL = "Lawful"
    NATIVE = "Native"
    SHAPECHANGER = "Shapechanger"
    SWARM = "Swarm"
    WATER = "Water"
    # Racial subtypes (Monster Manual p. 312).
    DWARF = "Dwarf"
    ELF = "Elf"
    GNOME = "Gnome"
    GOBLINOID = "Goblinoid"
    HALFLING = "Halfling"
    HUMAN = "Human"
    ORC = "Orc"
    REPTILIAN = "Reptilian"


class ArmorCategory(StrEnum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"
    SHIELD = "shield"
    TOWER_SHIELD = "tower_shield"


class LoadCategory(StrEnum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


class WeaponCategory(StrEnum):
    SIMPLE = "simple"
    MARTIAL = "martial"
    EXOTIC = "exotic"


class WieldClass(StrEnum):
    """
    How much effort a weapon takes to wield (PHB p. 113).

    Decides Weapon Finesse eligibility, which end of a
    two-weapon pairing counts as light, and how much Strength
    reaches the damage line.
    """

    LIGHT = "light"
    ONE_HANDED = "one_handed"
    TWO_HANDED = "two_handed"
    RANGED = "ranged"


class DamageType(StrEnum):
    SLASHING = "slashing"
    PIERCING = "piercing"
    BLUDGEONING = "bludgeoning"
    BLUDGEONING_AND_PIERCING = "bludgeoning and piercing"
    PIERCING_OR_SLASHING = "piercing or slashing"


class SourceBook(StrEnum):
    """
    Which book a rules entry came from.

    One canonical spelling per book: the established
    abbreviation where a book has one, the full title
    otherwise. The data previously carried both "MIC" and
    "Magic Item Compendium" for the same book, which made
    ``by_source_book`` return half an answer.
    """

    NONE = ""
    SRD = "SRD"
    PHB = "PHB"
    DMG = "DMG"
    MM = "MM"
    MIC = "MIC"
    COMPLETE_ADVENTURER = "Complete Adventurer"
    COMPLETE_ARCANE = "Complete Arcane"
    COMPLETE_CHAMPION = "Complete Champion"
    COMPLETE_DIVINE = "Complete Divine"
    COMPLETE_MAGE = "Complete Mage"
    COMPLETE_SCOUNDREL = "Complete Scoundrel"
    COMPLETE_WARRIOR = "Complete Warrior"
    DRACONOMICON = "Draconomicon"
    DRAGON_MAGAZINE = "Dragon #315"
    EBERRON_CAMPAIGN_SETTING = "Eberron Campaign Setting"
    EPIC_LEVEL_HANDBOOK = "Epic Level Handbook"
    HEROES_OF_BATTLE = "Heroes of Battle"
    LORDS_OF_MADNESS = "Lords of Madness"
    MINIATURES_HANDBOOK = "Miniatures Handbook"
    PLAYERS_HANDBOOK_II = "Player's Handbook II"
    RACES_OF_STONE = "Races of Stone"
    RACES_OF_THE_WILD = "Races of the Wild"
    SANDSTORM = "Sandstorm"


class SpellSchool(StrEnum):
    """
    A spell's school, as printed in its entry.

    Nine values, not the eight of ``School``: Universal is a
    school a spell can belong to but not one a specialist can
    choose or prohibit (PHB p. 57).
    """

    NONE = ""
    ABJURATION = "Abjuration"
    CONJURATION = "Conjuration"
    DIVINATION = "Divination"
    ENCHANTMENT = "Enchantment"
    EVOCATION = "Evocation"
    ILLUSION = "Illusion"
    NECROMANCY = "Necromancy"
    TRANSMUTATION = "Transmutation"
    UNIVERSAL = "Universal"
