"""
templates.py
SRD core templates.
"""

from __future__ import annotations

from enum import StrEnum


class KnownCoreTemplate(StrEnum):
    HALF_CELESTIAL = "Half-Celestial"
    HALF_FIEND = "Half-Fiend"
    HALF_DRAGON_RED = "Half-Dragon (Red)"
    HALF_DRAGON_WHITE = "Half-Dragon (White)"
    FIENDISH_CREATURE = "Fiendish Creature"
    CELESTIAL_CREATURE = "Celestial Creature"
    VAMPIRE = "Vampire"
    GHOST = "Ghost"
    LICH = "Lich"
    LYCANTHROPE_WEREWOLF = "Lycanthrope (Werewolf)"
