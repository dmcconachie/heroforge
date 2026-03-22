"""
tests/test_prerequisites.py
----------------------------
Test suite for engine/prerequisites.py.

Covers:
  - All atomic prerequisite types (stat, ability, feat, skill, class level,
    race, alignment, proficiency, spellcasting, class feature, creature type)
  - Compound prerequisites (all_of, any_of, none_of)
  - DM override short-circuiting
  - FeatAvailability states (AVAILABLE, TAKEN, OVERRIDE, UNAVAILABLE,
    CHAIN_PARTIAL)
  - CapabilityChecker: proficiency from class, race, and EWP feat;
    spellcasting levels; class features; creature types
  - build_prereq_from_yaml() for all vocabulary keys
  - PrerequisiteChecker.available_feats() and prc_availability()
  - Ongoing violation detection
  - Real 3.5e feat chain scenarios
"""

from __future__ import annotations

from heroforge.engine.character import Character, ClassLevel
from heroforge.engine.prerequisites import (
    AbilityPrereq,
    AlignmentPrereq,
    AllOfPrereq,
    AnyOfPrereq,
    CapabilityChecker,
    ClassFeaturePrereq,
    ClassLevelPrereq,
    CreatureTypePrereq,
    FeatAvailability,
    FeatPrereq,
    NoneOfPrereq,
    PrereqResult,
    PrerequisiteChecker,
    ProficiencyPrereq,
    RacePrereq,
    SkillPrereq,
    SpellcastingPrereq,
    StatPrereq,
    build_prereq_from_yaml,
)

# ===========================================================================
# Helpers
# ===========================================================================


def char(**kwargs: object) -> Character:
    c = Character()
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def with_class(
    name: str,
    level: int,
    bab: int = 0,
    fort: int = 0,
    ref: int = 0,
    will: int = 0,
) -> ClassLevel:
    return ClassLevel(
        class_name=name,
        level=level,
        hp_rolls=[8] * level,
        bab_contribution=bab,
        fort_contribution=fort,
        ref_contribution=ref,
        will_contribution=will,
    )


def fighter(n: int) -> Character:
    c = Character()
    c.race = "Human"
    c.set_class_levels(
        [
            with_class(
                "Fighter", n, bab=n, fort=2 + n // 2, ref=n // 3, will=n // 3
            )
        ]
    )
    return c


def make_checker(*feats_with_prereqs: object) -> PrerequisiteChecker:
    """
    Create a PrerequisiteChecker and register feats.
    feats_with_prereqs: (name, prereq, snapshot=False) tuples.
    """
    chk = PrerequisiteChecker()
    for item in feats_with_prereqs:
        if len(item) == 2:
            chk.register_feat(item[0], item[1])
        else:
            chk.register_feat(item[0], item[1], snapshot=item[2])
    return chk


# ===========================================================================
# Atomic prerequisites
# ===========================================================================


class TestStatPrereq:
    def _chk(self) -> PrerequisiteChecker:
        return PrerequisiteChecker()

    def test_met_when_bab_sufficient(self) -> None:
        c = fighter(6)
        result, _ = StatPrereq("bab", 6).check(c, self._chk())
        assert result == PrereqResult.MET

    def test_unmet_when_bab_insufficient(self) -> None:
        c = fighter(3)
        result, details = StatPrereq("bab", 6, label="BAB").check(
            c, self._chk()
        )
        assert result == PrereqResult.UNMET
        assert details[0].need == "+6"
        assert details[0].have == "+3"

    def test_exact_boundary_met(self) -> None:
        c = fighter(5)
        result, _ = StatPrereq("bab", 5).check(c, self._chk())
        assert result == PrereqResult.MET


class TestAbilityPrereq:
    def _chk(self) -> PrerequisiteChecker:
        return PrerequisiteChecker()

    def test_met_when_dex_sufficient(self) -> None:
        c = char()
        c.set_ability_score("dex", 19)
        result, _ = AbilityPrereq("dex", 19).check(c, self._chk())
        assert result == PrereqResult.MET

    def test_unmet_when_dex_insufficient(self) -> None:
        c = char()
        c.set_ability_score("dex", 15)
        result, details = AbilityPrereq("dex", 19).check(c, self._chk())
        assert result == PrereqResult.UNMET
        assert "19" in details[0].need

    def test_str_prereq(self) -> None:
        c = char()
        c.set_ability_score("str", 13)
        result, _ = AbilityPrereq("str", 13).check(c, self._chk())
        assert result == PrereqResult.MET


class TestFeatPrereq:
    def _chk(self) -> PrerequisiteChecker:
        return PrerequisiteChecker()

    def test_met_when_feat_present(self) -> None:
        c = char()
        c.feats = [{"name": "Point Blank Shot"}]
        result, _ = FeatPrereq("Point Blank Shot").check(c, self._chk())
        assert result == PrereqResult.MET

    def test_unmet_when_feat_absent(self) -> None:
        c = char()
        c.feats = []
        result, details = FeatPrereq("Point Blank Shot").check(c, self._chk())
        assert result == PrereqResult.UNMET
        assert details[0].is_feat_dep is True
        assert "Point Blank Shot" in details[0].description


