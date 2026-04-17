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

from heroforge.rules.known import (
    KnownAbility,
    KnownAlignment,
    KnownArmor,
    KnownBuff,
    KnownClass,
    KnownFeat,
    KnownMagicItem,
    KnownMaterial,
    KnownRace,
    KnownSkill,
    KnownTemplate,
    KnownWeapon,
)

if TYPE_CHECKING:
    from heroforge.engine.character import (
        Character,
    )
    from heroforge.ui.app_state import AppState


# -----------------------------------------------------------
# YAML schema dataclasses (parse/serialize only)
#
# Every string that represents a known name uses a
# StrEnum. cattrs validates at parse time — invalid
# names are rejected automatically.
# -----------------------------------------------------------


@dataclass
class CharIdentity:
    """identity: section of .char.yaml."""

    name: str
    race: KnownRace
    alignment: KnownAlignment
    player: str = ""
    deity: str = ""


@dataclass
class FeatEntry:
    """
    .char.yaml feat entry within a level.

    A list (not dict) because feats like Toughness
    can be taken multiple times, and parameterized
    feats (Weapon Focus) can appear with different
    parameters at the same level.
    """

    name: KnownFeat
    source: str = ""
    parameter: str | None = None


@dataclass
class CharLevelEntry:
    """.char.yaml level entry."""

    level: int
    class_: KnownClass  # "class" in YAML
    hp_roll: int = 0
    skill_ranks: dict[KnownSkill, int] = field(default_factory=dict)
    feats: list[FeatEntry] = field(default_factory=list)
    spells_learned: dict = field(default_factory=dict)
    spells_replaced: list[dict] = field(default_factory=list)
    ability_bump: KnownAbility | None = None
    inherent_bumps: dict[KnownAbility, int] = field(default_factory=dict)


@dataclass
class BuffEntry:
    """.char.yaml buff state entry."""

    active: bool = False
    caster_level: int | None = None
    parameter: int | None = None
    note: str = ""


@dataclass
class TemplateEntry:
    """
    .char.yaml template entry.

    The template name is the dict key in
    CharFile.templates, not a field here.
    """

    level: int = 0
    note: str = ""


@dataclass
class DmOverrideEntry:
    """
    .char.yaml DM override entry.

    TODO: type the target field once DM overrides
    are fully implemented.
    """

    target: str = ""
    note: str = ""


@dataclass
class ArmorSlotEntry:
    """.char.yaml armor/shield slot."""

    base: KnownArmor
    enhancement: int = 0
    material: KnownMaterial | None = None
    masterwork: bool = False
    properties: list[str] = field(default_factory=list)
    name: str = ""  # display name override


@dataclass
class WeaponSlotEntry:
    """.char.yaml weapon entry."""

    base: KnownWeapon
    enhancement: int = 0
    material: KnownMaterial | None = None
    properties: list[str] = field(default_factory=list)
    name: str = ""  # display name override


@dataclass
class EquipmentSection:
    """.char.yaml equipment section."""

    armor: ArmorSlotEntry | None = None
    shield: ArmorSlotEntry | None = None
    worn: list[KnownMagicItem] = field(default_factory=list)
    weapons: list[WeaponSlotEntry] = field(default_factory=list)


