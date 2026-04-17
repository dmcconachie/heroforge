"""
heroforge/engine/persistence.py
--------------------------------
Save and load Character objects as human-readable
YAML files.

Uses cattrs for structured parsing with
``forbid_extra_keys`` — unknown YAML keys are
rejected automatically. Registry name validation
(race, class, feat, buff, etc.) is a post-parse
step.

Public API:
  save_character(character, path)
  load_character(path, app_state)
  yaml_dump(data, stream)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from heroforge.engine.character import (
        Character,
    )
    from heroforge.ui.app_state import AppState


# -----------------------------------------------------------
# YAML schema dataclasses (parse/serialize only)
# -----------------------------------------------------------


@dataclass
class CharIdentity:
    """identity: section of .char.yaml."""

    name: str = ""
    player: str = ""
    race: str = ""
    alignment: str = ""
    deity: str = ""


@dataclass
class CharLevelEntry:
    """.char.yaml level entry."""

    level: int = 0
    class_: str = ""  # "class" in YAML
    hp_roll: int = 0
    skill_ranks: dict[str, int] = field(default_factory=dict)
    feats: list[dict] = field(default_factory=list)
    spells_learned: dict = field(default_factory=dict)
    spells_replaced: list[dict] = field(default_factory=list)
    ability_bump: str | None = None
    inherent_bumps: list[dict] = field(default_factory=list)


@dataclass
class BuffEntry:
    """.char.yaml buff state entry."""

    active: bool = False
    caster_level: int | None = None
    parameter: int | None = None
    note: str = ""


@dataclass
class TemplateEntry:
    """.char.yaml template entry."""

    template: str = ""
    level: int = 0
    note: str = ""


@dataclass
class DmOverrideEntry:
    """.char.yaml DM override entry."""

    target: str = ""
    note: str = ""


@dataclass
class ArmorSlotEntry:
    """.char.yaml armor/shield slot."""

    base: str = ""
    enhancement: int = 0
    material: str = ""
    masterwork: bool = False
    properties: list[str] = field(default_factory=list)
    name: str = ""  # old format compat


@dataclass
class WeaponSlotEntry:
    """.char.yaml weapon entry."""

    base: str = ""
    enhancement: int = 0
    material: str = ""
    properties: list[str] = field(default_factory=list)
    name: str = ""


@dataclass
class EquipmentSection:
    """.char.yaml equipment section."""

    armor: ArmorSlotEntry | None = None
    shield: ArmorSlotEntry | None = None
    worn: list[str] = field(default_factory=list)
    weapons: list[WeaponSlotEntry] = field(default_factory=list)


@dataclass
class CharFile:
    """Top-level .char.yaml schema."""

    identity: CharIdentity = field(default_factory=CharIdentity)
    ability_scores: dict[str, int] = field(default_factory=dict)
    levels: list[CharLevelEntry] = field(default_factory=list)
    buffs: dict[str, BuffEntry] = field(default_factory=dict)
    templates: list[TemplateEntry] = field(default_factory=list)
    dm_overrides: list[DmOverrideEntry] = field(default_factory=list)
    equipment: EquipmentSection = field(default_factory=EquipmentSection)
    notes: str = ""


# -----------------------------------------------------------
# YAML dumper
# -----------------------------------------------------------


class _IndentDumper(yaml.Dumper):
    """Dumper with indented sequences."""

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
    Dump YAML with indented sequences and stable
    key order."""
    return yaml.dump(
        data,
        stream,
        Dumper=_IndentDumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=72,
    )


# -----------------------------------------------------------
# Save
# -----------------------------------------------------------


def save_character(character: "Character", path: Path | str) -> None:
    """Serialize a Character to a .char.yaml file."""
    path = Path(path)
    cf = _character_to_charfile(character)
    data = _unstructure_charfile(cf)
    with open(path, "w") as f:
        yaml_dump(data, f)