class TestSkillPrereq:
    def _chk(self) -> PrerequisiteChecker:
        return PrerequisiteChecker()

    def test_met_when_ranks_sufficient(self) -> None:
        c = char()
        c.skills = {"Hide": 5}
        result, _ = SkillPrereq("Hide", 5).check(c, self._chk())
        assert result == PrereqResult.MET

    def test_unmet_when_ranks_insufficient(self) -> None:
        c = char()
        c.skills = {"Hide": 3}
        result, details = SkillPrereq("Hide", 5).check(c, self._chk())
        assert result == PrereqResult.UNMET
        assert details[0].have == "3"
        assert details[0].need == "5"

    def test_missing_skill_treated_as_zero(self) -> None:
        c = char()
        c.skills = {}
        result, _ = SkillPrereq("Tumble", 5).check(c, self._chk())
        assert result == PrereqResult.UNMET


class TestClassLevelPrereq:
    def _chk(self) -> PrerequisiteChecker:
        return PrerequisiteChecker()

    def test_met_with_sufficient_fighter_levels(self) -> None:
        c = fighter(4)
        result, _ = ClassLevelPrereq("Fighter", 4).check(c, self._chk())
        assert result == PrereqResult.MET

    def test_unmet_with_insufficient_levels(self) -> None:
        c = fighter(3)
        result, details = ClassLevelPrereq("Fighter", 4).check(c, self._chk())
        assert result == PrereqResult.UNMET
        assert "Fighter" in details[0].description

    def test_class_not_present_treated_as_zero(self) -> None:
        c = fighter(5)
        result, _ = ClassLevelPrereq("Rogue", 1).check(c, self._chk())
        assert result == PrereqResult.UNMET


class TestRacePrereq:
    def _chk(self) -> PrerequisiteChecker:
        return PrerequisiteChecker()

    def test_met_for_matching_race(self) -> None:
        c = char()
        c.race = "Elf"
        result, _ = RacePrereq(["Elf", "Half-Elf"]).check(c, self._chk())
        assert result == PrereqResult.MET

    def test_met_for_any_in_list(self) -> None:
        c = char()
        c.race = "Half-Elf"
        result, _ = RacePrereq(["Elf", "Half-Elf"]).check(c, self._chk())
        assert result == PrereqResult.MET

    def test_unmet_for_non_matching_race(self) -> None:
        c = char()
        c.race = "Human"
        result, details = RacePrereq(["Elf", "Half-Elf"]).check(c, self._chk())
        assert result == PrereqResult.UNMET
        assert "Human" in details[0].have


class TestAlignmentPrereq:
    def _chk(self) -> PrerequisiteChecker:
        return PrerequisiteChecker()

    def test_met_for_lawful_good(self) -> None:
        c = char()
        c.alignment = "lawful_good"
        result, _ = AlignmentPrereq(["lawful_good"]).check(c, self._chk())
        assert result == PrereqResult.MET

    def test_unmet_for_chaotic_neutral(self) -> None:
        c = char()
        c.alignment = "chaotic_neutral"
        result, _ = AlignmentPrereq(["lawful_good", "lawful_neutral"]).check(
            c, self._chk()
        )
        assert result == PrereqResult.UNMET


class TestCreatureTypePrereq:
    def _chk(self) -> PrerequisiteChecker:
        return PrerequisiteChecker()

    def test_met_for_humanoid(self) -> None:
        c = char()
        c.race = "Human"
        result, _ = CreatureTypePrereq(["Humanoid"]).check(c, self._chk())
        assert result == PrereqResult.MET

    def test_unmet_for_wrong_type(self) -> None:
        c = char()
        c.race = "Warforged"
        result, _ = CreatureTypePrereq(["Humanoid"]).check(c, self._chk())
        assert result == PrereqResult.UNMET

    def test_met_for_outsider(self) -> None:
        c = char()
        c.race = "Tiefling"
        result, _ = CreatureTypePrereq(["Outsider"]).check(c, self._chk())
        assert result == PrereqResult.MET


# ===========================================================================
# Compound prerequisites
# ===========================================================================


