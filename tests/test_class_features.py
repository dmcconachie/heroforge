"""
Tests for class feature mechanics: rage buffs, inspire
courage, resource tracking, etc.
"""

from __future__ import annotations

from pathlib import Path

from heroforge.engine.character import Character
from heroforge.engine.classes_races import ClassRegistry
from heroforge.engine.effects import (
    BuffRegistry,
    apply_buff,
    remove_buff,
)
from heroforge.engine.resources import (
    ResourceTracker,
)
from heroforge.rules.loader import ClassesLoader

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


def _load_class_buffs() -> BuffRegistry:
    reg = BuffRegistry()
    cr = ClassRegistry()
    ClassesLoader(RULES_DIR).load(
        cr,
        "core/classes",
        buff_registry=reg,
    )
    return reg


class TestBarbarianRage:
    def test_rage_adds_str_con(self) -> None:
        reg = _load_class_buffs()
        c = Character()
        c.set_ability_score("str", 16)
        c.set_ability_score("con", 14)
        rage = reg.get("Barbarian Rage")
        assert rage is not None
        apply_buff(rage, c)
        assert c.get("str_score") == 20  # 16+4
        assert c.get("con_score") == 18  # 14+4

    def test_rage_will_bonus(self) -> None:
        reg = _load_class_buffs()
        c = Character()
        c.set_ability_score("wis", 10)
        rage = reg.get("Barbarian Rage")
        apply_buff(rage, c)
        # Will save = base(0) + WIS(0) + morale(2)
        assert c.get("will_save") == 2

    def test_rage_ac_penalty(self) -> None:
        reg = _load_class_buffs()
        c = Character()
        rage = reg.get("Barbarian Rage")
        base_ac = c.get("ac")
        apply_buff(rage, c)
        assert c.get("ac") == base_ac - 2

    def test_rage_remove(self) -> None:
        reg = _load_class_buffs()
        c = Character()
        c.set_ability_score("str", 16)
        rage = reg.get("Barbarian Rage")
        apply_buff(rage, c)
        remove_buff(rage, c)
        assert c.get("str_score") == 16


class TestInspireCourage:
    def test_inspire_courage_plus_1(self) -> None:
        reg = _load_class_buffs()
        c = Character()
        ic = reg.get("Inspire Courage +1")
        assert ic is not None
        apply_buff(ic, c)
        assert c.get("attack_melee") >= 1


class TestResourceTracker:
    def test_use_and_exhaust(self) -> None:
        r = ResourceTracker(name="Rage", max_formula="3")
        r.reset(3)
        assert r.current == 3
        assert not r.exhausted
        assert r.use()
        assert r.current == 2
        assert r.use()
        assert r.use()
        assert r.exhausted
        assert not r.use()

    def test_reset(self) -> None:
        r = ResourceTracker(name="Turn Undead")
        r.reset(5)
        r.use()
        r.use()
        assert r.current == 3
        r.reset(5)
        assert r.current == 5


class TestClassBuffsLoader:
    def test_all_buffs_load(self) -> None:
        reg = _load_class_buffs()
        assert reg.get("Barbarian Rage") is not None
        assert reg.get("Greater Rage") is not None
        assert reg.get("Mighty Rage") is not None
        assert reg.get("Flurry of Blows") is not None
        assert reg.get("Smite Evil") is not None
        assert reg.get("Inspire Courage +1") is not None

    def test_at_least_10_buffs(self) -> None:
        reg = _load_class_buffs()
        # Count class category buffs
        count = sum(1 for n in reg._defs if reg.get(n) is not None)
        assert count >= 10
