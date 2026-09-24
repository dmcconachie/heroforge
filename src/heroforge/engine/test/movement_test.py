"""
tests/test_movement.py
----------------------
Test suite for engine/movement.py.

A creature's land speed is a stat, computed through the
speed pool. Climb, fly, swim and burrow are not: they are
separate movement modes a creature either has or lacks,
and two sources of the same mode do not add.
"""

from __future__ import annotations

import pytest

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.effects import apply_buff
from heroforge.engine.enums import Ability, MovementMode
from heroforge.engine.movement import collect_movement
from heroforge.rules.rules import get_rules


def _char(level: int = 5) -> Character:
    c = Character()
    for ab in Ability:
        c.set_ability_score(ab, 10)
    c.set_class_levels(
        [
            CharacterLevel(
                character_level=i + 1, class_name="Wizard", hp_roll=4
            )
            for i in range(level)
        ]
    )
    return c


def _cast(name: str, level: int = 5) -> Character:
    c = _char(level)
    apply_buff(get_rules().buffs.require(name), c, caster_level=level)
    return c


class TestLandSpeed:
    def test_a_walker_has_only_a_land_speed(self) -> None:
        speeds = collect_movement(_char())
        assert speeds == {MovementMode.LAND: 30}

    def test_land_speed_follows_the_speed_pool(self) -> None:
        c = _char()
        c._race_base_speed = 20
        c._graph.invalidate_pool("speed")
        c._graph.invalidate("speed")
        assert collect_movement(c)[MovementMode.LAND] == 20


class TestSpellsThatGrantModes:
    def test_spider_climb_grants_a_climb_speed(self) -> None:
        """PHB p. 283: "a climb speed of 20 feet"."""
        speeds = _cast("Spider Climb")
        assert collect_movement(speeds)[MovementMode.CLIMB] == 20

    def test_spider_climb_leaves_land_speed_alone(self) -> None:
        assert collect_movement(_cast("Spider Climb"))[MovementMode.LAND] == 30

    def test_overland_flight_grants_a_fly_speed(self) -> None:
        """PHB p. 259: "fly at a speed of 40 feet"."""
        speeds = collect_movement(_cast("Overland Flight"))
        assert speeds[MovementMode.FLY] == 40

    def test_modes_do_not_stack(self) -> None:
        """
        Two sources of the same mode give the better one,
        not the sum.
        """
        c = _cast("Spider Climb")
        apply_buff(get_rules().buffs.require("Spider Climb"), c, caster_level=9)
        assert collect_movement(c)[MovementMode.CLIMB] == 20

    def test_a_flier_who_also_climbs_keeps_both(self) -> None:
        c = _char()
        for name in ("Spider Climb", "Overland Flight"):
            apply_buff(get_rules().buffs.require(name), c, caster_level=9)
        speeds = collect_movement(c)
        assert speeds[MovementMode.LAND] == 30
        assert speeds[MovementMode.CLIMB] == 20
        assert speeds[MovementMode.FLY] == 40

    def test_an_inactive_buff_grants_nothing(self) -> None:
        c = _cast("Spider Climb")
        c.toggle_buff("Spider Climb", False)
        assert MovementMode.CLIMB not in collect_movement(c)


