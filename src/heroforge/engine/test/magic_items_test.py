"""
Tests for magic items YAML data.
"""

from __future__ import annotations

from pathlib import Path

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.equipment import (
    ArmorCategory,
    ArmorDefinition,
    equip_armor,
    equip_item,
    unequip_item,
)
from heroforge.engine.magic_items import (
    MagicItemRegistry,
)
from heroforge.rules.loader import MagicItemLoader

RULES_DIR = Path(__file__).parent.parent.parent / "rules"

SLOT_FILES = [
    "head",
    "face",
    "throat",
    "shoulders",
    "body",
    "torso",
    "arms",
    "hands",
    "ring",
    "waist",
    "feet",
    "slotless",
    "tool",
    "consumable",
]


def _load_items() -> MagicItemRegistry:
    item_reg = MagicItemRegistry()
    loader = MagicItemLoader(RULES_DIR)
    for slot_file in SLOT_FILES:
        loader.load(
            item_reg,
            f"core/magic_items/{slot_file}.yaml",
        )
    return item_reg


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
        c.set_ability_score("str", 14)
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

    def _state(self) -> object:
        from heroforge.ui.app_state import AppState

        state = AppState()
        state.load_rules()
        return state

    def _fighter(
        self, state: object, level: int = 5, wis: int = 10
    ) -> Character:
        state.new_character()  # type: ignore[attr-defined]
        c: Character = state.character  # type: ignore[attr-defined]
        c.race = "Human"
        c.set_ability_score("dex", 10)
        c.set_ability_score("wis", wis)
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

    def _monk(self, state: object, level: int, wis: int = 14) -> Character:
        state.new_character()  # type: ignore[attr-defined]
        c: Character = state.character  # type: ignore[attr-defined]
        c.race = "Human"
        c.set_ability_score("dex", 14)
        c.set_ability_score("wis", wis)
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
        self, state: object, fighter_level: int, monk_level: int, wis: int = 14
    ) -> Character:
        state.new_character()  # type: ignore[attr-defined]
        c: Character = state.character  # type: ignore[attr-defined]
        c.race = "Human"
        c.set_ability_score("dex", 14)
        c.set_ability_score("wis", wis)
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

    def _belt(self, state: object) -> object:
        return state.magic_item_registry.get("Monk's Belt")  # type: ignore[attr-defined]

    # Non-monk cases -------------------------------------

    def test_fighter_5_wis_10_bare_belt_gives_plus_1(self) -> None:
        state = self._state()
        c = self._fighter(state, level=5, wis=10)
        base = c.get("ac")
        equip_item(c, self._belt(state))
        # eff monk level = 5; formula = max(0, 0) + 5//5 = 1.
        assert c.get("ac") == base + 1

    def test_fighter_5_wis_14_bare_belt_gives_plus_3(self) -> None:
        state = self._state()
        c = self._fighter(state, level=5, wis=14)
        base = c.get("ac")
        equip_item(c, self._belt(state))
        # eff monk level = 5; formula = 2 (Wis) + 1 = 3.
        assert c.get("ac") == base + 3

    def test_fighter_plate_belt_gives_nothing(self) -> None:
        state = self._state()
        c = self._fighter(state, level=5, wis=14)
        equip_armor(c, _FULL_PLATE)
        base = c.get("ac")
        equip_item(c, self._belt(state))
        # Plate gates off monk AC formula → no delta.
        assert c.get("ac") == base

    def test_fighter_shield_belt_gives_nothing(self) -> None:
        state = self._state()
        c = self._fighter(state, level=5, wis=14)
        c.equipment["shield"] = {"name": "Buckler"}
        base = c.get("ac")
        equip_item(c, self._belt(state))
        assert c.get("ac") == base

    # Monk cases -----------------------------------------

    def test_monk_1_wis_14_belt_delta_plus_1(self) -> None:
        state = self._state()
        c = self._monk(state, level=1, wis=14)
        base = c.get("ac")
        equip_item(c, self._belt(state))
        # eff level 1 → 1+5=6 w/ belt; formula
        # 2 (Wis) + 6//5=1 = 3 vs baseline 2+0=2. Δ = 1.
        assert c.get("ac") - base == 1

    def test_monk_5_wis_14_belt_delta_plus_1(self) -> None:
        state = self._state()
        c = self._monk(state, level=5, wis=14)
        base = c.get("ac")
        equip_item(c, self._belt(state))
        # eff level 5 → 10; formula 2+2=4 vs 2+1=3. Δ=1.
        assert c.get("ac") - base == 1

    def test_monk_10_wis_14_belt_delta_plus_1(self) -> None:
        state = self._state()
        c = self._monk(state, level=10, wis=14)
        base = c.get("ac")
        equip_item(c, self._belt(state))
        # eff level 10 → 15; formula 2+3=5 vs 2+2=4. Δ=1.
        assert c.get("ac") - base == 1

    def test_monk_5_plate_belt_delta_zero(self) -> None:
        state = self._state()
        c = self._monk(state, level=5, wis=14)
        equip_armor(c, _FULL_PLATE)
        base = c.get("ac")
        equip_item(c, self._belt(state))
        # Both the monk's own AC bonus and the belt's
        # contribution are gated off by plate; Δ = 0.
        assert c.get("ac") - base == 0

    # Multiclass -----------------------------------------

    def test_fighter3_monk2_belt_delta_plus_1(self) -> None:
        state = self._state()
        c = self._multiclass(state, fighter_level=3, monk_level=2, wis=14)
        base = c.get("ac")
        equip_item(c, self._belt(state))
        # eff level 2 → 2+5=7; formula 2+1=3 vs 2+0=2.
        assert c.get("ac") - base == 1

    def test_fighter5_monk0_belt_gives_plus_3(self) -> None:
        # This is really _fighter(); included for parity
        # with the plan's multiclass coverage.
        state = self._state()
        c = self._fighter(state, level=5, wis=14)
        base = c.get("ac")
        equip_item(c, self._belt(state))
        assert c.get("ac") - base == 3

    def test_belt_removal_restores_baseline(self) -> None:
        state = self._state()
        c = self._monk(state, level=5, wis=14)
        base = c.get("ac")
        equip_item(c, self._belt(state))
        unequip_item(c, "Monk's Belt")
        assert c.get("ac") == base


