"""
races.py
SRD core races.
"""

from __future__ import annotations

from enum import StrEnum


class KnownCoreRace(StrEnum):
    HUMAN = "Human"
    DWARF = "Dwarf"
    ELF = "Elf"
    GNOME = "Gnome"
    HALF_ELF = "Half-Elf"
    HALF_ORC = "Half-Orc"
    HALFLING = "Halfling"
