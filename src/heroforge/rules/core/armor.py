"""
armor.py
SRD core armor and shields.
"""

from __future__ import annotations

from enum import StrEnum


class KnownCoreArmor(StrEnum):
    PADDED = "Padded"
    LEATHER = "Leather"
    STUDDED_LEATHER = "Studded Leather"
    CHAIN_SHIRT = "Chain Shirt"
    HIDE = "Hide"
    SCALE_MAIL = "Scale Mail"
    CHAINMAIL = "Chainmail"
    BREASTPLATE = "Breastplate"
    SPLINT_MAIL = "Splint Mail"
    BANDED_MAIL = "Banded Mail"
    HALF_PLATE = "Half-Plate"
    FULL_PLATE = "Full Plate"
    BUCKLER = "Buckler"
    LIGHT_WOODEN_SHIELD = "Light Wooden Shield"
    LIGHT_STEEL_SHIELD = "Light Steel Shield"
    HEAVY_WOODEN_SHIELD = "Heavy Wooden Shield"
    HEAVY_STEEL_SHIELD = "Heavy Steel Shield"
    TOWER_SHIELD = "Tower Shield"
