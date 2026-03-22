"""
heroforge/export/sheet_data.py
-------------------------------
Extracts all character data needed for PDF rendering into plain,
PDF-renderer-agnostic dicts.

The renderer (renderer.py) knows nothing about the engine — it only
draws what this module hands it.  This separation means the renderer
can be swapped or tested without an AppState.

Public API:
  SheetData         — dataclass carrying all page sections
  gather(character, app_state) -> SheetData
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from heroforge.engine.character import Character
    from heroforge.ui.app_state import AppState


# ---------------------------------------------------------------------------
# Sub-section dataclasses
# ---------------------------------------------------------------------------


@dataclass
class IdentityData:
    name: str = ""
    player: str = ""
    race: str = ""
    class_str: str = ""  # e.g. "Fighter 6 / Wizard 4"
    level: int = 0
    alignment: str = ""
    deity: str = ""
    size: str = "Medium"
    age: str = ""
    gender: str = ""


@dataclass
class AbilityData:
    """One ability score row."""

    name: str
    score: int
    mod: int


@dataclass
class CombatData:
    ac: int = 10
    touch_ac: int = 10
    flatfooted_ac: int = 10
    hp_max: int = 0
    bab: int = 0
    initiative: int = 0
    speed: int = 30
    sr: int = 0
    fort: int = 0
    ref: int = 0
    will: int = 0
    attack_melee: int = 0
    attack_ranged: int = 0
    damage_bonus: int = 0


@dataclass
class SkillRow:
    name: str
    ability: str
    class_skill: bool
    ranks: int
    misc: int
    total: int
    trained_only: bool = False


@dataclass
class FeatRow:
    name: str
    note: str = ""
    source: str = ""  # blank = normal; "template:..." = from template


@dataclass
class BuffRow:
    name: str
    active: bool
    caster_level: int | None
    parameter: int | None
    note: str = ""


@dataclass
class SheetData:
    identity: IdentityData = field(default_factory=IdentityData)
    abilities: list[AbilityData] = field(default_factory=list)
    combat: CombatData = field(default_factory=CombatData)
    skills: list[SkillRow] = field(default_factory=list)
    feats: list[FeatRow] = field(default_factory=list)
    active_buffs: list[BuffRow] = field(default_factory=list)
    all_buffs: list[BuffRow] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)
    dm_overrides: list[str] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# gather()
# ---------------------------------------------------------------------------


def gather(character: "Character", app_state: "AppState") -> SheetData:
    """
    Extract all display data from a Character + AppState into a SheetData.
    Pure function — no side effects.
    """
    from heroforge.engine.skills import compute_skill_total
    from heroforge.ui.widgets.combat_stats import (
        _compute_flatfooted,
        _compute_touch,
    )

    data = SheetData()

    # ── Identity ────────────────────────────────────────────────────────
    class_str = _class_summary(character)
    data.identity = IdentityData(
        name=character.name,
        player=getattr(character, "player", ""),
        race=character.race,
        class_str=class_str,
        level=character.total_level,
        alignment=character.alignment,
        deity=character.deity,
        size=_race_size(character, app_state),
    )

    # ── Abilities ────────────────────────────────────────────────────────
    _AB_LABELS = [
        ("STR", "str"),
        ("DEX", "dex"),
        ("CON", "con"),
        ("INT", "int"),
        ("WIS", "wis"),
        ("CHA", "cha"),
    ]
    for label, ab in _AB_LABELS:
        score = character.get_ability_score(ab)
        mod = character.get_ability_modifier(ab)
        data.abilities.append(AbilityData(name=label, score=score, mod=mod))

    # ── Combat ───────────────────────────────────────────────────────────
    data.combat = CombatData(
        ac=character.ac,
        touch_ac=_compute_touch(character),
        flatfooted_ac=_compute_flatfooted(character),
        hp_max=character.hp_max,
        bab=character.bab,
        initiative=character.get("initiative"),
        speed=character.get("speed"),
        sr=character.get("sr"),
        fort=character.fort,
        ref=character.ref,
        will=character.will,
        attack_melee=character.get("attack_melee"),
        attack_ranged=character.get("attack_ranged"),
        damage_bonus=character.get("damage_str_bonus"),
    )

    # ── Skills ───────────────────────────────────────────────────────────
    skill_reg = app_state.skill_registry
    class_skills = _class_skill_names(character, app_state)

    for skill_def in skill_reg.all_skills():
        result = compute_skill_total(character, skill_def)
        ranks = character.skills.get(skill_def.name, 0)
        misc = result.misc_bonus + result.synergy_bonus + result.armor_penalty
        data.skills.append(
            SkillRow(
                name=skill_def.name,
                ability=skill_def.ability.upper(),
                class_skill=skill_def.name in class_skills,
                ranks=ranks,
                misc=misc,
                total=result.total,
                trained_only=skill_def.trained_only,
            )
        )

    # ── Feats ────────────────────────────────────────────────────────────
    feat_reg = app_state.feat_registry
    for feat_dict in character.feats:
        name = feat_dict.get("name", "")
        source = feat_dict.get("source", "")
        defn = feat_reg.get(name)
        note = defn.note if defn else ""
        data.feats.append(FeatRow(name=name, note=note, source=source))

    # ── Buffs ────────────────────────────────────────────────────────────
    for buff_name, state in sorted(character._buff_states.items()):
        row = BuffRow(
            name=buff_name,
            active=state.active,
            caster_level=state.caster_level,
            parameter=state.parameter,
            note=state.note,
        )
        data.all_buffs.append(row)
        if state.active:
            data.active_buffs.append(row)

    # ── Templates ────────────────────────────────────────────────────────
    for app in character.templates:
        tpl_str = app.template_name
        if app.level:
            tpl_str += f" (level {app.level})"
        data.templates.append(tpl_str)

    # ── DM Overrides ─────────────────────────────────────────────────────
    for ov in character.dm_overrides:
        s = ov.target
        if ov.note:
            s += f" — {ov.note}"
        data.dm_overrides.append(s)

    return data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _class_summary(character: "Character") -> str:
    if not character.class_levels:
        return "—"
    return " / ".join(
        f"{cl.class_name} {cl.level}" for cl in character.class_levels
    )


def _race_size(character: "Character", app_state: "AppState") -> str:
    race_defn = app_state.race_registry.get(character.race)
    return race_defn.size if race_defn else "Medium"


def _class_skill_names(
    character: "Character",
    app_state: "AppState",
) -> set[str]:
    names: set[str] = set()
    for cl in character.class_levels:
        defn = app_state.class_registry.get(cl.class_name)
        if defn:
            names.update(defn.class_skills)
    return names
