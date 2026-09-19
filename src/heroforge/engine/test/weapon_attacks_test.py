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


def atk_sources(c: Character, index: int = 0) -> dict[str, int]:
    """
    Named contributions to a weapon's attack pool.

    The sheet reports attacks as the iterative sequence rather
    than a breakdown, so tests that care which source
    contributed read the pool directly.
    """
    pool = c.get_pool(f"weapon_{index}_attack")
    return pool.breakdown(c) if pool else {}


def atk_total(c: Character, index: int = 0) -> int:
    """A weapon's single-attack bonus: the first iterative."""
    return gather_sheet(c, None).equipment.weapons[index].attack_iteratives[0]


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
        assert w.attack_iteratives[0] == sheet.combat.attack_melee.total

    def test_enhancement_applies_to_its_own_weapon(self) -> None:
        c = arm(
            fighter(),
            {"base": "Longsword", "enhancement": 3},
            {"base": "Dagger"},
        )
        sword, dagger = gather_sheet(c, None).equipment.weapons
        assert atk_sources(c, 0).get("enhancement") == 3
        assert "enhancement" not in atk_sources(c, 1)
        assert atk_total(c, 0) == atk_total(c, 1) + 3

    def test_weapon_focus_reaches_only_its_weapon(self) -> None:
        c = fighter()
        take(c, "Weapon Focus", "Longsword")
        arm(c, {"base": "Longsword"}, {"base": "Longbow"})
        assert atk_sources(c, 0).get("weapon_focus") == 1
        assert "weapon_focus" not in atk_sources(c, 1)

    def test_ranged_weapon_uses_ranged_base(self) -> None:
        c = arm(fighter(), {"base": "Longbow"})
        sheet = gather_sheet(c, None)
        assert (
            sheet.equipment.weapons[0].attack_iteratives[0]
            == sheet.combat.attack_ranged.total
        )

    def test_greater_weapon_focus_stacks(self) -> None:
        c = fighter()
        take(c, "Weapon Focus", "Longsword")
        take(c, "Greater Weapon Focus", "Longsword")
        arm(c, {"base": "Longsword"})
        assert atk_sources(c, 0).get("weapon_focus") == 1
        assert atk_sources(c, 0).get("greater_weapon_focus") == 1

    def test_two_selections_do_not_cross_contaminate(self) -> None:
        """The bug that motivated per-weapon lines."""
        c = fighter()
        take(c, "Weapon Focus", "Longsword")
        take(c, "Weapon Focus", "Greatsword")
        arm(
            c, {"base": "Longsword"}, {"base": "Greatsword"}, {"base": "Dagger"}
        )
        assert atk_sources(c, 0).get("weapon_focus") == 1
        assert atk_sources(c, 1).get("weapon_focus") == 1
        assert "weapon_focus" not in atk_sources(c, 2)


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
        before = atk_total(c)
        c.set_ability_score("str", 20)
        after = atk_total(c)
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
        weapons = gather_sheet(c, None).equipment.weapons
        for index, w in enumerate(weapons):
            assert atk_sources(c, index).get("melee_weapon_mastery") == 2
            assert w.damage.typed.get("melee_weapon_mastery") == 2

    def test_melee_mastery_skips_other_damage_types(self) -> None:
        c = fighter()
        take(c, "Melee Weapon Mastery", "Slashing")
        arm(c, {"base": "Heavy Mace"})
        assert "melee_weapon_mastery" not in atk_sources(c, 0)

    def test_melee_mastery_does_not_reach_ranged(self) -> None:
        """A longbow is piercing, but Melee Mastery is melee-only."""
        c = fighter()
        take(c, "Melee Weapon Mastery", "Piercing")
        arm(c, {"base": "Longbow"})
        assert "melee_weapon_mastery" not in atk_sources(c, 0)

    def test_ranged_mastery_applies_to_ranged_only(self) -> None:
        c = fighter()
        take(c, "Ranged Weapon Mastery", "Piercing")
        arm(c, {"base": "Longbow"}, {"base": "Dagger"})
        bow, dagger = gather_sheet(c, None).equipment.weapons
        assert atk_sources(c, 0).get("ranged_weapon_mastery") == 2
        assert bow.damage.typed.get("ranged_weapon_mastery") == 2
        assert "ranged_weapon_mastery" not in atk_sources(c, 1)

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
        assert atk_sources(c, 0).get("weapon_focus") == 1
        assert atk_sources(c, 0).get("melee_weapon_mastery") == 2


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
        # Dex 20 (+5) against Str 10 (+0): finesse is worth +5.
        c = self._with_finesse({"base": "Dagger"})
        generic = gather_sheet(c, None).combat.attack_melee.total
        assert atk_total(c) == generic + 5

    def test_rapier_qualifies_though_not_light(self) -> None:
        c = self._with_finesse({"base": "Rapier"})
        generic = gather_sheet(c, None).combat.attack_melee.total
        assert atk_total(c) == generic + 5

    def test_heavy_weapon_still_uses_str(self) -> None:
        c = self._with_finesse({"base": "Greatsword"})
        generic = gather_sheet(c, None).combat.attack_melee.total
        assert atk_total(c) == generic

    def test_without_the_feat_str_is_used(self) -> None:
        c = finesse_rogue()
        arm(c, {"base": "Dagger"})
        generic = gather_sheet(c, None).combat.attack_melee.total
        assert atk_total(c) == generic

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
        assert w.damage.total == sum(w.damage.typed.values())


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
        assert atk_sources(c, 0).get("two_weapon_fighting") == -6
        assert atk_sources(c, 1).get("two_weapon_fighting") == -10

    def test_light_off_hand(self) -> None:
        c = self._pair("Dagger")
        primary, off = gather_sheet(c, None).equipment.weapons
        assert atk_sources(c, 0).get("two_weapon_fighting") == -4
        assert atk_sources(c, 1).get("two_weapon_fighting") == -8

    def test_with_the_feat(self) -> None:
        c = self._pair("Warhammer", feat=True)
        primary, off = gather_sheet(c, None).equipment.weapons
        assert atk_sources(c, 0).get("two_weapon_fighting") == -4
        assert atk_sources(c, 1).get("two_weapon_fighting") == -4

    def test_light_off_hand_with_the_feat(self) -> None:
        c = self._pair("Dagger", feat=True)
        primary, off = gather_sheet(c, None).equipment.weapons
        assert atk_sources(c, 0).get("two_weapon_fighting") == -2
        assert atk_sources(c, 1).get("two_weapon_fighting") == -2

    def test_undeclared_weapons_take_no_penalty(self) -> None:
        """Carrying two weapons is not fighting with two."""
        c = arm(fighter(), {"base": "Longsword"}, {"base": "Dagger"})
        for index in range(2):
            assert "two_weapon_fighting" not in atk_sources(c, index)

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


