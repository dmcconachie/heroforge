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
  SpellsLoader           — spell/condition/item YAML
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
        ClassRegistry,
        DomainRegistry,
        RaceRegistry,
    )
    from heroforge.engine.effects import BuffRegistry
    from heroforge.engine.equipment import (
        ArmorRegistry,
        WeaponRegistry,
    )
    from heroforge.engine.feats import FeatRegistry
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

        if not isinstance(data, dict) or "stats" not in data:
            raise LoaderError("stats.yaml must have a top-level 'stats' key.")

        registered: list[str] = []
        seen_keys: set[str] = set()

        from heroforge.rules.schema import (
            _forbid_extra,
        )

        for decl in data["stats"]:
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
# SpellsLoader
# ---------------------------------------------------------------------------

# Condition keys referenced in YAML map to Python callables.
# The loader attaches these to BonusEffect.condition at load time.
# New condition keys can be added here when new splatbooks need them.
CONDITION_REGISTRY: dict[str, object] = {
    "humanoid_only": lambda char: (
        getattr(char, "_race_type", "Humanoid") == "Humanoid"
    ),
    # Future:
    # "elf_only":      lambda char: ...,
    # "same_deity":    lambda char: ...,
}


def _forbid_extra_spell(val: dict, label: str) -> None:
    """Reject unknown spell keys."""
    from heroforge.engine.effects import (
        BuffDefinition as _BD,
    )
    from heroforge.rules.schema import (
        _forbid_extra,
    )

    _forbid_extra(val, _BD, label)


def _forbid_extra_effect(val: dict, label: str) -> None:
    """Reject unknown effect keys."""
    from heroforge.engine.effects import (
        BonusEffect as _BE,
    )
    from heroforge.rules.schema import (
        _forbid_extra,
    )

    _forbid_extra(val, _BE, label)


