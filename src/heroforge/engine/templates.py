"""
engine/templates.py
-------------------
Creature template application for D&D 3.5e.

Templates (Half-Celestial, Half-Dragon, Lycanthrope, etc.) are layered
modifications applied on top of a character's base race.  They can:
  - Modify ability scores (fixed amounts or formulas)
  - Change or add creature type / subtypes
  - Grant natural armor bonuses
  - Grant special qualities and abilities
  - Grant natural attacks
  - Grant spell-like abilities
  - Modify BAB and saves
  - Add feats
  - For "partially applicable" templates: scale with a level parameter

Templates are applied in order.  Multiple templates can stack (rare but
legal — Half-Celestial Half-Dragon exists in the rules).

Design:
  - TemplateDefinition: the data model loaded from YAML
  - TemplateApplication: one instance on a character (template + level)
  - TemplateRegistry: lookup by name
  - apply_template() / remove_template(): wire effects into Character pools
  - Templates use the same BonusEntry/BonusPool machinery as buffs

Public API:
  TemplateDefinition   — data model for a template
  TemplateApplication  — one applied template (with optional partial level)
  TemplateRegistry     — lookup
  apply_template()     — apply a template's effects to a Character
  remove_template()    — remove a template's effects from a Character
  effective_type()     — resolve creature type after all templates
  effective_subtypes() — resolve subtypes after all templates
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from heroforge.engine.bonus import BonusEntry, BonusType

if TYPE_CHECKING:
    from typing import Any

    from heroforge.engine.character import Character


# ---------------------------------------------------------------------------
# TemplateAbilityModifier
# ---------------------------------------------------------------------------


@dataclass
class TemplateAbilityModifier:
    """
    One ability score modification from a template.

    value: int (fixed) or str (formula — same syntax as BuffDefinition)
    bonus_type: typically untyped for template racial mods, but some
                templates grant enhancement or other typed bonuses.
    """

    ability: str  # "str", "dex", "con", "int", "wis", "cha"
    value: int | str
    bonus_type: BonusType = BonusType.UNTYPED


# ---------------------------------------------------------------------------
# TemplateDefinition
# ---------------------------------------------------------------------------


@dataclass
class TemplateDefinition:
    """
    Complete definition of a creature template.

    Attributes
    ----------
    name                : Unique template name.
    source_book         : e.g. "MM", "MM2"
    cr_adjustment       : e.g. "+1", "+2", "—" (display only)
    la_adjustment       : Level Adjustment as string, e.g. "+4"
    type_change         : If set, overrides the base creature type entirely.
                          e.g. "Dragon" for Half-Dragon.
    subtype_add         : List of subtypes added by this template.
    subtype_remove      : List of subtypes removed (rare).
    ability_modifiers   : List of TemplateAbilityModifier entries.
    natural_armor_bonus : Flat bonus to natural armor AC (untyped, stacks
                          with racial natural armor as enhancement bonus).
    partially_applicable: True if the template has a "level" field (like
                          Lycanthrope, Mostly Half-Celestial).
    max_level           : Maximum level for partial templates (0 = N/A).
    special_qualities   : List of strings (display only for now; full
                          implementation in a future phase).
    grants_feats        : List of feat names granted by the template.
    note                : Display hint.

    ongoing_prereq      : Optional prerequisite that must remain met to
                          keep the template benefits (e.g. alignment for
                          some templates).
    """

    name: str
    source_book: str = "MM"
    cr_adjustment: str = "+0"
    la_adjustment: str = "+0"
    type_change: str | None = None
    subtype_add: list[str] = field(default_factory=list)
    subtype_remove: list[str] = field(default_factory=list)
    ability_modifiers: list[TemplateAbilityModifier] = field(
        default_factory=list
    )
    natural_armor_bonus: int = 0
    partially_applicable: bool = False
    max_level: int = 0
    special_qualities: list[str] = field(default_factory=list)
    grants_feats: list[str] = field(default_factory=list)
    note: str = ""
    ongoing_prereq: Any | None = None  # Prerequisite


# ---------------------------------------------------------------------------
# TemplateApplication
# ---------------------------------------------------------------------------


@dataclass
class TemplateApplication:
    """
    One template applied to a character.

    template_name : Name of the TemplateDefinition.
    level         : For partially_applicable templates, which level is applied.
                    0 = not applicable / fully applied.
    dm_override   : True if the DM overrode the template's prerequisites.
    note          : Optional DM/player annotation.
    """

    template_name: str
    level: int = 0
    dm_override: bool = False
    note: str = ""


# ---------------------------------------------------------------------------
# TemplateRegistry
# ---------------------------------------------------------------------------


class TemplateRegistry:
    """Central lookup for TemplateDefinitions."""

    def __init__(self) -> None:
        self._defs: dict[str, TemplateDefinition] = {}

    def register(
        self, defn: TemplateDefinition, overwrite: bool = False
    ) -> None:
        if defn.name in self._defs and not overwrite:
            raise ValueError(
                f"TemplateDefinition {defn.name!r} already registered."
            )
        self._defs[defn.name] = defn

    def get(self, name: str) -> TemplateDefinition | None:
        return self._defs.get(name)

    def require(self, name: str) -> TemplateDefinition:
        defn = self._defs.get(name)
        if defn is None:
            raise KeyError(f"No TemplateDefinition registered for {name!r}.")
        return defn

    def all_names(self) -> list[str]:
        return sorted(self._defs.keys())

    def __len__(self) -> int:
        return len(self._defs)

    def __contains__(self, name: str) -> bool:
        return name in self._defs


# ---------------------------------------------------------------------------
# Pool source key helpers
# ---------------------------------------------------------------------------


def _template_source_key(template_name: str) -> str:
    """Stable pool source key for a template's contributions."""
    return f"template:{template_name}"


