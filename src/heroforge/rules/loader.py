"""
rules/loader.py
---------------
Loads rules YAML files and applies them to a Character's stat graph.

The loader is the bridge between the declarative YAML data layer and the
imperative engine layer.  It reads stats.yaml (and later feats.yaml,
spells.yaml, etc.) and translates declarations into StatNode registrations,
BonusPool registrations, and buff definitions.

The engine (engine/) has zero knowledge of YAML structure.
The YAML files have zero Python code.
This module is the only place where those two meet.

Public API:
  StatsLoader        — reads stats.yaml and builds/validates the stat graph
  LoaderError        — raised on malformed YAML or unknown compute strategies
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
        RaceRegistry,
    )
    from heroforge.engine.effects import BuffRegistry
    from heroforge.engine.feats import FeatRegistry
    from heroforge.engine.prerequisites import (
        Prerequisite,
        PrerequisiteChecker,
    )
    from heroforge.engine.skills import SkillRegistry
    from heroforge.engine.stat import StatGraph
    from heroforge.engine.templates import TemplateRegistry


class LoaderError(Exception):
    pass


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

        for decl in data["stats"]:
            key = decl.get("key")
            if not key:
                raise LoaderError(f"Stat declaration missing 'key': {decl}")

            # Duplicate check within the YAML itself
            if key in seen_keys:
                raise LoaderError(f"Duplicate stat key {key!r} in stats.yaml")
            seen_keys.add(key)

            # Skip if already registered by bootstrap (Character.__init__)
            if graph.has_node(key):
                continue

            # Ensure all pools this node references exist
            pool_keys = decl.get("pools", [])
            for pk in pool_keys:
                if not graph.has_pool(pk):
                    pool = BonusPool(pk)
                    graph.register_pool(pool)

            # Resolve compute strategy
            strategy_name = decl.get("compute", "base_plus_bonus")
            strategy_factory = COMPUTE_STRATEGIES.get(strategy_name)
            if strategy_factory is None:
                raise LoaderError(
                    f"Unknown compute strategy {strategy_name!r} "
                    f"for stat {key!r}. "
                    f"Known strategies: {sorted(COMPUTE_STRATEGIES)}"
                )
            compute_fn = strategy_factory(decl, character)

            node = StatNode(
                key=key,
                base=decl.get("base"),
                inputs=decl.get("inputs", []),
                pool_keys=pool_keys,
                compute=compute_fn,
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

    def validate_yaml(self) -> list[str]:
        """
        Parse stats.yaml and return a list of validation errors (empty = OK).
        Does not modify any graph — used for CI checks on the rules data.
        """
        errors: list[str] = []
        stats_path = self.rules_dir / "core" / "stats.yaml"

        try:
            with open(stats_path) as f:
                data = yaml.safe_load(f)
        except Exception as e:
            return [f"YAML parse error: {e}"]

        if not isinstance(data, dict) or "stats" not in data:
            return ["Missing top-level 'stats' key"]

        seen_keys: set[str] = set()
        declared_keys: set[str] = set()

        for decl in data["stats"]:
            key = decl.get("key", "<missing>")

            if not decl.get("key"):
                errors.append(f"Declaration missing 'key': {decl}")
                continue

            if key in seen_keys:
                errors.append(f"Duplicate key: {key!r}")
            seen_keys.add(key)
            declared_keys.add(key)

            strategy = decl.get("compute", "base_plus_bonus")
            if strategy not in COMPUTE_STRATEGIES:
                errors.append(f"{key!r}: unknown compute strategy {strategy!r}")

            # Check inputs reference declared keys (or are known bootstrap keys)
            bootstrap_keys = {
                "str_score",
                "dex_score",
                "con_score",
                "int_score",
                "wis_score",
                "cha_score",
                "str_mod",
                "dex_mod",
                "con_mod",
                "int_mod",
                "wis_mod",
                "cha_mod",
                "bab",
                "fort_save",
                "ref_save",
                "will_save",
                "ac",
                "initiative",
                "speed",
                "hp_max",
                "sr",
                "attack_melee",
                "attack_ranged",
                "damage_str_bonus",
                "max_dex_bonus",
                "ac_dex_contribution",
            }
            for inp in decl.get("inputs", []):
                if inp not in declared_keys and inp not in bootstrap_keys:
                    errors.append(
                        f"{key!r}: input {inp!r} not yet declared "
                        f"(ordering issue or typo)"
                    )

        return errors


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

# Maps YAML category strings to BuffCategory enum values.
_CATEGORY_MAP = {
    "spell": None,  # resolved after import
    "class": None,
    "condition": None,
    "racial": None,
    "feat": None,
    "item": None,
    "template": None,
}


def _init_category_map() -> None:
    from heroforge.engine.effects import BuffCategory

    global _CATEGORY_MAP
    _CATEGORY_MAP = {
        "spell": BuffCategory.SPELL,
        "class": BuffCategory.CLASS,
        "condition": BuffCategory.CONDITION,
        "racial": BuffCategory.RACIAL,
        "feat": BuffCategory.FEAT,
        "item": BuffCategory.ITEM,
        "template": BuffCategory.TEMPLATE,
    }


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
        _init_category_map()

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

            category_str = decl.get("category", "spell")
            category = _CATEGORY_MAP.get(category_str)
            if category is None:
                raise LoaderError(
                    f"{name!r}: unknown category {category_str!r}"
                )

            # Parse effects
            effects: list[BonusEffect] = []
            for eff_decl in decl.get("effects", []):
                target = eff_decl.get("target")
                if not target:
                    raise LoaderError(
                        f"{name!r}: effect missing 'target': {eff_decl}"
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

                # Resolve condition_key to a callable
                condition = None
                cond_key = eff_decl.get("condition_key")
                if cond_key:
                    condition = CONDITION_REGISTRY.get(cond_key)
                    if condition is None:
                        raise LoaderError(
                            f"{name!r}: unknown condition_key {cond_key!r}. "
                            f"Known keys: {sorted(CONDITION_REGISTRY)}"
                        )

                effects.append(
                    BonusEffect(
                        target=target,
                        bonus_type=bonus_type,
                        value=raw_value,
                        condition=condition,
                        source_label=eff_decl.get("source_label", ""),
                    )
                )

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

    def validate_yaml(
        self, relative_path: str = "core/spells_phb.yaml"
    ) -> list[str]:
        """
        Parse and validate a spell YAML file without touching any registry.
        Returns a list of error strings (empty = OK).
        """
        from heroforge.engine.bonus import BonusType

        errors: list[str] = []
        path = self.rules_dir / relative_path

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except Exception as e:
            return [f"YAML parse error: {e}"]

        if not isinstance(data, dict) or "spells" not in data:
            return ["Missing top-level 'spells' key"]

        valid_bonus_types = {bt.value for bt in BonusType}
        valid_categories = set(_CATEGORY_MAP.keys())
        seen_names: set[str] = set()

        for decl in data["spells"]:
            name = decl.get("name", "<missing>")
            if not decl.get("name"):
                errors.append(f"Declaration missing 'name': {decl}")
                continue

            if name in seen_names:
                errors.append(f"Duplicate name: {name!r}")
            seen_names.add(name)

            cat = decl.get("category", "spell")
            if cat not in valid_categories:
                errors.append(f"{name!r}: unknown category {cat!r}")

            for eff in decl.get("effects", []):
                if not eff.get("target"):
                    errors.append(f"{name!r}: effect missing 'target'")
                bt = eff.get("bonus_type", "untyped")
                if bt not in valid_bonus_types:
                    errors.append(f"{name!r}: unknown bonus_type {bt!r}")
                cond_key = eff.get("condition_key")
                if cond_key and cond_key not in CONDITION_REGISTRY:
                    errors.append(
                        f"{name!r}: unknown condition_key {cond_key!r}"
                    )

        return errors


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

    def validate_yaml(
        self, relative_path: str = "core/templates.yaml"
    ) -> list[str]:
        """Parse and validate without touching a registry."""
        errors: list[str] = []
        path = self.rules_dir / relative_path

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except Exception as e:
            return [f"YAML parse error: {e}"]

        if not isinstance(data, dict) or "templates" not in data:
            return ["Missing top-level 'templates' key"]

        valid_abilities = {"str", "dex", "con", "int", "wis", "cha"}
        from heroforge.engine.bonus import BonusType as _BT

        valid_bonus_types = {bt.value for bt in _BT}
        seen_names: set[str] = set()

        for decl in data["templates"]:
            name = decl.get("name", "<missing>")
            if not decl.get("name"):
                errors.append(f"Declaration missing 'name': {decl}")
                continue

            if name in seen_names:
                errors.append(f"Duplicate template name: {name!r}")
            seen_names.add(name)

            for amod in decl.get("ability_modifiers", []):
                ab = amod.get("ability", "")
                if ab not in valid_abilities:
                    errors.append(f"{name!r}: unknown ability {ab!r}")
                bt = amod.get("bonus_type", "untyped")
                if bt not in valid_bonus_types:
                    errors.append(f"{name!r}: unknown bonus_type {bt!r}")
                if "value" not in amod:
                    errors.append(f"{name!r}: ability modifier missing 'value'")

        return errors


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
                snapshot = decl.get("snapshot", False)
                prereq_checker.register_feat(
                    name,
                    defn.prerequisites,
                    snapshot=snapshot,
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

    def validate_yaml(
        self, relative_path: str = "core/feats_phb.yaml"
    ) -> list[str]:
        """Parse and validate without touching any registry."""
        from heroforge.engine.bonus import BonusType

        errors: list[str] = []
        path = self.rules_dir / relative_path

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except Exception as e:
            return [f"YAML parse error: {e}"]

        if not isinstance(data, dict) or "feats" not in data:
            return ["Missing top-level 'feats' key"]

        valid_kinds = {"always_on", "conditional", "passive"}
        valid_bt = {bt.value for bt in BonusType}
        seen: set[str] = set()

        for decl in data["feats"]:
            name = decl.get("name", "<missing>")
            if not decl.get("name"):
                errors.append(f"Declaration missing 'name': {decl}")
                continue

            if name in seen:
                errors.append(f"Duplicate feat name: {name!r}")
            seen.add(name)

            kind = decl.get("kind", "passive")
            if kind not in valid_kinds:
                errors.append(f"{name!r}: unknown kind {kind!r}")

            for eff in decl.get("effects", []):
                if not eff.get("target"):
                    errors.append(f"{name!r}: effect missing 'target'")
                bt = eff.get("bonus_type", "untyped")
                if bt not in valid_bt:
                    errors.append(f"{name!r}: unknown bonus_type {bt!r}")

        return errors


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
            build_class_from_yaml,
        )

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
                defn = build_class_from_yaml(decl)
                registry.register(defn, overwrite=overwrite)
                registered.append(name)
            except (KeyError, ValueError) as e:
                raise LoaderError(f"Failed to load class {name!r}: {e}") from e

        # Prestige classes
        for decl in data.get("prestige_classes", []):
            name = decl.get("name")
            if not name:
                raise LoaderError(f"PrC missing 'name': {decl}")
            decl["is_prestige"] = True
            try:
                defn = build_class_from_yaml(decl)
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

    def validate_yaml(
        self, relative_path: str = "core/classes.yaml"
    ) -> list[str]:
        errors: list[str] = []
        path = self.rules_dir / relative_path
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except Exception as e:
            return [f"YAML parse error: {e}"]

        if not isinstance(data, dict) or "classes" not in data:
            return ["Missing top-level 'classes' key"]

        valid_bab = {"full", "medium", "poor"}
        valid_save = {"good", "poor"}
        seen: set[str] = set()

        for decl in data["classes"]:
            name = decl.get("name", "<missing>")
            if not decl.get("name"):
                errors.append(f"Missing 'name': {decl}")
                continue
            if name in seen:
                errors.append(f"Duplicate class: {name!r}")
            seen.add(name)

            bab = decl.get("bab_progression", "")
            if bab not in valid_bab:
                errors.append(f"{name!r}: unknown bab_progression {bab!r}")

            for save_name in ("fort", "ref", "will"):
                s = decl.get("save_progressions", {}).get(save_name, "")
                if s not in valid_save:
                    errors.append(
                        f"{name!r}: unknown {save_name} progression {s!r}"
                    )

        return errors


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
        from heroforge.engine.classes_races import (
            build_race_from_yaml,
        )

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

        registered: list[str] = []
        for decl in data["races"]:
            name = decl.get("name")
            if not name:
                raise LoaderError(f"Race declaration missing 'name': {decl}")
            try:
                defn = build_race_from_yaml(decl)
                registry.register(defn, overwrite=overwrite)
                registered.append(name)
            except (KeyError, ValueError) as e:
                raise LoaderError(f"Failed to load race {name!r}: {e}") from e
        return registered

    def validate_yaml(
        self, relative_path: str = "core/races.yaml"
    ) -> list[str]:
        errors: list[str] = []
        path = self.rules_dir / relative_path
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except Exception as e:
            return [f"YAML parse error: {e}"]

        if not isinstance(data, dict) or "races" not in data:
            return ["Missing top-level 'races' key"]

        valid_sizes = {"Small", "Medium", "Large"}
        valid_abilities = {"str", "dex", "con", "int", "wis", "cha"}
        seen: set[str] = set()

        for decl in data["races"]:
            name = decl.get("name", "<missing>")
            if not decl.get("name"):
                errors.append(f"Missing 'name': {decl}")
                continue
            if name in seen:
                errors.append(f"Duplicate race: {name!r}")
            seen.add(name)

            size = decl.get("size", "Medium")
            if size not in valid_sizes:
                errors.append(f"{name!r}: unknown size {size!r}")

            for amod in decl.get("ability_modifiers", []):
                ab = amod.get("ability", "")
                if ab not in valid_abilities:
                    errors.append(f"{name!r}: unknown ability {ab!r}")

        return errors


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
        from heroforge.engine.skills import build_skill_from_yaml

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
                defn = build_skill_from_yaml(decl)
                registry.register(defn, overwrite=overwrite)
                registered.append(name)
            except (KeyError, ValueError) as e:
                raise LoaderError(f"Failed to load skill {name!r}: {e}") from e
        return registered

    def validate_yaml(
        self, relative_path: str = "core/skills.yaml"
    ) -> list[str]:
        errors: list[str] = []
        path = self.rules_dir / relative_path
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except Exception as e:
            return [f"YAML parse error: {e}"]

        if not isinstance(data, dict) or "skills" not in data:
            return ["Missing top-level 'skills' key"]

        valid_abilities = {"str", "dex", "con", "int", "wis", "cha"}
        seen: set[str] = set()

        for decl in data["skills"]:
            name = decl.get("name", "<missing>")
            if not decl.get("name"):
                errors.append(f"Missing 'name': {decl}")
                continue
            if name in seen:
                errors.append(f"Duplicate skill: {name!r}")
            seen.add(name)
            ab = decl.get("ability", "")
            if ab not in valid_abilities:
                errors.append(f"{name!r}: unknown ability {ab!r}")
            if not decl.get("key", "").startswith("skill_"):
                errors.append(f"{name!r}: key must start with 'skill_'")

        return errors
