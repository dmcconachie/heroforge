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
    MaterialRegistry,
    WeaponRegistry,
    adjust_for_material,
    equip_armor,
    equip_item,
    equip_shield,
    equipment_display_name,
    set_material_registry,
    unequip_armor,
    unequip_item,
    unequip_shield,
)
from heroforge.rules.loader import EquipmentLoader

RULES_DIR = Path(__file__).parent.parent.parent / "rules"


@pytest.fixture(autouse=True)
def _load_materials() -> None:
    """Ensure material registry is available."""
    reg = MaterialRegistry()
    loader = EquipmentLoader(RULES_DIR)
    loader.load_materials(reg, "core/materials.yaml")
    set_material_registry(reg)


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

    def test_enhancement_implies_masterwork_acp(self, char: Character) -> None:
        equip_armor(char, FULL_PLATE, enhancement=1)
        acp = char.equipment["armor"]["armor_check_penalty"]
        # Base -6, MW -1 = -5
        assert acp == -5

    def test_explicit_masterwork_acp(self, char: Character) -> None:
        equip_armor(char, FULL_PLATE, masterwork=True)
        acp = char.equipment["armor"]["armor_check_penalty"]
        assert acp == -5


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


# ===================================================
# Material adjustments
# ===================================================


class TestMaterialAdjustments:
    def test_mithral_reduces_acp(self) -> None:
        acp, max_dex, asf = adjust_for_material(-6, 1, 35, "Mithral")
        assert acp == -3
        assert max_dex == 3
        assert asf == 25

    def test_mithral_acp_floors_at_zero(self) -> None:
        acp, _, _ = adjust_for_material(-2, 4, 20, "Mithral")
        assert acp == 0

    def test_darkwood_reduces_acp(self) -> None:
        acp, max_dex, asf = adjust_for_material(-2, -1, 15, "Darkwood")
        assert acp == 0
        assert max_dex == -1  # unchanged
        assert asf == 15  # unchanged

    def test_adamantine_masterwork_only(self) -> None:
        acp, max_dex, asf = adjust_for_material(-6, 1, 35, "Adamantine")
        # Adamantine is masterwork: ACP -1 only
        assert acp == -5
        assert max_dex == 1
        assert asf == 35

    def test_no_material_no_change(self) -> None:
        acp, max_dex, asf = adjust_for_material(-6, 1, 35, "")
        assert acp == -6

    def test_mithral_armor_ac(self, char: Character) -> None:
        equip_armor(char, FULL_PLATE, material="Mithral")
        ac = char.get("ac")
        # 10 + DEX(3, capped at 1+2=3) + armor(8) = 21
        assert ac == 21

    def test_heavy_armor_speed_penalty(self, char: Character) -> None:
        equip_armor(char, FULL_PLATE)
        # Base 30 → 20 with heavy armor
        assert char.get("speed") == 20

    def test_light_armor_no_speed_penalty(self, char: Character) -> None:
        equip_armor(char, CHAIN_SHIRT)
        assert char.get("speed") == 30

    def test_mithral_heavy_still_reduces_speed(self, char: Character) -> None:
        # Mithral heavy → medium category → still -10
        equip_armor(char, FULL_PLATE, material="Mithral")
        assert char.get("speed") == 20

    def test_unequip_restores_speed(self, char: Character) -> None:
        equip_armor(char, FULL_PLATE)
        assert char.get("speed") == 20
        unequip_armor(char)
        assert char.get("speed") == 30


# ===================================================
# Worn magic items
# ===================================================


class TestEquipItem:
    def test_belt_of_strength(self) -> None:
        from heroforge.engine.magic_items import (
            MagicItemDefinition,
        )

        belt = MagicItemDefinition(
            name="Belt of Giant Strength +4",
            effects=[
                {
                    "target": "str_score",
                    "bonus_type": "enhancement",
                    "value": 4,
                }
            ],
        )
        c = Character()
        c.set_ability_score("str", 14)
        equip_item(c, belt)
        assert c.get_ability_score("str") == 18

    def test_unequip_item(self) -> None:
        from heroforge.engine.magic_items import (
            MagicItemDefinition,
        )

        belt = MagicItemDefinition(
            name="Belt of Giant Strength +4",
            effects=[
                {
                    "target": "str_score",
                    "bonus_type": "enhancement",
                    "value": 4,
                }
            ],
        )
        c = Character()
        c.set_ability_score("str", 14)
        equip_item(c, belt)
        assert c.get_ability_score("str") == 18
        unequip_item(c, belt.name)
        assert c.get_ability_score("str") == 14

    def test_ring_of_protection(self) -> None:
        from heroforge.engine.magic_items import (
            MagicItemDefinition,
        )

        ring = MagicItemDefinition(
            name="Ring of Protection +2",
            effects=[
                {
                    "target": "ac",
                    "bonus_type": "deflection",
                    "value": 2,
                }
            ],
        )
        c = Character()
        equip_item(c, ring)
        assert c.get("ac") == 12  # 10 + 2

    def test_item_no_effects(self) -> None:
        from heroforge.engine.magic_items import (
            MagicItemDefinition,
        )

        item = MagicItemDefinition(name="Mundane Trinket")
        c = Character()
        equip_item(c, item)  # should not crash
        assert c.get("ac") == 10


# ===================================================
# Display name
# ===================================================


class TestDisplayName:
    def test_enhancement_only(self) -> None:
        assert equipment_display_name("Lance", enhancement=1) == "+1 Lance"

    def test_enhancement_and_material(self) -> None:
        assert (
            equipment_display_name(
                "Lance",
                enhancement=1,
                material="Bronzewood",
            )
            == "+1 Bronzewood Lance"
        )

    def test_masterwork(self) -> None:
        assert (
            equipment_display_name("Longsword", masterwork=True)
            == "Masterwork Longsword"
        )

    def test_plain(self) -> None:
        assert equipment_display_name("Dagger") == "Dagger"

    def test_name_override(self) -> None:
        assert (
            equipment_display_name(
                "Longsword",
                enhancement=1,
                name="+1 Flaming Longsword",
            )
            == "+1 Flaming Longsword"
        )