class TestOffHandAttackCount:
    """
    PHB p. 160: an off-hand weapon gets one extra attack, not the
    full iterative sequence. Improved Two-Weapon Fighting adds a
    second at -5 and Greater adds a third at -10.
    """

    def _pair(self, *feats: str) -> Character:
        c = fighter(16)  # BAB 16 -> four primary iteratives
        take(c, "Two-Weapon Fighting", None)
        for f in feats:
            take(c, f, None)
        arm(
            c,
            {"base": "Longsword", "hand": "primary"},
            {"base": "Dagger", "hand": "off_hand"},
        )
        return c

    def test_primary_keeps_full_iteratives(self) -> None:
        primary = gather_sheet(self._pair(), None).equipment.weapons[0]
        assert len(primary.attack_iteratives) == 4

    def test_off_hand_gets_one_attack(self) -> None:
        off = gather_sheet(self._pair(), None).equipment.weapons[1]
        assert len(off.attack_iteratives) == 1

    def test_improved_adds_a_second_at_minus_five(self) -> None:
        c = self._pair("Improved Two-Weapon Fighting")
        off = gather_sheet(c, None).equipment.weapons[1]
        assert len(off.attack_iteratives) == 2
        assert off.attack_iteratives[1] == off.attack_iteratives[0] - 5

    def test_greater_adds_a_third_at_minus_ten(self) -> None:
        c = self._pair(
            "Improved Two-Weapon Fighting", "Greater Two-Weapon Fighting"
        )
        off = gather_sheet(c, None).equipment.weapons[1]
        assert len(off.attack_iteratives) == 3
        assert off.attack_iteratives[2] == off.attack_iteratives[0] - 10

    def test_undeclared_weapon_keeps_iteratives(self) -> None:
        c = fighter(16)
        arm(c, {"base": "Longsword"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert len(w.attack_iteratives) == 4


class TestConditionalItemGrant:
    """
    Gloves of the Balanced Hand (MIC p. 105) confer Two-Weapon
    Fighting, and Improved Two-Weapon Fighting as well if the
    wearer already had TWF of their own.
    """

    def _wearer(self, own_twf: bool) -> Character:
        c = fighter(16)
        if own_twf:
            take(c, "Two-Weapon Fighting", None)
        c.equipment["worn"] = ["Gloves of the Balanced Hand"]
        from heroforge.engine.feats import refresh_granted_feats

        refresh_granted_feats(c)
        return c

    def test_grants_twf_to_someone_without_it(self) -> None:
        c = self._wearer(own_twf=False)
        assert c.has_feat("Two-Weapon Fighting")
        assert not c.has_feat("Improved Two-Weapon Fighting")

    def test_grants_improved_when_already_had_twf(self) -> None:
        c = self._wearer(own_twf=True)
        assert c.has_feat("Improved Two-Weapon Fighting")

    def test_gloves_own_grant_does_not_satisfy_the_condition(self) -> None:
        """The gloves must not bootstrap themselves to Improved."""
        c = self._wearer(own_twf=False)
        assert not c.has_feat("Improved Two-Weapon Fighting")


class TestWeaponMaterials:
    """
    Most special materials bypass damage reduction or change
    hardness, which are conditional and do not move a number on
    the sheet. Alchemical silver is the exception: DMG p. 285
    gives a -1 penalty on the damage roll.
    """

    def test_alchemical_silver_penalises_damage(self) -> None:
        c = arm(
            fighter(),
            {"base": "Light Mace", "material": "Alchemical Silver"},
            {"base": "Light Mace"},
        )
        silver, plain = gather_sheet(c, None).equipment.weapons
        assert silver.damage.typed.get("material") == -1
        assert "material" not in plain.damage.typed
        assert silver.damage.total == plain.damage.total - 1

    def test_silver_does_not_touch_attack(self) -> None:
        c = arm(
            fighter(), {"base": "Light Mace", "material": "Alchemical Silver"}
        )
        assert "material" not in atk_sources(c, 0)

    def test_other_materials_move_no_number(self) -> None:
        """Adamantine and cold iron bypass DR; they add nothing."""
        c = arm(
            fighter(),
            {"base": "Longsword", "material": "Adamantine"},
            {"base": "Longsword", "material": "Cold Iron"},
        )
        weapons = gather_sheet(c, None).equipment.weapons
        for index, w in enumerate(weapons):
            assert "material" not in w.damage.typed
            assert "material" not in atk_sources(c, index)


class TestRapidShot:
    """
    PHB: Rapid Shot grants one extra ranged attack at the highest
    base attack bonus, and every ranged attack that round takes
    -2. It requires a full attack, so it shapes the iterative
    sequence rather than the single-attack total.
    """

    def _archer(self, rapid: bool) -> Character:
        c = fighter(11)  # BAB 11 -> three iteratives
        take(c, "Point Blank Shot", None)
        if rapid:
            take(c, "Rapid Shot", None)
        arm(c, {"base": "Longbow"})
        return c

    def test_without_rapid_shot(self) -> None:
        w = gather_sheet(self._archer(False), None).equipment.weapons[0]
        assert len(w.attack_iteratives) == 3

    def test_adds_one_attack_at_highest_bonus(self) -> None:
        w = gather_sheet(self._archer(True), None).equipment.weapons[0]
        assert len(w.attack_iteratives) == 4
        assert w.attack_iteratives[0] == w.attack_iteratives[1]

    def test_every_attack_takes_minus_two(self) -> None:
        plain = gather_sheet(self._archer(False), None).equipment.weapons[0]
        rapid = gather_sheet(self._archer(True), None).equipment.weapons[0]
        assert rapid.attack_iteratives[0] == plain.attack_iteratives[0] - 2
        assert rapid.attack_iteratives[2] == plain.attack_iteratives[1] - 2
        assert rapid.attack_iteratives[3] == plain.attack_iteratives[2] - 2

    def test_melee_weapons_unaffected(self) -> None:
        c = fighter(11)
        take(c, "Point Blank Shot", None)
        take(c, "Rapid Shot", None)
        arm(c, {"base": "Longsword"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert len(w.attack_iteratives) == 3


class TestWeaponStanceInName:
    """
    The stance a weapon is being used in rides in its display
    name, since it changes how the iteratives read:

        +5 Dagger (TWF: Primary)
        +3 Longbow (Rapid Shot)
        +1 Greatsword (Power Attack: 5)
    """

    def test_twf_primary(self) -> None:
        c = fighter()
        take(c, "Two-Weapon Fighting", None)
        arm(
            c,
            {"base": "Dagger", "enhancement": 5, "hand": "primary"},
            {"base": "Dagger", "hand": "off_hand"},
        )
        primary, off = gather_sheet(c, None).equipment.weapons
        assert primary.name == "+5 Dagger (TWF: Primary)"
        assert off.name == "Dagger (TWF: Off-hand)"

    def test_rapid_shot(self) -> None:
        c = fighter()
        take(c, "Point Blank Shot", None)
        take(c, "Rapid Shot", None)
        arm(c, {"base": "Longbow", "enhancement": 3})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert w.name == "+3 Longbow (Rapid Shot)"

    def test_no_stance_leaves_the_name_alone(self) -> None:
        c = arm(fighter(), {"base": "Longsword", "enhancement": 1})
        assert gather_sheet(c, None).equipment.weapons[0].name == (
            "+1 Longsword"
        )

    def test_rapid_shot_not_shown_on_a_melee_weapon(self) -> None:
        c = fighter()
        take(c, "Point Blank Shot", None)
        take(c, "Rapid Shot", None)
        arm(c, {"base": "Longsword"})
        assert gather_sheet(c, None).equipment.weapons[0].name == "Longsword"

    def test_parameterised_buff_shows_its_value(self) -> None:
        """Power Attack: 5, once such a buff is active."""
        from heroforge.engine.bonus import BonusEntry, BonusType

        c = arm(fighter(), {"base": "Greatsword", "enhancement": 1})
        c.register_buff_definition(
            "Power Attack",
            [
                (
                    "attack_melee",
                    BonusEntry(
                        value=-5,
                        bonus_type=BonusType.UNTYPED,
                        source="power_attack",
                    ),
                )
            ],
        )
        c.toggle_buff("Power Attack", True, parameter=5)
        w = gather_sheet(c, None).equipment.weapons[0]
        assert w.name == "+1 Greatsword (Power Attack: 5)"

    def test_stances_combine(self) -> None:
        c = fighter()
        take(c, "Two-Weapon Fighting", None)
        arm(
            c,
            {"base": "Dagger", "hand": "primary"},
            {"base": "Dagger", "hand": "off_hand"},
        )
        assert gather_sheet(c, None).equipment.weapons[0].name == (
            "Dagger (TWF: Primary)"
        )


class TestAttackTotalMatchesFirstIterative:
    """
    The breakdown and the sequence are the same number seen two
    ways, so anything shaping the sequence has to show in the
    breakdown as well. Rapid Shot's -2 is the case that forced
    this: it applies to every attack that round, so it belongs
    on the line and not only on the iteratives.
    """

    def _check(self, c: Character) -> None:
        for w in gather_sheet(c, None).equipment.weapons:
            assert w.attack.total == w.attack_iteratives[0]
            assert w.attack.total == sum(w.attack.typed.values())

    def test_plain_weapon(self) -> None:
        self._check(arm(fighter(), {"base": "Longsword"}))

    def test_with_feats_and_enhancement(self) -> None:
        c = fighter()
        take(c, "Weapon Focus", "Longsword")
        take(c, "Melee Weapon Mastery", "Slashing")
        arm(c, {"base": "Longsword", "enhancement": 3})
        self._check(c)

    def test_rapid_shot_penalty_is_on_the_line(self) -> None:
        c = fighter(11)
        take(c, "Point Blank Shot", None)
        take(c, "Rapid Shot", None)
        arm(c, {"base": "Longbow"})
        w = gather_sheet(c, None).equipment.weapons[0]
        assert w.attack.typed.get("rapid_shot") == -2
        self._check(c)

    def test_two_weapon_pairing(self) -> None:
        c = fighter()
        take(c, "Two-Weapon Fighting", None)
        arm(
            c,
            {"base": "Longsword", "hand": "primary"},
            {"base": "Dagger", "hand": "off_hand"},
        )
        self._check(c)

    def test_finesse_weapon(self) -> None:
        c = finesse_rogue()
        take(c, "Weapon Finesse", None)
        arm(c, {"base": "Dagger"})
        self._check(c)