@dataclass
class CharFile:
    """Top-level .char.yaml schema."""

    identity: CharIdentity
    ability_scores: dict[KnownAbility, int] = field(default_factory=dict)
    levels: list[CharLevelEntry] = field(default_factory=list)
    buffs: dict[KnownBuff, BuffEntry] = field(default_factory=dict)
    templates: dict[KnownTemplate, TemplateEntry] = field(default_factory=dict)
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
        race=KnownRace(c.race),
        alignment=KnownAlignment(c.alignment),
        player=getattr(c, "player", ""),
        deity=c.deity,
    )

    levels = []
    for lv in c.levels:
        feats = [
            FeatEntry(
                name=KnownFeat(f["name"]),
                source=f.get("source", ""),
                parameter=f.get("parameter"),
            )
            for f in lv.feats
            if f.get("name")
        ]
        sr = {KnownSkill(k): v for k, v in sorted(lv.skill_ranks.items())}
        ib = {KnownAbility(d["ability"]): d["value"] for d in lv.inherent_bumps}
        levels.append(
            CharLevelEntry(
                level=lv.character_level,
                class_=KnownClass(lv.class_name),
                hp_roll=lv.hp_roll,
                skill_ranks=sr,
                feats=feats,
                spells_learned=lv.spells_learned,
                spells_replaced=lv.spells_replaced,
                ability_bump=lv.ability_bump,
                inherent_bumps=ib,
            )
        )

    buffs: dict[KnownBuff, BuffEntry] = {}
    for name, state in sorted(c._buff_states.items()):
        buffs[KnownBuff(name)] = BuffEntry(
            active=state.active,
            caster_level=state.caster_level,
            parameter=state.parameter,
            note=state.note,
        )

    templates: dict[KnownTemplate, TemplateEntry] = {}
    for app in c.templates:
        templates[KnownTemplate(app.template_name)] = TemplateEntry(
            level=app.level,
            note=app.note,
        )

    dm_overrides = [
        DmOverrideEntry(target=ov.target, note=ov.note) for ov in c.dm_overrides
    ]

    eq = c.equipment
    armor = _armor_to_entry(eq.get("armor"))
    shield = _armor_to_entry(eq.get("shield"))
    worn = [KnownMagicItem(n) for n in eq.get("worn", [])]
    weapons = []
    for w in eq.get("weapons", []):
        if isinstance(w, dict) and w.get("base"):
            weapons.append(
                WeaponSlotEntry(
                    base=KnownWeapon(w["base"]),
                    enhancement=w.get("enhancement", 0),
                    material=(
                        KnownMaterial(w["material"])
                        if w.get("material")
                        else None
                    ),
                    properties=list(w.get("properties", [])),
                    name=w.get("name", ""),
                )
            )

    return CharFile(
        identity=identity,
        ability_scores={
            KnownAbility(ab): c._ability_scores.get(ab, 10)
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


def _armor_to_entry(
    a: dict | None,
) -> ArmorSlotEntry | None:
    if not a:
        return None
    mat = a.get("material", "")
    return ArmorSlotEntry(
        base=KnownArmor(a.get("name", "")),
        enhancement=a.get("enhancement", 0),
        material=(KnownMaterial(mat) if mat else None),
        properties=list(a.get("properties", [])),
    )


def _unstructure_charfile(cf: CharFile) -> dict:
    """Convert CharFile to a plain dict for YAML."""
    d: dict = {}
    d["identity"] = {
        "name": cf.identity.name,
        "player": cf.identity.player,
        "race": str(cf.identity.race),
        "alignment": str(cf.identity.alignment),
        "deity": cf.identity.deity,
    }
    d["ability_scores"] = {str(k): v for k, v in cf.ability_scores.items()}

    levels = []
    for lv in cf.levels:
        ld: dict = {
            "level": lv.level,
            "class": str(lv.class_),
            "hp_roll": lv.hp_roll,
        }
        if lv.skill_ranks:
            ld["skill_ranks"] = {str(k): v for k, v in lv.skill_ranks.items()}
        if lv.feats:
            ld["feats"] = [_feat_to_dict(f) for f in lv.feats]
        if lv.spells_learned:
            ld["spells_learned"] = lv.spells_learned
        if lv.spells_replaced:
            ld["spells_replaced"] = lv.spells_replaced
        if lv.ability_bump is not None:
            ld["ability_bump"] = str(lv.ability_bump)
        if lv.inherent_bumps:
            ld["inherent_bumps"] = {
                str(k): v for k, v in lv.inherent_bumps.items()
            }
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
        buffs[str(name)] = bd
    d["buffs"] = buffs

    templates: dict = {}
    for name, te in cf.templates.items():
        td: dict = {}
        if te.level:
            td["level"] = te.level
        if te.note:
            td["note"] = te.note
        templates[str(name)] = td
    d["templates"] = templates

    d["dm_overrides"] = [
        {"target": o.target, "note": o.note} for o in cf.dm_overrides
    ]

    eq: dict = {}
    if cf.equipment.armor is not None:
        a = cf.equipment.armor
        ad: dict = {"base": str(a.base)}
        if a.enhancement:
            ad["enhancement"] = a.enhancement
        if a.material:
            ad["material"] = str(a.material)
        if a.properties:
            ad["properties"] = a.properties
        eq["armor"] = ad
    if cf.equipment.shield is not None:
        s = cf.equipment.shield
        sd: dict = {"base": str(s.base)}
        if s.enhancement:
            sd["enhancement"] = s.enhancement
        if s.material:
            sd["material"] = str(s.material)
        if s.properties:
            sd["properties"] = s.properties
        eq["shield"] = sd
    if cf.equipment.worn:
        eq["worn"] = [str(n) for n in cf.equipment.worn]
    if cf.equipment.weapons:
        wl = []
        for w in cf.equipment.weapons:
            wd: dict = {}
            if w.name:
                wd["name"] = w.name
            if w.base:
                wd["base"] = str(w.base)
            if w.enhancement:
                wd["enhancement"] = w.enhancement
            if w.material:
                wd["material"] = str(w.material)
            if w.properties:
                wd["properties"] = w.properties
            wl.append(wd)
        eq["weapons"] = wl
    d["equipment"] = eq

    d["notes"] = cf.notes
    return d


def _feat_to_dict(f: FeatEntry) -> dict:
    """Convert a FeatEntry to a plain dict."""
    d: dict = {"name": str(f.name)}
    if f.source:
        d["source"] = f.source
    if f.parameter is not None:
        d["parameter"] = f.parameter
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

    Raises ValueError on unknown keys or names
    (via cattrs StrEnum validation).
    """
    from heroforge.rules.schema import converter

    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    try:
        cf = converter.structure(raw, CharFile)
    except Exception as e:
        detail = _flatten_cattrs_error(e)
        raise ValueError(f"Invalid YAML in {path}: {detail}") from e

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
    c.alignment = str(cf.identity.alignment)
    c.deity = cf.identity.deity

    # Ability scores
    for ab, val in cf.ability_scores.items():
        c.set_ability_score(str(ab), val)

    # Race (validated by KnownRace)
    race_defn = app_state.race_registry.get(str(cf.identity.race))
    apply_race(race_defn, c)

    # Levels (class validated by KnownClass)
    for lv in cf.levels:
        c.levels.append(
            CharacterLevel(
                character_level=lv.level,
                class_name=str(lv.class_),
                hp_roll=lv.hp_roll,
                skill_ranks={str(k): v for k, v in lv.skill_ranks.items()},
                feats=[
                    {
                        "name": str(f.name),
                        "source": f.source,
                        "parameter": f.parameter,
                    }
                    for f in lv.feats
                ],
                spells_learned=lv.spells_learned,
                spells_replaced=lv.spells_replaced,
                ability_bump=(
                    str(lv.ability_bump) if lv.ability_bump else None
                ),
                inherent_bumps=[
                    {
                        "ability": str(ab),
                        "value": v,
                    }
                    for ab, v in lv.inherent_bumps.items()
                ],
            )
        )
    if c.levels:
        c._invalidate_class_stats()

    # Feats (validated by KnownFeat)
    for lv in c.levels:
        for feat_dict in lv.feats:
            feat_name = feat_dict.get("name", "")
            if not feat_name:
                continue
            feat_defn = app_state.feat_registry.get(feat_name)
            c.add_feat(
                feat_name,
                feat_defn,
                level=lv.character_level,
                source=feat_dict.get("source", ""),
                parameter=feat_dict.get("parameter"),
            )

    # Skills (validated by KnownSkill)
    for lv in c.levels:
        for skill_name, pts in lv.skill_ranks.items():
            set_skill_ranks(
                c,
                skill_name,
                c.skills.get(skill_name, 0) + pts,
            )

    # Buffs (validated by KnownBuff)
    for buff_name, be in cf.buffs.items():
        name = str(buff_name)
        buff_defn = app_state.buff_registry.get(name)
        cl_val = be.caster_level if be.caster_level is not None else 0
        pairs = buff_defn.pool_entries(cl_val, c)
        c.register_buff_definition(name, pairs)
        if be.active:
            c.toggle_buff(
                name,
                True,
                caster_level=be.caster_level,
                parameter=be.parameter,
            )
        else:
            state = c._buff_states[name]
            if be.caster_level is not None:
                state.caster_level = be.caster_level
            if be.parameter is not None:
                state.parameter = be.parameter
            state.note = be.note

    # Templates (validated by KnownTemplate)
    for tpl_name, te in cf.templates.items():
        tpl_defn = app_state.template_registry.get(str(tpl_name))
        apply_template(tpl_defn, c, level=te.level)

    # DM overrides
    for ov in cf.dm_overrides:
        if ov.target:
            c.add_dm_override(ov.target, note=ov.note)

    # Equipment
    _load_equipment(cf.equipment, c, app_state)

    # Notes
    c.notes = cf.notes

    return c


def _load_equipment(
    eq: EquipmentSection,
    c: "Character",
    app_state: "AppState",
) -> None:
    """Apply equipment from parsed schema."""
    from heroforge.engine.equipment import (
        equip_armor,
        equip_item,
        equip_shield,
    )

    if eq.armor is not None:
        base = str(eq.armor.base or eq.armor.name)
        defn = app_state.armor_registry.get(base)
        equip_armor(
            c,
            defn,
            eq.armor.enhancement,
            material=(str(eq.armor.material) if eq.armor.material else ""),
            masterwork=eq.armor.masterwork,
        )
        if eq.armor.properties:
            c.equipment["armor"]["properties"] = list(eq.armor.properties)

    if eq.shield is not None:
        base = str(eq.shield.base or eq.shield.name)
        defn = app_state.armor_registry.get(base)
        equip_shield(
            c,
            defn,
            eq.shield.enhancement,
            material=(str(eq.shield.material) if eq.shield.material else ""),
            masterwork=eq.shield.masterwork,
        )
        if eq.shield.properties:
            c.equipment["shield"]["properties"] = list(eq.shield.properties)

    for item_name in eq.worn:
        item_defn = app_state.magic_item_registry.get(str(item_name))
        equip_item(c, item_defn)
    if eq.worn:
        c.equipment["worn"] = [str(n) for n in eq.worn]

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