class TestAllOfPrereq:
    def _chk(self) -> PrerequisiteChecker:
        return PrerequisiteChecker()

    def test_met_when_all_children_met(self) -> None:
        c = fighter(6)
        c.feats = [{"name": "Point Blank Shot"}, {"name": "Precise Shot"}]
        c.set_ability_score("dex", 19)
        prereq = AllOfPrereq(
            [
                StatPrereq("bab", 6),
                FeatPrereq("Point Blank Shot"),
                FeatPrereq("Precise Shot"),
                AbilityPrereq("dex", 19),
            ]
        )
        result, details = prereq.check(c, self._chk())
        assert result == PrereqResult.MET
        assert details == []

    def test_unmet_when_one_child_unmet(self) -> None:
        c = fighter(3)
        prereq = AllOfPrereq([StatPrereq("bab", 6), StatPrereq("bab", 3)])
        result, details = prereq.check(c, self._chk())
        assert result == PrereqResult.UNMET
        assert len(details) == 1  # only BAB +6 unmet

    def test_unmet_collects_all_failing_details(self) -> None:
        c = char()
        c.set_ability_score("dex", 13)
        c.set_ability_score("str", 13)
        c.feats = []
        prereq = AllOfPrereq(
            [
                AbilityPrereq("dex", 19),
                AbilityPrereq("str", 19),
                FeatPrereq("Point Blank Shot"),
            ]
        )
        result, details = prereq.check(c, self._chk())
        assert result == PrereqResult.UNMET
        assert len(details) == 3

    def test_empty_children_always_met(self) -> None:
        c = char()
        result, _ = AllOfPrereq([]).check(c, self._chk())
        assert result == PrereqResult.MET


class TestAnyOfPrereq:
    def _chk(self) -> PrerequisiteChecker:
        return PrerequisiteChecker()

    def test_met_when_first_child_met(self) -> None:
        c = char()
        c.race = "Elf"
        prereq = AnyOfPrereq([RacePrereq(["Elf"]), RacePrereq(["Half-Elf"])])
        result, _ = prereq.check(c, self._chk())
        assert result == PrereqResult.MET

    def test_met_when_second_child_met(self) -> None:
        c = char()
        c.race = "Half-Elf"
        prereq = AnyOfPrereq([RacePrereq(["Elf"]), RacePrereq(["Half-Elf"])])
        result, _ = prereq.check(c, self._chk())
        assert result == PrereqResult.MET

    def test_unmet_when_none_met(self) -> None:
        c = char()
        c.race = "Human"
        prereq = AnyOfPrereq([RacePrereq(["Elf"]), RacePrereq(["Half-Elf"])])
        result, details = prereq.check(c, self._chk())
        assert result == PrereqResult.UNMET
        assert len(details) == 1  # wrapped in single "Any of" detail


class TestNoneOfPrereq:
    def _chk(self) -> PrerequisiteChecker:
        return PrerequisiteChecker()

    def test_met_when_none_of_children_met(self) -> None:
        c = char()
        c.feats = []
        prereq = NoneOfPrereq([FeatPrereq("Vow of Poverty")])
        result, _ = prereq.check(c, self._chk())
        assert result == PrereqResult.MET

    def test_unmet_when_one_child_met(self) -> None:
        c = char()
        c.feats = [{"name": "Vow of Poverty"}]
        prereq = NoneOfPrereq([FeatPrereq("Vow of Poverty")])
        result, _ = prereq.check(c, self._chk())
        assert result == PrereqResult.UNMET


# ===========================================================================
# CapabilityChecker — proficiency
# ===========================================================================