class TestHaste:
    """
    "All of the hasted creature's modes of movement
    (including land movement, burrow, climb, fly, and swim)
    increase by 30 feet, to a maximum of twice the
    subject's normal speed using that form of movement.
    This increase counts as an enhancement bonus" (PHB,
    haste).

    Three things have to hold: it reaches every mode, the
    cap bites on any mode slower than 30 ft., and being an
    enhancement bonus it does not stack with another one.
    """

    def test_haste_speeds_up_land(self) -> None:
        c = _cast("Haste")
        assert collect_movement(c)[MovementMode.LAND] == 60

    def test_haste_reaches_climb_and_fly(self) -> None:
        c = _char()
        for name in ("Spider Climb", "Overland Flight", "Haste"):
            apply_buff(get_rules().buffs.require(name), c, caster_level=9)
        speeds = collect_movement(c)
        assert speeds[MovementMode.LAND] == 60
        assert speeds[MovementMode.CLIMB] == 40  # 20 + 30 capped at 2x
        assert speeds[MovementMode.FLY] == 70  # 40 + 30, under the cap

    def test_the_cap_bites_on_a_slow_mode(self) -> None:
        """A 20 ft. climb speed hastes to 40, not 50."""
        c = _char()
        for name in ("Spider Climb", "Haste"):
            apply_buff(get_rules().buffs.require(name), c, caster_level=9)
        assert collect_movement(c)[MovementMode.CLIMB] == 40

    def test_the_cap_bites_on_a_slow_race(self) -> None:
        """A dwarf's 20 ft. land speed hastes to 40, not 50."""
        c = _char()
        c._race_base_speed = 20
        c._graph.invalidate_pool("speed")
        c._graph.invalidate("speed")
        apply_buff(get_rules().buffs.require("Haste"), c, caster_level=9)
        assert collect_movement(c)[MovementMode.LAND] == 40

    def test_haste_does_not_stack_with_expeditious_retreat(self) -> None:
        """
        Both are +30 enhancement bonuses to land speed, so
        the better one applies once: 30 + 30 = 60, not 90.
        """
        c = _char()
        for name in ("Expeditious Retreat", "Haste"):
            apply_buff(get_rules().buffs.require(name), c, caster_level=9)
        assert collect_movement(c)[MovementMode.LAND] == 60

    def test_expeditious_retreat_alone_is_land_only(self) -> None:
        """
        "Your base land speed increases by 30 feet" — it
        does not touch a climb speed.
        """
        c = _char()
        for name in ("Spider Climb", "Expeditious Retreat"):
            apply_buff(get_rules().buffs.require(name), c, caster_level=9)
        speeds = collect_movement(c)
        assert speeds[MovementMode.LAND] == 60
        assert speeds[MovementMode.CLIMB] == 20


class TestHasteCapUsesNormalSpeed:
    """
    "to a maximum of twice the subject's normal speed using
    that form of movement" — normal speed is what the
    creature actually moves at before the haste, not its
    racial base. Armour, a heavy load and a barbarian's
    fast movement have all already changed it.

    Capping against the racial base gets it wrong in both
    directions: too fast in armour, too slow for anything
    that was already quick.
    """

    @staticmethod
    def _fighter_in_full_plate() -> Character:
        from heroforge.engine.equipment import equip_armor

        c = Character()
        for ab in Ability:
            c.set_ability_score(ab, 10)
        c.set_class_levels(
            [
                CharacterLevel(
                    character_level=i + 1, class_name="Fighter", hp_roll=10
                )
                for i in range(5)
            ]
        )
        equip_armor(c, get_rules().armor.require("Full Plate"))
        return c

    @staticmethod
    def _barbarian() -> Character:
        c = Character()
        for ab in Ability:
            c.set_ability_score(ab, 10)
        c.set_class_levels(
            [
                CharacterLevel(
                    character_level=i + 1,
                    class_name="Barbarian",
                    hp_roll=12,
                )
                for i in range(5)
            ]
        )
        return c

    def test_full_plate_slows_the_cap_too(self) -> None:
        """Normal speed 20, so hasted is 40 and not 50."""
        c = self._fighter_in_full_plate()
        assert c.get("speed") == 20
        apply_buff(get_rules().buffs.require("Haste"), c, caster_level=9)
        assert collect_movement(c)[MovementMode.LAND] == 40

    def test_fast_movement_raises_the_cap(self) -> None:
        """Normal speed 40, so hasted is 70 and not 60."""
        c = self._barbarian()
        assert c.get("speed") == 40
        apply_buff(get_rules().buffs.require("Haste"), c, caster_level=9)
        assert collect_movement(c)[MovementMode.LAND] == 70


