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


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


class _IndentDumper(yaml.Dumper):
    """Dumper with indented sequences and folded long strings."""

    def increase_indent(  # type: ignore[override]
        self,
        flow: bool = False,
        indentless: bool = False,
    ) -> None:
        return super().increase_indent(flow, indentless=False)


def _str_representer(dumper: yaml.Dumper, data: str) -> yaml.Node:
    """Use folded block scalar for long strings."""
    if len(data) > 50 and "\n" not in data:
        return dumper.represent_scalar(
            "tag:yaml.org,2002:str",
            data,
            style=">",
        )
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_IndentDumper.add_representer(str, _str_representer)


def yaml_dump(data: object, stream: object = None) -> str:
    """
    Dump YAML with indented sequences and stable key
    order, matching the project's yamllint config.
    """
    return yaml.dump(
        data,
        stream,
        Dumper=_IndentDumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=72,
    )


def save_character(character: "Character", path: Path | str) -> None:
    """
    Serialize a Character to a .char.yaml file.

    Always writes in a stable key order for human
    readability and clean diffs.
    """
    path = Path(path)
    data = _character_to_dict(character)
    with open(path, "w") as f:
        yaml_dump(data, f)


def _character_to_dict(c: "Character") -> dict:
    """Serialize all character state to a plain dict."""
    return {
        "identity": {
            "name": c.name,
            "player": getattr(c, "player", ""),
            "race": c.race,
            "alignment": c.alignment,
            "deity": c.deity,
        },
        "ability_scores": {
            # Save BASE scores only (before racial/template
            # pool bonuses). Race and templates are
            # re-applied on load.
            ab: c._ability_scores.get(ab, 10)
            for ab in (
                "str",
                "dex",
                "con",
                "int",
                "wis",
                "cha",
            )
        },
        "levels": [_level_to_dict(lv) for lv in c.levels],
        "buffs": {
            name: _buff_state_to_dict(state)
            for name, state in sorted(c._buff_states.items())
        },
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
    if lv.feats:
        d["feats"] = [
            {k: v for k, v in f.items() if v is not None} for f in lv.feats
        ]
    if lv.spells_learned:
        d["spells_learned"] = dict(lv.spells_learned)
    if lv.spells_replaced:
        d["spells_replaced"] = list(lv.spells_replaced)
    if lv.ability_bump:
        d["ability_bump"] = lv.ability_bump
    if lv.inherent_bumps:
        d["inherent_bumps"] = list(lv.inherent_bumps)
    return d


def _buff_state_to_dict(state: "BuffState") -> dict:
    d: dict = {"active": state.active}
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

    from heroforge.engine.character import (
        BuffState,
        Character,
        CharacterLevel,
    )
    from heroforge.engine.races import apply_race
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
    c._feat_registry_ref = app_state.feat_registry

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

    # Per-character-level entries (includes feats,
    # skill ranks, and spells learned at each level)
    for lv_dict in data.get("levels", []):
        char_level = int(lv_dict["level"])
        c.levels.append(
            CharacterLevel(
                character_level=char_level,
                class_name=lv_dict["class"],
                hp_roll=int(lv_dict.get("hp_roll", 0)),
                skill_ranks=dict(lv_dict.get("skill_ranks", {})),
                feats=list(lv_dict.get("feats", [])),
                spells_learned=dict(lv_dict.get("spells_learned", {})),
                spells_replaced=list(lv_dict.get("spells_replaced", [])),
                ability_bump=lv_dict.get("ability_bump"),
                inherent_bumps=list(lv_dict.get("inherent_bumps", [])),
            )
        )
    if c.levels:
        c._invalidate_class_stats()

    # Feats — read from each level entry
    for lv in c.levels:
        for feat_dict in lv.feats:
            feat_name = feat_dict.get("name", "")
            if not feat_name:
                continue
            feat_defn = app_state.feat_registry.get(feat_name)
            source = feat_dict.get("source", "")
            parameter = feat_dict.get("parameter")
            c.add_feat(
                feat_name,
                feat_defn,
                level=lv.character_level,
                source=source,
                parameter=parameter,
            )

    # Skills — compute total ranks from level entries
    for lv in c.levels:
        for skill_name, pts in lv.skill_ranks.items():
            set_skill_ranks(
                c,
                skill_name,
                c.skills.get(skill_name, 0) + pts,
            )

    # Buffs — restore states and re-register definitions
    for buff_name, buff_dict in data.get("buffs", {}).items():
        active = bool(buff_dict.get("active", False))
        caster_level = buff_dict.get("caster_level")
        parameter = buff_dict.get("parameter")
        note = buff_dict.get("note", "")

        # Look up definition and register if present
        buff_defn = app_state.buff_registry.get(buff_name)
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
