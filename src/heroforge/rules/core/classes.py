"""
classes.py
SRD core classes (base + prestige + NPC).
"""

from __future__ import annotations

from enum import StrEnum


class KnownCoreClass(StrEnum):
    ADEPT = "Adept"
    ARCANE_ARCHER = "Arcane Archer"
    ARCANE_TRICKSTER = "Arcane Trickster"
    ARCHMAGE = "Archmage"
    ARISTOCRAT = "Aristocrat"
    ASSASSIN = "Assassin"
    BARBARIAN = "Barbarian"
    BARD = "Bard"
    BLACKGUARD = "Blackguard"
    CLERIC = "Cleric"
    COMMONER = "Commoner"
    DRAGON_DISCIPLE = "Dragon Disciple"
    DRUID = "Druid"
    DUELIST = "Duelist"
    DWARVEN_DEFENDER = "Dwarven Defender"
    ELDRITCH_KNIGHT = "Eldritch Knight"
    EXPERT = "Expert"
    FIGHTER = "Fighter"
    HIEROPHANT = "Hierophant"
    HORIZON_WALKER = "Horizon Walker"
    LOREMASTER = "Loremaster"
    MONK = "Monk"
    MYSTIC_THEURGE = "Mystic Theurge"
    PALADIN = "Paladin"
    RANGER = "Ranger"
    ROGUE = "Rogue"
    SHADOWDANCER = "Shadowdancer"
    SORCERER = "Sorcerer"
    THAUMATURGIST = "Thaumaturgist"
    WARRIOR = "Warrior"
    WIZARD = "Wizard"