# ---------------------------------------------------------------------------
# Apply / remove template
# ---------------------------------------------------------------------------


def apply_template(
    defn: TemplateDefinition,
    character: "Character",
    level: int = 0,
) -> None:
    """
    Apply a TemplateDefinition's effects to a Character.

    - Ability score bonuses → registered in the relevant ability score pools
    - Natural armor bonus   → registered in the "ac" pool
    - Type / subtype changes → stored as character attributes
    - Granted feats         → added to character.feats if not already present
    - Template application  → recorded in character.templates list

    Idempotent: applying the same template twice updates to the latest values
    (set_source overwrites).

    level: for partially_applicable templates, controls which level's bonuses
           apply.  Ignored for non-partial templates.
    """
    source_key = _template_source_key(defn.name)

    # --- Ability score bonuses -------------------------------------------
    for mod in defn.ability_modifiers:
        pool_key = f"{mod.ability}_score"
        pool = character.get_pool(pool_key)
        if pool is None:
            continue

        # Resolve value (formula or int)
        if isinstance(mod.value, str):
            from heroforge.engine.effects import evaluate_formula

            resolved = evaluate_formula(mod.value, character=character)
        else:
            resolved = mod.value

        # For partial templates, scale by level if applicable
        if defn.partially_applicable and level > 0 and defn.max_level > 0:
            fraction = level / defn.max_level
            resolved = int(resolved * fraction)

        entry = BonusEntry(
            value=resolved,
            bonus_type=mod.bonus_type,
            source=defn.name,
        )
        pool.set_source(source_key, [entry])
        character._graph.invalidate_pool(pool_key)

    # --- Natural armor bonus ---------------------------------------------
    if defn.natural_armor_bonus != 0:
        ac_pool = character.get_pool("ac")
        if ac_pool is not None:
            na_value = defn.natural_armor_bonus
            if defn.partially_applicable and level > 0 and defn.max_level > 0:
                na_value = int(na_value * level / defn.max_level)

            entry = BonusEntry(
                value=na_value,
                bonus_type=BonusType.NATURAL_ARMOR,
                source=f"{defn.name} (natural armor)",
            )
            ac_source_key = f"{source_key}:natural_armor"
            ac_pool.set_source(ac_source_key, [entry])
            character._graph.invalidate_pool("ac")

    # --- Type / subtype changes ------------------------------------------
    if defn.type_change:
        character._creature_type_override = defn.type_change

    if defn.subtype_add or defn.subtype_remove:
        existing = list(getattr(character, "_template_subtypes", []))
        for sub in defn.subtype_add:
            if sub not in existing:
                existing.append(sub)
        for sub in defn.subtype_remove:
            if sub in existing:
                existing.remove(sub)
        character._template_subtypes = existing

    # --- Granted feats ---------------------------------------------------
    for feat_name in defn.grants_feats:
        # Use add_feat so always-on effects apply
        feat_reg = getattr(character, "_feat_registry_ref", None)
        feat_defn = feat_reg.get(feat_name) if feat_reg else None
        character.add_feat(
            feat_name,
            feat_defn,
            source=defn.name,
        )

    # --- Record application ----------------------------------------------
    existing_apps = [
        a for a in character.templates if a.template_name != defn.name
    ]
    existing_apps.append(
        TemplateApplication(
            template_name=defn.name,
            level=level,
        )
    )
    character.templates = existing_apps

    # Notify
    affected = {
        f"{ab}_score" for ab in ("str", "dex", "con", "int", "wis", "cha")
    }
    affected.add("ac")
    character._notify(affected)


