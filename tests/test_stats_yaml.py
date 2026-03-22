"""
tests/test_stats_yaml.py
------------------------
Tests for rules/core/stats.yaml and rules/loader.py.

Covers:
  - YAML is valid and parses cleanly
  - All declared compute strategies are known
  - No duplicate keys
  - Input dependency ordering is correct (no forward references)
  - Loader registers nodes onto a fresh StatGraph
  - Loader skips already-registered bootstrap nodes
  - Loader on a full Character produces correct stat values
  - validate_yaml() returns no errors for the shipped file
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.bonus import BonusPool
from heroforge.engine.character import Character, ClassLevel
from heroforge.engine.stat import StatGraph
from heroforge.rules.loader import COMPUTE_STRATEGIES, LoaderError, StatsLoader

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


# ===========================================================================
# Helpers
# ===========================================================================


def fresh_graph() -> StatGraph:
    return StatGraph()


def fighter(n: int) -> list[ClassLevel]:
    return [
        ClassLevel(
            class_name="Fighter",
            level=n,
            hp_rolls=[10] * n,
            bab_contribution=n,
            fort_contribution=2 + n // 2,
            ref_contribution=n // 3,
            will_contribution=n // 3,
        )
    ]


# ===========================================================================
# YAML structure validation
# ===========================================================================


class TestYamlStructure:
    def test_validate_yaml_returns_no_errors(self) -> None:
        """The shipped stats.yaml must pass all validation checks."""
        loader = StatsLoader(RULES_DIR)
        errors = loader.validate_yaml()
        assert errors == [], "stats.yaml validation errors:\n" + "\n".join(
            errors
        )

    def test_all_compute_strategies_referenced_are_known(self) -> None:
        """
        Every compute strategy name used in stats.yaml must exist in
        the COMPUTE_STRATEGIES registry.
        """
        import yaml

        with open(RULES_DIR / "core" / "stats.yaml") as f:
            data = yaml.safe_load(f)
        unknown = []
        for decl in data["stats"]:
            strategy = decl.get("compute", "base_plus_bonus")
            if strategy not in COMPUTE_STRATEGIES:
                unknown.append(f"{decl.get('key')!r}: {strategy!r}")
        assert unknown == [], f"Unknown strategies: {unknown}"

    def test_no_duplicate_keys_in_yaml(self) -> None:
        import yaml

        with open(RULES_DIR / "core" / "stats.yaml") as f:
            data = yaml.safe_load(f)
        keys = [d["key"] for d in data["stats"] if "key" in d]
        assert len(keys) == len(set(keys)), (
            f"Duplicate keys: {[k for k in keys if keys.count(k) > 1]}"
        )

    def test_every_declaration_has_a_key(self) -> None:
        import yaml

        with open(RULES_DIR / "core" / "stats.yaml") as f:
            data = yaml.safe_load(f)
        for decl in data["stats"]:
            assert "key" in decl, f"Declaration missing 'key': {decl}"

    def test_every_declaration_has_a_description(self) -> None:
        import yaml

        with open(RULES_DIR / "core" / "stats.yaml") as f:
            data = yaml.safe_load(f)
        missing = [d["key"] for d in data["stats"] if not d.get("description")]
        assert missing == [], f"Missing descriptions: {missing}"


# ===========================================================================
# Loader behaviour
# ===========================================================================


class TestLoader:
    def test_loader_instantiates(self) -> None:
        loader = StatsLoader(RULES_DIR)
        assert loader is not None

    def test_loader_raises_on_missing_file(self, tmp_path: Path) -> None:
        loader = StatsLoader(tmp_path)
        g = fresh_graph()
        with pytest.raises(LoaderError, match="stats.yaml not found"):
            loader.load(g)

    def test_loader_raises_on_malformed_yaml(self, tmp_path: Path) -> None:
        core = tmp_path / "core"
        core.mkdir()
        # This YAML has a parse error (colons in wrong positions)
        (core / "stats.yaml").write_text("not: a: valid: stats: file\n")
        loader = StatsLoader(tmp_path)
        g = fresh_graph()
        with pytest.raises(
            LoaderError, match="YAML parse error|top-level 'stats' key"
        ):
            loader.load(g)

    def test_loader_raises_on_unknown_strategy(self, tmp_path: Path) -> None:
        core = tmp_path / "core"
        core.mkdir()
        (core / "stats.yaml").write_text(
            "stats:\n"
            "  - key: x\n"
            "    compute: totally_unknown\n"
            "    description: X\n"
        )
        loader = StatsLoader(tmp_path)
        g = fresh_graph()
        with pytest.raises(LoaderError, match="Unknown compute strategy"):
            loader.load(g)

    def test_loader_raises_on_duplicate_key(self, tmp_path: Path) -> None:
        core = tmp_path / "core"
        core.mkdir()
        (core / "stats.yaml").write_text(
            "stats:\n"
            "  - key: x\n    compute: sum\n    description: X\n"
            "  - key: x\n    compute: sum\n    description: X again\n"
        )
        loader = StatsLoader(tmp_path)
        g = fresh_graph()
        with pytest.raises(LoaderError, match="Duplicate stat key"):
            loader.load(g)

    def test_loader_on_fresh_graph_registers_nodes(self) -> None:
        """Loading onto a bare graph registers all declared nodes."""
        loader = StatsLoader(RULES_DIR)
        g = fresh_graph()
        # Pre-register pools that the stats reference
        for pk in [
            "str_score",
            "dex_score",
            "con_score",
            "int_score",
            "wis_score",
            "cha_score",
            "fort_save",
            "ref_save",
            "will_save",
            "ac",
            "initiative",
            "speed",
            "hp_bonus",
            "sr",
            "attack_melee",
            "attack_ranged",
            "attack_all",
            "damage_melee",
            "damage_all",
            "bab_misc",
        ]:
            if not g.has_pool(pk):
                g.register_pool(BonusPool(pk))

        registered = loader.load(g)
        assert len(registered) > 0
        # Key nodes should be present
        for key in (
            "str_score",
            "str_mod",
            "dex_mod",
            "con_mod",
            "bab",
            "fort_save",
            "ref_save",
            "will_save",
            "ac",
            "initiative",
            "hp_max",
            "attack_melee",
            "attack_ranged",
        ):
            assert g.has_node(key), f"Expected node {key!r} to be registered"

    def test_loader_skips_bootstrap_nodes(self) -> None:
        """
        When loading onto a Character (which bootstraps its own nodes),
        the loader should skip already-registered keys rather than raising.
        """
        c = Character()
        loader = StatsLoader(RULES_DIR)
        # Should not raise even though Character already has str_score etc.
        registered = loader.load(c._graph, c)
        # Nodes already in bootstrap are skipped
        assert "str_score" not in registered
        assert "str_mod" not in registered

    def test_loader_returns_list_of_registered_keys(self) -> None:
        c = Character()
        loader = StatsLoader(RULES_DIR)
        registered = loader.load(c._graph, c)
        # All returned keys should now be in the graph
        for key in registered:
            assert c._graph.has_node(key), (
                f"{key!r} in returned list but not in graph"
            )

    def test_loader_auto_creates_missing_pools(self, tmp_path: Path) -> None:
        """The loader creates any pools referenced that don't yet exist."""
        core = tmp_path / "core"
        core.mkdir()
        (core / "stats.yaml").write_text(
            "stats:\n"
            "  - key: test_stat\n"
            "    compute: sum\n"
            "    pools: [new_pool]\n"
            "    description: Test\n"
        )
        loader = StatsLoader(tmp_path)
        g = fresh_graph()
        loader.load(g)
        assert g.has_pool("new_pool")
        assert g.has_node("test_stat")


