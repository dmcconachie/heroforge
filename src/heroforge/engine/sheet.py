"""
heroforge/engine/sheet.py
--------------------------
Build a typed :class:`Sheet` from a Character.

`Sheet` (defined in ``engine/sheet_schema.py``) holds
every derived value on the character sheet with full
bonus-type breakdowns. Serialisation runs through the
shared cattrs converter so every enum emits as a plain
string.

Public API:
  extract_sheet(path, app_state) -> Sheet
  gather_sheet(character, app_state) -> Sheet

CLI:
  uv run charsheet input.char.yaml [-o output.yaml]
  python -m heroforge.engine.sheet input.char.yaml
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from heroforge.engine.bonus import ALWAYS_STACKING, BonusPool, BonusType
from heroforge.engine.character import (
    SAVE_ABILITY,
    Ability,
    Alignment,
    Save,
    Size,
)
from heroforge.engine.persistence import load_character, yaml_dump
from heroforge.engine.sheet_schema import (
    AbilityEntry,
    ArmorDisplay,
    Breakdown,
    CarryingCapacity,
    CombatSection,
    EquipmentSection,
    Iteratives,
    Sheet,
    SheetIdentity,
    SkillEntry,
    SpellcastingEntry,
    WeaponDisplay,
)
from heroforge.rules.known import (
    KnownClass,
    KnownMagicItem,
    KnownRace,
    KnownSkill,
)
from heroforge.rules.schema import converter
from heroforge.ui.app_state import AppState

if TYPE_CHECKING:
    from heroforge.engine.character import Character


# -----------------------------------------------------------
# Pool breakdown helper
# -----------------------------------------------------------


def _pool_breakdown(
    pool: BonusPool | None,
    character: "Character",
) -> dict[str, int]:
    """
    Break down a BonusPool into effective contributions
    per bonus type (keyed by BonusType.value so it can
    merge directly into a Breakdown.typed dict). Applies
    stacking rules. Returns only non-zero entries.
    """
    if pool is None:
        return {}
    active = pool.active_entries(character)
    if not active:
        return {}

    stacking: dict[BonusType, int] = defaultdict(int)
    typed_buckets: dict[BonusType, list[int]] = defaultdict(list)

    for e in active:
        if e.value < 0 or e.bonus_type in ALWAYS_STACKING:
            stacking[e.bonus_type] += e.value
        else:
            typed_buckets[e.bonus_type].append(e.value)

    result: dict[str, int] = {}
    for bt, val in stacking.items():
        if val != 0:
            result[bt.value] = val
    for bt, vals in typed_buckets.items():
        best = max(vals)
        if best != 0:
            result[bt.value] = best
    return result


def _merge(dst: dict[str, int], src: dict[str, int]) -> None:
    """Add src into dst in place; later entries accumulate."""
    for k, v in src.items():
        if v:
            dst[k] = dst.get(k, 0) + v


def _drop_zeros(d: dict[str, int]) -> dict[str, int]:
    return {k: v for k, v in d.items() if v != 0}


# -----------------------------------------------------------
# Main extraction
# -----------------------------------------------------------


def extract_sheet(
    char_path: Path | str,
    app_state: "AppState",
) -> Sheet:
    """Load a .char.yaml and return the full sheet."""
    char = load_character(Path(char_path), app_state)
    return gather_sheet(char, app_state)


def gather_sheet(
    character: "Character",
    app_state: "AppState",
) -> Sheet:
    """Build a Sheet from a Character + loaded rules."""
    return Sheet(
        identity=_identity(character, app_state),
        abilities=_abilities(character),
        combat=_combat(character),
        attack_iteratives=_iteratives(character),
        skills=_skills(character, app_state),
        carrying_capacity=_carrying(character),
        feats=_feats(character),
        class_features=_class_features(character, app_state),
        spellcasting=_spellcasting(character, app_state),
        special_qualities=_special_qualities(character, app_state),
        equipment=_equipment(character),
    )


# -----------------------------------------------------------
# Identity
# -----------------------------------------------------------


def _identity(c: "Character", app_state: "AppState") -> SheetIdentity:
    clm = c.class_level_map
    if clm:
        class_str = " / ".join(f"{cn} {lvl}" for cn, lvl in clm.items())
    else:
        class_str = ""

    race_defn = app_state.race_registry.get(c.race)
    size = Size(race_defn.size) if race_defn else Size.MEDIUM

    return SheetIdentity(
        name=c.name,
        race=KnownRace(c.race) if c.race else KnownRace("Human"),
        class_str=class_str,
        level=c.total_level,
        alignment=Alignment(c.alignment) if c.alignment else Alignment.NEUTRAL,
        deity=c.deity,
        size=size,
    )


# -----------------------------------------------------------
# Abilities
# -----------------------------------------------------------


def _abilities(c: "Character") -> dict[Ability, AbilityEntry]:
    result: dict[Ability, AbilityEntry] = {}
    for ab in Ability:
        typed: dict[str, int] = {
            "base": c._ability_scores.get(ab, 10),
        }
        bumps = c._level_bump_total(ab)
        if bumps:
            typed["level_bumps"] = bumps
        inherent = c._inherent_bonus_total(ab)
        if inherent:
            typed["inherent"] = inherent
        _merge(typed, _pool_breakdown(c.get_pool(f"{ab}_score"), c))
        result[ab] = AbilityEntry(
            score=c.get_ability_score(ab),
            mod=c.get_ability_modifier(ab),
            typed=_drop_zeros(typed),
        )
    return result


# -----------------------------------------------------------
# Combat
# -----------------------------------------------------------


def _combat(c: "Character") -> CombatSection:
    str_mod = c.get_ability_modifier(Ability.STR)

    # AC
    ac_typed: dict[str, int] = {"base": 10}
    ac_dex = c.get("ac_dex_contribution")
    if ac_dex:
        ac_typed[Ability.DEX.value] = ac_dex
    ac_size = c._compute_size_mod_attack()
    if ac_size:
        ac_typed["size"] = ac_size
    _merge(ac_typed, _pool_breakdown(c.get_pool("ac"), c))
    ac = Breakdown(total=c.ac, typed=_drop_zeros(ac_typed))

    # HP
    hp_typed: dict[str, int] = {"base": c._compute_hp_from_rolls()}
    con_hp = c.get_ability_modifier(Ability.CON) * c.total_level
    if con_hp:
        hp_typed[Ability.CON.value] = con_hp
    _merge(hp_typed, _pool_breakdown(c.get_pool("hp_bonus"), c))
    hp_max = Breakdown(total=c.hp_max, typed=_drop_zeros(hp_typed))

    # BAB
    bab_typed: dict[str, int] = {"base": c._compute_bab()}
    _merge(bab_typed, _pool_breakdown(c.get_pool("bab_misc"), c))
    bab = Breakdown(total=c.bab, typed=_drop_zeros(bab_typed))

    # Initiative (no base progression — only ability + pool)
    init_typed: dict[str, int] = {}
    dex_mod = c.get_ability_modifier(Ability.DEX)
    if dex_mod:
        init_typed[Ability.DEX.value] = dex_mod
    _merge(init_typed, _pool_breakdown(c.get_pool("initiative"), c))
    initiative = Breakdown(
        total=c.get("initiative"),
        typed=_drop_zeros(init_typed),
    )

    # Speed
    speed_typed: dict[str, int] = {"base": c._compute_base_speed()}
    _merge(speed_typed, _pool_breakdown(c.get_pool("speed"), c))
    speed = Breakdown(total=c.get("speed"), typed=_drop_zeros(speed_typed))

    # Saves
    saves: dict[Save, Breakdown] = {}
    for save in Save:
        ab = SAVE_ABILITY[save]
        ab_mod = c.get_ability_modifier(ab)
        save_typed: dict[str, int] = {"base": c._compute_base_save(save.value)}
        if ab_mod:
            save_typed[ab.value] = ab_mod
        _merge(
            save_typed,
            _pool_breakdown(c.get_pool(f"{save.value}_save"), c),
        )
        saves[save] = Breakdown(
            total=getattr(c, save.value),
            typed=_drop_zeros(save_typed),
        )

    # Damage (melee STR bonus)
    dmg_typed: dict[str, int] = {}
    if str_mod:
        dmg_typed[Ability.STR.value] = str_mod
    _merge(dmg_typed, _pool_breakdown(c.get_pool("damage_melee"), c))
    _merge(dmg_typed, _pool_breakdown(c.get_pool("damage_all"), c))
    damage_melee = Breakdown(
        total=c.get("damage_str_bonus"),
        typed=_drop_zeros(dmg_typed),
    )

    # Grapple
    grapple_typed: dict[str, int] = {"base": c.bab}
    if str_mod:
        grapple_typed[Ability.STR.value] = str_mod
    grapple_size = c._compute_size_mod_grapple()
    if grapple_size:
        grapple_typed["size"] = grapple_size
    _merge(grapple_typed, _pool_breakdown(c.get_pool("grapple"), c))
    grapple = Breakdown(
        total=c.get("grapple"),
        typed=_drop_zeros(grapple_typed),
    )

    return CombatSection(
        ac=ac,
        touch_ac=c.touch_ac(),
        flatfooted_ac=c.flatfooted_ac(),
        hp_max=hp_max,
        bab=bab,
        initiative=initiative,
        speed=speed,
        sr=c.get("sr"),
        saves=saves,
        attack_melee=_attack_breakdown(c, "attack_melee", Ability.STR),
        attack_ranged=_attack_breakdown(c, "attack_ranged", Ability.DEX),
        damage_melee=damage_melee,
        grapple=grapple,
    )


def _attack_breakdown(
    c: "Character",
    stat_key: str,
    ability: Ability,
) -> Breakdown:
    typed: dict[str, int] = {"base": c.bab}
    ab_mod = c.get_ability_modifier(ability)
    if ab_mod:
        typed[ability.value] = ab_mod
    size = c._compute_size_mod_attack()
    if size:
        typed["size"] = size
    _merge(typed, _pool_breakdown(c.get_pool(stat_key), c))
    _merge(typed, _pool_breakdown(c.get_pool("attack_all"), c))
    return Breakdown(total=c.get(stat_key), typed=_drop_zeros(typed))


# -----------------------------------------------------------
# Attack iteratives
# -----------------------------------------------------------


def _iteratives(c: "Character") -> Iteratives:
    return Iteratives(
        melee=c.attack_iteratives(melee=True),
        ranged=c.attack_iteratives(melee=False),
    )


# -----------------------------------------------------------
# Skills
# -----------------------------------------------------------


def _skills(
    c: "Character",
    app_state: "AppState",
) -> dict[KnownSkill, SkillEntry]:
    from heroforge.engine.skills import compute_skill_total

    result: dict[KnownSkill, SkillEntry] = {}
    for sd in app_state.skill_registry.all_skills():
        st = compute_skill_total(c, sd)
        pool_bd = _pool_breakdown(c.get_pool(sd.key), c)

        # Pool's untyped bucket includes ranks — subtract so only
        # genuine untyped bonuses from the pool remain.
        untyped_key = BonusType.UNTYPED.value
        if pool_bd.get(untyped_key, 0):
            remaining = pool_bd[untyped_key] - st.ranks
            if remaining:
                pool_bd[untyped_key] = remaining
            else:
                del pool_bd[untyped_key]

        typed: dict[str, int] = {}
        if st.ability_mod:
            typed["ability_mod"] = st.ability_mod
        if st.ranks:
            typed["ranks"] = st.ranks
        if st.synergy_bonus:
            typed["synergy"] = st.synergy_bonus
        if st.armor_penalty:
            typed["armor_penalty"] = st.armor_penalty
        if st.speed_mod:
            typed["speed_mod"] = st.speed_mod
        _merge(typed, pool_bd)

        if not typed:
            continue

        result[KnownSkill(sd.name)] = SkillEntry(
            total=st.total,
            typed=_drop_zeros(typed),
        )
    return result


# -----------------------------------------------------------
# Carrying capacity
# -----------------------------------------------------------


def _carrying(c: "Character") -> CarryingCapacity:
    light, med, heavy = c.carrying_capacity()
    return CarryingCapacity(light=light, medium=med, heavy=heavy)


# -----------------------------------------------------------
# Feats
# -----------------------------------------------------------


def _feats(c: "Character") -> list[str]:
    return [f.get("name", "") for f in c.feats]


# -----------------------------------------------------------
# Class features
# -----------------------------------------------------------


def _class_features(c: "Character", app_state: "AppState") -> list[str]:
    features: list[str] = []
    for class_name, level in c.class_level_map.items():
        defn = app_state.class_registry.get(class_name)
        if defn is None:
            continue
        for feat in defn.class_features:
            if feat.level <= level:
                features.append(f"{feat.feature}: {feat.description}")
    return features


# -----------------------------------------------------------
# Spellcasting
# -----------------------------------------------------------


def _spellcasting(
    c: "Character",
    app_state: "AppState",
) -> dict[KnownClass, SpellcastingEntry]:
    from heroforge.engine.classes import SpellPreparation
    from heroforge.engine.spellcasting import (
        slots_per_day,
        spell_save_dc,
        spells_known,
    )

    result: dict[KnownClass, SpellcastingEntry] = {}
    for class_name, level in c.class_level_map.items():
        defn = app_state.class_registry.get(class_name)
        if defn is None or defn.spellcasting is None:
            continue
        sc = defn.spellcasting
        if level < sc.starts_at_level:
            continue

        ab_score = c.get_ability_score(sc.stat)
        ab_mod = c.get_ability_modifier(sc.stat)
        slots = slots_per_day(class_name, level, ab_score)
        while slots and slots[-1] is None:
            slots.pop()

        dcs: dict[int, int] = {}
        for spell_lvl in range(len(slots)):
            if slots[spell_lvl] is not None:
                dcs[spell_lvl] = spell_save_dc(ab_mod, spell_lvl)

        known_count: list[int | None] | None = None
        known_spells: dict[int, list[str]] | None = None
        if sc.preparation == SpellPreparation.SPONTANEOUS:
            known = spells_known(class_name, level)
            while known and known[-1] is None:
                known.pop()
            known_count = known

            by_level: dict[int, list[str]] = {}
            replaced: set[str] = set()
            for lv in c.levels:
                if lv.class_name != class_name:
                    continue
                for r in lv.spells_replaced:
                    replaced.add(r.get("old", ""))
                for sl, names in lv.spells_learned.items():
                    by_level.setdefault(int(sl), [])
                    by_level[int(sl)].extend(names)
            for sl in by_level:
                by_level[sl] = [s for s in by_level[sl] if s not in replaced]
            spells_dict = {
                sl: names for sl, names in sorted(by_level.items()) if names
            }
            if spells_dict:
                known_spells = spells_dict

        result[KnownClass(class_name)] = SpellcastingEntry(
            caster_level=level,
            key_ability=sc.stat,
            cast_type=sc.cast_type,
            preparation=sc.preparation,
            slots_per_day=slots,
            spell_save_dc=dcs,
            spells_known_count=known_count,
            spells_known=known_spells,
        )
    return result


# -----------------------------------------------------------
# Special qualities (from templates)
# -----------------------------------------------------------


def _special_qualities(c: "Character", app_state: "AppState") -> list[str]:
    result: list[str] = []
    for app in c.templates:
        defn = app_state.template_registry.get(app.template_name)
        if defn is None:
            continue
        result.extend(defn.special_qualities)
    return result


# -----------------------------------------------------------
# Equipment
# -----------------------------------------------------------


def _equipment(c: "Character") -> EquipmentSection:
    from heroforge.engine.equipment import equipment_display_name

    eq = c.equipment
    section = EquipmentSection()

    armor = eq.get("armor")
    if armor:
        max_dex_raw = armor.get("max_dex_bonus", -1)
        section.armor = ArmorDisplay(
            name=equipment_display_name(
                base=armor.get("name", ""),
                enhancement=armor.get("enhancement", 0),
                material=armor.get("material", ""),
            ),
            acp=armor.get("armor_check_penalty", 0),
            max_dex=max_dex_raw if max_dex_raw >= 0 else None,
            asf=armor.get("arcane_spell_failure", 0) or None,
            properties=list(armor.get("properties", [])),
        )

    shield = eq.get("shield")
    if shield:
        section.shield = ArmorDisplay(
            name=equipment_display_name(
                base=shield.get("name", ""),
                enhancement=shield.get("enhancement", 0),
                material=shield.get("material", ""),
            ),
            acp=shield.get("armor_check_penalty", 0),
            asf=shield.get("arcane_spell_failure", 0) or None,
            properties=list(shield.get("properties", [])),
        )

    section.worn = [KnownMagicItem(n) for n in eq.get("worn", [])]

    for w in eq.get("weapons", []):
        section.weapons.append(
            WeaponDisplay(
                name=equipment_display_name(
                    base=w.get("base", ""),
                    enhancement=w.get("enhancement", 0),
                    material=w.get("material", ""),
                    name=w.get("name", ""),
                ),
                damage_dice=w.get("damage_dice", ""),
                crit_range=w.get("crit_range", ""),
                crit_mult=w.get("crit_mult", ""),
                range_inc=w.get("range_inc") or None,
                damage_types=list(w.get("damage_types", [])),
                weapon_type=w.get("weapon_type", ""),
                weight=w.get("weight") or None,
                properties=list(w.get("properties", [])),
            )
        )

    return section


# -----------------------------------------------------------
# CLI
# -----------------------------------------------------------


def main() -> None:
    """CLI entry point: uv run charsheet."""
    parser = argparse.ArgumentParser(
        description="Build a character sheet from YAML",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to .char.yaml input file",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write output YAML to file",
    )
    args = parser.parse_args()

    state = AppState()
    state.load_rules()

    sheet = extract_sheet(args.input, state)
    out = yaml_dump(converter.unstructure(sheet))

    if args.output:
        args.output.write_text(out)
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