def _character_to_charfile(
    c: "Character",
) -> CharFile:
    """Build a CharFile from a Character."""
    identity = CharIdentity(
        name=c.name,
        player=getattr(c, "player", ""),
        race=c.race,
        alignment=c.alignment,
        deity=c.deity,
    )

    levels = []
    for lv in c.levels:
        levels.append(
            CharLevelEntry(
                level=lv.character_level,
                class_=lv.class_name,
                hp_roll=lv.hp_roll,
                skill_ranks=dict(sorted(lv.skill_ranks.items())),
                feats=[
                    {k: v for k, v in f.items() if v is not None}
                    for f in lv.feats
                ],
                spells_learned=dict(lv.spells_learned),
                spells_replaced=list(lv.spells_replaced),
                ability_bump=lv.ability_bump,
                inherent_bumps=list(lv.inherent_bumps),
            )
        )

    buffs = {}
    for name, state in sorted(c._buff_states.items()):
        buffs[name] = BuffEntry(
            active=state.active,
            caster_level=state.caster_level,
            parameter=state.parameter,
            note=state.note,
        )

    templates = [
        TemplateEntry(
            template=app.template_name,
            level=app.level,
            note=app.note,
        )
        for app in c.templates
    ]

    dm_overrides = [
        DmOverrideEntry(target=ov.target, note=ov.note) for ov in c.dm_overrides
    ]

    eq = c.equipment
    armor = None
    if "armor" in eq:
        a = eq["armor"]
        armor = ArmorSlotEntry(
            base=a.get("name", ""),
            enhancement=a.get("enhancement", 0),
            material=a.get("material", ""),
            properties=list(a.get("properties", [])),
        )
    shield = None
    if "shield" in eq:
        s = eq["shield"]
        shield = ArmorSlotEntry(
            base=s.get("name", ""),
            enhancement=s.get("enhancement", 0),
            material=s.get("material", ""),
            properties=list(s.get("properties", [])),
        )
    worn = list(eq.get("worn", []))
    weapons = []
    for w in eq.get("weapons", []):
        if isinstance(w, dict):
            weapons.append(
                WeaponSlotEntry(
                    base=w.get("base", ""),
                    enhancement=w.get("enhancement", 0),
                    material=w.get("material", ""),
                    properties=list(w.get("properties", [])),
                    name=w.get("name", ""),
                )
            )

    return CharFile(
        identity=identity,
        ability_scores={
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
        levels=levels,
        buffs=buffs,
        templates=templates,
        dm_overrides=dm_overrides,
        equipment=EquipmentSection(
            armor=armor,
            shield=shield,
            worn=worn,
            weapons=weapons,
        ),
        notes=c.notes,
    )


def _unstructure_charfile(cf: CharFile) -> dict:
    """Convert CharFile to a plain dict for YAML."""
    d: dict = {}
    d["identity"] = _nz_dict(
        {
            "name": cf.identity.name,
            "player": cf.identity.player,
            "race": cf.identity.race,
            "alignment": cf.identity.alignment,
            "deity": cf.identity.deity,
        }
    )
    d["ability_scores"] = cf.ability_scores

    levels = []
    for lv in cf.levels:
        ld: dict = {
            "level": lv.level,
            "class": lv.class_,
            "hp_roll": lv.hp_roll,
        }
        if lv.skill_ranks:
            ld["skill_ranks"] = lv.skill_ranks
        if lv.feats:
            ld["feats"] = lv.feats
        if lv.spells_learned:
            ld["spells_learned"] = lv.spells_learned
        if lv.spells_replaced:
            ld["spells_replaced"] = lv.spells_replaced
        if lv.ability_bump:
            ld["ability_bump"] = lv.ability_bump
        if lv.inherent_bumps:
            ld["inherent_bumps"] = lv.inherent_bumps
        levels.append(ld)
    d["levels"] = levels

    buffs: dict = {}
    for name, be in cf.buffs.items():
        bd: dict = {"active": be.active}
        if be.caster_level is not None:
            bd["caster_level"] = be.caster_level
        if be.parameter is not None:
            bd["parameter"] = be.parameter
        if be.note:
            bd["note"] = be.note
        buffs[name] = bd
    d["buffs"] = buffs

    d["templates"] = [
        _nz_dict(
            {
                "template": t.template,
                "level": t.level,
                "note": t.note,
            }
        )
        for t in cf.templates
    ]
    d["dm_overrides"] = [
        _nz_dict({"target": o.target, "note": o.note}) for o in cf.dm_overrides
    ]

    eq: dict = {}
    if cf.equipment.armor is not None:
        a = cf.equipment.armor
        ad: dict = {"base": a.base}
        if a.enhancement:
            ad["enhancement"] = a.enhancement
        if a.material:
            ad["material"] = a.material
        if a.properties:
            ad["properties"] = a.properties
        eq["armor"] = ad
    if cf.equipment.shield is not None:
        s = cf.equipment.shield
        sd: dict = {"base": s.base}
        if s.enhancement:
            sd["enhancement"] = s.enhancement
        if s.material:
            sd["material"] = s.material
        if s.properties:
            sd["properties"] = s.properties
        eq["shield"] = sd
    if cf.equipment.worn:
        eq["worn"] = cf.equipment.worn
    if cf.equipment.weapons:
        wl = []
        for w in cf.equipment.weapons:
            wd: dict = {}
            if w.name:
                wd["name"] = w.name
            if w.base:
                wd["base"] = w.base
            if w.enhancement:
                wd["enhancement"] = w.enhancement
            if w.material:
                wd["material"] = w.material
            if w.properties:
                wd["properties"] = w.properties
            wl.append(wd)
        eq["weapons"] = wl
    d["equipment"] = eq

    d["notes"] = cf.notes
    return d


def _nz_dict(d: dict) -> dict:
    """
    Return dict with falsy values kept (for
    identity fields like empty strings)."""
    return d


def _flatten_cattrs_error(e: Exception) -> str:
    """Extract readable detail from cattrs errors."""
    # cattrs wraps errors in ClassValidationError
    # with nested exceptions. Dig to the leaf.
    if hasattr(e, "exceptions"):
        parts = []
        for sub in e.exceptions:
            parts.append(_flatten_cattrs_error(sub))
        return "; ".join(parts)
    # cattrs notes contain the field path
    notes = getattr(e, "__notes__", [])
    if notes:
        return f"{e} ({', '.join(notes)})"
    return str(e)


# -----------------------------------------------------------
# Load
# -----------------------------------------------------------


def load_character(
    path: Path | str,
    app_state: "AppState",
) -> "Character":
    """
    Deserialize a .char.yaml file into a Character.

    Raises ValueError on unknown keys (via cattrs)
    or unknown registry names.
    """
    from heroforge.rules.schema import converter

    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    # --- Structural parse via cattrs ---------------
    try:
        cf = converter.structure(raw, CharFile)
    except Exception as e:
        detail = _flatten_cattrs_error(e)
        raise ValueError(f"Invalid YAML in {path}: {detail}") from e

    # --- Build Character from parsed schema --------
    from heroforge.engine.character import (
        Character,
        CharacterLevel,
    )
    from heroforge.engine.races import apply_race
    from heroforge.engine.skills import (
        register_skills_on_character,
        set_skill_ranks,
    )
    from heroforge.engine.templates import (
        apply_template,
    )

    c = Character()
    c._class_registry_ref = app_state.class_registry
    c._feat_registry_ref = app_state.feat_registry
    register_skills_on_character(app_state.skill_registry, c)

    # Identity
    c.name = cf.identity.name
    c.player = cf.identity.player
    c.alignment = cf.identity.alignment
    c.deity = cf.identity.deity

    # Ability scores
    for ab, val in cf.ability_scores.items():
        c.set_ability_score(ab, val)

    # Race
    if cf.identity.race:
        race_defn = app_state.race_registry.get(cf.identity.race)
        if race_defn is None:
            raise ValueError(
                f"Unknown race {cf.identity.race!r} in {path}:identity.race"
            )
        apply_race(race_defn, c)

    # Levels
    for lv in cf.levels:
        if app_state.class_registry.get(lv.class_) is None:
            raise ValueError(
                f"Unknown class {lv.class_!r}"
                f" in {path}:"
                f"levels[{lv.level}].class"
            )
        c.levels.append(
            CharacterLevel(
                character_level=lv.level,
                class_name=lv.class_,
                hp_roll=lv.hp_roll,
                skill_ranks=dict(lv.skill_ranks),
                feats=list(lv.feats),
                spells_learned=dict(lv.spells_learned),
                spells_replaced=list(lv.spells_replaced),
                ability_bump=lv.ability_bump,
                inherent_bumps=list(lv.inherent_bumps),
            )
        )
    if c.levels:
        c._invalidate_class_stats()

    # Feats
    for lv in c.levels:
        for feat_dict in lv.feats:
            feat_name = feat_dict.get("name", "")
            if not feat_name:
                continue
            feat_defn = app_state.feat_registry.get(feat_name)
            if feat_defn is None:
                raise ValueError(
                    f"Unknown feat {feat_name!r}"
                    f" in {path}:levels"
                    f"[{lv.character_level}].feats"
                )
            c.add_feat(
                feat_name,
                feat_defn,
                level=lv.character_level,
                source=feat_dict.get("source", ""),
                parameter=feat_dict.get("parameter"),
            )

    # Skills
    for lv in c.levels:
        for skill_name, pts in lv.skill_ranks.items():
            if app_state.skill_registry.get(skill_name) is None:
                raise ValueError(
                    f"Unknown skill"
                    f" {skill_name!r} in"
                    f" {path}:levels"
                    f"[{lv.character_level}]"
                    f".skill_ranks"
                )
            set_skill_ranks(
                c,
                skill_name,
                c.skills.get(skill_name, 0) + pts,
            )

    # Buffs
    for buff_name, be in cf.buffs.items():
        buff_defn = app_state.buff_registry.get(buff_name)
        if buff_defn is None:
            raise ValueError(
                f"Unknown buff {buff_name!r} in {path}:buffs[{buff_name}]"
            )
        cl_val = be.caster_level if be.caster_level is not None else 0
        pairs = buff_defn.pool_entries(cl_val, c)
        c.register_buff_definition(buff_name, pairs)
        if be.active:
            c.toggle_buff(
                buff_name,
                True,
                caster_level=be.caster_level,
                parameter=be.parameter,
            )
        else:
            state = c._buff_states[buff_name]
            if be.caster_level is not None:
                state.caster_level = be.caster_level
            if be.parameter is not None:
                state.parameter = be.parameter
            state.note = be.note

    # Templates
    for i, te in enumerate(cf.templates):
        if not te.template:
            continue
        tpl_defn = app_state.template_registry.get(te.template)
        if tpl_defn is None:
            raise ValueError(
                f"Unknown template {te.template!r} in {path}:templates[{i}]"
            )
        apply_template(tpl_defn, c, level=te.level)

    # DM overrides
    for ov in cf.dm_overrides:
        if ov.target:
            c.add_dm_override(ov.target, note=ov.note)

    # Equipment
    _load_equipment(cf.equipment, c, app_state, path)

    # Notes
    c.notes = cf.notes

    return c


def _load_equipment(
    eq: EquipmentSection,
    c: "Character",
    app_state: "AppState",
    path: Path,
) -> None:
    """Apply equipment from parsed schema."""
    from heroforge.engine.equipment import (
        equip_armor,
        equip_item,
        equip_shield,
    )

    if eq.armor is not None:
        base = eq.armor.base or eq.armor.name
        defn = app_state.armor_registry.get(base)
        if defn is None:
            raise ValueError(
                f"Unknown armor {base!r} in {path}:equipment.armor"
            )
        equip_armor(
            c,
            defn,
            eq.armor.enhancement,
            material=eq.armor.material,
            masterwork=eq.armor.masterwork,
        )
        if eq.armor.properties:
            c.equipment["armor"]["properties"] = list(eq.armor.properties)

    if eq.shield is not None:
        base = eq.shield.base or eq.shield.name
        defn = app_state.armor_registry.get(base)
        if defn is None:
            raise ValueError(
                f"Unknown shield {base!r} in {path}:equipment.shield"
            )
        equip_shield(
            c,
            defn,
            eq.shield.enhancement,
            material=eq.shield.material,
            masterwork=eq.shield.masterwork,
        )
        if eq.shield.properties:
            c.equipment["shield"]["properties"] = list(eq.shield.properties)

    for i, item_name in enumerate(eq.worn):
        item_defn = app_state.magic_item_registry.get(item_name)
        if item_defn is None:
            raise ValueError(
                f"Unknown item {item_name!r} in {path}:equipment.worn[{i}]"
            )
        equip_item(c, item_defn)
    if eq.worn:
        c.equipment["worn"] = list(eq.worn)

    if eq.weapons:
        c.equipment["weapons"] = [
            {
                k: v
                for k, v in {
                    "base": w.base,
                    "enhancement": w.enhancement,
                    "material": w.material,
                    "properties": w.properties,
                    "name": w.name,
                }.items()
                if v
            }
            for w in eq.weapons
        ]
