"""
ui/app_state.py
---------------
Central application state object.

Holds the loaded rule registries (read-only after startup) and the
mutable active character.  All UI widgets take a reference to AppState
and read/write through it rather than keeping their own copies.

This is intentionally not a singleton — tests can create multiple
independent instances.
"""

from __future__ import annotations

from pathlib import Path

from heroforge.engine.character import Character
from heroforge.engine.classes import ClassRegistry
from heroforge.engine.conditions import ConditionRegistry
from heroforge.engine.domains import DomainRegistry
from heroforge.engine.effects import BuffRegistry
from heroforge.engine.equipment import (
    ArmorRegistry,
    WeaponRegistry,
)
from heroforge.engine.feats import FeatRegistry
from heroforge.engine.magic_items import MagicItemRegistry
from heroforge.engine.prerequisites import (
    PrerequisiteChecker,
)
from heroforge.engine.races import RaceRegistry
from heroforge.engine.skills import (
    SkillRegistry,
    register_skills_on_character,
)
from heroforge.engine.spells import SpellCompendium
from heroforge.engine.templates import TemplateRegistry
from heroforge.rules.loader import (
    ClassesLoader,
    ConditionLoader,
    DomainsLoader,
    EquipmentLoader,
    FeatsLoader,
    MagicItemLoader,
    RacesLoader,
    SkillsLoader,
    SpellCompendiumLoader,
    TemplatesLoader,
)

RULES_DIR = Path(__file__).parent.parent / "rules"


class AppState:
    """
    Loaded once at startup; shared across all UI widgets.

    Attributes
    ----------
    buff_registry      : BuffRegistry — buff spells, conditions, items
    magic_item_registry: MagicItemRegistry
    spell_compendium   : SpellCompendium — all 601 SRD spells
    feat_registry      : FeatRegistry
    armor_registry     : ArmorRegistry
    weapon_registry    : WeaponRegistry
    domain_registry    : DomainRegistry
    skill_registry     : SkillRegistry
    template_registry  : TemplateRegistry
    class_registry     : ClassRegistry
    race_registry      : RaceRegistry
    prereq_checker     : PrerequisiteChecker
    character          : Character — the active character
    """

    def __init__(self) -> None:
        self.buff_registry = BuffRegistry()
        self.condition_registry = ConditionRegistry()
        self.magic_item_registry = MagicItemRegistry()
        self.spell_compendium = SpellCompendium()
        self.feat_registry = FeatRegistry()
        self.armor_registry = ArmorRegistry()
        self.weapon_registry = WeaponRegistry()
        self.domain_registry = DomainRegistry()
        self.skill_registry = SkillRegistry()
        self.template_registry = TemplateRegistry()
        self.class_registry = ClassRegistry()
        self.race_registry = RaceRegistry()
        self.character: Character = Character()
        self._loaded = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_rules(self, rules_dir: Path | None = None) -> None:
        """
        Load all rule YAML files from rules_dir (defaults to RULES_DIR).
        Idempotent — subsequent calls are no-ops.
        """
        if self._loaded:
            return

        rd = rules_dir or RULES_DIR

        prereq_checker = PrerequisiteChecker()

        ConditionLoader(rd).load(
            self.condition_registry,
            self.buff_registry,
            "core/conditions_srd.yaml",
        )
        MagicItemLoader(rd).load(
            self.magic_item_registry,
            self.buff_registry,
            "core/magic_items.yaml",
        )
        FeatsLoader(rd).load(
            self.feat_registry,
            "core/feats.yaml",
            prereq_checker,
            self.buff_registry,
        )
        SkillsLoader(rd).load(self.skill_registry, "core/skills.yaml")
        TemplatesLoader(rd).load(self.template_registry, "core/templates.yaml")
        ClassesLoader(rd).load(
            self.class_registry,
            "core/classes",
            prereq_checker=prereq_checker,
            buff_registry=self.buff_registry,
        )
        RacesLoader(rd).load(self.race_registry, "core/races.yaml")

        # Load domains
        DomainsLoader(rd).load(self.domain_registry, "core/domains.yaml")

        # Load equipment
        eq_loader = EquipmentLoader(rd)
        eq_loader.load_armor(self.armor_registry, "core/armor.yaml")
        eq_loader.load_weapons(self.weapon_registry, "core/weapons.yaml")

        # Load spell compendium (all spells, with
        # dual registration of buff effects)
        scl = SpellCompendiumLoader(rd)
        for lvl in range(10):
            sp_file = f"core/spells_level_{lvl}.yaml"
            scl.load(
                self.spell_compendium,
                sp_file,
                buff_registry=self.buff_registry,
            )

        # Store prereq checker for UI access
        self.prereq_checker = prereq_checker

        self._loaded = True

    # ------------------------------------------------------------------
    # Character management
    # ------------------------------------------------------------------

    def new_character(self) -> None:
        """Create a fresh blank character and wire skills into it."""
        self.character = Character()
        self._wire_character()

    def set_character(self, character: Character) -> None:
        """Replace the active character (e.g. after loading from YAML)."""
        self.character = character
        self._wire_character()

    def _wire_character(self) -> None:
        """Wire registries onto the character."""
        if self._loaded:
            self.character._class_registry_ref = self.class_registry
            self.character._feat_registry_ref = self.feat_registry
            register_skills_on_character(self.skill_registry, self.character)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def skill_total(self, skill_name: str) -> int:
        """Return the computed total for a named skill."""
        from heroforge.engine.skills import compute_skill_total

        defn = self.skill_registry.get(skill_name)
        if defn is None:
            return 0
        result = compute_skill_total(self.character, defn)
        return result.total

    @property
    def c(self) -> Character:
        """Short alias for self.character."""
        return self.character
