"""
ui/app_state.py
---------------
Holds the active mutable Character and exposes registry shims
that forward to the module-level Rules singleton
(``heroforge.rules.rules.get_rules``).

Rule-definition registries are loaded once per process by
``Rules.load`` and live on the Rules object, not on AppState.
The shims below are a migration aid for UI code that still
reads ``app_state.feat_registry`` / ``app_state.class_registry``
/ etc. — new code should call ``get_rules()`` directly.
"""

from __future__ import annotations

from heroforge.engine.character import Character
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
from heroforge.engine.skills import (
    SkillRegistry,
    register_skills_on_character,
)
from heroforge.engine.spells import SpellCompendium
from heroforge.engine.templates import TemplateRegistry
from heroforge.rules.rules import get_rules


class AppState:
    """
    Owns the active Character; forwards registry reads to
    the process-wide Rules via ``get_rules()``."""

    def __init__(self) -> None:
        self.character: Character = Character()
        self._loaded = False

    def load_rules(self) -> None:
        """Trigger the lazy Rules load (idempotent)."""
        if self._loaded:
            return
        get_rules()
        self._loaded = True

    # ------------------------------------------------------------------
    # Registry shims — forward to the process-wide Rules singleton.
    # UI code should migrate to calling get_rules() directly.
    # ------------------------------------------------------------------

    @property
    def buff_registry(self) -> BuffRegistry:
        return get_rules().buffs

    @property
    def condition_registry(self) -> ConditionRegistry:
        return get_rules().conditions

    @property
    def magic_item_registry(self) -> MagicItemRegistry:
        return get_rules().magic_items

    @property
    def spell_compendium(self) -> SpellCompendium:
        return get_rules().spells

    @property
    def feat_registry(self) -> FeatRegistry:
        return get_rules().feats

    @property
    def armor_registry(self) -> ArmorRegistry:
        return get_rules().armor

    @property
    def weapon_registry(self) -> WeaponRegistry:
        return get_rules().weapons

    @property
    def material_registry(self) -> MaterialRegistry:
        return get_rules().materials

    @property
    def domain_registry(self) -> DomainRegistry:
        return get_rules().domains

    @property
    def skill_registry(self) -> SkillRegistry:
        return get_rules().skills

    @property
    def template_registry(self) -> TemplateRegistry:
        return get_rules().templates

    @property
    def class_registry(self) -> ClassRegistry:
        return get_rules().classes

    @property
    def race_registry(self) -> RaceRegistry:
        return get_rules().races

    @property
    def prereq_checker(self) -> PrerequisiteChecker | None:
        return get_rules().prereq_checker

    @property
    def derived_pools(self) -> dict:
        return get_rules().derived_pools

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
        """Wire skills and derived-pool consumers onto the character."""
        if not self._loaded:
            return
        register_skills_on_character(self.character)
        dp = get_rules().derived_pools
        if dp:
            from heroforge.engine.derived_pools import install_consumers

            install_consumers(self.character, dp)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def skill_total(self, skill_name: str) -> int:
        """Return the computed total for a named skill."""
        from heroforge.engine.skills import compute_skill_total

        defn = get_rules().skills.get(skill_name)
        if defn is None:
            return 0
        result = compute_skill_total(self.character, defn)
        return result.total

    @property
    def c(self) -> Character:
        """Short alias for self.character."""
        return self.character
