"""
tests/test_stat.py
------------------
Test suite for engine/stat.py.

Tests cover:
  - StatNode construction and default compute behaviour
  - StatGraph registration, dependency ordering, cycle detection
  - Lazy evaluation and caching
  - Dirty-flag cascade through the graph
  - BonusPool integration
  - Conditional BonusEntry interaction via character mock
  - Standard compute helpers
  - Real 3.5e stat chain scenarios (STR score → modifier → attack bonus)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from heroforge.engine.bonus import BonusEntry, BonusPool, BonusType
from heroforge.engine.stat import (
    StatError,
    StatGraph,
    StatNode,
    compute_ability_modifier,
    compute_capped_dex,
    compute_max_zero,
    compute_save,
    compute_sum,
)

# ===========================================================================
# Helpers
# ===========================================================================


def simple_node(
    key: str,
    base: int = 0,
    inputs: list[str] | None = None,
    pools: list[str] | None = None,
    compute: Callable | None = None,
) -> StatNode:
    return StatNode(
        key=key,
        base=base,
        inputs=inputs or [],
        pools=pools or [],
        compute=compute,
    )


def make_pool(key: str, *entries: BonusEntry) -> BonusPool:
    p = BonusPool(key)
    for i, e in enumerate(entries):
        label = e.source if e.source else f"entry_{i}"
        p.set_source(label, [e])
    return p


def bonus(
    value: int, btype: BonusType = BonusType.UNTYPED, source: str = "test"
) -> BonusEntry:
    return BonusEntry(value=value, bonus_type=btype, source=source)


class MockCharacter:
    """Minimal stand-in so conditional BonusEntries can be tested."""

    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


# ===========================================================================
# StatNode construction
# ===========================================================================


class TestStatNodeConstruction:
    def test_node_with_base_defaults_to_base_plus_bonus(self) -> None:
        g = StatGraph()
        g.register_node(simple_node("hp", base=10))
        assert g.resolve("hp") == 10

    def test_node_base_none_defaults_to_zero_plus_bonus(self) -> None:
        g = StatGraph()
        g.register_node(simple_node("x", base=None))
        assert g.resolve("x") == 0

    def test_node_with_pool_adds_pool_total_to_base(self) -> None:
        g = StatGraph()
        p = make_pool("hp_bonus", bonus(5))
        g.register_pool(p)
        g.register_node(simple_node("hp", base=10, pools=["hp_bonus"]))
        assert g.resolve("hp") == 15

    def test_node_with_custom_compute(self) -> None:
        g = StatGraph()
        g.register_node(
            StatNode(
                key="doubled",
                base=4,
                compute=lambda bt: 4 * 2 + bt,
            )
        )
        assert g.resolve("doubled") == 8

    def test_node_is_initially_dirty(self) -> None:
        node = simple_node("x", base=1)
        assert node.is_dirty is True

    def test_node_is_clean_after_resolve(self) -> None:
        g = StatGraph()
        g.register_node(simple_node("x", base=5))
        g.resolve("x")
        assert g.node("x").is_dirty is False

    def test_node_invalidate_marks_dirty(self) -> None:
        g = StatGraph()
        g.register_node(simple_node("x", base=5))
        g.resolve("x")
        g.node("x").invalidate()
        assert g.node("x").is_dirty is True


# ===========================================================================
# StatGraph registration
# ===========================================================================


class TestStatGraphRegistration:
    def test_register_node_succeeds(self) -> None:
        g = StatGraph()
        g.register_node(simple_node("a"))
        assert g.has_node("a")

    def test_duplicate_key_raises(self) -> None:
        g = StatGraph()
        g.register_node(simple_node("a"))
        with pytest.raises(StatError, match="already registered"):
            g.register_node(simple_node("a"))

    def test_missing_input_dependency_raises(self) -> None:
        g = StatGraph()
        with pytest.raises(StatError, match="not yet registered"):
            g.register_node(simple_node("b", inputs=["a"]))

    def test_dependency_must_be_registered_before_dependent(self) -> None:
        g = StatGraph()
        g.register_node(simple_node("a", base=3))
        g.register_node(simple_node("b", inputs=["a"], compute=compute_sum))
        assert g.has_node("b")

    def test_cycle_detection_direct(self) -> None:
        """a → b → a is a cycle."""
        g = StatGraph()
        g.register_node(simple_node("a", base=1))
        # Manually inject a back-edge to simulate cycle attempt
        # (normal registration prevents this, but we test _assert_no_cycle)
        g._nodes["b"] = StatNode(key="b", inputs=["a"])
        g._dependents.setdefault("a", set()).add("b")
        g._dependents.setdefault("b", set())
        # Now try adding a node that depends on b and
        # b depends on a — no cycle yet
        # Real cycle: inject a → b and b → a
        g._nodes["a"].inputs.append("b")  # create the cycle manually
        with pytest.raises(StatError, match="cycle"):
            g._assert_no_cycle("a")

    def test_register_pool(self) -> None:
        g = StatGraph()
        p = BonusPool("ac")
        g.register_pool(p)
        assert g.has_pool("ac")

    def test_pool_used_by_multiple_nodes(self) -> None:
        g = StatGraph()
        p = make_pool("shared", bonus(2))
        g.register_pool(p)
        g.register_node(simple_node("x", pools=["shared"]))
        g.register_node(simple_node("y", base=10, pools=["shared"]))
        assert g.resolve("x") == 2
        assert g.resolve("y") == 12

    def test_unknown_pool_key_is_silently_zero(self) -> None:
        """Unregistered pool key contributes 0."""
        g = StatGraph()
        g.register_node(simple_node("x", pools=["nonexistent"]))
        assert g.resolve("x") == 0

    def test_resolve_unknown_key_raises(self) -> None:
        g = StatGraph()
        with pytest.raises(StatError, match="No stat node"):
            g.resolve("ghost")

    def test_pool_unknown_key_raises(self) -> None:
        g = StatGraph()
        with pytest.raises(StatError, match="No bonus pool"):
            g.pool("ghost")


# ===========================================================================
# Lazy evaluation and caching
# ===========================================================================


class TestLazyEvaluation:
    def test_value_cached_after_first_resolve(self) -> None:
        call_count = [0]

        def counting_compute(bt: int) -> int:
            call_count[0] += 1
            return 42 + bt

        g = StatGraph()
        g.register_node(StatNode(key="x", compute=counting_compute))
        g.resolve("x")
        g.resolve("x")
        g.resolve("x")
        assert call_count[0] == 1, "Should only compute once when clean"

    def test_invalidation_forces_recompute(self) -> None:
        call_count = [0]

        def counting_compute(bt: int) -> int:
            call_count[0] += 1
            return 42 + bt

        g = StatGraph()
        g.register_node(StatNode(key="x", compute=counting_compute))
        g.resolve("x")
        g.invalidate("x")
        g.resolve("x")
        assert call_count[0] == 2

    def test_resolve_returns_correct_value_after_pool_change(self) -> None:
        g = StatGraph()
        p = BonusPool("p")
        g.register_pool(p)
        g.register_node(simple_node("x", base=10, pools=["p"]))

        assert g.resolve("x") == 10

        p.set_source("new_bonus", [bonus(5)])
        g.invalidate_pool("p")
        assert g.resolve("x") == 15

    def test_invalidate_all_marks_every_node_dirty(self) -> None:
        g = StatGraph()
        g.register_node(simple_node("a", base=1))
        g.register_node(simple_node("b", base=2))
        g.resolve("a")
        g.resolve("b")
        assert g.node("a").is_dirty is False
        assert g.node("b").is_dirty is False

        g.invalidate_all()
        assert g.node("a").is_dirty is True
        assert g.node("b").is_dirty is True


# ===========================================================================
# Dirty-flag cascade
# ===========================================================================


class TestDirtyCascade:
    def _make_chain(self) -> StatGraph:
        """a → b → c: c depends on b, b depends on a."""
        g = StatGraph()
        g.register_node(simple_node("a", base=1))
        g.register_node(StatNode("b", inputs=["a"], compute=compute_sum))
        g.register_node(StatNode("c", inputs=["b"], compute=compute_sum))
        return g

    def test_invalidating_root_cascades_to_all_dependents(self) -> None:
        g = self._make_chain()
        g.resolve("c")  # warm the cache
        assert g.node("a").is_dirty is False
        assert g.node("b").is_dirty is False
        assert g.node("c").is_dirty is False

        g.invalidate("a")
        assert g.node("a").is_dirty is True
        assert g.node("b").is_dirty is True
        assert g.node("c").is_dirty is True

    def test_invalidating_mid_node_cascades_downward_not_upward(self) -> None:
        g = self._make_chain()
        g.resolve("c")

        g.invalidate("b")
        assert g.node("a").is_dirty is False  # upstream not affected
        assert g.node("b").is_dirty is True
        assert g.node("c").is_dirty is True

    def test_invalidating_leaf_does_not_cascade_upward(self) -> None:
        g = self._make_chain()
        g.resolve("c")

        g.invalidate("c")
        assert g.node("a").is_dirty is False
        assert g.node("b").is_dirty is False
        assert g.node("c").is_dirty is True

    def test_value_propagates_through_chain(self) -> None:
        g = StatGraph()
        g.register_node(simple_node("a", base=3))
        g.register_node(
            StatNode(
                "b", inputs=["a"], compute=lambda inp, bt: inp["a"] * 2 + bt
            )
        )
        g.register_node(
            StatNode(
                "c", inputs=["b"], compute=lambda inp, bt: inp["b"] + 1 + bt
            )
        )
        # a=3, b=6, c=7
        assert g.resolve("a") == 3
        assert g.resolve("b") == 6
        assert g.resolve("c") == 7

    def test_changing_base_via_pool_and_resolving_chain(self) -> None:
        g = StatGraph()
        p = BonusPool("a_pool")
        g.register_pool(p)
        g.register_node(simple_node("a", base=10, pools=["a_pool"]))
        g.register_node(
            StatNode("b", inputs=["a"], compute=lambda inp, bt: inp["a"] + bt)
        )

        assert g.resolve("b") == 10

        p.set_source("enh", [bonus(4, BonusType.ENHANCEMENT)])
        g.invalidate_pool("a_pool")

        assert g.resolve("b") == 14

    def test_diamond_dependency_no_double_compute(self) -> None:
        """
        a → b → d
        a → c → d
        Invalidating a should dirty d only once (not twice).
        """
        compute_calls = [0]

        def counting(
            inputs: dict[str, int],
            bt: int,
        ) -> int:
            compute_calls[0] += 1
            return sum(inputs.values()) + bt

        g = StatGraph()
        g.register_node(simple_node("a", base=1))
        g.register_node(StatNode("b", inputs=["a"], compute=compute_sum))
        g.register_node(StatNode("c", inputs=["a"], compute=compute_sum))
        g.register_node(StatNode("d", inputs=["b", "c"], compute=counting))

        g.resolve("d")  # warms cache, counting_calls = 1
        g.invalidate("a")
        compute_calls[0] = 0
        g.resolve("d")  # should compute d exactly once
        assert compute_calls[0] == 1

    def test_invalidate_pool_only_affects_nodes_using_that_pool(self) -> None:
        g = StatGraph()
        p1 = BonusPool("p1")
        p2 = BonusPool("p2")
        g.register_pool(p1)
        g.register_pool(p2)
        g.register_node(simple_node("uses_p1", pools=["p1"]))
        g.register_node(simple_node("uses_p2", pools=["p2"]))

        g.resolve("uses_p1")
        g.resolve("uses_p2")

        g.invalidate_pool("p1")
        assert g.node("uses_p1").is_dirty is True
        assert g.node("uses_p2").is_dirty is False


# ===========================================================================
# BonusPool integration
# ===========================================================================


class TestBonusPoolIntegration:
    def test_pool_total_included_in_node_value(self) -> None:
        g = StatGraph()
        p = make_pool(
            "str_pool",
            BonusEntry(4, BonusType.ENHANCEMENT, "Bull's Strength"),
            BonusEntry(2, BonusType.MORALE, "Rage"),
        )
        g.register_pool(p)
        g.register_node(simple_node("str_score", base=14, pools=["str_pool"]))
        # 14 base + 4 enhancement + 2 morale = 20
        assert g.resolve("str_score") == 20

    def test_stacking_rules_applied_in_pool(self) -> None:
        """Two enhancement bonuses in pool — only highest counts."""
        g = StatGraph()
        p = make_pool(
            "str_pool",
            BonusEntry(4, BonusType.ENHANCEMENT, "Bull's Strength"),
            BonusEntry(2, BonusType.ENHANCEMENT, "Gauntlets"),
        )
        g.register_pool(p)
        g.register_node(simple_node("str_score", base=10, pools=["str_pool"]))
        assert g.resolve("str_score") == 14  # 10 + 4

    def test_conditional_bonus_excluded_without_character(self) -> None:
        g = StatGraph()
        p = BonusPool("con_pool")
        p.set_source(
            "Rage",
            [
                BonusEntry(
                    4, BonusType.MORALE, "Rage", condition=lambda c: c.is_raging
                )
            ],
        )
        g.register_pool(p)
        g.register_node(simple_node("con_score", base=12, pools=["con_pool"]))
        # No character → condition can't evaluate → excluded
        assert g.resolve("con_score", character=None) == 12

    def test_conditional_bonus_included_when_active(self) -> None:
        g = StatGraph()
        p = BonusPool("con_pool")
        p.set_source(
            "Rage",
            [
                BonusEntry(
                    4, BonusType.MORALE, "Rage", condition=lambda c: c.is_raging
                )
            ],
        )
        g.register_pool(p)
        g.register_node(simple_node("con_score", base=12, pools=["con_pool"]))

        char = MockCharacter(is_raging=True)
        assert g.resolve("con_score", character=char) == 16

    def test_conditional_bonus_excluded_when_inactive(self) -> None:
        g = StatGraph()
        p = BonusPool("con_pool")
        p.set_source(
            "Rage",
            [
                BonusEntry(
                    4, BonusType.MORALE, "Rage", condition=lambda c: c.is_raging
                )
            ],
        )
        g.register_pool(p)
        g.register_node(simple_node("con_score", base=12, pools=["con_pool"]))

        char = MockCharacter(is_raging=False)
        assert g.resolve("con_score", character=char) == 12

    def test_multiple_pools_on_one_node(self) -> None:
        g = StatGraph()
        p1 = make_pool("atk_feats", bonus(1, BonusType.UNTYPED, "Weapon Focus"))
        p2 = make_pool("atk_buffs", bonus(1, BonusType.MORALE, "Bless"))
        g.register_pool(p1)
        g.register_pool(p2)
        g.register_node(
            simple_node("attack_base", base=5, pools=["atk_feats", "atk_buffs"])
        )
        assert g.resolve("attack_base") == 7


# ===========================================================================
# Introspection helpers
# ===========================================================================


class TestIntrospection:
    def test_dependencies_of(self) -> None:
        g = StatGraph()
        g.register_node(simple_node("a"))
        g.register_node(simple_node("b", inputs=["a"]))
        assert g.dependencies_of("b") == ["a"]

    def test_dependents_of(self) -> None:
        g = StatGraph()
        g.register_node(simple_node("a"))
        g.register_node(simple_node("b", inputs=["a"]))
        g.register_node(simple_node("c", inputs=["a"]))
        deps = g.dependents_of("a")
        assert set(deps) == {"b", "c"}

    def test_all_keys_returns_registration_order(self) -> None:
        g = StatGraph()
        for k in ("a", "b", "c"):
            g.register_node(simple_node(k))
        assert g.all_keys() == ["a", "b", "c"]

    def test_dirty_keys_tracks_state(self) -> None:
        g = StatGraph()
        g.register_node(simple_node("a"))
        g.register_node(simple_node("b"))
        assert set(g.dirty_keys()) == {"a", "b"}

        g.resolve("a")
        assert "a" not in g.dirty_keys()
        assert "b" in g.dirty_keys()


# ===========================================================================
# Standard compute helpers
# ===========================================================================


class TestComputeHelpers:
    def test_ability_modifier_10_gives_0(self) -> None:
        assert compute_ability_modifier({"str_score": 10}, 0) == 0

    def test_ability_modifier_18_gives_4(self) -> None:
        assert compute_ability_modifier({"str_score": 18}, 0) == 4

    def test_ability_modifier_8_gives_neg1(self) -> None:
        assert compute_ability_modifier({"str_score": 8}, 0) == -1

    def test_ability_modifier_1_gives_neg5(self) -> None:
        assert compute_ability_modifier({"str_score": 1}, 0) == -5

    def test_ability_modifier_floors_not_truncates(self) -> None:
        """Score 9 → (9-10)/2 = -0.5 → floor = -1, not 0."""
        assert compute_ability_modifier({"str_score": 9}, 0) == -1

    def test_ability_modifier_bonus_total_added(self) -> None:
        """bonus_total represents flat bonuses to the modifier itself."""
        assert compute_ability_modifier({"str_score": 10}, 2) == 2

    def test_compute_sum_sums_all_inputs_and_bonus(self) -> None:
        assert compute_sum({"a": 3, "b": 4}, 2) == 9

    def test_compute_sum_empty_inputs(self) -> None:
        assert compute_sum({}, 5) == 5

    def test_compute_max_zero_floors_at_zero(self) -> None:
        assert compute_max_zero({"a": -3}, 0) == 0

    def test_compute_max_zero_positive_passes_through(self) -> None:
        assert compute_max_zero({"a": 3}, 2) == 5

    def test_compute_capped_dex_no_cap(self) -> None:
        """cap = -1 means no cap."""
        fn = compute_capped_dex("max_dex_bonus")
        assert fn({"dex_mod": 5, "max_dex_bonus": -1}, 0) == 5

    def test_compute_capped_dex_cap_lower_than_mod(self) -> None:
        fn = compute_capped_dex("max_dex_bonus")
        assert fn({"dex_mod": 5, "max_dex_bonus": 2}, 0) == 2

    def test_compute_capped_dex_cap_higher_than_mod(self) -> None:
        fn = compute_capped_dex("max_dex_bonus")
        assert fn({"dex_mod": 2, "max_dex_bonus": 5}, 0) == 2

    def test_compute_capped_dex_negative_dex_floors_at_zero(self) -> None:
        """Helpless character loses DEX bonus, floors at 0."""
        fn = compute_capped_dex("max_dex_bonus")
        assert fn({"dex_mod": -2, "max_dex_bonus": -1}, 0) == 0

    def test_compute_save_sums_base_and_mod(self) -> None:
        assert compute_save({"base_save": 4, "con_mod": 2}, 0) == 6

    def test_compute_save_with_bonus_total(self) -> None:
        assert compute_save({"base_save": 4, "con_mod": 2}, 3) == 9


# ===========================================================================
# Real 3.5e stat chain scenarios
# ===========================================================================


class TestRealStatChains:
    def _make_str_chain(self, base_str: int = 16) -> StatGraph:
        """
        str_score → str_mod → attack_melee (simplified, no BAB)
        Demonstrates the canonical ability-score → modifier → downstream chain.
        """
        g = StatGraph()

        str_pool = BonusPool("str_score")
        atk_pool = BonusPool("attack_melee")
        g.register_pool(str_pool)
        g.register_pool(atk_pool)

        g.register_node(
            StatNode(
                key="str_score",
                base=base_str,
                pools=["str_score"],
                compute=lambda bt: base_str + bt,
            )
        )
        g.register_node(
            StatNode(
                key="str_mod",
                inputs=["str_score"],
                compute=compute_ability_modifier,
            )
        )
        g.register_node(
            StatNode(
                key="attack_melee",
                inputs=["str_mod"],
                pools=["attack_melee"],
                compute=compute_sum,
            )
        )

        return g, str_pool, atk_pool

    def test_str16_gives_mod_plus3(self) -> None:
        g, _, _ = self._make_str_chain(16)
        assert g.resolve("str_mod") == 3

    def test_str_mod_flows_to_attack(self) -> None:
        g, _, _ = self._make_str_chain(16)
        # attack_melee = str_mod(3) + no pool bonuses = 3
        assert g.resolve("attack_melee") == 3

    def test_bulls_strength_updates_str_mod_and_attack(self) -> None:
        g, str_pool, _ = self._make_str_chain(16)
        # Before buff: str=16, mod=3, attack=3
        assert g.resolve("attack_melee") == 3

        str_pool.set_source(
            "Bull", [BonusEntry(4, BonusType.ENHANCEMENT, "Bull's Strength")]
        )
        g.invalidate_pool("str_score")

        # str = 16+4 = 20, mod = 5, attack = 5
        assert g.resolve("str_score") == 20
        assert g.resolve("str_mod") == 5
        assert g.resolve("attack_melee") == 5

    def test_weapon_focus_adds_to_attack_not_str(self) -> None:
        g, _, atk_pool = self._make_str_chain(16)
        atk_pool.set_source(
            "Weapon Focus", [BonusEntry(1, BonusType.UNTYPED, "Weapon Focus")]
        )
        g.invalidate_pool("attack_melee")

        # str_mod = 3, weapon focus = 1 → attack = 4
        assert g.resolve("str_mod") == 3
        assert g.resolve("attack_melee") == 4

    def test_enhancement_to_str_and_to_attack_combine_correctly(self) -> None:
        """
        Bull's Strength (+4 enhancement to str_score) and
        Magic Weapon (+1 enhancement to attack directly).
        Different pools/stats so both apply.
        """
        g, str_pool, atk_pool = self._make_str_chain(14)
        str_pool.set_source(
            "Bull", [BonusEntry(4, BonusType.ENHANCEMENT, "Bull's Strength")]
        )
        atk_pool.set_source(
            "Magic Weapon +1",
            [BonusEntry(1, BonusType.ENHANCEMENT, "Magic Weapon +1")],
        )

        g.invalidate_pool("str_score")
        g.invalidate_pool("attack_melee")

        # str = 14+4 = 18, mod = 4
        # attack = str_mod(4) + magic_weapon(1) = 5
        assert g.resolve("str_score") == 18
        assert g.resolve("str_mod") == 4
        assert g.resolve("attack_melee") == 5

    def test_buff_deactivation_reverts_stats(self) -> None:
        g, str_pool, _ = self._make_str_chain(16)
        e = BonusEntry(4, BonusType.ENHANCEMENT, "Bull's Strength")
        str_pool.set_source("Bull's Strength", [e])
        g.invalidate_pool("str_score")

        assert g.resolve("attack_melee") == 5

        str_pool.clear_source("Bull's Strength")
        g.invalidate_pool("str_score")

        assert g.resolve("attack_melee") == 3

    def test_ac_calculation_with_dex_cap(self) -> None:
        """
        Full AC chain:
          base_ac(10) + armor(5) + shield(2) + dex_contribution + deflection(2)
        With Mithral Full Plate (max dex +3) and DEX 16 (mod +3):
          dex_contribution = min(3, 3) = 3
          total = 10 + 5 + 2 + 3 + 2 = 22
        """
        g = StatGraph()

        dex_pool = BonusPool("dex_score")
        armor_pool = BonusPool("ac")
        g.register_pool(dex_pool)
        g.register_pool(armor_pool)

        g.register_node(
            StatNode(
                "dex_score",
                base=16,
                pools=["dex_score"],
                compute=lambda bt: 16 + bt,
            )
        )
        g.register_node(
            StatNode(
                "dex_mod",
                inputs=["dex_score"],
                compute=compute_ability_modifier,
            )
        )
        g.register_node(
            StatNode("max_dex_bonus", base=3, compute=lambda bt: 3 + bt)
        )
        g.register_node(
            StatNode(
                "ac_dex",
                inputs=["dex_mod", "max_dex_bonus"],
                compute=compute_capped_dex("max_dex_bonus"),
            )
        )
        g.register_node(
            StatNode(
                "ac",
                base=10,
                inputs=["ac_dex"],
                pools=["ac"],
                compute=lambda inp, bt: 10 + inp["ac_dex"] + bt,
            )
        )

        armor_pool.set_source(
            "Full Plate", [BonusEntry(5, BonusType.ARMOR, "Full Plate")]
        )
        armor_pool.set_source(
            "Heavy Shield", [BonusEntry(2, BonusType.SHIELD, "Heavy Shield")]
        )
        armor_pool.set_source(
            "Ring of Protection +2",
            [BonusEntry(2, BonusType.DEFLECTION, "Ring of Protection +2")],
        )

        assert g.resolve("dex_mod") == 3
        assert g.resolve("ac_dex") == 3  # min(3, 3) = 3
        assert g.resolve("ac") == 22  # 10 + 3 + 5 + 2 + 2

    def test_ac_dex_capped_below_actual_mod(self) -> None:
        """
        Heavy armour: max dex +1.  DEX 16 (mod +3).
        AC dex contribution should be capped at +1.
        """
        g = StatGraph()
        g.register_node(
            StatNode("dex_score", base=16, compute=lambda bt: 16 + bt)
        )
        g.register_node(
            StatNode(
                "dex_mod",
                inputs=["dex_score"],
                compute=compute_ability_modifier,
            )
        )
        g.register_node(
            StatNode("max_dex_bonus", base=1, compute=lambda bt: 1 + bt)
        )
        g.register_node(
            StatNode(
                "ac_dex",
                inputs=["dex_mod", "max_dex_bonus"],
                compute=compute_capped_dex("max_dex_bonus"),
            )
        )

        assert g.resolve("ac_dex") == 1

    def test_save_chain(self) -> None:
        """
        Will save = base_will(5) + wis_mod + resistance_bonus
        WIS 14 → mod +2.  Cloak of Resistance +2 (resistance bonus).
        Total = 5 + 2 + 2 = 9.
        """
        g = StatGraph()
        will_pool = BonusPool("will_save")
        g.register_pool(will_pool)

        g.register_node(
            StatNode("wis_score", base=14, compute=lambda bt: 14 + bt)
        )
        g.register_node(
            StatNode(
                "wis_mod",
                inputs=["wis_score"],
                compute=compute_ability_modifier,
            )
        )
        g.register_node(
            StatNode(
                "will_save",
                inputs=["wis_mod"],
                pools=["will_save"],
                compute=lambda inp, bt: 5 + inp["wis_mod"] + bt,
            )
        )

        will_pool.set_source(
            "Cloak of Resistance",
            [BonusEntry(2, BonusType.RESISTANCE, "Cloak of Resistance")],
        )
        assert g.resolve("will_save") == 9

    def test_negative_ability_score_edge_case(self) -> None:
        """
        Ability score of 1 (minimum in 3.5e) gives modifier of -5.
        Ensure floor division handles this correctly.
        """
        g = StatGraph()
        g.register_node(
            StatNode("str_score", base=1, compute=lambda bt: 1 + bt)
        )
        g.register_node(
            StatNode(
                "str_mod",
                inputs=["str_score"],
                compute=compute_ability_modifier,
            )
        )
        assert g.resolve("str_mod") == -5

    def test_very_high_ability_score(self) -> None:
        """Score 30 → modifier +10."""
        g = StatGraph()
        g.register_node(
            StatNode("str_score", base=30, compute=lambda bt: 30 + bt)
        )
        g.register_node(
            StatNode(
                "str_mod",
                inputs=["str_score"],
                compute=compute_ability_modifier,
            )
        )
        assert g.resolve("str_mod") == 10
