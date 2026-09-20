"""
Tests for creature size: category stepping, PHB Table 7-4
weapon damage stepping, and the effects that change size
(Enlarge Person, Reduce Person, Righteous Might).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.bonus import BonusType
from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.enums import Size
from heroforge.engine.persistence import load_character, save_character
from heroforge.engine.sheet import gather_sheet
from heroforge.engine.size import (
    SIZE_ORDER,
    damage_dice_for_size,
    large_damage_dice,
    net_size_steps,
    step_down_ladder,
    step_size,
    tiny_damage_dice,
)
from heroforge.engine.skills import compute_skill_total
from heroforge.engine.weapons import register_weapons_on_character
from heroforge.rules.rules import get_rules


class TestStepSize:
    def test_order_is_fine_to_colossal(self) -> None:
        assert SIZE_ORDER[0] is Size.FINE
        assert SIZE_ORDER[-1] is Size.COLOSSAL
        assert len(SIZE_ORDER) == 9

    def test_one_step_up(self) -> None:
        assert step_size(Size.MEDIUM, 1) is Size.LARGE

    def test_one_step_down(self) -> None:
        assert step_size(Size.MEDIUM, -1) is Size.SMALL

    def test_zero_steps_is_identity(self) -> None:
        assert step_size(Size.SMALL, 0) is Size.SMALL

    def test_multi_step(self) -> None:
        assert step_size(Size.SMALL, 3) is Size.HUGE

    def test_clamps_at_colossal(self) -> None:
        assert step_size(Size.HUGE, 9) is Size.COLOSSAL

    def test_clamps_at_fine(self) -> None:
        assert step_size(Size.SMALL, -9) is Size.FINE


class TestNetSizeSteps:
    """
    Mirrors bonus.aggregate() for a size-typed bonus: the
    largest increase applies, the largest decrease applies,
    and the two sum. Two +1 effects are one step.
    """

    def test_empty(self) -> None:
        assert net_size_steps([]) == 0

    def test_two_increases_do_not_stack(self) -> None:
        assert net_size_steps([1, 1]) == 1

    def test_largest_increase_wins(self) -> None:
        assert net_size_steps([1, 2]) == 2

    def test_increase_and_decrease_cancel(self) -> None:
        assert net_size_steps([1, -1]) == 0

    def test_two_decreases_do_not_stack(self) -> None:
        assert net_size_steps([-1, -1]) == -1


class TestTable7_4:
    """
    PHB Table 7-4, p. 114. Large is one size category above
    Medium; Tiny is two below, because Small sits between
    them with its own column in Table 7-5.
    """

    @pytest.mark.parametrize(
        ("medium", "large"),
        [
            ("1d2", "1d3"),
            ("1d3", "1d4"),
            ("1d4", "1d6"),
            ("1d6", "1d8"),
            ("1d8", "2d6"),
            ("1d10", "2d8"),
            ("1d12", "3d6"),
            ("2d4", "2d6"),
            ("2d6", "3d6"),
        ],
    )
    def test_large_column(self, medium: str, large: str) -> None:
        assert large_damage_dice(medium) == large

    @pytest.mark.parametrize(
        ("medium", "tiny"),
        [
            ("1d3", "1"),
            ("1d4", "1d2"),
            ("1d6", "1d3"),
            ("1d8", "1d4"),
            ("1d10", "1d6"),
            ("1d12", "1d8"),
            ("2d4", "1d4"),
            ("2d6", "1d8"),
        ],
    )
    def test_tiny_column(self, medium: str, tiny: str) -> None:
        assert tiny_damage_dice(medium) == tiny

    def test_no_damage_is_left_alone(self) -> None:
        assert tiny_damage_dice("0") == "0"
        assert large_damage_dice("0") == "0"

    def test_unknown_die_raises(self) -> None:
        with pytest.raises(KeyError):
            tiny_damage_dice("1d7")


class TestTinyIsOneStepBelowSmall:
    """
    The two printed tables have to agree: whatever Table 7-5
    gives a weapon at Small, Table 7-4's Tiny column must be
    exactly one rung below it on the damage ladder. This is
    what makes Tiny relative to Small rather than to Medium.
    """

    def test_every_weapon_in_the_data(self) -> None:
        reg = get_rules().weapons
        mismatched = []
        for name in sorted(reg._entries):
            defn = reg.get(name)
            if defn.damage_dice in ("0", ""):
                continue
            tiny = tiny_damage_dice(defn.damage_dice)
            expected = step_down_ladder(defn.damage_dice_small)
            if tiny != expected:
                mismatched.append(
                    f"{name}: M={defn.damage_dice} "
                    f"S={defn.damage_dice_small} "
                    f"T={tiny} but one below S is {expected}"
                )
        assert mismatched == []


class TestDamageDiceForSize:
    def test_longsword_ladder(self) -> None:
        # PHB: M 1d8, S 1d6 (Table 7-5), T 1d4 and L 2d6
        # (Table 7-4). Tiny is one step below Small.
        assert damage_dice_for_size("1d8", "1d6", Size.LARGE) == "2d6"
        assert damage_dice_for_size("1d8", "1d6", Size.MEDIUM) == "1d8"
        assert damage_dice_for_size("1d8", "1d6", Size.SMALL) == "1d6"
        assert damage_dice_for_size("1d8", "1d6", Size.TINY) == "1d4"

    def test_sizes_outside_the_tables_raise(self) -> None:
        with pytest.raises(ValueError):
            damage_dice_for_size("1d8", "1d6", Size.HUGE)


def _humanoid(size: str = "Medium") -> Character:
    c = Character(name="Grunt")
    c.set_ability_score("str", 14)
    c.set_ability_score("dex", 14)
    c.levels = [
        CharacterLevel(character_level=1, class_name="Fighter", hp_roll=10)
    ]
    c._invalidate_class_stats()
    c._race_size = size
    return c


def _activate(c: Character, buff_name: str) -> None:
    defn = get_rules().buffs.get(buff_name)
    assert defn is not None, f"{buff_name} not in the buff registry"
    c.register_buff_definition(
        defn.name,
        defn.pool_entries(10, c),
        size_steps=defn.size_steps,
    )
    c.toggle_buff(defn.name, True, caster_level=10)


class TestSizeChangingBuffs:
    def test_enlarge_person_makes_a_medium_human_large(self) -> None:
        c = _humanoid()
        assert c.size == "Medium"
        _activate(c, "Enlarge Person")
        assert c.size == "Large"

    def test_reduce_person_makes_a_medium_human_small(self) -> None:
        c = _humanoid()
        _activate(c, "Reduce Person")
        assert c.size == "Small"

    def test_size_reverts_when_the_buff_drops(self) -> None:
        c = _humanoid()
        _activate(c, "Enlarge Person")
        c.toggle_buff("Enlarge Person", False)
        assert c.size == "Medium"

    def test_enlarge_person_gives_a_size_bonus_not_enhancement(
        self,
    ) -> None:
        """PHB p. 226: +2 size bonus to STR, -2 size penalty to DEX."""
        defn = get_rules().buffs.get("Enlarge Person")
        assert defn is not None
        by_target = {e.target: e for e in defn.effects}
        assert by_target["str_score"].bonus_type is BonusType.SIZE
        assert by_target["dex_score"].bonus_type is BonusType.SIZE


class TestSizeCascades:
    def test_enlarge_person_costs_one_ac_and_attack(self) -> None:
        c = _humanoid()
        ac_before = c.get("ac")
        atk_before = c.get("attack_melee")
        _activate(c, "Enlarge Person")
        # -1 size on AC, and DEX drops 2 (one modifier point).
        assert c.get("ac") == ac_before - 2
        # -1 size on attack, +1 from the STR size bonus.
        assert c.get("attack_melee") == atk_before

    def test_enlarge_person_improves_grapple(self) -> None:
        c = _humanoid()
        before = c.get("grapple")
        _activate(c, "Enlarge Person")
        # +4 special size modifier, +1 from the STR size bonus.
        assert c.get("grapple") == before + 5

    def test_reduce_person_helps_hide(self) -> None:
        c = _humanoid()
        before = c._compute_size_mod_hide()
        _activate(c, "Reduce Person")
        assert c._compute_size_mod_hide() == before + 4

    def test_enlarge_person_doubles_carrying_capacity(self) -> None:
        c = _humanoid()
        light_before = c.carrying_capacity()[0]
        _activate(c, "Enlarge Person")
        # x2 for Large, and STR 14 -> 16 raises the base too.
        assert c.carrying_capacity()[0] > light_before * 2


class TestSizeReachesTheSheet:
    def test_identity_size_follows_an_active_buff(self) -> None:
        c = _humanoid()
        _activate(c, "Enlarge Person")
        assert gather_sheet(c, None).identity.size is Size.LARGE

    def test_identity_size_follows_a_template_override(self) -> None:
        """
        Regression: _identity() read the size off the *race*
        definition, so a template that changed size never
        reached the sheet.
        """
        c = _humanoid()
        c.race = "Human"
        c._size_override = "Large"
        assert gather_sheet(c, None).identity.size is Size.LARGE

    def test_hide_carries_the_size_modifier(self) -> None:
        """
        Regression: _compute_size_mod_hide() existed but had no
        production caller, so a Small character got no Hide
        bonus and Enlarge Person no penalty.
        """
        c = _humanoid()
        hide = get_rules().skills.get("Hide")
        assert hide is not None
        assert compute_skill_total(c, hide).size_mod == 0
        _activate(c, "Enlarge Person")
        # -4 for Large, and the spell's DEX penalty costs a
        # further point of ability modifier.
        after = compute_skill_total(c, hide)
        assert after.size_mod == -4
        assert after.total == after.ability_mod - 4


class TestWeaponDamageBySize:
    def _armed(self, size: str) -> "Character":
        c = _humanoid(size)
        c.equipment["weapons"] = [{"base": "Greataxe"}]
        register_weapons_on_character(c)
        return c

    def test_medium_greataxe(self) -> None:
        sheet = gather_sheet(self._armed("Medium"), None)
        assert sheet.equipment.weapons[0].damage_dice == "1d12"

    def test_small_greataxe_uses_the_printed_small_value(self) -> None:
        """PHB Table 7-5: Greataxe Dmg (S) is 1d10, not 1d8."""
        sheet = gather_sheet(self._armed("Small"), None)
        assert sheet.equipment.weapons[0].damage_dice == "1d10"

    def test_enlarge_person_steps_the_die(self) -> None:
        """PHB Table 7-4: a Large greataxe deals 3d6."""
        c = self._armed("Medium")
        _activate(c, "Enlarge Person")
        sheet = gather_sheet(c, None)
        assert sheet.equipment.weapons[0].damage_dice == "3d6"


class TestSizePersists:
    """
    A rules item only counts when it survives the round trip:
    declared in the input YAML, visible in the output YAML.
    """

    CHAR = """
identity:
  name: Growth Spurt
  race: Human
  alignment: neutral
ability_scores:
  str: 14
  dex: 14
  con: 12
  int: 10
  wis: 10
  cha: 10
levels:
  - level: 1
    class: Fighter
    hp_roll: 10
buffs:
  Enlarge Person:
    active: true
    caster_level: 5
equipment:
  weapons:
    - base: Greataxe
"""

    def test_enlarge_person_survives_load(self, tmp_path: Path) -> None:
        path = tmp_path / "growth.char.yaml"
        path.write_text(self.CHAR)
        c = load_character(path, None)

        assert c.size == "Large"
        sheet = gather_sheet(c, None)
        assert sheet.identity.size is Size.LARGE
        assert sheet.equipment.weapons[0].damage_dice == "3d6"

    def test_saving_keeps_the_buff(self, tmp_path: Path) -> None:
        src = tmp_path / "growth.char.yaml"
        src.write_text(self.CHAR)
        out = tmp_path / "out.char.yaml"
        save_character(load_character(src, None), out)

        reloaded = load_character(out, None)
        assert reloaded.is_buff_active("Enlarge Person")
        assert reloaded.size == "Large"
