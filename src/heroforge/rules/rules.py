"""
rules/rules.py
--------------
Single container for every rule-definition artifact loaded from
YAML at startup, plus a module-level accessor so engine code can
reach rules without wiring through Character or AppState.

Usage:
    from heroforge.rules.rules import get_rules
    rules = get_rules()            # lazy-loads on first call
    feat = rules.feats.get("Power Attack")

Tests override via ``set_rules(r)`` and reset with
``reset_rules()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from heroforge.engine.classes import ClassRegistry
from heroforge.engine.conditions import ConditionRegistry
from heroforge.engine.domains import DomainRegistry
from heroforge.engine.effects import BuffRegistry
from heroforge.engine.equipment import (
    ArmorRegistry,
    MaterialRegistry,
    WeaponRegistry,
)
from heroforge.engine.feats import FeatRegistry
from heroforge.engine.magic_items import MagicItemRegistry
from heroforge.engine.prerequisites import PrerequisiteChecker
from heroforge.engine.races import RaceRegistry
from heroforge.engine.skills import SkillRegistry
from heroforge.engine.spells import SpellCompendium
from heroforge.engine.templates import TemplateRegistry
from heroforge.rules.loader import (
    ClassesLoader,
    ConditionLoader,
    DerivedPoolsLoader,
    DomainsLoader,
    EquipmentLoader,
    FeatsLoader,
    MagicItemLoader,
    RacesLoader,
    SkillsLoader,
    SpellCompendiumLoader,
    TemplatesLoader,
)

RULES_DIR = Path(__file__).parent


@dataclass
class Rules:
    """
    All rule-definition registries + derived pools + prereq
    checker. Treat as read-only after load()."""

    buffs: BuffRegistry = field(default_factory=BuffRegistry)
    conditions: ConditionRegistry = field(default_factory=ConditionRegistry)
    magic_items: MagicItemRegistry = field(default_factory=MagicItemRegistry)
    spells: SpellCompendium = field(default_factory=SpellCompendium)
    feats: FeatRegistry = field(default_factory=FeatRegistry)
    armor: ArmorRegistry = field(default_factory=ArmorRegistry)
    weapons: WeaponRegistry = field(default_factory=WeaponRegistry)
    materials: MaterialRegistry = field(default_factory=MaterialRegistry)
    domains: DomainRegistry = field(default_factory=DomainRegistry)
    skills: SkillRegistry = field(default_factory=SkillRegistry)
    templates: TemplateRegistry = field(default_factory=TemplateRegistry)
    classes: ClassRegistry = field(default_factory=ClassRegistry)
    races: RaceRegistry = field(default_factory=RaceRegistry)
    derived_pools: dict = field(default_factory=dict)
    prereq_checker: PrerequisiteChecker | None = None

    def load(self, rules_dir: Path | None = None) -> None:
        """
        Populate from YAML. Instantiates PrerequisiteChecker
        locally, passes it to loaders that register into it,
        then assigns the populated checker to self."""
        rd = rules_dir or RULES_DIR

        prereq_checker = PrerequisiteChecker()

        ConditionLoader(rd).load(
            self.conditions,
            self.buffs,
            "core/conditions_srd.yaml",
        )
        mi_loader = MagicItemLoader(rd)
        for mi_file in (
            "head",
            "face",
            "throat",
            "shoulders",
            "body",
            "torso",
            "arms",
            "hands",
            "ring",
            "waist",
            "feet",
            "slotless",
            "tool",
            "consumable",
        ):
            mi_loader.load(
                self.magic_items,
                f"core/magic_items/{mi_file}.yaml",
            )
        mi_loader.load(self.magic_items, "custom/magic_items.yaml")

        FeatsLoader(rd).load(
            self.feats,
            "core/feats.yaml",
            prereq_checker,
            self.buffs,
        )
        FeatsLoader(rd).load(
            self.feats,
            "custom/feats.yaml",
            prereq_checker,
            self.buffs,
        )
        SkillsLoader(rd).load(self.skills, "core/skills.yaml")
        TemplatesLoader(rd).load(self.templates, "core/templates.yaml")
        ClassesLoader(rd).load(
            self.classes,
            "core/classes",
            prereq_checker=prereq_checker,
            buff_registry=self.buffs,
        )
        ClassesLoader(rd).load(
            self.classes,
            "custom/classes",
            prereq_checker=prereq_checker,
            buff_registry=self.buffs,
        )
        RacesLoader(rd).load(self.races, "core/races.yaml")
        DomainsLoader(rd).load(self.domains, "core/domains.yaml")

        eq_loader = EquipmentLoader(rd)
        eq_loader.load_armor(self.armor, "core/armor.yaml")
        eq_loader.load_weapons(self.weapons, "core/weapons.yaml")
        eq_loader.load_materials(self.materials, "core/materials.yaml")
        eq_loader.load_materials(
            self.materials,
            "custom/materials.yaml",
        )

        scl = SpellCompendiumLoader(rd)
        for lvl in range(10):
            scl.load(
                self.spells,
                f"core/spells_level_{lvl}.yaml",
                buff_registry=self.buffs,
            )

        self.prereq_checker = prereq_checker
        self.derived_pools = DerivedPoolsLoader(rd).load(
            "core/derived_pools.yaml"
        )


_rules: Rules | None = None


def get_rules() -> Rules:
    """Return the process-wide Rules, lazy-loading on first call."""
    global _rules  # noqa: PLW0603
    if _rules is None:
        r = Rules()
        r.load()
        _rules = r
    return _rules


def set_rules(rules: Rules) -> None:
    """Override the singleton. For tests and alternate rulesets."""
    global _rules  # noqa: PLW0603
    _rules = rules


def reset_rules() -> None:
    """Forget the current singleton. Next get_rules() rebuilds."""
    global _rules  # noqa: PLW0603
    _rules = None
