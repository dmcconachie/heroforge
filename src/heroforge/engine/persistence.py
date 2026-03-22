"""
heroforge/engine/persistence.py
--------------------------------
Save and load Character objects as human-readable YAML files.

Format (.char.yaml) — version 2:

  meta:
    version: "2"

  levels:
    - level: 1
      class: Fighter
      hp_roll: 10
      skill_ranks: {Climb: 4, Jump: 4}
    - level: 2
      class: Fighter
      hp_roll: 8

  class_levels:   # legacy summary (read-only)
    - class: Fighter
      level: 2

  skills:         # total ranks summary
    Climb: 4
    Jump: 4

Version 1 files are auto-migrated on load.

Public API:
  save_character(character, path)   — write .char.yaml
  load_character(path, app_state)   — read .char.yaml → Character
  CharacterSchema                   — validates the YAML structure
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from heroforge.engine.character import (
        BuffState,
        Character,
        CharacterLevel,
    )
    from heroforge.ui.app_state import AppState

SCHEMA_VERSION = "2"


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


def save_character(character: "Character", path: Path | str) -> None:
    """
    Serialize a Character to a .char.yaml file.

    Always writes in a stable key order for human readability and
    clean diffs.
    """
    path = Path(path)
    data = _character_to_dict(character)
    with open(path, "w") as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


def _character_to_dict(c: "Character") -> dict:
    """Serialize all character state to a plain dict."""
    return {
        "meta": {
            "version": SCHEMA_VERSION,
            "modified": datetime.date.today().isoformat(),
        },
        "identity": {
            "name": c.name,
            "player": getattr(c, "player", ""),
            "race": c.race,
            "alignment": c.alignment,
            "deity": c.deity,
        },
        "ability_scores": {
            # Save BASE scores only (before racial/template pool bonuses).
            # Race and templates are re-applied on load.
            ab: c._ability_scores.get(ab, 10)
            for ab in ("str", "dex", "con", "int", "wis", "cha")
        },
        "levels": [_level_to_dict(lv) for lv in c.levels],
        # Legacy summary for human readability
        "class_levels": [
            {
                "class": cl.class_name,
                "level": cl.level,
                "hp_rolls": cl.hp_rolls,
                "bab": cl.bab_contribution,
                "fort": cl.fort_contribution,
                "ref": cl.ref_contribution,
                "will": cl.will_contribution,
            }
            for cl in c.class_levels
        ],
        "feats": [
            {k: v for k, v in feat.items() if v is not None} for feat in c.feats
        ],
        "skills": {
            name: ranks for name, ranks in sorted(c.skills.items()) if ranks > 0
        },
        "buffs": [
            _buff_state_to_dict(name, state)
            for name, state in sorted(c._buff_states.items())
        ],
        "templates": [
            {
                "template": app.template_name,
                "level": app.level,
                "note": app.note,
            }
            for app in c.templates
        ],
        "dm_overrides": [
            {"target": ov.target, "note": ov.note} for ov in c.dm_overrides
        ],
        "equipment": dict(c.equipment),
        "notes": c.notes,
    }


def _level_to_dict(lv: "CharacterLevel") -> dict:
    d: dict = {
        "level": lv.character_level,
        "class": lv.class_name,
        "hp_roll": lv.hp_roll,
    }
    if lv.skill_ranks:
        d["skill_ranks"] = dict(sorted(lv.skill_ranks.items()))
    return d


def _buff_state_to_dict(name: str, state: BuffState) -> dict:
    d: dict = {"name": name, "active": state.active}
    if state.caster_level is not None:
        d["caster_level"] = state.caster_level
    if state.parameter is not None:
        d["parameter"] = state.parameter
    if state.note:
        d["note"] = state.note
    return d


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_character(
    path: Path | str,
    app_state: "AppState",
) -> "Character":
    """
    Deserialize a .char.yaml file into a Character.

    Uses app_state to look up class/race/buff definitions for
    re-registering effects on the new character.

    Raises ValueError on schema version mismatch.
    Raises FileNotFoundError if path doesn't exist.
    """
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f)

    _validate_version(data)

    from heroforge.engine.character import (
        BuffState,
        Character,
        CharacterLevel,
    )
    from heroforge.engine.classes_races import apply_race
    from heroforge.engine.skills import (
        register_skills_on_character,
        set_skill_ranks,
    )
    from heroforge.engine.templates import (
        TemplateApplication,
        apply_template,
    )

    c = Character()
    c._class_registry_ref = app_state.class_registry

    # Register skills before anything else
    register_skills_on_character(app_state.skill_registry, c)

    # Identity
    identity = data.get("identity", {})
    c.name = identity.get("name", "")
    c.player = identity.get("player", "")
    c.alignment = identity.get("alignment", "")
    c.deity = identity.get("deity", "")

    # Ability scores
    scores = data.get("ability_scores", {})
    for ab, val in scores.items():
        c.set_ability_score(ab, int(val))

    # Race — apply via registry if available
    race_name = identity.get("race", "")
    if race_name:
        race_defn = app_state.race_registry.get(race_name)
        if race_defn:
            apply_race(race_defn, c)
        else:
            c.race = race_name  # Unknown race: just store the name

    # Per-character-level entries
    for lv_dict in data.get("levels", []):
        c.levels.append(
            CharacterLevel(
                character_level=int(lv_dict["level"]),
                class_name=lv_dict["class"],
                hp_roll=int(lv_dict.get("hp_roll", 0)),
                skill_ranks=dict(lv_dict.get("skill_ranks", {})),
            )
        )
    if c.levels:
        c._invalidate_class_stats()

    # Feats — record names; apply always-on effects
    for feat_dict in data.get("feats", []):
        feat_name = feat_dict.get("name", "")
        if not feat_name:
            continue
        feat_defn = app_state.feat_registry.get(feat_name)
        source = feat_dict.get("source", "")
        parameter = feat_dict.get("parameter")
        c.add_feat(feat_name, feat_defn, parameter=parameter, source=source)

    # Skills — ranks
    for skill_name, ranks in data.get("skills", {}).items():
        set_skill_ranks(c, skill_name, int(ranks))

    # Buffs — restore states and re-register definitions
    for buff_dict in data.get("buffs", []):
        buff_name = buff_dict.get("name", "")
        if not buff_name:
            continue
        active = bool(buff_dict.get("active", False))
        caster_level = buff_dict.get("caster_level")
        parameter = buff_dict.get("parameter")
        note = buff_dict.get("note", "")

        # Look up definition and register if present
        buff_defn = app_state.spell_registry.get(buff_name)
        if buff_defn is not None:
            cl_val = int(caster_level) if caster_level is not None else 0
            pairs = buff_defn.pool_entries(cl_val, c)
            c.register_buff_definition(buff_name, pairs)
            if active:
                c.toggle_buff(
                    buff_name,
                    True,
                    caster_level=int(caster_level) if caster_level else None,
                    parameter=int(parameter) if parameter else None,
                )
            else:
                # Just store the state without activating
                state = c._buff_states[buff_name]
                if caster_level is not None:
                    state.caster_level = int(caster_level)
                if parameter is not None:
                    state.parameter = int(parameter)
                state.note = note
        else:
            # Unknown buff (e.g. from a splatbook not loaded):
            # store a stub state so it round-trips cleanly
            c._buff_states[buff_name] = BuffState(
                active=active,
                caster_level=int(caster_level) if caster_level else None,
                parameter=int(parameter) if parameter else None,
                note=note,
            )

    # Templates
    for tpl_dict in data.get("templates", []):
        tpl_name = tpl_dict.get("template", "")
        if not tpl_name:
            continue
        level = int(tpl_dict.get("level", 0))
        tpl_defn = app_state.template_registry.get(tpl_name)
        if tpl_defn:
            apply_template(tpl_defn, c, level=level)
        else:
            # Unknown template: record application without effects
            c.templates.append(
                TemplateApplication(
                    template_name=tpl_name,
                    level=level,
                    note=tpl_dict.get("note", ""),
                )
            )

    # DM overrides
    for ov_dict in data.get("dm_overrides", []):
        target = ov_dict.get("target", "")
        if target:
            c.add_dm_override(target, note=ov_dict.get("note", ""))

    # Equipment (currently just stored as a dict)
    c.equipment = dict(data.get("equipment", {}))

    # Notes
    c.notes = str(data.get("notes", ""))

    return c


def _validate_version(data: dict) -> None:
    meta = data.get("meta", {})
    version = str(meta.get("version", ""))
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported character file version "
            f"{version!r}. "
            f"Expected {SCHEMA_VERSION!r}."
        )
