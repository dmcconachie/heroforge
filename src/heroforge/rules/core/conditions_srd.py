"""
conditions_srd.py
SRD core conditions.
"""

from __future__ import annotations

from enum import StrEnum


class KnownCoreCondition(StrEnum):
    COWERING = "Cowering"
    DEAFENED = "Deafened"
    ENERGY_DRAINED = "Energy Drained"
    INVISIBLE = "Invisible"
    PRONE = "Prone"
    CONFUSED = "Confused"
    DAZED = "Dazed"
    DISABLED = "Disabled"
    DYING = "Dying"
    FASCINATED = "Fascinated"
    FLAT_FOOTED = "Flat-Footed"
    GRAPPLING = "Grappling"
    HELPLESS = "Helpless"
    NAUSEATED = "Nauseated"
    PARALYZED = "Paralyzed"
    PETRIFIED = "Petrified"
    STAGGERED = "Staggered"
    TURNED = "Turned"
