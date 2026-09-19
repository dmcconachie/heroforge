"""
Per-weapon attack and damage lines.

A weapon's line is the generic attack/damage pool plus everything
that applies to *that* weapon: its enhancement bonus, and only
those feats whose selection matches it. Weapon Focus (Longsword)
must not touch a bow.
"""

from __future__ import annotations

import pytest

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.sheet import gather_sheet
from heroforge.engine.weapons import (
    feat_applies_to_weapon,
    register_weapons_on_character,
)
from heroforge.rules.rules import get_rules


def fighter(level: int = 12) -> Character:
    c = Character()
    c.race = "Human"
    c.set_ability_score("str", 18)
    c.set_ability_score("dex", 14)
    c.set_class_levels(
        [
            CharacterLevel(
                character_level=i + 1, class_name="Fighter", hp_roll=10
            )
            for i in range(level)
        ]
    )
    return c


def arm(c: Character, *weapons: dict) -> Character:
    c.equipment["weapons"] = list(weapons)
    register_weapons_on_character(c)
    return c


def take(c: Character, feat: str, selection: str) -> None:
    c.add_feat(
        feat,
        get_rules().feats.get(feat),
        level=1,
        source="character",
        parameter=selection,
    )


class TestFeatApplicability:
    """Which feats reach which weapon."""

    def _w(self, base: str) -> dict:
        return {"base": base}

    def test_name_match_applies(self) -> None:
        defn = get_rules().feats.get("Weapon Focus")
        assert feat_applies_to_weapon(defn, "Longsword", self._w("Longsword"))

    def test_name_mismatch_does_not_apply(self) -> None:
        defn = get_rules().feats.get("Weapon Focus")
        assert not feat_applies_to_weapon(defn, "Longsword", self._w("Longbow"))

    def test_feat_without_weapon_effects_never_applies(self) -> None:
        defn = get_rules().feats.get("Iron Will")
        assert not feat_applies_to_weapon(defn, None, self._w("Longsword"))