# ===========================================================================
# Stat values via loader on a real Character
# ===========================================================================


class TestLoaderStatValues:
    def _loaded_char(self) -> Character:
        c = Character()
        loader = StatsLoader(RULES_DIR)
        loader.load(c._graph, c)
        return c

    def test_default_ability_scores_resolve_correctly(self) -> None:
        c = self._loaded_char()
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            assert c.get(f"{ab}_score") == 10
            assert c.get(f"{ab}_mod") == 0

    def test_ability_score_change_propagates(self) -> None:
        c = self._loaded_char()
        c.set_ability_score("str", 18)
        assert c.get("str_score") == 18
        assert c.get("str_mod") == 4

    def test_ac_default_is_ten(self) -> None:
        c = self._loaded_char()
        assert c.get("ac") == 10

    def test_dex_change_updates_ac(self) -> None:
        c = self._loaded_char()
        c.set_ability_score("dex", 16)
        assert c.get("ac") == 13  # 10 + 3

    def test_dex_change_updates_initiative(self) -> None:
        c = self._loaded_char()
        c.set_ability_score("dex", 14)
        assert c.get("initiative") == 2

    def test_bab_zero_before_levels(self) -> None:
        c = self._loaded_char()
        assert c.get("bab") == 0

    def test_class_levels_update_bab(self) -> None:
        c = self._loaded_char()
        c.set_class_levels(fighter(6))
        assert c.get("bab") == 6

    def test_fort_save_with_class_and_con(self) -> None:
        c = self._loaded_char()
        c.set_ability_score("con", 14)  # mod +2
        c.set_class_levels(fighter(4))  # base fort = 2 + 4//2 = 4
        assert c.get("fort_save") == 6

    def test_will_save_with_wis(self) -> None:
        c = self._loaded_char()
        c.set_ability_score("wis", 16)  # mod +3
        c.set_class_levels(fighter(3))  # poor will: 3//3 = 1
        assert c.get("will_save") == 4

    def test_hp_max_from_rolls_and_con(self) -> None:
        c = self._loaded_char()
        c.set_ability_score("con", 12)  # mod +1
        c.set_class_levels(fighter(3))  # 30 hp rolls, +1×3 = 33
        assert c.get("hp_max") == 33

    def test_attack_melee_bab_plus_str(self) -> None:
        c = self._loaded_char()
        c.set_ability_score("str", 16)  # mod +3
        c.set_class_levels(fighter(5))  # bab = 5
        assert c.get("attack_melee") == 8

    def test_attack_ranged_bab_plus_dex(self) -> None:
        c = self._loaded_char()
        c.set_ability_score("dex", 14)  # mod +2
        c.set_class_levels(fighter(4))  # bab = 4
        assert c.get("attack_ranged") == 6

    def test_speed_default_thirty(self) -> None:
        c = self._loaded_char()
        assert c.get("speed") == 30

    def test_sr_default_zero(self) -> None:
        c = self._loaded_char()
        assert c.get("sr") == 0


# ===========================================================================
# Validate YAML file has sensible stat coverage
# ===========================================================================


class TestYamlCoverage:
    def _get_keys(self) -> set[str]:
        import yaml

        with open(RULES_DIR / "core" / "stats.yaml") as f:
            data = yaml.safe_load(f)
        return {d["key"] for d in data["stats"]}

    def test_all_six_ability_scores_declared(self) -> None:
        keys = self._get_keys()
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            assert f"{ab}_score" in keys
            assert f"{ab}_mod" in keys

    def test_three_saves_declared(self) -> None:
        keys = self._get_keys()
        for save in ("fort_save", "ref_save", "will_save"):
            assert save in keys

    def test_combat_stats_declared(self) -> None:
        keys = self._get_keys()
        for stat in (
            "bab",
            "ac",
            "initiative",
            "attack_melee",
            "attack_ranged",
        ):
            assert stat in keys

    def test_hp_and_speed_declared(self) -> None:
        keys = self._get_keys()
        assert "hp_max" in keys
        assert "speed" in keys

    def test_ac_chain_complete(self) -> None:
        """max_dex_bonus and ac_dex_contribution must both be declared."""
        keys = self._get_keys()
        assert "max_dex_bonus" in keys
        assert "ac_dex_contribution" in keys