class TestSlowRacesInHeavyArmour:
    """
    A 20 ft. race in full plate is the case that separates
    the racial base from the normal speed twice over: once
    for the smaller armour penalty a 20 ft. creature takes,
    and once for the dwarf, who takes none at all.

    "Dwarf base land speed is 20 feet. However, dwarves can
    move at this speed even when wearing medium or heavy
    armor or when carrying a medium or heavy load (unlike
    other creatures, whose speed is reduced in such
    situations)" — PHB p. 15.
    """

    @staticmethod
    def _plated(race: str) -> Character:
        from heroforge.engine.equipment import equip_armor
        from heroforge.engine.races import apply_race

        c = Character()
        for ab in Ability:
            c.set_ability_score(ab, 10)
        c.set_class_levels(
            [
                CharacterLevel(
                    character_level=i + 1, class_name="Fighter", hp_roll=10
                )
                for i in range(5)
            ]
        )
        apply_race(get_rules().races.require(race), c)
        equip_armor(c, get_rules().armor.require("Full Plate"))
        return c

    def test_a_halfling_is_slowed_to_15(self) -> None:
        """A 20 ft. base takes -5, not the -10 a 30 ft. does."""
        assert self._plated("Halfling").get("speed") == 15

    def test_a_gnome_is_slowed_to_15(self) -> None:
        assert self._plated("Gnome").get("speed") == 15

    def test_a_dwarf_is_not_slowed_at_all(self) -> None:
        assert self._plated("Dwarf").get("speed") == 20

    def test_a_hasted_halfling_in_plate_caps_at_30(self) -> None:
        """Normal 15, so twice that, not twice the base 20."""
        c = self._plated("Halfling")
        apply_buff(get_rules().buffs.require("Haste"), c, caster_level=9)
        assert collect_movement(c)[MovementMode.LAND] == 30

    def test_a_hasted_dwarf_in_plate_caps_at_40(self) -> None:
        """Never slowed, so normal is still 20 and twice is 40."""
        c = self._plated("Dwarf")
        apply_buff(get_rules().buffs.require("Haste"), c, caster_level=9)
        assert collect_movement(c)[MovementMode.LAND] == 40


