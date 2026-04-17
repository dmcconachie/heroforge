"""
materials.py
SRD core materials.
"""

from __future__ import annotations

from enum import StrEnum


class KnownCoreMaterial(StrEnum):
    ADAMANTINE = "Adamantine"
    ALCHEMICAL_SILVER = "Alchemical Silver"
    COLD_IRON = "Cold Iron"
    DARKWOOD = "Darkwood"
    DRAGONHIDE = "Dragonhide"
    MITHRAL = "Mithral"
