"""
Tests for the equipment system: armor, shields, weapons.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.character import Character
from heroforge.engine.equipment import (
    ArmorCategory,
    ArmorDefinition,
    ArmorRegistry,
    WeaponRegistry,
    equip_armor,
    equip_shield,
    unequip_armor,
    unequip_shield,
)
from heroforge.rules.loader import EquipmentLoader

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


@pytest.fixture()
def char() -> Character:
    c = Character()
    c.set_ability_score("dex", 16)  # +3 mod
    return c


CHAIN_SHIRT = ArmorDefinition(
    name="Chain Shirt",
    category=ArmorCategory.LIGHT,
    armor_bonus=4,
    max_dex_bonus=4,
    armor_check_penalty=-2,
    arcane_spell_failure=20,
    speed_30=30,
    speed_20=20,
)

FULL_PLATE = ArmorDefinition(
    name="Full Plate",
    category=ArmorCategory.HEAVY,
    armor_bonus=8,
    max_dex_bonus=1,
    armor_check_penalty=-6,
    arcane_spell_failure=35,
    speed_30=20,
    speed_20=15,
)

HEAVY_SHIELD = ArmorDefinition(
    name="Heavy Steel Shield",
    category=ArmorCategory.SHIELD,
    armor_bonus=2,
    max_dex_bonus=-1,
    armor_check_penalty=-2,
    arcane_spell_failure=15,
    speed_30=0,
    speed_20=0,
)


class TestEquipArmor:
    def test_armor_adds_ac(self, char: Character) -> None:
        equip_armor(char, CHAIN_SHIRT)
        ac = char.get("ac")
        # 10 + DEX(3, capped at 4) + armor(4) = 17
        assert ac == 17

    def test_full_plate_caps_dex(self, char: Character) -> None:
        equip_armor(char, FULL_PLATE)
        ac = char.get("ac")
        # 10 + DEX(1, capped) + armor(8) = 19
        assert ac == 19

    def test_unequip_removes_ac(self, char: Character) -> None:
        equip_armor(char, CHAIN_SHIRT)
        unequip_armor(char)
        ac = char.get("ac")
        # 10 + DEX(3) = 13
        assert ac == 13

    def test_equip_is_idempotent(self, char: Character) -> None:
        equip_armor(char, CHAIN_SHIRT)
        equip_armor(char, CHAIN_SHIRT)
        ac = char.get("ac")
        assert ac == 17


class TestEquipShield:
    def test_shield_adds_ac(self, char: Character) -> None:
        equip_shield(char, HEAVY_SHIELD)
        ac = char.get("ac")
        # 10 + DEX(3) + shield(2) = 15
        assert ac == 15

    def test_armor_plus_shield(self, char: Character) -> None:
        equip_armor(char, CHAIN_SHIRT)
        equip_shield(char, HEAVY_SHIELD)
        ac = char.get("ac")
        # 10 + DEX(3) + armor(4) + shield(2) = 19
        assert ac == 19

    def test_unequip_shield(self, char: Character) -> None:
        equip_armor(char, CHAIN_SHIRT)
        equip_shield(char, HEAVY_SHIELD)
        unequip_shield(char)
        ac = char.get("ac")
        # 10 + DEX(3) + armor(4) = 17
        assert ac == 17


class TestEquipmentEnhancement:
    def test_plus_one_armor(self, char: Character) -> None:
        equip_armor(char, CHAIN_SHIRT, enhancement=1)
        ac = char.get("ac")
        # 10 + DEX(3) + armor(4+1) = 18
        assert ac == 18


class TestEquipmentLoader:
    def test_load_armor(self) -> None:
        reg = ArmorRegistry()
        loader = EquipmentLoader(RULES_DIR)
        names = loader.load_armor(reg, "core/armor.yaml")
        assert len(names) >= 16
        fp = reg.get("Full Plate")
        assert fp is not None
        assert fp.armor_bonus == 8

    def test_load_weapons(self) -> None:
        reg = WeaponRegistry()
        loader = EquipmentLoader(RULES_DIR)
        names = loader.load_weapons(reg, "core/weapons.yaml")
        assert len(names) >= 40
        ls = reg.get("Longsword")
        assert ls is not None
        assert ls.damage_dice == "1d8"
        assert ls.critical_range == 19

    def test_all_armor_categories(self) -> None:
        reg = ArmorRegistry()
        loader = EquipmentLoader(RULES_DIR)
        loader.load_armor(reg, "core/armor.yaml")
        assert len(reg.all_armor()) >= 12
        assert len(reg.all_shields()) >= 4