def remove_template(
    defn: TemplateDefinition,
    character: "Character",
) -> None:
    """
    Remove a template's effects from a Character.

    Reverses ability score bonuses, natural armor, type changes (if this
    was the only template changing the type), and removes granted feats
    that came from this template.

    Idempotent: safe to call if the template is not applied.
    """
    source_key = _template_source_key(defn.name)

    # --- Ability score bonuses -------------------------------------------
    for mod in defn.ability_modifiers:
        pool_key = f"{mod.ability}_score"
        pool = character.get_pool(pool_key)
        if pool is not None:
            pool.clear_source(source_key)
            character._graph.invalidate_pool(pool_key)

    # --- Natural armor bonus ---------------------------------------------
    ac_pool = character.get_pool("ac")
    if ac_pool is not None:
        ac_source_key = f"{source_key}:natural_armor"
        ac_pool.clear_source(ac_source_key)
        character._graph.invalidate_pool("ac")

    # --- Type / subtype changes ------------------------------------------
    # Only clear type override if no other template sets it
    remaining_apps = [
        a for a in character.templates if a.template_name != defn.name
    ]
    other_type_changes = any(
        # We'd need the registry here — for now, clear unconditionally
        # if this template was responsible.
        # Full resolution requires checking other templates in the registry.
        False  # placeholder: registry lookup in a full implementation
        for a in remaining_apps
    )
    if defn.type_change and not other_type_changes and not remaining_apps:
        character._creature_type_override = None

    # Remove added subtypes
    existing = list(getattr(character, "_template_subtypes", []))
    for sub in defn.subtype_add:
        if sub in existing:
            existing.remove(sub)
    character._template_subtypes = existing

    # --- Granted feats ---------------------------------------------------
    feat_reg = getattr(character, "_feat_registry_ref", None)
    for feat_name in defn.grants_feats:
        feat_defn = feat_reg.get(feat_name) if feat_reg else None
        character.remove_feat(feat_name, feat_defn)

    # --- Update application list -----------------------------------------
    character.templates = [
        a for a in character.templates if a.template_name != defn.name
    ]

    # Notify
    affected = {
        f"{ab}_score" for ab in ("str", "dex", "con", "int", "wis", "cha")
    }
    affected.add("ac")
    character._notify(affected)


# ---------------------------------------------------------------------------
# Effective type resolution
# ---------------------------------------------------------------------------


def effective_type(character: "Character") -> str:
    """
    Resolve the character's effective creature type after all templates.

    Walks templates in application order; the last type_change wins.
    Falls back to the race-derived type via CapabilityChecker.
    """
    # Check for template overrides (last one wins)
    type_override = getattr(character, "_creature_type_override", None)
    if type_override:
        return type_override

    # Race-derived type (same logic as CapabilityChecker)
    from heroforge.engine.prerequisites import CapabilityChecker

    return CapabilityChecker().effective_creature_type(character)


def effective_subtypes(character: "Character") -> list[str]:
    """
    Resolve the character's effective subtypes after all templates.
    """
    from heroforge.engine.prerequisites import CapabilityChecker

    base = CapabilityChecker().effective_subtypes(character)
    template_subs = list(getattr(character, "_template_subtypes", []))
    # Deduplicate, preserving order
    seen = set(base)
    result = list(base)
    for sub in template_subs:
        if sub not in seen:
            result.append(sub)
            seen.add(sub)
    return result


# ---------------------------------------------------------------------------
# YAML builder
# ---------------------------------------------------------------------------


_TEMPLATE_ALLOWED_KEYS = {
    "name",
    "source_book",
    "cr_adjustment",
    "la_adjustment",
    "type_change",
    "subtype_add",
    "subtype_remove",
    "ability_modifiers",
    "natural_armor_bonus",
    "natural_armor_bonus_type",
    "special_qualities",
    "grants_feats",
    "partially_applicable",
    "note",
    "ongoing_prereq",
    "max_level",
}


def build_template_from_yaml(
    decl: dict,
) -> TemplateDefinition:
    """
    Build a TemplateDefinition from a YAML dict.

    Expected structure:
      name: "Half-Celestial"
      source_book: MM
      cr_adjustment: "+1"
      la_adjustment: "+4"
      type_change: null
      subtype_add: [Extraplanar]
      ability_modifiers:
        - ability: str
          value: 4
          bonus_type: untyped
      natural_armor_bonus: 1
      partially_applicable: false
      special_qualities: [...]
      grants_feats: [...]
      note: "..."
    """
    from heroforge.rules.schema import (
        _forbid_extra,
    )

    _forbid_extra(
        decl,
        _TEMPLATE_ALLOWED_KEYS,
        decl.get("name", "?"),
    )
    ability_mods = []
    for amod in decl.get("ability_modifiers", []):
        bt_str = amod.get("bonus_type", "untyped")
        try:
            bt = BonusType(bt_str)
        except ValueError:
            bt = BonusType.UNTYPED
        ability_mods.append(
            TemplateAbilityModifier(
                ability=amod["ability"],
                value=amod["value"],
                bonus_type=bt,
            )
        )

    return TemplateDefinition(
        name=decl["name"],
        source_book=decl.get("source_book", "MM"),
        cr_adjustment=str(decl.get("cr_adjustment", "+0")),
        la_adjustment=str(decl.get("la_adjustment", "+0")),
        type_change=decl.get("type_change"),
        subtype_add=decl.get("subtype_add", []),
        subtype_remove=decl.get("subtype_remove", []),
        ability_modifiers=ability_mods,
        natural_armor_bonus=int(decl.get("natural_armor_bonus", 0)),
        partially_applicable=bool(decl.get("partially_applicable", False)),
        max_level=int(decl.get("max_level", 0)),
        special_qualities=decl.get("special_qualities", []),
        grants_feats=decl.get("grants_feats", []),
        note=decl.get("note", ""),
    )