class SpellsLoader:
    """
    Reads rules/core/spells_phb.yaml (and other spell/buff YAML files)
    and populates a BuffRegistry with BuffDefinition objects.

    Usage:
        registry = BuffRegistry()
        loader = SpellsLoader(rules_dir)
        loader.load(registry)           # loads PHB spells
        loader.load(registry, "spell_compendium/spells.yaml", overwrite=True)

    condition_key entries in effect declarations are resolved against
    CONDITION_REGISTRY to attach Python callables.
    """

    def __init__(self, rules_dir: Path | str) -> None:
        self.rules_dir = Path(rules_dir)

    def load(
        self,
        registry: BuffRegistry,
        relative_path: str = "core/spells_phb.yaml",
        overwrite: bool = False,
    ) -> list[str]:
        """
        Load a spell YAML file into the registry.

        Returns a list of buff names that were registered.
        Raises LoaderError on unknown bonus types, strategies, or bad YAML.
        """
        from heroforge.engine.bonus import BonusType
        from heroforge.engine.effects import (
            BonusEffect,
            BuffCategory,
            BuffDefinition,
        )

        path = self.rules_dir / relative_path
        if not path.exists():
            raise LoaderError(f"Spell file not found: {path}")

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise LoaderError(f"YAML parse error in {path}: {e}") from e

        if not isinstance(data, dict) or "spells" not in data:
            raise LoaderError(f"{path} must have a top-level 'spells' key.")

        # Build BonusType lookup once
        bonus_type_map: dict[str, BonusType] = {
            bt.value: bt for bt in BonusType
        }

        registered: list[str] = []

        for decl in data["spells"]:
            name = decl.get("name")
            if not name:
                raise LoaderError(f"Spell declaration missing 'name': {decl}")

            _forbid_extra_spell(decl, name)

            category_str = decl.get("category", "spell")
            try:
                category = BuffCategory(category_str)
            except ValueError as e:
                raise LoaderError(
                    f"{name!r}: unknown category "
                    f"{category_str!r}"
                ) from e

            # Parse effects
            effects: list[BonusEffect] = []
            for eff_decl in decl.get("effects", []):
                target = eff_decl.get("target")
                if not target:
                    raise LoaderError(
                        f"{name!r}: effect missing 'target': {eff_decl}"
                    )

                _forbid_extra_effect(
                    eff_decl,
                    f"{name!r} effect",
                )

                bt_str = eff_decl.get("bonus_type", "untyped")
                bonus_type = bonus_type_map.get(bt_str)
                if bonus_type is None:
                    raise LoaderError(
                        f"{name!r}: unknown bonus_type {bt_str!r}"
                    )

                raw_value = eff_decl.get("value", 0)
                # YAML may parse small formulas as ints automatically;
                # ensure formula strings stay as strings
                if isinstance(raw_value, bool):
                    raw_value = int(raw_value)

                cond_key = eff_decl.get("condition_key", "")
                eff = BonusEffect(
                    target=target,
                    bonus_type=bonus_type,
                    value=raw_value,
                    condition_key=cond_key,
                    source_label=eff_decl.get("source_label", ""),
                )
                # Resolve condition_key → callable
                if cond_key:
                    resolved = CONDITION_REGISTRY.get(cond_key)
                    if resolved is None:
                        raise LoaderError(
                            f"{name!r}: unknown "
                            f"condition_key "
                            f"{cond_key!r}. Known: "
                            f"{sorted(CONDITION_REGISTRY)}"
                        )
                    eff.condition = resolved
                effects.append(eff)

            defn = BuffDefinition(
                name=name,
                category=category,
                source_book=decl.get("source_book", "PHB"),
                effects=effects,
                requires_caster_level=decl.get("requires_caster_level", False),
                mutually_exclusive_with=decl.get("mutually_exclusive_with", []),
                note=decl.get("note", ""),
            )

            try:
                registry.register(defn, overwrite=overwrite)
                registered.append(name)
            except ValueError as e:
                raise LoaderError(str(e)) from e

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
        relative_path: str = "core/templates.yaml",
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

        if not isinstance(data, dict) or "templates" not in data:
            raise LoaderError(f"{path} must have a top-level 'templates' key.")

        registered: list[str] = []

        for decl in data["templates"]:
            if not decl.get("name"):
                raise LoaderError(
                    f"Template declaration missing 'name': {decl}"
                )
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
        prereq_checker: PrerequisiteChecker | None = None,
        buff_registry: BuffRegistry | None = None,
        relative_path: str = "core/feats_phb.yaml",
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

        if not isinstance(data, dict) or "feats" not in data:
            raise LoaderError(f"{path} must have a top-level 'feats' key.")

        registered: list[str] = []

        for decl in data["feats"]:
            name = decl.get("name")
            if not name:
                raise LoaderError(f"Feat declaration missing 'name': {decl}")

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
    Reads rules/core/classes.yaml and populates a ClassRegistry.

    Usage:
        registry = ClassRegistry()
        loader = ClassesLoader(rules_dir)
        loader.load(registry)
    """

    def __init__(self, rules_dir: Path | str) -> None:
        self.rules_dir = Path(rules_dir)

    def load(
        self,
        registry: ClassRegistry,
        relative_path: str = "core/classes.yaml",
        overwrite: bool = False,
        prereq_checker: PrerequisiteChecker | None = None,
    ) -> list[str]:
        from heroforge.engine.classes_races import (
            ClassDefinition,
        )
        from heroforge.rules.schema import converter

        path = self.rules_dir / relative_path
        if not path.exists():
            raise LoaderError(f"Classes file not found: {path}")

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise LoaderError(f"YAML parse error in {path}: {e}") from e

        if not isinstance(data, dict) or "classes" not in data:
            raise LoaderError(f"{path} must have a top-level 'classes' key.")

        registered: list[str] = []
        for decl in data["classes"]:
            name = decl.get("name")
            if not name:
                raise LoaderError(f"Class missing 'name': {decl}")
            try:
                defn = converter.structure(decl, ClassDefinition)
                registry.register(defn, overwrite=overwrite)
                registered.append(name)
            except Exception as e:
                raise LoaderError(f"Failed to load class {name!r}: {e}") from e

        # Prestige classes
        for decl in data.get("prestige_classes", []):
            name = decl.get("name")
            if not name:
                raise LoaderError(f"PrC missing 'name': {decl}")
            decl["is_prestige"] = True
            try:
                defn = converter.structure(decl, ClassDefinition)
                registry.register(defn, overwrite=overwrite)
                registered.append(name)
            except (KeyError, ValueError) as e:
                raise LoaderError(f"Failed to load PrC {name!r}: {e}") from e
            if prereq_checker is not None:
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

        return registered

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
        relative_path: str = "core/races.yaml",
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

        if not isinstance(data, dict) or "races" not in data:
            raise LoaderError(f"{path} must have a top-level 'races' key.")

        from heroforge.engine.classes_races import (
            RaceDefinition,
        )
        from heroforge.rules.schema import converter

        registered: list[str] = []
        for decl in data["races"]:
            name = decl.get("name")
            if not name:
                raise LoaderError(f"Race declaration missing 'name': {decl}")
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
        relative_path: str = "core/skills.yaml",
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

        if not isinstance(data, dict) or "skills" not in data:
            raise LoaderError(f"{path} must have a top-level 'skills' key.")

        registered: list[str] = []
        for decl in data["skills"]:
            name = decl.get("name")
            if not name:
                raise LoaderError(f"Skill declaration missing 'name': {decl}")
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
        relative_path: str = "core/domains.yaml",
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
        if not isinstance(data, dict) or "domains" not in data:
            raise LoaderError(f"{path}: missing 'domains' key")

        registered: list[str] = []
        for decl in data["domains"]:
            name = decl.get("name")
            if not name:
                raise LoaderError(f"Domain missing 'name': {decl}")
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
        relative_path: str = "core/armor.yaml",
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
        if not isinstance(data, dict) or "armor" not in data:
            raise LoaderError(f"{path}: missing 'armor' key")

        registered: list[str] = []
        for decl in data["armor"]:
            name = decl.get("name")
            if not name:
                raise LoaderError(f"Armor missing 'name': {decl}")
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
        relative_path: str = "core/weapons.yaml",
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
        if not isinstance(data, dict) or "weapons" not in data:
            raise LoaderError(f"{path}: missing 'weapons' key")

        registered: list[str] = []
        for decl in data["weapons"]:
            name = decl.get("name")
            if not name:
                raise LoaderError(f"Weapon missing 'name': {decl}")
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
        relative_path: str = ("core/spells_srd_0_3.yaml"),
    ) -> list[str]:
        from heroforge.engine.spells import SpellEntry
        from heroforge.rules.schema import converter

        path = self.rules_dir / relative_path
        if not path.exists():
            raise LoaderError(f"Spell compendium file not found: {path}")

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise LoaderError(f"YAML parse error in {path}: {e}") from e

        key = "spell_compendium"
        if not isinstance(data, dict) or key not in data:
            raise LoaderError(f"{path} must have a top-level '{key}' key.")

        registered: list[str] = []
        for decl in data[key]:
            name = decl.get("name")
            if not name:
                raise LoaderError(
                    f"Spell compendium entry missing 'name': {decl}"
                )

            try:
                entry = converter.structure(decl, SpellEntry)
            except Exception as e:
                raise LoaderError(
                    f"Failed to load spell entry {name!r}: {e}"
                ) from e
            compendium.register(entry)
            registered.append(name)

        return registered