class TestPerWeaponAttack:
    def test_base_line_matches_generic_pool(self) -> None:
        c = arm(fighter(), {"base": "Longsword"})
        sheet = gather_sheet(c, None)
        w = sheet.equipment.weapons[0]
        assert w.attack.total == sheet.combat.attack_melee.total

    def test_enhancement_applies_to_its_own_weapon(self) -> None:
        c = arm(
            fighter(),
            {"base": "Longsword", "enhancement": 3},
            {"base": "Dagger"},
        )
        sword, dagger = gather_sheet(c, None).equipment.weapons
        assert sword.attack.typed.get("enhancement") == 3
        assert "enhancement" not in dagger.attack.typed
        assert sword.attack.total == dagger.attack.total + 3

    def test_weapon_focus_reaches_only_its_weapon(self) -> None:
        c = fighter()
        take(c, "Weapon Focus", "Longsword")
        arm(c, {"base": "Longsword"}, {"base": "Longbow"})
        sword, bow = gather_sheet(c, None).equipment.weapons
        assert sword.attack.typed.get("weapon_focus") == 1
        assert "weapon_focus" not in bow.attack.typed

    def test_ranged_weapon_uses_ranged_base(self) -> None:
        c = arm(fighter(), {"base": "Longbow"})
        sheet = gather_sheet(c, None)
        assert (
            sheet.equipment.weapons[0].attack.total
            == sheet.combat.attack_ranged.total
        )

    def test_greater_weapon_focus_stacks(self) -> None:
        c = fighter()
        take(c, "Weapon Focus", "Longsword")
        take(c, "Greater Weapon Focus", "Longsword")
        arm(c, {"base": "Longsword"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert w.attack.typed.get("weapon_focus") == 1
        assert w.attack.typed.get("greater_weapon_focus") == 1

    def test_two_selections_do_not_cross_contaminate(self) -> None:
        """The bug that motivated per-weapon lines."""
        c = fighter()
        take(c, "Weapon Focus", "Longsword")
        take(c, "Weapon Focus", "Greatsword")
        arm(
            c, {"base": "Longsword"}, {"base": "Greatsword"}, {"base": "Dagger"}
        )
        sword, great, dagger = gather_sheet(c, None).equipment.weapons
        assert sword.attack.typed.get("weapon_focus") == 1
        assert great.attack.typed.get("weapon_focus") == 1
        assert "weapon_focus" not in dagger.attack.typed


class TestPerWeaponDamage:
    def test_weapon_specialization_reaches_only_its_weapon(self) -> None:
        c = fighter()
        take(c, "Weapon Specialization", "Longsword")
        arm(c, {"base": "Longsword"}, {"base": "Dagger"})
        sword, dagger = gather_sheet(c, None).equipment.weapons
        assert sword.damage.typed.get("weapon_specialization") == 2
        assert "weapon_specialization" not in dagger.damage.typed

    def test_enhancement_adds_damage(self) -> None:
        c = arm(fighter(), {"base": "Longsword", "enhancement": 2})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert w.damage.typed.get("enhancement") == 2


class TestWeaponPoolLifecycle:
    def test_reregistering_drops_stale_weapons(self) -> None:
        c = arm(fighter(), {"base": "Longsword"}, {"base": "Dagger"})
        assert len(gather_sheet(c, None).equipment.weapons) == 2
        arm(c, {"base": "Longsword"})
        assert len(gather_sheet(c, None).equipment.weapons) == 1
        assert c.get_pool("weapon_1_attack") is None

    def test_unarmed_character_has_no_weapon_lines(self) -> None:
        c = fighter()
        register_weapons_on_character(c)
        assert gather_sheet(c, None).equipment.weapons == []


class TestWeaponLineCascades:
    def test_strength_change_moves_the_weapon_line(self) -> None:
        """Graph-backed: the generic pool feeds the weapon node."""
        c = arm(fighter(), {"base": "Longsword"})
        before = gather_sheet(c, None).equipment.weapons[0].attack.total
        c.set_ability_score("str", 20)
        after = gather_sheet(c, None).equipment.weapons[0].attack.total
        assert after == before + 1


class TestBreakdownConsistency:
    """
    A line's total must equal the sum of its parts. The damage
    node once omitted the Strength bonus that the breakdown
    listed, so the sheet showed 4 = 3 + 2 + 2.
    """

    @pytest.mark.parametrize(
        "weapon", [{"base": "Longsword"}, {"base": "Longbow"}]
    )
    def test_totals_match_typed_sum(self, weapon: dict) -> None:
        c = fighter()
        take(c, "Weapon Focus", weapon["base"])
        take(c, "Weapon Specialization", weapon["base"])
        arm(c, weapon)
        w = gather_sheet(c, None).equipment.weapons[0]
        assert w.attack.total == sum(w.attack.typed.values())
        assert w.damage.total == sum(w.damage.typed.values())

    def test_strength_reaches_melee_damage_only(self) -> None:
        c = arm(fighter(), {"base": "Longsword"}, {"base": "Longbow"})
        sword, bow = gather_sheet(c, None).equipment.weapons
        assert sword.damage.typed.get("str") == 4
        assert "str" not in bow.damage.typed


class TestWeaponMastery:
    """
    Melee/Ranged Weapon Mastery (PHB II) select a *damage type*,
    not a weapon, so they reach every weapon of that type — and
    only on the right side of the melee/ranged divide.
    """

    def test_melee_mastery_covers_matching_damage_type(self) -> None:
        c = fighter()
        take(c, "Melee Weapon Mastery", "Slashing")
        arm(c, {"base": "Longsword"}, {"base": "Greatsword"})
        for w in gather_sheet(c, None).equipment.weapons:
            assert w.attack.typed.get("melee_weapon_mastery") == 2
            assert w.damage.typed.get("melee_weapon_mastery") == 2

    def test_melee_mastery_skips_other_damage_types(self) -> None:
        c = fighter()
        take(c, "Melee Weapon Mastery", "Slashing")
        arm(c, {"base": "Heavy Mace"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert "melee_weapon_mastery" not in w.attack.typed

    def test_melee_mastery_does_not_reach_ranged(self) -> None:
        """A longbow is piercing, but Melee Mastery is melee-only."""
        c = fighter()
        take(c, "Melee Weapon Mastery", "Piercing")
        arm(c, {"base": "Longbow"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert "melee_weapon_mastery" not in w.attack.typed

    def test_ranged_mastery_applies_to_ranged_only(self) -> None:
        c = fighter()
        take(c, "Ranged Weapon Mastery", "Piercing")
        arm(c, {"base": "Longbow"}, {"base": "Dagger"})
        bow, dagger = gather_sheet(c, None).equipment.weapons
        assert bow.attack.typed.get("ranged_weapon_mastery") == 2
        assert bow.damage.typed.get("ranged_weapon_mastery") == 2
        assert "ranged_weapon_mastery" not in dagger.attack.typed

    def test_ranged_mastery_extends_range_increment(self) -> None:
        c = fighter()
        take(c, "Ranged Weapon Mastery", "Piercing")
        arm(c, {"base": "Longbow"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert w.range_inc == 120  # 100 + 20

    def test_mastery_stacks_with_weapon_focus(self) -> None:
        c = fighter()
        take(c, "Weapon Focus", "Longsword")
        take(c, "Melee Weapon Mastery", "Slashing")
        arm(c, {"base": "Longsword"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert w.attack.typed.get("weapon_focus") == 1
        assert w.attack.typed.get("melee_weapon_mastery") == 2


def finesse_rogue() -> Character:
    """High Dex, low Str — finesse is a clear win."""
    c = Character()
    c.race = "Human"
    c.alignment = "neutral"
    c.set_ability_score("str", 10)
    c.set_ability_score("dex", 20)
    c.set_class_levels(
        [
            CharacterLevel(character_level=i + 1, class_name="Rogue", hp_roll=6)
            for i in range(8)
        ]
    )
    return c


class TestWeaponFinesse:
    """
    PHB p. 102: with a light weapon, rapier, whip or spiked chain
    you may use Dexterity instead of Strength on attack rolls.
    Rapier, whip and spiked chain are not light, so the rule names
    them explicitly.
    """

    def _with_finesse(self, *weapons: dict) -> Character:
        c = finesse_rogue()
        take(c, "Weapon Finesse", None)
        arm(c, *weapons)
        return c

    def test_light_weapon_uses_dex(self) -> None:
        c = self._with_finesse({"base": "Dagger"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert w.attack.typed.get("dex") == 5
        assert "str" not in w.attack.typed

    def test_rapier_qualifies_though_not_light(self) -> None:
        c = self._with_finesse({"base": "Rapier"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert w.attack.typed.get("dex") == 5

    def test_heavy_weapon_still_uses_str(self) -> None:
        c = self._with_finesse({"base": "Greatsword"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert "dex" not in w.attack.typed

    def test_without_the_feat_str_is_used(self) -> None:
        c = finesse_rogue()
        arm(c, {"base": "Dagger"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert "dex" not in w.attack.typed

    def test_damage_still_uses_strength(self) -> None:
        """Finesse changes attack rolls only, never damage."""
        c = self._with_finesse({"base": "Dagger"})
        c.set_ability_score("str", 16)
        w = gather_sheet(c, None).equipment.weapons[0]
        assert w.damage.typed.get("str") == 3
        assert "dex" not in w.damage.typed

    def test_total_matches_breakdown(self) -> None:
        c = self._with_finesse({"base": "Dagger"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert w.attack.total == sum(w.attack.typed.values())


class TestCriticalThreatRange:
    """
    Improved Critical (PHB p. 96) and keen (DMG p. 225) each
    double a weapon's threat range, and explicitly do not stack
    with each other: doubled once, however many sources apply.
    """

    def test_base_threat_range(self) -> None:
        c = arm(fighter(), {"base": "Longsword"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert w.crit_range == "19-20"
        assert w.crit_mult == "x2"

    def test_single_number_threat_range(self) -> None:
        c = arm(fighter(), {"base": "Heavy Mace"})
        assert gather_sheet(c, None).equipment.weapons[0].crit_range == "20"

    def test_improved_critical_doubles(self) -> None:
        """PHB's own example: a longsword goes 19-20 to 17-20."""
        c = fighter()
        take(c, "Improved Critical", "Longsword")
        arm(c, {"base": "Longsword"})
        assert gather_sheet(c, None).equipment.weapons[0].crit_range == "17-20"

    def test_improved_critical_only_its_weapon(self) -> None:
        c = fighter()
        take(c, "Improved Critical", "Longsword")
        arm(c, {"base": "Longsword"}, {"base": "Greatsword"})
        sword, great = gather_sheet(c, None).equipment.weapons
        assert sword.crit_range == "17-20"
        assert great.crit_range == "19-20"

    def test_keen_doubles(self) -> None:
        c = arm(fighter(), {"base": "Longsword", "properties": ["keen"]})
        assert gather_sheet(c, None).equipment.weapons[0].crit_range == "17-20"

    def test_keen_and_improved_critical_do_not_stack(self) -> None:
        c = fighter()
        take(c, "Improved Critical", "Longsword")
        arm(c, {"base": "Longsword", "properties": ["keen"]})
        assert gather_sheet(c, None).equipment.weapons[0].crit_range == "17-20"

    def test_doubling_a_single_number(self) -> None:
        c = fighter()
        take(c, "Improved Critical", "Heavy Mace")
        arm(c, {"base": "Heavy Mace"})
        assert gather_sheet(c, None).equipment.weapons[0].crit_range == "19-20"

    def test_multiplier_is_untouched(self) -> None:
        """Doubling widens the range; it never changes the multiplier."""
        c = fighter()
        take(c, "Improved Critical", "Heavy Pick")
        arm(c, {"base": "Heavy Pick"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert w.crit_mult == "x4"
        assert w.crit_range == "19-20"


class TestTwoWeaponFighting:
    """
    PHB Table 8-10. The penalty depends on whether the off-hand
    weapon is light and whether the character has the Two-Weapon
    Fighting feat:

        normal                    -6 / -10
        off-hand light            -4 /  -8
        TWF feat                  -4 /  -4
        off-hand light + feat     -2 /  -2

    Penalties apply only to weapons declared as a pairing, since
    fighting with two weapons is a choice made per full attack,
    not a property of carrying two.
    """

    def _pair(self, off: str, feat: bool = False) -> Character:
        c = fighter()
        if feat:
            take(c, "Two-Weapon Fighting", None)
        arm(
            c,
            {"base": "Longsword", "hand": "primary"},
            {"base": off, "hand": "off_hand"},
        )
        return c

    def test_normal_penalties(self) -> None:
        c = self._pair("Warhammer")  # one-handed off-hand
        primary, off = gather_sheet(c, None).equipment.weapons
        assert primary.attack.typed.get("two_weapon_fighting") == -6
        assert off.attack.typed.get("two_weapon_fighting") == -10

    def test_light_off_hand(self) -> None:
        c = self._pair("Dagger")
        primary, off = gather_sheet(c, None).equipment.weapons
        assert primary.attack.typed.get("two_weapon_fighting") == -4
        assert off.attack.typed.get("two_weapon_fighting") == -8

    def test_with_the_feat(self) -> None:
        c = self._pair("Warhammer", feat=True)
        primary, off = gather_sheet(c, None).equipment.weapons
        assert primary.attack.typed.get("two_weapon_fighting") == -4
        assert off.attack.typed.get("two_weapon_fighting") == -4

    def test_light_off_hand_with_the_feat(self) -> None:
        c = self._pair("Dagger", feat=True)
        primary, off = gather_sheet(c, None).equipment.weapons
        assert primary.attack.typed.get("two_weapon_fighting") == -2
        assert off.attack.typed.get("two_weapon_fighting") == -2

    def test_undeclared_weapons_take_no_penalty(self) -> None:
        """Carrying two weapons is not fighting with two."""
        c = arm(fighter(), {"base": "Longsword"}, {"base": "Dagger"})
        for w in gather_sheet(c, None).equipment.weapons:
            assert "two_weapon_fighting" not in w.attack.typed

    def test_off_hand_damage_is_half_strength(self) -> None:
        """PHB p. 113: one-half the Strength bonus in the off hand."""
        c = self._pair("Dagger")
        primary, off = gather_sheet(c, None).equipment.weapons
        assert primary.damage.typed.get("str") == 4
        assert off.damage.typed.get("str") == 2

    def test_off_hand_half_strength_rounds_down(self) -> None:
        c = self._pair("Dagger")
        c.set_ability_score("str", 19)  # +4 -> +2
        off = gather_sheet(c, None).equipment.weapons[1]
        assert off.damage.typed.get("str") == 2
