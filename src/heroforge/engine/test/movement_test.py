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
