"""
heroforge/engine/sheet.py
--------------------------
Extract a complete character sheet from a .char.yaml
input file. Produces a plain dict with all numerical
values and full bonus-type breakdowns.

Public API:
  extract_sheet(path, app_state) -> dict
  gather_sheet(character, app_state) -> dict

CLI:
  uv run charsheet input.char.yaml [-o output.yaml]
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from heroforge.engine.character import Ability

if TYPE_CHECKING:
    from heroforge.engine.character import Character
    from heroforge.ui.app_state import AppState

from heroforge.engine.bonus import (
    ALWAYS_STACKING,
    BonusPool,
)

# -----------------------------------------------------------
# Pool breakdown helper
# -----------------------------------------------------------


def _pool_breakdown(
    pool: BonusPool | None,
    character: "Character",
) -> dict[str, int]:
    """
    Break down a BonusPool into effective contributions
    per bonus type. Applies stacking rules. Returns only
    non-zero entries keyed by bonus_type.value.
    """
    if pool is None:
        return {}

    active = pool.active_entries(character)
    if not active:
        return {}

    stacking: dict[str, int] = defaultdict(int)
    typed_buckets: dict[str, list[int]] = defaultdict(list)

    for e in active:
        name = e.bonus_type.value
        if e.value < 0:
            # Penalties always stack
            stacking[name] += e.value
        elif e.bonus_type in ALWAYS_STACKING:
            stacking[name] += e.value
        else:
            typed_buckets[name].append(e.value)

    result: dict[str, int] = {}
    for name, val in stacking.items():
        if val != 0:
            result[name] = val
    for name, vals in typed_buckets.items():
        best = max(vals)
        if best != 0:
            result[name] = best
    return result


def _nz(d: dict) -> dict:
    """Return dict with zero-value entries removed."""
    return {k: v for k, v in d.items() if v != 0}


# -----------------------------------------------------------
# Main extraction
# -----------------------------------------------------------


def extract_sheet(
    char_path: Path | str,
    app_state: "AppState",
) -> dict:
    """Load a .char.yaml and return the full sheet."""
    from heroforge.engine.persistence import (
        load_character,
    )

    char = load_character(Path(char_path), app_state)
    return gather_sheet(char, app_state)


def gather_sheet(
    character: "Character",
    app_state: "AppState",
) -> dict:
    """
    Extract all numerical values from a Character
    into a plain, YAML-serializable dict with full
    bonus-type breakdowns.
    """
    d: dict = {}
    d["identity"] = _identity(character, app_state)
    d["abilities"] = _abilities(character)
    d["combat"] = _combat(character)
    d["attack_iteratives"] = _iteratives(character)
    d["skills"] = _skills(character, app_state)
    d["carrying_capacity"] = _carrying(character)
    d["feats"] = _feats(character)
    d["class_features"] = _class_features(character, app_state)
    sc = _spellcasting(character, app_state)
    if sc:
        d["spellcasting"] = sc
    sq = _special_qualities(character, app_state)
    if sq:
        d["special_qualities"] = sq
    eq = _equipment(character)
    if eq:
        d["equipment"] = eq
    d["resources"] = {}  # TODO: wire ResourceTracker
    return d


# -----------------------------------------------------------
# Identity
# -----------------------------------------------------------


def _identity(c: "Character", app_state: "AppState") -> dict:
    clm = c.class_level_map
    if clm:
        class_str = " / ".join(f"{cn} {lvl}" for cn, lvl in clm.items())
    else:
        class_str = ""

    race_defn = app_state.race_registry.get(c.race)
    size = race_defn.size if race_defn else "Medium"

    return _nz(
        {
            "name": c.name,
            "race": c.race,
            "class_str": class_str,
            "level": c.total_level,
            "alignment": c.alignment,
            "deity": c.deity,
            "size": size,
        }
    )


# -----------------------------------------------------------
# Abilities
# -----------------------------------------------------------


def _abilities(c: "Character") -> dict:
    result = {}
    for ab in Ability:
        base = c._ability_scores.get(ab, 10)
        pool = c.get_pool(f"{ab}_score")
        bd = _pool_breakdown(pool, c)
        entry: dict = {"base": base}
        bumps = c._level_bump_total(ab)
        if bumps:
            entry["level_bumps"] = bumps
        inherent = c._inherent_bonus_total(ab)
        if inherent:
            entry["inherent"] = inherent
        entry.update(bd)
        entry["score"] = c.get_ability_score(ab)
        entry["mod"] = c.get_ability_modifier(ab)
        result[ab.upper()] = entry
    return result


# -----------------------------------------------------------
# Combat
# -----------------------------------------------------------

_SAVE_ABILITY = {
    "fort": Ability.CON,
    "ref": Ability.DEX,
    "will": Ability.WIS,
}


def _combat(c: "Character") -> dict:
    d: dict = {}

    # AC
    ac_pool = c.get_pool("ac")
    ac_bd = _pool_breakdown(ac_pool, c)
    dex_contrib = c.get("ac_dex_contribution")
    ac_entry: dict = {"base": 10}
    if dex_contrib:
        ac_entry["dex"] = dex_contrib
    size = c._compute_size_mod_attack()
    if size:
        ac_entry["size"] = size
    ac_entry.update(ac_bd)
    ac_entry["total"] = c.ac
    d["ac"] = ac_entry
    d["touch_ac"] = c.touch_ac()
    d["flatfooted_ac"] = c.flatfooted_ac()

    # HP
    hp_dice = c._compute_hp_from_rolls()
    con_hp = c.get_ability_modifier(Ability.CON) * c.total_level
    hp_pool = c.get_pool("hp_bonus")
    hp_bd = _pool_breakdown(hp_pool, c)
    hp_entry: dict = {"hit_dice": hp_dice}
    if con_hp:
        hp_entry["con"] = con_hp
    hp_entry.update(hp_bd)
    hp_entry["total"] = c.hp_max
    d["hp_max"] = hp_entry

    # BAB
    base_bab = c._compute_bab()
    bab_pool = c.get_pool("bab_misc")
    bab_bd = _pool_breakdown(bab_pool, c)
    bab_entry: dict = {"base": base_bab}
    bab_entry.update(bab_bd)
    bab_entry["total"] = c.bab
    d["bab"] = bab_entry

    # Initiative
    dex_mod = c.get_ability_modifier(Ability.DEX)
    init_pool = c.get_pool("initiative")
    init_bd = _pool_breakdown(init_pool, c)
    init_entry: dict = {}
    if dex_mod:
        init_entry["dex"] = dex_mod
    init_entry.update(init_bd)
    init_entry["total"] = c.get("initiative")
    d["initiative"] = init_entry

    # Speed
    base_speed = c._compute_base_speed()
    speed_pool = c.get_pool("speed")
    speed_bd = _pool_breakdown(speed_pool, c)
    speed_entry: dict = {"base": base_speed}
    speed_entry.update(speed_bd)
    speed_entry["total"] = c.get("speed")
    d["speed"] = speed_entry

    # SR
    d["sr"] = c.get("sr")

    # Saves
    for save, ab in _SAVE_ABILITY.items():
        base_save = c._compute_base_save(save)
        ab_mod = c.get_ability_modifier(ab)
        pool = c.get_pool(f"{save}_save")
        bd = _pool_breakdown(pool, c)
        entry: dict = {"base": base_save}
        if ab_mod:
            entry[ab] = ab_mod
        entry.update(bd)
        entry["total"] = getattr(c, save)
        d[save] = entry

    # Melee attack
    d["attack_melee"] = _attack_breakdown(c, "attack_melee", Ability.STR)
    # Ranged attack
    d["attack_ranged"] = _attack_breakdown(c, "attack_ranged", Ability.DEX)

    # Damage (melee STR bonus)
    str_mod = c.get_ability_modifier(Ability.STR)
    dmg_m_pool = c.get_pool("damage_melee")
    dmg_a_pool = c.get_pool("damage_all")
    dmg_bd = _pool_breakdown(dmg_m_pool, c)
    dmg_all_bd = _pool_breakdown(dmg_a_pool, c)
    dmg_entry: dict = {}
    if str_mod:
        dmg_entry["str"] = str_mod
    dmg_entry.update(dmg_bd)
    # Merge damage_all pool (e.g. Weapon Specialization)
    for k, v in dmg_all_bd.items():
        dmg_entry[k] = dmg_entry.get(k, 0) + v
    dmg_entry = _nz(dmg_entry)
    dmg_entry["total"] = c.get("damage_str_bonus")
    d["damage_melee"] = dmg_entry

    # Grapple
    grapple_size = c._compute_size_mod_grapple()
    grapple_pool = c.get_pool("grapple")
    grapple_bd = _pool_breakdown(grapple_pool, c)
    grapple_entry: dict = {"bab": c.bab}
    if str_mod:
        grapple_entry["str"] = str_mod
    if grapple_size:
        grapple_entry["size"] = grapple_size
    grapple_entry.update(grapple_bd)
    grapple_entry["total"] = c.get("grapple")
    d["grapple"] = grapple_entry

    return d


def _attack_breakdown(
    c: "Character",
    stat_key: str,
    ability: Ability,
) -> dict:
    """Build attack breakdown for melee or ranged."""
    bab = c.bab
    ab_mod = c.get_ability_modifier(ability)
    size = c._compute_size_mod_attack()

    # Merge specific + attack_all pools
    pool = c.get_pool(stat_key)
    all_pool = c.get_pool("attack_all")
    bd = _pool_breakdown(pool, c)
    all_bd = _pool_breakdown(all_pool, c)

    entry: dict = {"bab": bab}
    if ab_mod:
        entry[ability] = ab_mod
    if size:
        entry["size"] = size
    entry.update(bd)
    for k, v in all_bd.items():
        entry[k] = entry.get(k, 0) + v
    entry = {k: v for k, v in entry.items() if v != 0}
    entry["total"] = c.get(stat_key)
    return entry


# -----------------------------------------------------------
# Attack iteratives
# -----------------------------------------------------------


def _iteratives(c: "Character") -> dict:
    return {
        "melee": c.attack_iteratives(melee=True),
        "ranged": c.attack_iteratives(melee=False),
    }


# -----------------------------------------------------------
# Skills
# -----------------------------------------------------------


def _skills(c: "Character", app_state: "AppState") -> dict:
    from heroforge.engine.skills import (
        compute_skill_total,
    )

    result = {}
    for sd in app_state.skill_registry.all_skills():
        st = compute_skill_total(c, sd)
        # Include skill only if it has any modifier
        # beyond the base ability mod
        has_extra = (
            st.ranks != 0
            or st.misc_bonus != 0
            or st.synergy_bonus != 0
            or st.armor_penalty != 0
            or st.speed_mod != 0
        )
        if not has_extra:
            # Check pool for typed bonuses (racial, etc.)
            pool = c.get_pool(sd.key)
            if pool:
                bd = _pool_breakdown(pool, c)
                # Pool includes ranks as untyped;
                # if only ranks and ability mod,
                # skip. Check for non-rank entries.
                non_rank = {
                    k: v
                    for k, v in bd.items()
                    if k != "untyped" or v != st.ranks
                }
                if non_rank:
                    has_extra = True
        if not has_extra:
            continue

        entry: dict = {}
        if st.ranks:
            entry["ranks"] = st.ranks
        entry["ability_mod"] = st.ability_mod
        if st.synergy_bonus:
            entry["synergy"] = st.synergy_bonus
        if st.armor_penalty:
            entry["armor_penalty"] = st.armor_penalty
        if st.speed_mod:
            entry["speed_mod"] = st.speed_mod

        # Add typed pool bonuses (racial, competence...)
        pool = c.get_pool(sd.key)
        if pool:
            bd = _pool_breakdown(pool, c)
            # Remove ranks (already shown) and
            # ability mod (shown separately)
            # Pool "untyped" includes ranks, so
            # subtract them
            if "untyped" in bd:
                remaining = bd["untyped"] - st.ranks
                if remaining:
                    bd["untyped"] = remaining
                else:
                    del bd["untyped"]
            for k, v in bd.items():
                if v != 0:
                    entry[k] = v

        entry["total"] = st.total
        result[sd.name] = entry
    return result


# -----------------------------------------------------------
# Carrying capacity
# -----------------------------------------------------------


def _carrying(c: "Character") -> dict:
    light, med, heavy = c.carrying_capacity()
    return {
        "light": light,
        "medium": med,
        "heavy": heavy,
    }


# -----------------------------------------------------------
# Feats
# -----------------------------------------------------------


def _feats(c: "Character") -> list[str]:
    return [f.get("name", "") for f in c.feats]


# -----------------------------------------------------------
# Class features
# -----------------------------------------------------------


def _class_features(c: "Character", app_state: "AppState") -> list[str]:
    features = []
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


def _spellcasting(c: "Character", app_state: "AppState") -> dict:
    from heroforge.engine.spellcasting import (
        slots_per_day,
        spell_save_dc,
        spells_known,
    )

    result = {}
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
        # Strip trailing None entries
        while slots and slots[-1] is None:
            slots.pop()

        entry: dict = {
            "caster_level": level,
            "key_ability": sc.stat,
            "cast_type": sc.cast_type,
            "preparation": sc.preparation,
            "slots_per_day": slots,
        }

        # Spell save DCs per level
        dcs = {}
        for spell_lvl in range(len(slots)):
            if slots[spell_lvl] is not None:
                dcs[spell_lvl] = spell_save_dc(ab_mod, spell_lvl)
        entry["spell_save_dc"] = dcs

        # Spells known (spontaneous casters)
        if sc.preparation == "spontaneous":
            known = spells_known(class_name, level)
            while known and known[-1] is None:
                known.pop()
            entry["spells_known_count"] = known

            # Actual spell list from level entries
            # spells_learned is {spell_level: [names]}
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
            # Remove replaced spells
            for sl in by_level:
                by_level[sl] = [s for s in by_level[sl] if s not in replaced]
            # Only include non-empty levels
            spells_dict = {
                sl: names for sl, names in sorted(by_level.items()) if names
            }
            if spells_dict:
                entry["spells_known"] = spells_dict

        result[class_name] = entry
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


def _equipment(c: "Character") -> dict:
    from heroforge.engine.equipment import (
        equipment_display_name,
    )

    eq = c.equipment
    result: dict = {}

    armor = eq.get("armor")
    if armor:
        entry: dict = {
            "name": equipment_display_name(
                base=armor.get("name", ""),
                enhancement=armor.get("enhancement", 0),
                material=armor.get("material", ""),
            ),
            "acp": armor.get("armor_check_penalty", 0),
        }
        max_dex = armor.get("max_dex_bonus", -1)
        if max_dex >= 0:
            entry["max_dex"] = max_dex
        asf = armor.get("arcane_spell_failure", 0)
        if asf:
            entry["asf"] = asf
        props = armor.get("properties", [])
        if props:
            entry["properties"] = props
        result["armor"] = entry

    shield = eq.get("shield")
    if shield:
        entry = {
            "name": equipment_display_name(
                base=shield.get("name", ""),
                enhancement=shield.get("enhancement", 0),
                material=shield.get("material", ""),
            ),
            "acp": shield.get("armor_check_penalty", 0),
        }
        asf = shield.get("arcane_spell_failure", 0)
        if asf:
            entry["asf"] = asf
        props = shield.get("properties", [])
        if props:
            entry["properties"] = props
        result["shield"] = entry

    worn = eq.get("worn", [])
    if worn:
        result["worn"] = list(worn)

    weapons = eq.get("weapons", [])
    if weapons:
        wlist = []
        for w in weapons:
            wlist.append(
                {
                    "name": equipment_display_name(
                        base=w.get("base", ""),
                        enhancement=w.get("enhancement", 0),
                        material=w.get("material", ""),
                        name=w.get("name", ""),
                    ),
                    **{
                        k: v
                        for k, v in w.items()
                        if k
                        not in (
                            "name",
                            "base",
                            "enhancement",
                            "material",
                        )
                        and v
                    },
                }
            )
        result["weapons"] = wlist

    return result


# -----------------------------------------------------------
# CLI
# -----------------------------------------------------------


def main() -> None:
    """CLI entry point: uv run charsheet."""
    parser = argparse.ArgumentParser(
        description=("Build a character sheet from YAML"),
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

    from heroforge.ui.app_state import AppState

    state = AppState()
    state.load_rules()

    sheet = extract_sheet(args.input, state)

    from heroforge.engine.persistence import yaml_dump

    out = yaml_dump(sheet)

    if args.output:
        args.output.write_text(out)
    else:
        sys.stdout.write(out)
