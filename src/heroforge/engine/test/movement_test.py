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