class TestCapabilityCheckerProficiency:
    def _cap(self) -> CapabilityChecker:
        return CapabilityChecker()

    def test_fighter_proficient_with_longsword(self) -> None:
        c = fighter(1)
        assert self._cap().is_proficient(c, "Longsword") is True

    def test_fighter_proficient_with_greataxe(self) -> None:
        c = fighter(1)
        assert self._cap().is_proficient(c, "Greataxe") is True

    def test_wizard_not_proficient_with_longsword(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Wizard", 3)])
        assert self._cap().is_proficient(c, "Longsword") is False

    def test_wizard_proficient_with_dagger(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Wizard", 3)])
        assert self._cap().is_proficient(c, "Dagger") is True

    def test_gnome_proficient_with_gnome_hooked_hammer(self) -> None:
        c = Character()
        c.race = "Gnome"
        c.set_class_levels([with_class("Fighter", 1, bab=1)])
        # Gnome treats gnome hooked hammer as martial
        assert self._cap().is_proficient(c, "Gnome Hooked Hammer") is True

    def test_non_gnome_not_proficient_with_gnome_hooked_hammer(self) -> None:
        c = fighter(1)  # Human fighter
        assert self._cap().is_proficient(c, "Gnome Hooked Hammer") is False

    def test_ewp_feat_grants_exotic_proficiency(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Fighter", 1, bab=1)])
        c.feats = [{"name": "Exotic Weapon Proficiency (Bastard Sword)"}]
        assert self._cap().is_proficient(c, "Bastard Sword") is True

    def test_fighter_not_proficient_with_bastard_sword_without_ewp(
        self,
    ) -> None:
        c = fighter(1)
        # Bastard Sword is exotic; Fighter doesn't auto-get it
        assert self._cap().is_proficient(c, "Bastard Sword") is False

    def test_elf_proficient_with_longsword_even_as_wizard(self) -> None:
        c = Character()
        c.race = "Elf"
        c.set_class_levels([with_class("Wizard", 5)])
        assert self._cap().is_proficient(c, "Longsword") is True

    def test_elf_proficient_with_longbow(self) -> None:
        c = Character()
        c.race = "Elf"
        c.set_class_levels([with_class("Wizard", 1)])
        assert self._cap().is_proficient(c, "Longbow") is True

    def test_dwarf_proficient_with_dwarven_waraxe(self) -> None:
        c = Character()
        c.race = "Dwarf"
        c.set_class_levels([with_class("Fighter", 1, bab=1)])
        assert self._cap().is_proficient(c, "Dwarven Waraxe") is True


# ===========================================================================
# CapabilityChecker — spellcasting
# ===========================================================================


class TestCapabilityCheckerSpellcasting:
    def _cap(self) -> CapabilityChecker:
        return CapabilityChecker()

    def test_wizard_5_can_cast_level_3(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Wizard", 5)])
        assert self._cap().can_cast(c, 3, "arcane") is True

    def test_wizard_1_can_cast_level_1(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Wizard", 1)])
        assert self._cap().can_cast(c, 1, "arcane") is True

    def test_fighter_cannot_cast(self) -> None:
        c = fighter(10)
        assert self._cap().can_cast(c, 1, "either") is False

    def test_paladin_4_can_cast_divine_1(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Paladin", 4)])
        assert self._cap().can_cast(c, 1, "divine") is True

    def test_paladin_3_cannot_cast(self) -> None:
        """Paladin gets spells at level 4."""
        c = Character()
        c.set_class_levels([with_class("Paladin", 3)])
        assert self._cap().can_cast(c, 1, "divine") is False

    def test_cleric_1_can_cast_divine(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Cleric", 1)])
        assert self._cap().can_cast(c, 1, "divine") is True

    def test_cleric_cannot_cast_arcane(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Cleric", 10)])
        assert self._cap().can_cast(c, 1, "arcane") is False

    def test_either_accepts_arcane_caster(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Sorcerer", 3)])
        assert self._cap().can_cast(c, 1, "either") is True

    def test_either_accepts_divine_caster(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Cleric", 3)])
        assert self._cap().can_cast(c, 1, "either") is True


# ===========================================================================
# CapabilityChecker — class features
# ===========================================================================


class TestCapabilityCheckerClassFeatures:
    def _cap(self) -> CapabilityChecker:
        return CapabilityChecker()

    def test_rogue_has_sneak_attack(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Rogue", 1)])
        assert self._cap().has_class_feature(c, "sneak_attack") is True

    def test_rogue_1_does_not_have_sneak_2d6(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Rogue", 1)])
        assert self._cap().has_class_feature(c, "sneak_attack", "2d6") is False

    def test_rogue_3_has_sneak_2d6(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Rogue", 3)])
        assert self._cap().has_class_feature(c, "sneak_attack", "2d6") is True

    def test_fighter_no_sneak_attack(self) -> None:
        c = fighter(10)
        assert self._cap().has_class_feature(c, "sneak_attack") is False

    def test_cleric_has_turn_undead(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Cleric", 1)])
        assert self._cap().has_class_feature(c, "turn_undead") is True

    def test_fighter_no_turn_undead(self) -> None:
        c = fighter(5)
        assert self._cap().has_class_feature(c, "turn_undead") is False

    def test_druid_5_has_wild_shape(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Druid", 5)])
        assert self._cap().has_class_feature(c, "wild_shape") is True

    def test_druid_4_no_wild_shape(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Druid", 4)])
        assert self._cap().has_class_feature(c, "wild_shape") is False


# ===========================================================================
# PrerequisiteChecker — DM overrides
# ===========================================================================


class TestDmOverrides:
    def test_dm_override_short_circuits_unmet_prereqs(self) -> None:
        c = fighter(2)  # bab = 2, doesn't meet +6
        c.add_dm_override("Improved Precise Shot", note="DM approved")

        chk = PrerequisiteChecker()
        chk.register_feat(
            "Improved Precise Shot",
            AllOfPrereq(
                [StatPrereq("bab", 11), FeatPrereq("Point Blank Shot")]
            ),
        )
        result, details = chk.check(
            chk._feat_prereqs["Improved Precise Shot"],
            c,
            "Improved Precise Shot",
        )
        assert result == PrereqResult.OVERRIDE
        assert details == []

    def test_feat_availability_override_state(self) -> None:
        c = fighter(2)
        c.add_dm_override("Improved Precise Shot")

        chk = PrerequisiteChecker()
        chk.register_feat("Improved Precise Shot", StatPrereq("bab", 11))

        avail, details = chk.feat_availability("Improved Precise Shot", c)
        assert avail == FeatAvailability.OVERRIDE
        assert details == []

    def test_no_override_returns_normal_result(self) -> None:
        c = fighter(2)  # no override
        chk = PrerequisiteChecker()
        chk.register_feat("Power Attack", StatPrereq("bab", 1))
        avail, _ = chk.feat_availability("Power Attack", c)
        assert avail == FeatAvailability.AVAILABLE


# ===========================================================================
# FeatAvailability states
# ===========================================================================


class TestFeatAvailabilityStates:
    def test_available_when_all_prereqs_met(self) -> None:
        c = fighter(6)
        chk = PrerequisiteChecker()
        chk.register_feat(
            "Weapon Specialization",
            AllOfPrereq([ClassLevelPrereq("Fighter", 4)]),
        )
        avail, details = chk.feat_availability("Weapon Specialization", c)
        assert avail == FeatAvailability.AVAILABLE
        assert details == []

    def test_taken_when_feat_already_selected(self) -> None:
        c = fighter(6)
        c.feats = [{"name": "Power Attack"}]
        chk = PrerequisiteChecker()
        chk.register_feat("Power Attack", StatPrereq("bab", 1))
        avail, _ = chk.feat_availability("Power Attack", c)
        assert avail == FeatAvailability.TAKEN

    def test_unavailable_when_prereqs_not_met(self) -> None:
        c = fighter(2)
        chk = PrerequisiteChecker()
        chk.register_feat(
            "Improved Precise Shot",
            AllOfPrereq(
                [
                    StatPrereq("bab", 11, label="BAB"),
                    FeatPrereq("Point Blank Shot"),
                    FeatPrereq("Precise Shot"),
                    AbilityPrereq("dex", 19),
                ]
            ),
        )
        avail, details = chk.feat_availability("Improved Precise Shot", c)
        assert avail == FeatAvailability.UNAVAILABLE
        assert len(details) >= 3  # BAB, both feats, DEX all unmet

    def test_chain_partial_when_some_feat_deps_met(self) -> None:
        """
        Improved Precise Shot requires Point Blank Shot AND Precise Shot.
        Character has Point Blank Shot but not Precise Shot.
        → CHAIN_PARTIAL.
        """
        c = fighter(11)
        c.set_ability_score("dex", 19)
        c.feats = [{"name": "Point Blank Shot"}]  # has one, not the other

        chk = PrerequisiteChecker()
        chk.register_feat(
            "Improved Precise Shot",
            AllOfPrereq(
                [
                    StatPrereq("bab", 11, label="BAB"),
                    FeatPrereq("Point Blank Shot"),
                    FeatPrereq("Precise Shot"),
                    AbilityPrereq("dex", 19),
                ]
            ),
        )
        avail, details = chk.feat_availability("Improved Precise Shot", c)
        assert avail == FeatAvailability.CHAIN_PARTIAL
        # Only Precise Shot is unmet
        assert any("Precise Shot" in d.description for d in details)

    def test_no_prereqs_registered_returns_available(self) -> None:
        c = fighter(1)
        chk = PrerequisiteChecker()
        chk.register_feat("Toughness", None)
        avail, _ = chk.feat_availability("Toughness", c)
        assert avail == FeatAvailability.AVAILABLE

    def test_feat_not_in_registry_returns_available(self) -> None:
        c = fighter(1)
        chk = PrerequisiteChecker()
        avail, _ = chk.feat_availability("Unknown Feat", c)
        assert avail == FeatAvailability.AVAILABLE


# ===========================================================================
# available_feats() bulk evaluation
# ===========================================================================


class TestAvailableFeats:
    def test_returns_all_registered_feats(self) -> None:
        c = fighter(6)
        chk = PrerequisiteChecker()
        chk.register_feat("Toughness", None)
        chk.register_feat("Power Attack", StatPrereq("bab", 1))
        chk.register_feat(
            "Great Cleave",
            AllOfPrereq([StatPrereq("bab", 4), FeatPrereq("Cleave")]),
        )

        results = chk.available_feats(c)
        names = [name for name, _, _ in results]
        assert "Toughness" in names
        assert "Power Attack" in names
        assert "Great Cleave" in names

    def test_sorted_alphabetically(self) -> None:
        c = fighter(1)
        chk = PrerequisiteChecker()
        for name in ("Toughness", "Alertness", "Endurance"):
            chk.register_feat(name, None)
        results = chk.available_feats(c)
        names = [n for n, _, _ in results]
        assert names == sorted(names)

    def test_correct_states_in_bulk_results(self) -> None:
        c = fighter(6)
        c.feats = [{"name": "Power Attack"}]  # already taken

        chk = PrerequisiteChecker()
        chk.register_feat("Power Attack", StatPrereq("bab", 1))
        chk.register_feat(
            "Cleave",
            AllOfPrereq([StatPrereq("bab", 1), FeatPrereq("Power Attack")]),
        )
        chk.register_feat(
            "Great Cleave",
            AllOfPrereq([StatPrereq("bab", 4), FeatPrereq("Cleave")]),
        )
        chk.register_feat(
            "Improved Cleave", StatPrereq("bab", 99)
        )  # impossible

        result_map = {name: avail for name, avail, _ in chk.available_feats(c)}
        assert result_map["Power Attack"] == FeatAvailability.TAKEN
        assert (
            result_map["Cleave"] == FeatAvailability.AVAILABLE
        )  # Power Attack taken ✓
        assert (
            result_map["Great Cleave"] == FeatAvailability.UNAVAILABLE
        )  # Cleave not taken
        assert result_map["Improved Cleave"] == FeatAvailability.UNAVAILABLE


# ===========================================================================
# PrC availability
# ===========================================================================


class TestPrcAvailability:
    def test_available_when_prereqs_met(self) -> None:
        c = Character()
        c.race = "Elf"
        c.set_class_levels([with_class("Fighter", 6, bab=6)])
        c.feats = [{"name": "Point Blank Shot"}, {"name": "Precise Shot"}]
        c.set_ability_score("dex", 10)

        chk = PrerequisiteChecker()
        chk.register_prc(
            "Arcane Archer",
            AllOfPrereq(
                [
                    StatPrereq("bab", 6),
                    FeatPrereq("Point Blank Shot"),
                    FeatPrereq("Precise Shot"),
                    AnyOfPrereq(
                        [RacePrereq(["Elf"]), RacePrereq(["Half-Elf"])]
                    ),
                    SpellcastingPrereq(1, "arcane"),
                ]
            ),
        )

        avail, details = chk.prc_availability("Arcane Archer", c)
        # Arcane spellcasting 1st level required but not present
        assert avail == FeatAvailability.UNAVAILABLE
        assert any("arcane" in d.description.lower() for d in details)

    def test_available_when_all_met(self) -> None:
        c = Character()
        c.race = "Elf"
        c.set_class_levels(
            [
                with_class("Fighter", 6, bab=6),
                with_class("Wizard", 1),
            ]
        )
        c.feats = [{"name": "Point Blank Shot"}, {"name": "Precise Shot"}]

        chk = PrerequisiteChecker()
        chk.register_prc(
            "Arcane Archer",
            AllOfPrereq(
                [
                    StatPrereq("bab", 6),
                    FeatPrereq("Point Blank Shot"),
                    FeatPrereq("Precise Shot"),
                    AnyOfPrereq(
                        [RacePrereq(["Elf"]), RacePrereq(["Half-Elf"])]
                    ),
                    SpellcastingPrereq(1, "arcane"),
                ]
            ),
        )
        avail, _ = chk.prc_availability("Arcane Archer", c)
        assert avail == FeatAvailability.AVAILABLE

    def test_taken_when_already_in_class_list(self) -> None:
        c = Character()
        c.set_class_levels([with_class("Arcane Archer", 3, bab=3)])

        chk = PrerequisiteChecker()
        chk.register_prc("Arcane Archer", None)
        avail, _ = chk.prc_availability("Arcane Archer", c)
        assert avail == FeatAvailability.TAKEN

    def test_dm_override_on_prc(self) -> None:
        c = fighter(1)
        c.add_dm_override("Arcane Archer", note="DM approved for campaign")

        chk = PrerequisiteChecker()
        chk.register_prc("Arcane Archer", AllOfPrereq([StatPrereq("bab", 99)]))
        avail, _ = chk.prc_availability("Arcane Archer", c)
        assert avail == FeatAvailability.OVERRIDE


# ===========================================================================
# Ongoing violations
# ===========================================================================


class TestOngoingViolations:
    def test_no_violations_when_all_ongoing_met(self) -> None:
        c = Character()
        c.alignment = "lawful_good"
        c.set_class_levels([with_class("Paladin", 5)])

        chk = PrerequisiteChecker()
        chk.register_prc(
            "Paladin", None, ongoing_prereq=AlignmentPrereq(["lawful_good"])
        )
        violations = chk.ongoing_violations(c)
        assert violations == []

    def test_violation_when_ongoing_unmet(self) -> None:
        c = Character()
        c.alignment = "chaotic_evil"
        c.set_class_levels([with_class("Paladin", 5)])

        chk = PrerequisiteChecker()
        chk.register_prc(
            "Paladin", None, ongoing_prereq=AlignmentPrereq(["lawful_good"])
        )
        violations = chk.ongoing_violations(c)
        assert len(violations) == 1
        assert violations[0][0] == "Paladin"

    def test_ongoing_only_checked_for_classes_entered(self) -> None:
        c = fighter(5)  # no Paladin levels
        chk = PrerequisiteChecker()
        chk.register_prc(
            "Paladin", None, ongoing_prereq=AlignmentPrereq(["lawful_good"])
        )
        violations = chk.ongoing_violations(c)
        assert violations == []


# ===========================================================================
# build_prereq_from_yaml
# ===========================================================================


class TestBuildPrereqFromYaml:
    def _chk(self) -> PrerequisiteChecker:
        return PrerequisiteChecker()

    def test_stat_prereq(self) -> None:
        prereq = build_prereq_from_yaml({"stat": {"key": "bab", "min": 6}})
        assert isinstance(prereq, StatPrereq)
        assert prereq.min_value == 6

    def test_ability_prereq(self) -> None:
        prereq = build_prereq_from_yaml(
            {"ability": {"key": "dex_score", "min": 19}}
        )
        assert isinstance(prereq, AbilityPrereq)
        assert prereq.min_value == 19

    def test_feat_prereq(self) -> None:
        prereq = build_prereq_from_yaml({"feat": "Point Blank Shot"})
        assert isinstance(prereq, FeatPrereq)
        assert prereq.feat_name == "Point Blank Shot"

    def test_skill_prereq(self) -> None:
        prereq = build_prereq_from_yaml(
            {"skill": {"name": "Hide", "min_ranks": 5}}
        )
        assert isinstance(prereq, SkillPrereq)
        assert prereq.min_ranks == 5

    def test_class_level_prereq(self) -> None:
        prereq = build_prereq_from_yaml(
            {"class_level": {"class": "Fighter", "min": 4}}
        )
        assert isinstance(prereq, ClassLevelPrereq)
        assert prereq.class_name == "Fighter"

    def test_race_prereq_string(self) -> None:
        prereq = build_prereq_from_yaml({"race": "Elf"})
        assert isinstance(prereq, RacePrereq)
        assert "Elf" in prereq.races

    def test_race_prereq_list(self) -> None:
        prereq = build_prereq_from_yaml({"race": ["Elf", "Half-Elf"]})
        assert isinstance(prereq, RacePrereq)
        assert len(prereq.races) == 2

    def test_alignment_prereq(self) -> None:
        prereq = build_prereq_from_yaml(
            {"alignment": {"any_of": ["lawful_good", "lawful_neutral"]}}
        )
        assert isinstance(prereq, AlignmentPrereq)
        assert "lawful_good" in prereq.allowed

    def test_proficiency_prereq(self) -> None:
        prereq = build_prereq_from_yaml(
            {"proficient_with": {"weapon": "Bastard Sword"}}
        )
        assert isinstance(prereq, ProficiencyPrereq)
        assert prereq.weapon == "Bastard Sword"

    def test_can_cast_prereq(self) -> None:
        prereq = build_prereq_from_yaml(
            {"can_cast": {"spell_level": 2, "type": "arcane"}}
        )
        assert isinstance(prereq, SpellcastingPrereq)
        assert prereq.min_level == 2
        assert prereq.cast_type == "arcane"

    def test_has_class_feature_prereq(self) -> None:
        prereq = build_prereq_from_yaml(
            {
                "has_class_feature": {
                    "feature": "sneak_attack",
                    "min_value": "2d6",
                }
            }
        )
        assert isinstance(prereq, ClassFeaturePrereq)
        assert prereq.feature == "sneak_attack"
        assert prereq.min_value == "2d6"

    def test_creature_type_prereq(self) -> None:
        prereq = build_prereq_from_yaml(
            {"creature_type_is": {"any_of": ["Humanoid", "Monstrous Humanoid"]}}
        )
        assert isinstance(prereq, CreatureTypePrereq)
        assert "Humanoid" in prereq.allowed

    def test_all_of_compound(self) -> None:
        prereq = build_prereq_from_yaml(
            {
                "all_of": [
                    {"stat": {"key": "bab", "min": 6}},
                    {"feat": "Point Blank Shot"},
                ]
            }
        )
        assert isinstance(prereq, AllOfPrereq)
        assert len(prereq.children) == 2

    def test_any_of_compound(self) -> None:
        prereq = build_prereq_from_yaml(
            {
                "any_of": [
                    {"race": "Elf"},
                    {"race": "Half-Elf"},
                ]
            }
        )
        assert isinstance(prereq, AnyOfPrereq)
        assert len(prereq.children) == 2

    def test_none_of_compound(self) -> None:
        prereq = build_prereq_from_yaml(
            {
                "none_of": [
                    {"feat": "Vow of Poverty"},
                ]
            }
        )
        assert isinstance(prereq, NoneOfPrereq)
        assert len(prereq.children) == 1

    def test_none_returns_none(self) -> None:
        assert build_prereq_from_yaml(None) is None
        assert build_prereq_from_yaml({}) is None

    def test_unknown_key_returns_none(self) -> None:
        result = build_prereq_from_yaml({"totally_made_up": "value"})
        assert result is None

    def test_nested_compound(self) -> None:
        """Arcane Archer prereq tree."""
        prereq = build_prereq_from_yaml(
            {
                "all_of": [
                    {"stat": {"key": "bab", "min": 6}},
                    {"feat": "Point Blank Shot"},
                    {"feat": "Precise Shot"},
                    {
                        "any_of": [
                            {"race": "Elf"},
                            {"race": "Half-Elf"},
                        ]
                    },
                    {"can_cast": {"spell_level": 1, "type": "arcane"}},
                ]
            }
        )
        assert isinstance(prereq, AllOfPrereq)
        assert len(prereq.children) == 5
        any_of = prereq.children[3]
        assert isinstance(any_of, AnyOfPrereq)


# ===========================================================================
# Real 3.5e feat chain scenarios
# ===========================================================================


class TestRealFeatChains:
    def _archery_checker(self) -> PrerequisiteChecker:
        chk = PrerequisiteChecker()
        chk.register_feat("Point Blank Shot", None)
        chk.register_feat("Precise Shot", FeatPrereq("Point Blank Shot"))
        chk.register_feat(
            "Improved Precise Shot",
            AllOfPrereq(
                [
                    FeatPrereq("Point Blank Shot"),
                    FeatPrereq("Precise Shot"),
                    AbilityPrereq("dex", 19),
                    StatPrereq("bab", 11, label="BAB"),
                ]
            ),
        )
        chk.register_feat(
            "Rapid Shot",
            AllOfPrereq(
                [
                    FeatPrereq("Point Blank Shot"),
                    StatPrereq("bab", 1, label="BAB"),
                ]
            ),
        )
        return chk

    def test_no_feats_point_blank_shot_available(self) -> None:
        c = fighter(1)
        chk = self._archery_checker()
        avail, _ = chk.feat_availability("Point Blank Shot", c)
        assert avail == FeatAvailability.AVAILABLE

    def test_with_pbs_precise_shot_available(self) -> None:
        c = fighter(1)
        c.feats = [{"name": "Point Blank Shot"}]
        chk = self._archery_checker()
        avail, _ = chk.feat_availability("Precise Shot", c)
        assert avail == FeatAvailability.AVAILABLE

    def test_without_pbs_precise_shot_unavailable(self) -> None:
        c = fighter(1)
        c.feats = []
        chk = self._archery_checker()
        avail, _ = chk.feat_availability("Precise Shot", c)
        assert avail == FeatAvailability.UNAVAILABLE

    def test_pbs_only_ips_is_chain_partial(self) -> None:
        """Has Point Blank Shot but not Precise Shot → CHAIN_PARTIAL for IPS."""
        c = fighter(11)
        c.set_ability_score("dex", 19)
        c.feats = [{"name": "Point Blank Shot"}]
        chk = self._archery_checker()
        avail, _ = chk.feat_availability("Improved Precise Shot", c)
        assert avail == FeatAvailability.CHAIN_PARTIAL

    def test_full_chain_ips_available(self) -> None:
        c = fighter(11)
        c.set_ability_score("dex", 19)
        c.feats = [
            {"name": "Point Blank Shot"},
            {"name": "Precise Shot"},
        ]
        chk = self._archery_checker()
        avail, _ = chk.feat_availability("Improved Precise Shot", c)
        assert avail == FeatAvailability.AVAILABLE

    def test_weapon_focus_requires_proficiency(self) -> None:
        """
        Weapon Focus (Bastard Sword) requires proficiency with Bastard Sword.
        Fighter without EWP → UNAVAILABLE.
        Fighter with EWP → AVAILABLE.
        """
        chk = PrerequisiteChecker()
        chk.register_feat(
            "Weapon Focus (Bastard Sword)",
            AllOfPrereq(
                [
                    StatPrereq("bab", 1, label="BAB"),
                    ProficiencyPrereq("Bastard Sword"),
                ]
            ),
        )

        c_no_ewp = fighter(1)
        avail, _ = chk.feat_availability(
            "Weapon Focus (Bastard Sword)", c_no_ewp
        )
        assert avail == FeatAvailability.UNAVAILABLE

        c_ewp = fighter(1)
        c_ewp.feats = [{"name": "Exotic Weapon Proficiency (Bastard Sword)"}]
        avail, _ = chk.feat_availability("Weapon Focus (Bastard Sword)", c_ewp)
        assert avail == FeatAvailability.AVAILABLE

    def test_weapon_specialization_requires_fighter_4(self) -> None:
        chk = PrerequisiteChecker()
        chk.register_feat(
            "Weapon Focus (Longsword)",
            AllOfPrereq(
                [
                    StatPrereq("bab", 1),
                    ProficiencyPrereq("Longsword"),
                ]
            ),
        )
        chk.register_feat(
            "Weapon Specialization (Longsword)",
            AllOfPrereq(
                [
                    FeatPrereq("Weapon Focus (Longsword)"),
                    ClassLevelPrereq("Fighter", 4),
                ]
            ),
            snapshot=True,
        )

        c3 = fighter(3)
        c3.feats = [{"name": "Weapon Focus (Longsword)"}]
        avail, _ = chk.feat_availability(
            "Weapon Specialization (Longsword)", c3
        )
        assert avail == FeatAvailability.UNAVAILABLE

        c4 = fighter(4)
        c4.feats = [{"name": "Weapon Focus (Longsword)"}]
        avail, _ = chk.feat_availability(
            "Weapon Specialization (Longsword)", c4
        )
        assert avail == FeatAvailability.AVAILABLE
