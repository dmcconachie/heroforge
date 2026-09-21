"""
Tests for magic items YAML data.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from cattrs.errors import ClassValidationError

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.derived_pools import install_consumers
from heroforge.engine.enums import Ability, ArmorCategory
from heroforge.engine.equipment import (
    ArmorDefinition,
    equip_armor,
    equip_item,
    unequip_item,
)
from heroforge.engine.magic_items import (
    BodySlot,
    MagicItemDefinition,
    MagicItemRegistry,
)
from heroforge.engine.skills import register_skills_on_character
from heroforge.rules.loader import MagicItemLoader
from heroforge.rules.rules import get_rules
from heroforge.rules.schema import converter


def new_character() -> Character:
    """A blank Character with skills and derived pools wired."""
    c = Character()
    register_skills_on_character(c)
    dp = get_rules().derived_pools
    if dp:
        install_consumers(c, dp)
    return c


RULES_DIR = Path(__file__).parent.parent.parent / "rules"

# One YAML file per slot, named after it.
SLOT_FILES = [s.value for s in BodySlot if s is not BodySlot.NONE]


def _load_items() -> MagicItemRegistry:
    item_reg = MagicItemRegistry()
    loader = MagicItemLoader(RULES_DIR)
    for slot_file in SLOT_FILES:
        loader.load(
            item_reg,
            f"core/magic_items/{slot_file}.yaml",
        )
    return item_reg


class TestTheBodySlots:
    """
    Where an item is worn is a closed set: the eleven body
    slots of the Magic Item Compendium plus the three ways of
    occupying none of them.
    """

    def test_every_loaded_item_names_a_real_slot(self) -> None:
        for defn in _load_items().all_items():
            assert isinstance(defn.slot, BodySlot), defn.name

    def test_a_misspelled_slot_is_refused_at_load(self) -> None:
        with pytest.raises(ClassValidationError):
            converter.structure(
                {"name": "Hat of Doom", "slot": "hed"}, MagicItemDefinition
            )


class TestMagicItemsLoader:
    def test_loads_successfully(self) -> None:
        item_reg = _load_items()
        assert len(item_reg) >= 50

    def test_ring_of_protection(self) -> None:
        item_reg = _load_items()
        r = item_reg.get("Ring of Protection +2")
        assert r is not None
        targets = {e["target"] for e in r.effects}
        assert "ac" in targets

    def test_cloak_of_resistance(self) -> None:
        item_reg = _load_items()
        c = item_reg.get("Cloak of Resistance +3")
        assert c is not None
        targets = {e["target"] for e in c.effects}
        assert "fort_save" in targets
        assert "ref_save" in targets
        assert "will_save" in targets

    def test_belt_of_giant_strength(self) -> None:
        item_reg = _load_items()
        b = item_reg.get("Belt of Giant Strength +4")
        assert b is not None
        assert any(e["target"] == "str_score" for e in b.effects)

    def test_item_definition_fields(self) -> None:
        """MagicItemDefinition has correct fields."""
        item_reg = _load_items()
        ring = item_reg.get("Ring of Protection +2")
        assert ring is not None
        assert ring.source_book == "SRD"
        assert len(ring.effects) > 0


class TestMagicItemEffects:
    def test_ring_of_protection_ac(self) -> None:
        item_reg = _load_items()
        c = Character()
        base_ac = c.get("ac")
        ring = item_reg.get("Ring of Protection +2")
        assert ring is not None
        equip_item(c, ring)
        assert c.get("ac") == base_ac + 2

    def test_ability_enhancement(self) -> None:
        item_reg = _load_items()
        c = Character()
        c.set_ability_score(Ability.STR, 14)
        belt = item_reg.get("Belt of Giant Strength +4")
        assert belt is not None
        equip_item(c, belt)
        assert c.get("str_score") == 18


_FULL_PLATE = ArmorDefinition(
    name="Full Plate",
    category=ArmorCategory.HEAVY,
    armor_bonus=8,
    max_dex_bonus=1,
    armor_check_penalty=-6,
    arcane_spell_failure=35,
    speed_30=20,
    speed_20=15,
)


class TestMonksBeltGate:
    """
    Monk's Belt (DMG p.?): grants AC bonus and unarmed
    damage as a 5th-level monk; for a monk, adds 5 to
    effective monk level. The AC bonus itself gates on
    unarmored, no shield, light load or less (inherited
    from the derived_pools consumer formula).
    """

    def _fighter(self, level: int = 5, wis: int = 10) -> Character:
        c = new_character()
        c.race = "Human"
        c.set_ability_score(Ability.DEX, 10)
        c.set_ability_score(Ability.WIS, wis)
        c.set_class_levels(
            [
                CharacterLevel(
                    character_level=i + 1,
                    class_name="Fighter",
                    hp_roll=10,
                )
                for i in range(level)
            ]
        )
        return c

    def _monk(self, level: int, wis: int = 14) -> Character:
        c = new_character()
        c.race = "Human"
        c.set_ability_score(Ability.DEX, 14)
        c.set_ability_score(Ability.WIS, wis)
        c.set_class_levels(
            [
                CharacterLevel(
                    character_level=i + 1,
                    class_name="Monk",
                    hp_roll=8,
                )
                for i in range(level)
            ]
        )
        return c

    def _multiclass(
        self,
        fighter_level: int,
        monk_level: int,
        wis: int = 14,
    ) -> Character:
        c = new_character()
        c.race = "Human"
        c.set_ability_score(Ability.DEX, 14)
        c.set_ability_score(Ability.WIS, wis)
        levels: list[CharacterLevel] = [
            CharacterLevel(
                character_level=i + 1,
                class_name="Fighter",
                hp_roll=10,
            )
            for i in range(fighter_level)
        ] + [
            CharacterLevel(
                character_level=fighter_level + i + 1,
                class_name="Monk",
                hp_roll=8,
            )
            for i in range(monk_level)
        ]
        c.set_class_levels(levels)
        return c

    def _belt(self) -> MagicItemDefinition:
        return get_rules().magic_items.require("Monk's Belt")

    # Non-monk cases -------------------------------------

    def test_fighter_5_wis_10_bare_belt_gives_plus_1(self) -> None:
        c = self._fighter(level=5, wis=10)
        base = c.get("ac")
        equip_item(c, self._belt())
        # eff monk level = 5; formula = max(0, 0) + 5//5 = 1.
        assert c.get("ac") == base + 1

    def test_fighter_5_wis_14_bare_belt_gives_plus_3(self) -> None:
        c = self._fighter(level=5, wis=14)
        base = c.get("ac")
        equip_item(c, self._belt())
        # eff monk level = 5; formula = 2 (Wis) + 1 = 3.
        assert c.get("ac") == base + 3

    def test_fighter_plate_belt_gives_nothing(self) -> None:
        c = self._fighter(level=5, wis=14)
        equip_armor(c, _FULL_PLATE)
        base = c.get("ac")
        equip_item(c, self._belt())
        # Plate gates off monk AC formula → no delta.
        assert c.get("ac") == base

    def test_fighter_shield_belt_gives_nothing(self) -> None:
        c = self._fighter(level=5, wis=14)
        c.equipment["shield"] = {"name": "Buckler"}
        base = c.get("ac")
        equip_item(c, self._belt())
        assert c.get("ac") == base

    # Monk cases -----------------------------------------

    def test_monk_1_wis_14_belt_delta_plus_1(self) -> None:
        c = self._monk(level=1, wis=14)
        base = c.get("ac")
        equip_item(c, self._belt())
        # eff level 1 → 1+5=6 w/ belt; formula
        # 2 (Wis) + 6//5=1 = 3 vs baseline 2+0=2. Δ = 1.
        assert c.get("ac") - base == 1

    def test_monk_5_wis_14_belt_delta_plus_1(self) -> None:
        c = self._monk(level=5, wis=14)
        base = c.get("ac")
        equip_item(c, self._belt())
        # eff level 5 → 10; formula 2+2=4 vs 2+1=3. Δ=1.
        assert c.get("ac") - base == 1

    def test_monk_10_wis_14_belt_delta_plus_1(self) -> None:
        c = self._monk(level=10, wis=14)
        base = c.get("ac")
        equip_item(c, self._belt())
        # eff level 10 → 15; formula 2+3=5 vs 2+2=4. Δ=1.
        assert c.get("ac") - base == 1

    def test_monk_5_plate_belt_delta_zero(self) -> None:
        c = self._monk(level=5, wis=14)
        equip_armor(c, _FULL_PLATE)
        base = c.get("ac")
        equip_item(c, self._belt())
        # Both the monk's own AC bonus and the belt's
        # contribution are gated off by plate; Δ = 0.
        assert c.get("ac") - base == 0

    # Multiclass -----------------------------------------

    def test_fighter3_monk2_belt_delta_plus_1(self) -> None:
        c = self._multiclass(fighter_level=3, monk_level=2, wis=14)
        base = c.get("ac")
        equip_item(c, self._belt())
        # eff level 2 → 2+5=7; formula 2+1=3 vs 2+0=2.
        assert c.get("ac") - base == 1

    def test_fighter5_monk0_belt_gives_plus_3(self) -> None:
        # This is really _fighter(); included for parity
        # with the plan's multiclass coverage.
        c = self._fighter(level=5, wis=14)
        base = c.get("ac")
        equip_item(c, self._belt())
        assert c.get("ac") - base == 3

    def test_belt_removal_restores_baseline(self) -> None:
        c = self._monk(level=5, wis=14)
        base = c.get("ac")
        equip_item(c, self._belt())
        unequip_item(c, "Monk's Belt")
        assert c.get("ac") == base


class TestSpellResistanceNonStacking:
    """
    Per 3.5e rules, spell resistance from different
    sources does not stack. Item descriptions say 'SR 21'
    or 'SR HD+5' rather than '+N to SR', because only the
    highest applicable SR counts.
    """

    def test_two_sr_items_take_highest(self) -> None:
        c = new_character()
        c.race = "Human"
        # Robe of the Archmagi (SR 18) + Mantle of Spell
        # Resistance (SR 21) → SR 21, not 39.
        robe = get_rules().magic_items.get("Robe of the Archmagi")
        mantle = get_rules().magic_items.require("Mantle of Spell Resistance")
        assert robe is not None
        assert mantle is not None
        equip_item(c, robe)
        equip_item(c, mantle)
        assert c.get("sr") == 21

    def test_single_sr_source(self) -> None:
        c = new_character()
        c.race = "Human"
        mantle = get_rules().magic_items.require("Mantle of Spell Resistance")
        equip_item(c, mantle)
        assert c.get("sr") == 21

    def test_no_sr_sources(self) -> None:
        c = new_character()
        c.race = "Human"
        assert c.get("sr") == 0


class TestMagicItemsSort:
    """
    Within each slot yaml file, every item's
    ``slot`` field must match the filename and
    entries must be sorted alphabetically.
    """

    def _file_items(self, slot_file: str) -> list[tuple[str, dict]]:

        path = RULES_DIR / "core" / "magic_items" / f"{slot_file}.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        if data is None:
            return []
        return list(data.items())

    def test_all_have_slot(self) -> None:
        for slot_file in SLOT_FILES:
            for name, item in self._file_items(slot_file):
                assert "slot" in item, f"{name!r} missing slot"

    def test_slot_matches_filename(self) -> None:
        for slot_file in SLOT_FILES:
            for name, item in self._file_items(slot_file):
                assert item["slot"] == slot_file, (
                    f"{name!r} in {slot_file}.yaml has slot {item['slot']!r}"
                )

    def test_sorted_alphabetically(self) -> None:
        for slot_file in SLOT_FILES:
            names = [n for n, _ in self._file_items(slot_file)]
            sorted_names = sorted(names, key=str.lower)
            assert names == sorted_names, (
                f"{slot_file}.yaml not sorted: {names} != {sorted_names}"
            )