class TestBarbariansInArmour:
    """
    A 20 ft. barbarian is where three rules meet, and each
    one moves the answer:

      - fast movement is +10, but only "when not wearing
        heavy armor and not carrying a heavy load"
        (PHB p. 25), so heavy armour switches it off while
        medium leaves it on
      - medium and heavy armour cost a 20 ft. creature 5 ft.,
        where a 30 ft. one loses 10
      - a dwarf pays neither, keeping its speed "even when
        wearing medium or heavy armor" (PHB p. 15)

    Unarmoured the dwarf and the halfling are identical.
    Every other row is a different number, and haste doubles
    whichever one is right rather than twice the racial 20.
    """

    @staticmethod
    def _barbarian(
        race: str, armour: str = "", hasted: bool = False
    ) -> Character:
        from heroforge.engine.equipment import equip_armor
        from heroforge.engine.races import apply_race

        c = Character()
        for ab in Ability:
            c.set_ability_score(ab, 10)
        apply_race(get_rules().races.require(race), c)
        c.set_class_levels(
            [
                CharacterLevel(
                    character_level=i + 1,
                    class_name="Barbarian",
                    hp_roll=12,
                )
                for i in range(5)
            ]
        )
        if armour:
            equip_armor(c, get_rules().armor.require(armour))
        if hasted:
            apply_buff(get_rules().buffs.require("Haste"), c, caster_level=9)
        return c

    # -- unarmoured: fast movement, no penalty, no difference --

    def test_unarmoured_they_agree(self) -> None:
        for race in ("Dwarf", "Halfling"):
            c = self._barbarian(race)
            assert c.get("speed") == 30, race  # 20 + 10

    def test_unarmoured_haste_doubles_to_60(self) -> None:
        for race in ("Dwarf", "Halfling"):
            c = self._barbarian(race, hasted=True)
            assert collect_movement(c)[MovementMode.LAND] == 60, race

    # -- medium armour: fast movement survives, the penalty does not --

    def test_dwarf_in_breastplate_keeps_all_30(self) -> None:
        """
        No armour penalty, and medium does not gate fast
        movement: 20 + 10."""
        assert self._barbarian("Dwarf", "Breastplate").get("speed") == 30

    def test_halfling_in_breastplate_is_25(self) -> None:
        """-5 for the armour, +10 still: 20 - 5 + 10."""
        assert self._barbarian("Halfling", "Breastplate").get("speed") == 25

    def test_haste_doubles_each_of_those(self) -> None:
        dwarf = self._barbarian("Dwarf", "Breastplate", hasted=True)
        halfling = self._barbarian("Halfling", "Breastplate", hasted=True)
        assert collect_movement(dwarf)[MovementMode.LAND] == 60
        assert collect_movement(halfling)[MovementMode.LAND] == 50

    # -- heavy armour: fast movement gated off --

    def test_dwarf_in_full_plate_is_20(self) -> None:
        """Fast movement gated off, but still no penalty."""
        assert self._barbarian("Dwarf", "Full Plate").get("speed") == 20

    def test_halfling_in_full_plate_is_15(self) -> None:
        """Fast movement gated off and -5 for the plate."""
        assert self._barbarian("Halfling", "Full Plate").get("speed") == 15

    def test_haste_caps_at_twice_the_slowed_speed(self) -> None:
        """
        40 and 30 -- not 40 for both, which capping against
        the racial 20 would have given.
        """
        dwarf = self._barbarian("Dwarf", "Full Plate", hasted=True)
        halfling = self._barbarian("Halfling", "Full Plate", hasted=True)
        assert collect_movement(dwarf)[MovementMode.LAND] == 40
        assert collect_movement(halfling)[MovementMode.LAND] == 30

    # -- light armour: neither rule fires --

    def test_light_armour_costs_nothing(self) -> None:
        """
        Light armour has no speed entry and does not gate
        fast movement, so a chain shirt reads as unarmoured.
        """
        for race in ("Dwarf", "Halfling"):
            c = self._barbarian(race, "Chain Shirt")
            assert c.get("speed") == 30, race

    # -- the category, not the piece --

    @pytest.mark.parametrize(
        "armour", ["Breastplate", "Chainmail", "Hide", "Scale Mail"]
    )
    def test_every_medium_armour_behaves_alike(self, armour: str) -> None:
        """
        Medium is medium: -5 for the halfling, none for
        the dwarf, fast movement surviving either way."""
        assert self._barbarian("Dwarf", armour).get("speed") == 30
        assert self._barbarian("Halfling", armour).get("speed") == 25

    @pytest.mark.parametrize(
        "armour",
        ["Banded Mail", "Full Plate", "Half-Plate", "Splint Mail"],
    )
    def test_every_heavy_armour_behaves_alike(self, armour: str) -> None:
        """Heavy gates fast movement off in every case."""
        assert self._barbarian("Dwarf", armour).get("speed") == 20
        assert self._barbarian("Halfling", armour).get("speed") == 15


def test_armour_speed_data_is_uniform_per_category() -> None:
    """
    The tests above use one armour as a stand-in for its
    category, which only holds while the data agrees. Medium
    and heavy both cost a 30 ft. creature 10 and a 20 ft.
    one 5; light costs nothing (PHB Table 7-6).
    """
    expected = {
        "light": (30, 20),
        "medium": (20, 15),
        "heavy": (20, 15),
    }
    seen: dict[str, set[tuple[int, int]]] = {}
    for defn in get_rules().armor.all_entries():
        cat = str(defn.category)
        if cat not in expected:
            continue  # shields carry no speed
        seen.setdefault(cat, set()).add((defn.speed_30, defn.speed_20))
    for cat, want in expected.items():
        assert seen[cat] == {want}, cat