class TestSpellResistanceNonStacking:
    """
    Per 3.5e rules, spell resistance from different
    sources does not stack. Item descriptions say 'SR 21'
    or 'SR HD+5' rather than '+N to SR', because only the
    highest applicable SR counts.
    """

    def _state(self) -> object:
        from heroforge.ui.app_state import AppState

        state = AppState()
        state.load_rules()
        return state

    def test_two_sr_items_take_highest(self) -> None:
        state = self._state()
        state.new_character()  # type: ignore[attr-defined]
        c = state.character  # type: ignore[attr-defined]
        c.race = "Human"
        # Robe of the Archmagi (SR 18) + Mantle of Spell
        # Resistance (SR 21) → SR 21, not 39.
        robe = state.magic_item_registry.get("Robe of the Archmagi")
        mantle = state.magic_item_registry.get("Mantle of Spell Resistance")
        assert robe is not None
        assert mantle is not None
        equip_item(c, robe)
        equip_item(c, mantle)
        assert c.get("sr") == 21

    def test_single_sr_source(self) -> None:
        state = self._state()
        state.new_character()  # type: ignore[attr-defined]
        c = state.character  # type: ignore[attr-defined]
        c.race = "Human"
        mantle = state.magic_item_registry.get("Mantle of Spell Resistance")
        equip_item(c, mantle)
        assert c.get("sr") == 21

    def test_no_sr_sources(self) -> None:
        state = self._state()
        state.new_character()  # type: ignore[attr-defined]
        c = state.character  # type: ignore[attr-defined]
        c.race = "Human"
        assert c.get("sr") == 0


class TestMagicItemsSort:
    """
    Within each slot yaml file, every item's
    ``slot`` field must match the filename and
    entries must be sorted alphabetically.
    """

    def _file_items(self, slot_file: str) -> list[tuple[str, dict]]:
        import yaml

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
