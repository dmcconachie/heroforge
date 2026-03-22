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
from heroforge.engine.classes_races import (
    ClassRegistry,
    RaceRegistry,
)
from heroforge.engine.effects import BuffRegistry
from heroforge.engine.feats import FeatRegistry
from heroforge.engine.skills import SkillRegistry, register_skills_on_character
from heroforge.engine.templates import TemplateRegistry

RULES_DIR = Path(__file__).parent.parent / "rules"


class AppState:
    """
    Loaded once at startup; shared across all UI widgets.

    Attributes
    ----------
    spell_registry    : BuffRegistry  — spells and conditions as BuffDefinitions
    feat_registry     : FeatRegistry  — feat definitions
    skill_registry    : SkillRegistry — skill metadata
    template_registry : TemplateRegistry
    class_registry    : ClassRegistry
    race_registry     : RaceRegistry
    character         : Character     — the currently active character
    """

    def __init__(self) -> None:
        self.spell_registry = BuffRegistry()
        self.feat_registry = FeatRegistry()
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
        from heroforge.engine.prerequisites import PrerequisiteChecker
        from heroforge.rules.loader import (
            ClassesLoader,
            FeatsLoader,
            RacesLoader,
            SkillsLoader,
            SpellsLoader,
            TemplatesLoader,
        )

        prereq_checker = PrerequisiteChecker()

        SpellsLoader(rd).load(self.spell_registry)
        SpellsLoader(rd).load(
            self.spell_registry,
            "core/conditions_srd.yaml",
        )
        FeatsLoader(rd).load(
            self.feat_registry,
            prereq_checker,
            self.spell_registry,
        )
        FeatsLoader(rd).load(
            self.feat_registry,
            prereq_checker,
            self.spell_registry,
            "core/feats_srd.yaml",
        )
        SkillsLoader(rd).load(self.skill_registry)
        TemplatesLoader(rd).load(self.template_registry)
        ClassesLoader(rd).load(
            self.class_registry,
            prereq_checker=prereq_checker,
        )
        RacesLoader(rd).load(self.race_registry)

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
