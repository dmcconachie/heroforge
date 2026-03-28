"""
rules/loader.py
---------------
Loads rules YAML files and populates engine registries.

The loader is the bridge between the declarative YAML
data layer and the imperative engine layer.  It reads
YAML files and translates declarations into engine
objects (stat nodes, buff definitions, feat definitions,
class/race definitions, equipment, domains, spell
compendium entries).

The engine (engine/) has zero knowledge of YAML structure.
The YAML files have zero Python code.
This module is the only place where those two meet.

Public API:
  LoaderError            — raised on malformed YAML
  StatsLoader            — stats.yaml → stat graph
  ConditionLoader        — condition YAML
  MagicItemLoader        — magic item YAML
  FeatsLoader            — feat YAML → FeatRegistry
  TemplatesLoader        — templates YAML
  ClassesLoader          — classes YAML
  RacesLoader            — races YAML
  SkillsLoader           — skills YAML
  DomainsLoader          — domains YAML
  EquipmentLoader        — armor/weapons YAML
  SpellCompendiumLoader  — spell compendium YAML
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from heroforge.engine.bonus import BonusPool
from heroforge.engine.stat import (
    StatNode,
    compute_ability_modifier,
    compute_sum,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from heroforge.engine.character import Character
    from heroforge.engine.classes_races import (
        ClassDefinition,
        ClassRegistry,
        DomainRegistry,
        RaceRegistry,
    )
    from heroforge.engine.conditions import (
        ConditionRegistry,
    )
    from heroforge.engine.effects import BuffRegistry
    from heroforge.engine.equipment import (
        ArmorRegistry,
        WeaponRegistry,
    )
    from heroforge.engine.feats import FeatRegistry
    from heroforge.engine.magic_items import (
        MagicItemRegistry,
    )
    from heroforge.engine.prerequisites import (
        Prerequisite,
        PrerequisiteChecker,
    )
    from heroforge.engine.skills import SkillRegistry
    from heroforge.engine.spells import SpellCompendium
    from heroforge.engine.stat import StatGraph
    from heroforge.engine.templates import TemplateRegistry


class LoaderError(Exception):
    pass


# ---------------------------------------------------------------------------
# Schema key definitions: (required_keys, optional_keys)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Compute strategy registry
# ---------------------------------------------------------------------------
# Maps strategy name strings (from YAML) to factory functions.
# Each factory receives the node declaration dict and the character reference
# (via closure) and returns a compute callable matching the StatNode signature:
#   fn(inputs: dict[str, int], bonus_total: int) -> int


def _strategy_base_plus_bonus(
    decl: dict,
    char_ref: Character | None,
) -> Callable:
    base = decl.get("base", 0)
    ability = decl.get("key", "").replace("_score", "")

    def compute(inputs: dict[str, int], bonus_total: int) -> int:
        # Ability score nodes read live from character._ability_scores
        if char_ref is not None and ability in getattr(
            char_ref, "_ability_scores", {}
        ):
            return char_ref._ability_scores[ability] + bonus_total
        return base + bonus_total

    return compute


def _strategy_ability_modifier(
    _decl: dict,
    _char_ref: Character | None,
) -> Callable:
    return compute_ability_modifier


def _strategy_sum(
    _decl: dict,
    _char_ref: Character | None,
) -> Callable:
    return compute_sum


def _strategy_max_zero(
    _decl: dict,
    _char_ref: Character | None,
) -> Callable:
    def compute(inputs: dict[str, int], bonus_total: int) -> int:
        return max(0, sum(inputs.values()) + bonus_total)

    return compute


def _strategy_capped_dex(
    _decl: dict,
    _char_ref: Character | None,
) -> Callable:
    def compute(inputs: dict[str, int], bonus_total: int) -> int:
        dex_mod = inputs.get("dex_mod", 0)
        max_dex = inputs.get("max_dex_bonus", -1)
        capped = dex_mod if max_dex < 0 else min(dex_mod, max_dex)
        return max(0, capped) + bonus_total

    return compute


def _strategy_bab(
    _decl: dict,
    char_ref: Character | None,
) -> Callable:
    def compute(inputs: dict[str, int], bonus_total: int) -> int:
        if char_ref is None:
            return bonus_total
        return char_ref._compute_bab() + bonus_total

    return compute


def _strategy_base_save(
    decl: dict,
    char_ref: Character | None,
) -> Callable:
    save_name = decl.get("save_name", "")

    def compute(inputs: dict[str, int], bonus_total: int) -> int:
        base = char_ref._compute_base_save(save_name) if char_ref else 0
        return base + sum(inputs.values()) + bonus_total

    return compute


def _strategy_hp_max(
    _decl: dict,
    char_ref: Character | None,
) -> Callable:
    def compute(inputs: dict[str, int], bonus_total: int) -> int:
        if char_ref is None:
            return bonus_total
        rolls = char_ref._compute_hp_from_rolls()
        con_mod = inputs.get("con_mod", 0)
        level = char_ref.total_level
        return rolls + con_mod * level + bonus_total

    return compute


def _strategy_base_speed(
    _decl: dict,
    char_ref: Character | None,
) -> Callable:
    def compute(inputs: dict[str, int], bonus_total: int) -> int:
        base = char_ref._compute_base_speed() if char_ref else 30
        return base + bonus_total

    return compute


def _strategy_max_dex_bonus(
    _decl: dict,
    char_ref: Character | None,
) -> Callable:
    def compute(inputs: dict[str, int], bonus_total: int) -> int:
        base = char_ref._compute_max_dex_bonus() if char_ref else -1
        return base + bonus_total

    return compute


def _strategy_ac_total(
    _decl: dict,
    char_ref: Character | None,
) -> Callable:
    def compute(inputs: dict[str, int], bonus_total: int) -> int:
        size_mod = char_ref._compute_size_mod_attack() if char_ref else 0
        return (
            10 + inputs.get("ac_dex_contribution", 0) + size_mod + bonus_total
        )

    return compute


def _strategy_attack_melee_total(
    _decl: dict,
    char_ref: Character | None,
) -> Callable:
    def compute(inputs: dict[str, int], bonus_total: int) -> int:
        size_mod = char_ref._compute_size_mod_attack() if char_ref else 0
        return (
            inputs.get("bab", 0)
            + inputs.get("str_mod", 0)
            + size_mod
            + bonus_total
        )

    return compute


def _strategy_attack_ranged_total(
    _decl: dict,
    char_ref: Character | None,
) -> Callable:
    def compute(inputs: dict[str, int], bonus_total: int) -> int:
        size_mod = char_ref._compute_size_mod_attack() if char_ref else 0
        return (
            inputs.get("bab", 0)
            + inputs.get("dex_mod", 0)
            + size_mod
            + bonus_total
        )

    return compute


COMPUTE_STRATEGIES: dict[str, Callable] = {
    "base_plus_bonus": _strategy_base_plus_bonus,
    "ability_modifier": _strategy_ability_modifier,
    "sum": _strategy_sum,
    "max_zero": _strategy_max_zero,
    "capped_dex": _strategy_capped_dex,
    "bab": _strategy_bab,
    "base_save": _strategy_base_save,
    "hp_max": _strategy_hp_max,
    "base_speed": _strategy_base_speed,
    "max_dex_bonus": _strategy_max_dex_bonus,
    "ac_total": _strategy_ac_total,
    "attack_melee_total": _strategy_attack_melee_total,
    "attack_ranged_total": _strategy_attack_ranged_total,
}


# ---------------------------------------------------------------------------
# StatsLoader
# ---------------------------------------------------------------------------


class StatsLoader:
    """
    Reads rules/core/stats.yaml and registers StatNodes and BonusPools
    onto a StatGraph.

    Usage:
        loader = StatsLoader(rules_dir)
        loader.load(graph, character)

    The `character` reference is captured in compute closures so that
    delegate strategies (bab, base_save, hp_max, etc.) can call back into
    the character object at evaluation time.  Pass None for headless testing
    without a character.
    """

    def __init__(self, rules_dir: Path | str) -> None:
        self.rules_dir = Path(rules_dir)

    def load(
        self,
        graph: StatGraph,
        character: Character | None = None,
    ) -> list[str]:
        """
        Load stats.yaml and register all nodes and pools onto graph.

        Returns a list of keys that were registered, in declaration order.
        Skips nodes whose keys are already registered (bootstrap nodes).
        Raises LoaderError on unknown compute strategies or missing inputs.
        """
        stats_path = self.rules_dir / "core" / "stats.yaml"
        if not stats_path.exists():
            raise LoaderError(f"stats.yaml not found at {stats_path}")

        try:
            with open(stats_path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise LoaderError(f"YAML parse error in stats.yaml: {e}") from e

        if not isinstance(data, list):
            raise LoaderError("stats.yaml must be a YAML list.")

        registered: list[str] = []
        seen_keys: set[str] = set()

        from heroforge.rules.schema import (
            _forbid_extra,
        )

        for decl in data:
            key = decl.get("key")
            if not key:
                raise LoaderError(f"Stat declaration missing 'key': {decl}")

            _forbid_extra(decl, StatNode, f"stat {key!r}")

            # Duplicate check within the YAML itself
            if key in seen_keys:
                raise LoaderError(f"Duplicate stat key {key!r} in stats.yaml")
            seen_keys.add(key)

            # Skip if already registered by bootstrap (Character.__init__)
            if graph.has_node(key):
                continue

            # Ensure all pools this node references
            # exist
            pools = decl.get("pools", [])
            for pk in pools:
                if not graph.has_pool(pk):
                    pool = BonusPool(pk)
                    graph.register_pool(pool)

            # Resolve compute strategy
            strategy_name = decl.get("compute", "base_plus_bonus")
            strategy_factory = COMPUTE_STRATEGIES.get(strategy_name)
            if strategy_factory is None:
                raise LoaderError(
                    f"Unknown compute strategy "
                    f"{strategy_name!r} for stat "
                    f"{key!r}. Known strategies: "
                    f"{sorted(COMPUTE_STRATEGIES)}"
                )
            compute_fn = strategy_factory(decl, character)

            node = StatNode(
                key=key,
                base=decl.get("base"),
                inputs=decl.get("inputs", []),
                compute=compute_fn,
                pools=pools,
                description=decl.get("description", ""),
            )

            try:
                graph.register_node(node)
            except Exception as e:
                raise LoaderError(
                    f"Failed to register stat {key!r}: {e}"
                ) from e

            registered.append(key)

        return registered


# ---------------------------------------------------------------------------
# ConditionLoader
# ---------------------------------------------------------------------------


class ConditionLoader:
    """
    Reads conditions_srd.yaml and populates both a
    ConditionRegistry and a BuffRegistry.

    Each condition is stored as a ConditionDefinition
    (the canonical domain object) and also converted
    into a BuffDefinition so the buff-toggle UI keeps
    working.

    Usage:
        cond_reg = ConditionRegistry()
        buff_reg = BuffRegistry()
        loader = ConditionLoader(rules_dir)
        loader.load(
            cond_reg, buff_reg,
            "core/conditions_srd.yaml",
        )
    """

    def __init__(self, rules_dir: Path | str) -> None:
        self.rules_dir = Path(rules_dir)

    def load(
        self,
        registry: "ConditionRegistry",
        buff_registry: "BuffRegistry",
        relative_path: str,
    ) -> list[str]:
        """
        Load a conditions YAML file.

        Returns list of condition names registered.
        """
        from heroforge.engine.conditions import (
            ConditionDefinition,
        )
        from heroforge.engine.effects import (
            BuffCategory,
            build_buff_from_effects,
        )
        from heroforge.rules.schema import converter

        path = self.rules_dir / relative_path
        if not path.exists():
            raise LoaderError(f"Conditions file not found: {path}")

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise LoaderError(f"YAML parse error in {path}: {e}") from e

        if not isinstance(data, dict):
            raise LoaderError(f"{path} must be a YAML mapping.")

        registered: list[str] = []

        for name, decl in data.items():
            decl["name"] = name

            try:
                defn = converter.structure(decl, ConditionDefinition)
            except Exception as e:
                raise LoaderError(
                    f"Failed to load condition {name!r}: {e}"
                ) from e

            registry.register(defn)

            # Also register as a buff so the toggle
            # UI keeps working.
            buff = build_buff_from_effects(
                name=defn.name,
                category=BuffCategory.CONDITION,
                effects_raw=defn.effects,
                source_book=defn.source_book,
                note=defn.note,
                requires_caster_level=(defn.requires_caster_level),
            )
            if buff is not None:
                try:
                    buff_registry.register(buff)
                except ValueError as e:
                    raise LoaderError(str(e)) from e
            elif defn.note:
                # Note-only condition (no stat
                # effects); still needs a buff
                # entry for the toggle UI.
                from heroforge.engine.effects import (
                    BuffDefinition,
                )

                note_buff = BuffDefinition(
                    name=defn.name,
                    category=BuffCategory.CONDITION,
                    source_book=defn.source_book,
                    note=defn.note,
                )
                try:
                    buff_registry.register(note_buff)
                except ValueError as e:
                    raise LoaderError(str(e)) from e

            registered.append(name)

        return registered


# ---------------------------------------------------------------------------
# MagicItemLoader
# ---------------------------------------------------------------------------


class MagicItemLoader:
    """
    Reads magic_items.yaml and populates both a
    MagicItemRegistry and a BuffRegistry.

    Each item is stored as a MagicItemDefinition
    (the canonical domain object) and also converted
    into a BuffDefinition so the buff-toggle UI keeps
    working.

    Usage:
        item_reg = MagicItemRegistry()
        buff_reg = BuffRegistry()
        loader = MagicItemLoader(rules_dir)
        loader.load(
            item_reg, buff_reg,
            "core/magic_items.yaml",
        )
    """

    def __init__(self, rules_dir: Path | str) -> None:
        self.rules_dir = Path(rules_dir)

    def load(
        self,
        registry: "MagicItemRegistry",
        buff_registry: "BuffRegistry",
        relative_path: str,
    ) -> list[str]:
        """
        Load a magic items YAML file.

        Returns list of item names registered.
        """
        from heroforge.engine.effects import (
            BuffCategory,
            BuffDefinition,
            build_buff_from_effects,
        )
        from heroforge.engine.magic_items import (
            MagicItemDefinition,
        )
        from heroforge.rules.schema import converter

        path = self.rules_dir / relative_path
        if not path.exists():
            raise LoaderError(f"Magic items file not found: {path}")

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise LoaderError(f"YAML parse error in {path}: {e}") from e

        if not isinstance(data, dict):
            raise LoaderError(f"{path} must be a YAML mapping.")

        registered: list[str] = []

        for name, decl in data.items():
            decl["name"] = name

            try:
                defn = converter.structure(decl, MagicItemDefinition)
            except Exception as e:
                raise LoaderError(
                    f"Failed to load magic item {name!r}: {e}"
                ) from e

            registry.register(defn)

            # Also register as a buff so the toggle
            # UI keeps working.
            buff = build_buff_from_effects(
                name=defn.name,
                category=BuffCategory.ITEM,
                effects_raw=defn.effects,
                source_book=defn.source_book,
                note=defn.note,
            )
            if buff is not None:
                try:
                    buff_registry.register(buff)
                except ValueError as e:
                    raise LoaderError(str(e)) from e
            elif defn.note:
                # Note-only item (no stat effects);
                # still needs a buff entry for the
                # toggle UI.
                note_buff = BuffDefinition(
                    name=defn.name,
                    category=BuffCategory.ITEM,
                    source_book=defn.source_book,
                    note=defn.note,
                )
                try:
                    buff_registry.register(note_buff)
                except ValueError as e:
                    raise LoaderError(str(e)) from e

            registered.append(name)

        return registered


# ---------------------------------------------------------------------------
# TemplatesLoader
# ---------------------------------------------------------------------------


class TemplatesLoader:
    """
    Reads rules/core/templates.yaml and populates a TemplateRegistry.

    Usage:
        registry = TemplateRegistry()
        loader = TemplatesLoader(rules_dir)
        loader.load(registry)
    """

    def __init__(self, rules_dir: Path | str) -> None:
        self.rules_dir = Path(rules_dir)

    def load(
        self,
        registry: TemplateRegistry,
        relative_path: str,
        overwrite: bool = False,
    ) -> list[str]:
        """
        Load a templates YAML file into the registry.
        Returns list of template names registered.
        """
        from heroforge.engine.templates import (
            build_template_from_yaml,
        )

        path = self.rules_dir / relative_path
        if not path.exists():
            raise LoaderError(f"Templates file not found: {path}")

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise LoaderError(f"YAML parse error in {path}: {e}") from e

        if not isinstance(data, dict):
            raise LoaderError(f"{path} must be a YAML mapping.")

        registered: list[str] = []

        for name, decl in data.items():
            decl["name"] = name
            try:
                defn = build_template_from_yaml(decl)
                registry.register(defn, overwrite=overwrite)
                registered.append(defn.name)
            except (KeyError, ValueError) as e:
                raise LoaderError(
                    f"Failed to load template {decl.get('name', '?')!r}: {e}"
                ) from e

        return registered


# ---------------------------------------------------------------------------
# FeatsLoader
# ---------------------------------------------------------------------------


class FeatsLoader:
    """
    Reads rules/core/feats_phb.yaml (and other feat files) and populates:
      - A FeatRegistry with FeatDefinition objects
      - A PrerequisiteChecker with feat prerequisite trees
      - Optionally a BuffRegistry with always_on and conditional buff defs

    Usage:
        feat_reg = FeatRegistry()
        prereq_chk = PrerequisiteChecker()
        buff_reg = BuffRegistry()
        loader = FeatsLoader(rules_dir)
        loader.load(feat_reg, prereq_chk, buff_reg)
    """

    def __init__(self, rules_dir: Path | str) -> None:
        self.rules_dir = Path(rules_dir)

    def load(
        self,
        feat_registry: FeatRegistry,
        relative_path: str,
        prereq_checker: PrerequisiteChecker | None = None,
        buff_registry: BuffRegistry | None = None,
        overwrite: bool = False,
    ) -> list[str]:
        """
        Load a feat YAML file.

        Returns list of feat names registered.
        """
        from heroforge.engine.feats import (
            build_feat_from_yaml,
        )

        path = self.rules_dir / relative_path
        if not path.exists():
            raise LoaderError(f"Feats file not found: {path}")

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise LoaderError(f"YAML parse error in {path}: {e}") from e

        if not isinstance(data, dict):
            raise LoaderError(f"{path} must be a YAML mapping.")

        registered: list[str] = []

        for name, decl in data.items():
            decl["name"] = name

            try:
                defn = build_feat_from_yaml(decl)
            except Exception as e:
                raise LoaderError(f"Failed to build feat {name!r}: {e}") from e

            try:
                feat_registry.register(defn, overwrite=overwrite)
            except ValueError as e:
                raise LoaderError(str(e)) from e

            # Register prerequisites with PrerequisiteChecker
            if prereq_checker is not None:
                prereq_checker.register_feat(
                    name,
                    defn.prerequisites,
                    snapshot=defn.snapshot,
                )

            # Register buff definitions with BuffRegistry
            # (only conditional feats — always-on feats
            # apply directly to pools via Character)
            kind_val = getattr(defn.kind, "value", defn.kind)
            if (
                buff_registry is not None
                and defn.buff_definition is not None
                and kind_val == "conditional"
            ):
                with contextlib.suppress(ValueError):
                    buff_registry.register(
                        defn.buff_definition,
                        overwrite=overwrite,
                    )

            registered.append(name)

        return registered


# ---------------------------------------------------------------------------
# ClassesLoader
# ---------------------------------------------------------------------------


class ClassesLoader:
    """
    Reads per-class YAML files from a directory and
    populates a ClassRegistry.

    Each file has either a `classes:` or
    `prestige_classes:` top-level key with a
    single-element list.

    Usage:
        registry = ClassRegistry()
        loader = ClassesLoader(rules_dir)
        loader.load(registry, "core/classes")
    """

    def __init__(self, rules_dir: Path | str) -> None:
        self.rules_dir = Path(rules_dir)

    def load(
        self,
        registry: ClassRegistry,
        relative_path: str,
        overwrite: bool = False,
        prereq_checker: (PrerequisiteChecker | None) = None,
        buff_registry: BuffRegistry | None = None,
    ) -> list[str]:
        from heroforge.engine.classes_races import (
            ClassDefinition,
        )
        from heroforge.rules.schema import converter

        dir_path = self.rules_dir / relative_path
        if not dir_path.is_dir():
            raise LoaderError(f"Classes dir not found: {dir_path}")

        registered: list[str] = []
        for path in sorted(dir_path.glob("*.yaml")):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise LoaderError(f"YAML parse error in {path}: {e}") from e

            if not isinstance(data, dict):
                raise LoaderError(f"{path}: expected a dict")

            for name, decl in data.items():
                decl["name"] = name
                is_prc = decl.get("is_prestige", False)
                try:
                    defn = converter.structure(decl, ClassDefinition)
                    registry.register(defn, overwrite=overwrite)
                    registered.append(name)
                except Exception as e:
                    raise LoaderError(
                        f"Failed to load class {name!r} from {path}: {e}"
                    ) from e
                if is_prc and prereq_checker is not None:
                    entry_prereq = self._build_prereq(
                        decl.get("entry_prerequisites")
                    )
                    ongoing_prereq = self._build_prereq(
                        decl.get("ongoing_prerequisites")
                    )
                    prereq_checker.register_prc(
                        name,
                        entry_prereq,
                        ongoing_prereq,
                    )
                if buff_registry is not None:
                    self._register_feature_buffs(defn, buff_registry)

        return registered

    @staticmethod
    def _register_feature_buffs(
        defn: "ClassDefinition",
        buff_registry: "BuffRegistry",
    ) -> None:
        """Register BuffDefinitions for features with effects."""
        from heroforge.engine.effects import (
            BuffCategory,
            build_buff_from_effects,
        )

        for feat in defn.class_features:
            if not feat.effects:
                continue
            buff_name = feat.buff_name or (f"{defn.name} {feat.feature}")
            buff = build_buff_from_effects(
                name=buff_name,
                category=BuffCategory.CLASS,
                effects_raw=list(feat.effects),
                source_book=defn.source_book,
                note=feat.note,
                requires_caster_level=(feat.requires_caster_level),
                mutually_exclusive_with=list(feat.mutually_exclusive_with),
            )
            if buff is not None:
                with contextlib.suppress(ValueError):
                    buff_registry.register(buff)

    def _build_prereq(self, decl: dict | None) -> "Prerequisite | None":
        if decl is None:
            return None
        from heroforge.engine.prerequisites import (
            build_prereq_from_yaml,
        )

        return build_prereq_from_yaml(decl)


# ---------------------------------------------------------------------------
# RacesLoader
# ---------------------------------------------------------------------------


class RacesLoader:
    """
    Reads rules/core/races.yaml and populates a RaceRegistry.

    Usage:
        registry = RaceRegistry()
        loader = RacesLoader(rules_dir)
        loader.load(registry)
    """

    def __init__(self, rules_dir: Path | str) -> None:
        self.rules_dir = Path(rules_dir)

    def load(
        self,
        registry: RaceRegistry,
        relative_path: str,
        overwrite: bool = False,
    ) -> list[str]:

        path = self.rules_dir / relative_path
        if not path.exists():
            raise LoaderError(f"Races file not found: {path}")

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise LoaderError(f"YAML parse error in {path}: {e}") from e

        if not isinstance(data, dict):
            raise LoaderError(f"{path} must be a YAML mapping.")

        from heroforge.engine.classes_races import (
            RaceDefinition,
        )
        from heroforge.rules.schema import converter

        registered: list[str] = []
        for name, decl in data.items():
            decl["name"] = name
            try:
                defn = converter.structure(decl, RaceDefinition)
                registry.register(defn, overwrite=overwrite)
                registered.append(name)
            except Exception as e:
                raise LoaderError(f"Failed to load race {name!r}: {e}") from e
        return registered


# ---------------------------------------------------------------------------
# SkillsLoader
# ---------------------------------------------------------------------------


class SkillsLoader:
    """
    Reads rules/core/skills.yaml and populates a SkillRegistry.

    Usage:
        registry = SkillRegistry()
        loader = SkillsLoader(rules_dir)
        loader.load(registry)
    """

    def __init__(self, rules_dir: Path | str) -> None:
        self.rules_dir = Path(rules_dir)

    def load(
        self,
        registry: SkillRegistry,
        relative_path: str,
        overwrite: bool = False,
    ) -> list[str]:
        from heroforge.engine.skills import (
            SkillDefinition,
        )
        from heroforge.rules.schema import converter

        path = self.rules_dir / relative_path
        if not path.exists():
            raise LoaderError(f"Skills file not found: {path}")

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise LoaderError(f"YAML parse error in {path}: {e}") from e

        if not isinstance(data, dict):
            raise LoaderError(f"{path} must be a YAML mapping.")

        registered: list[str] = []
        for name, decl in data.items():
            decl["name"] = name
            try:
                defn = converter.structure(decl, SkillDefinition)
                registry.register(defn, overwrite=overwrite)
                registered.append(name)
            except Exception as e:
                raise LoaderError(f"Failed to load skill {name!r}: {e}") from e
        return registered


# -----------------------------------------------------------
# Domains loader
# -----------------------------------------------------------


class DomainsLoader:
    """Reads domains.yaml and populates a DomainRegistry."""

    def __init__(self, rules_dir: Path | str) -> None:
        self.rules_dir = Path(rules_dir)

    def load(
        self,
        registry: "DomainRegistry",
        relative_path: str,
    ) -> list[str]:
        from heroforge.engine.classes_races import (
            DomainDefinition,
        )
        from heroforge.rules.schema import converter

        path = self.rules_dir / relative_path
        if not path.exists():
            raise LoaderError(f"Domains file not found: {path}")
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise LoaderError(f"{path} must be a YAML mapping.")

        registered: list[str] = []
        for name, decl in data.items():
            decl["name"] = name
            try:
                defn = converter.structure(decl, DomainDefinition)
            except Exception as e:
                raise LoaderError(f"Failed to load domain {name!r}: {e}") from e
            registry.register(defn)
            registered.append(name)
        return registered


# -----------------------------------------------------------
# Equipment loader
# -----------------------------------------------------------


class EquipmentLoader:
    """
    Reads armor.yaml and weapons.yaml, populates
    ArmorRegistry and WeaponRegistry.
    """

    def __init__(self, rules_dir: Path | str) -> None:
        self.rules_dir = Path(rules_dir)

    def load_armor(
        self,
        registry: "ArmorRegistry",
        relative_path: str,
    ) -> list[str]:
        from heroforge.engine.equipment import (
            ArmorDefinition,
        )
        from heroforge.rules.schema import converter

        path = self.rules_dir / relative_path
        if not path.exists():
            raise LoaderError(f"Armor file not found: {path}")
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise LoaderError(f"{path} must be a YAML mapping.")

        registered: list[str] = []
        for name, decl in data.items():
            decl["name"] = name
            try:
                defn = converter.structure(decl, ArmorDefinition)
            except Exception as e:
                raise LoaderError(f"Failed to load armor {name!r}: {e}") from e
            registry.register(defn)
            registered.append(name)
        return registered

    def load_weapons(
        self,
        registry: "WeaponRegistry",
        relative_path: str,
    ) -> list[str]:
        from heroforge.engine.equipment import (
            WeaponDefinition,
        )
        from heroforge.rules.schema import converter

        path = self.rules_dir / relative_path
        if not path.exists():
            raise LoaderError(f"Weapons file not found: {path}")
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise LoaderError(f"{path} must be a YAML mapping.")

        registered: list[str] = []
        for name, decl in data.items():
            decl["name"] = name
            try:
                defn = converter.structure(decl, WeaponDefinition)
            except Exception as e:
                raise LoaderError(f"Failed to load weapon {name!r}: {e}") from e
            registry.register(defn)
            registered.append(name)
        return registered


# -----------------------------------------------------------
# Spell compendium loader
# -----------------------------------------------------------


class SpellCompendiumLoader:
    """
    Reads spell compendium YAML files containing metadata
    for all spells (including non-buff spells).

    YAML schema:
      spell_compendium:
        - name: "Fireball"
          school: Evocation
          descriptor: Fire
          level: {Sorcerer: 3, Wizard: 3}
          casting_time: "1 standard action"
          range: "Long (400 ft. + 40 ft./level)"
          duration: Instantaneous
          saving_throw: "Reflex half"
          spell_resistance: "Yes"
          description: "..."
          has_buff_effects: false
    """

    def __init__(self, rules_dir: Path | str) -> None:
        self.rules_dir = Path(rules_dir)

    def load(
        self,
        compendium: "SpellCompendium",
        relative_path: str,
        buff_registry: "BuffRegistry | None" = None,
    ) -> list[str]:
        """
        Load spells into compendium and optionally
        register buff definitions for spells with
        effects.
        """
        from heroforge.engine.effects import (
            BuffCategory,
            build_buff_from_effects,
        )
        from heroforge.engine.spells import (
            SpellEntry,
        )
        from heroforge.rules.schema import converter

        path = self.rules_dir / relative_path
        if not path.exists():
            raise LoaderError(f"Spell compendium file not found: {path}")

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise LoaderError(f"YAML parse error in {path}: {e}") from e

        if not isinstance(data, dict):
            raise LoaderError(f"{path} must be a YAML mapping.")

        registered: list[str] = []
        for name, decl in data.items():
            decl["name"] = name

            try:
                entry = converter.structure(decl, SpellEntry)
            except Exception as e:
                raise LoaderError(
                    f"Failed to load spell entry {name!r}: {e}"
                ) from e
            compendium.register(entry)
            registered.append(name)

            # Dual registration: if the spell has
            # effects, also register a buff.
            if buff_registry is not None and entry.effects:
                buff = build_buff_from_effects(
                    name=name,
                    category=BuffCategory.SPELL,
                    effects_raw=entry.effects,
                    source_book=entry.source_book,
                    note=entry.note,
                    requires_caster_level=(entry.requires_caster_level),
                    mutually_exclusive_with=(entry.mutually_exclusive_with),
                    condition_key=(entry.condition_key),
                )
                if buff is not None:
                    with contextlib.suppress(ValueError):
                        buff_registry.register(buff)

        return registered
