"""
engine/weapons.py
-----------------
Per-weapon attack and damage lines.

A weapon's attack bonus is the character's generic attack pool
plus everything that applies to *that* weapon: its enhancement
bonus, and only those feats whose selection matches it. Weapon
Focus (Longsword) must not reach a bow, which is exactly what the
shared attack_all pool used to get wrong.

Each equipped weapon gets its own BonusPool and StatNode, keyed
``weapon_<index>_attack`` / ``weapon_<index>_damage``, so the
generic pool feeds it through the stat graph and a Strength
change cascades into every weapon line for free.

Feat applicability is data, declared by a `weapon_effects:` block
on the feat:

  applies.match: name         -- selection names the weapon
  applies.match: damage_type  -- selection names a damage type
  applies.ranged: true/false  -- restrict to ranged or melee

Public API:
  register_weapons_on_character()
  feat_applies_to_weapon()
  weapon_pool_keys()
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from heroforge.engine.bonus import BonusEntry, BonusPool, BonusType
from heroforge.engine.classes import Designation
from heroforge.engine.enums import (
    Ability,
    Size,
    WieldClass,
)
from heroforge.engine.equipment import (
    WeaponDefinition,
    WeaponEnd,
)
from heroforge.engine.proficiency import is_proficient_with_weapon
from heroforge.engine.size import damage_dice_for_size
from heroforge.engine.stat import StatNode

if TYPE_CHECKING:
    from typing import Callable

    from heroforge.engine.character import Character
    from heroforge.engine.feats import FeatDefinition


class WeaponLine(StrEnum):
    """Which of a weapon's two numbers is being built."""

    ATTACK = "attack"
    DAMAGE = "damage"


ATTACK = WeaponLine.ATTACK
DAMAGE = WeaponLine.DAMAGE


class Stance(StrEnum):
    """
    How a weapon is being used for one full attack.

    Two-handed, two-weapon fighting, flurry and Rapid Shot are
    the same shape: a choice made for one full attack about one
    weapon, declared on the slot rather than inferred from a
    feat or a weapon's own properties.
    """

    TWO_HANDED = "two_handed"
    PRIMARY = "primary"
    OFF_HAND = "off_hand"
    FLURRY = "flurry"
    RAPID_SHOT = "rapid_shot"


# Stances that cannot be held at once with the same weapon.
_INCOMPATIBLE: tuple[frozenset[Stance], ...] = (
    # Both hands on one weapon is not a pairing.
    frozenset({Stance.TWO_HANDED, Stance.PRIMARY}),
    frozenset({Stance.TWO_HANDED, Stance.OFF_HAND}),
    # A weapon is in one hand or the other.
    frozenset({Stance.PRIMARY, Stance.OFF_HAND}),
    # One is a melee routine, the other a ranged one.
    frozenset({Stance.FLURRY, Stance.RAPID_SHOT}),
)

_STANCE_LABELS: dict[Stance, str] = {
    Stance.TWO_HANDED: "Two-Handed",
    Stance.PRIMARY: "TWF: Primary",
    Stance.OFF_HAND: "TWF: Off-hand",
    Stance.FLURRY: "Flurry of Blows",
    Stance.RAPID_SHOT: "Rapid Shot",
}


def weapon_pool_keys(index: int) -> tuple[str, str]:
    """(attack, damage) pool keys for the weapon at *index*."""
    return f"weapon_{index}_attack", f"weapon_{index}_damage"


def weapon_definition(item: dict) -> WeaponDefinition | None:
    from heroforge.rules.rules import get_rules

    return get_rules().weapons.get(item.get("base", ""))


def _is_ranged(item: dict) -> bool:
    defn = weapon_definition(item)
    return bool(defn and defn.is_ranged)


def feat_applies_to_weapon(
    defn: "FeatDefinition | None",
    selection: str | None,
    item: dict,
) -> bool:
    """
    True if a feat taken with *selection* applies to this weapon.

    Feats with no `weapon_effects` block never apply — a feat is
    not weapon-specific unless it says so.
    """
    if defn is None:
        return False
    spec = getattr(defn, "weapon_effects", None)
    if not spec:
        return False
    applies = spec.get("applies", {})

    ranged = applies.get("ranged")
    if ranged is not None and bool(ranged) != _is_ranged(item):
        return False

    match = applies.get("match", "name")
    if match == "name":
        return bool(selection) and selection == item.get("base", "")
    if match == "wield_class":
        wdef = weapon_definition(item)
        if wdef is None:
            return False
        if item.get("base", "") in applies.get("also", []):
            return True
        return wdef.wield_class.value == applies.get("wield_class")
    if match == "damage_type":
        wdef = weapon_definition(item)
        if wdef is None or not selection:
            return False
        return str(wdef.damage_type).lower() == selection.lower()
    return False


def _feat_entries(
    character: "Character",
    item: dict,
    which: str,
) -> list[BonusEntry]:
    """Untyped entries from every feat that applies to this weapon."""
    from heroforge.rules.rules import get_rules

    registry = get_rules().feats
    out: list[BonusEntry] = []
    for entry in character.feats:
        defn = registry.get(entry.get("name", ""))
        if not feat_applies_to_weapon(defn, entry.get("parameter"), item):
            continue
        spec = defn.weapon_effects  # type: ignore[union-attr]
        value = int(spec.get(which, 0))
        if not value:
            continue
        out.append(
            BonusEntry(
                value=value,
                bonus_type=BonusType.UNTYPED,
                source=spec.get("source_label", entry["name"]),
            )
        )
    return out


def range_increment_bonus(character: "Character", item: dict) -> int:
    """
    Extra range increment from feats (Ranged Weapon Mastery).

    Range is a weapon property rather than a bonus pool, so it is
    resolved directly rather than through the stat graph.
    """
    from heroforge.rules.rules import get_rules

    registry = get_rules().feats
    total = 0
    for entry in character.feats:
        defn = registry.get(entry.get("name", ""))
        if not feat_applies_to_weapon(defn, entry.get("parameter"), item):
            continue
        total += int(
            defn.weapon_effects.get("range_increment", 0)  # type: ignore[union-attr]
        )
    return total


def attack_ability_override(
    character: "Character",
    item: dict,
) -> str | None:
    """
    The ability a feat substitutes on this weapon's attack roll.

    Weapon Finesse swaps Dexterity for Strength; that is an
    ability swap, not a bonus, so it cannot be a pool entry.
    """
    from heroforge.rules.rules import get_rules

    registry = get_rules().feats
    for entry in character.feats:
        defn = registry.get(entry.get("name", ""))
        if not feat_applies_to_weapon(defn, entry.get("parameter"), item):
            continue
        ability = defn.weapon_effects.get(  # type: ignore[union-attr]
            "attack_ability"
        )
        if ability:
            return str(ability)
    return None


def threat_range(character: "Character", item: dict) -> tuple[int, int]:
    """
    (low, high) of this weapon's critical threat range.

    Improved Critical (PHB p. 96) and keen (DMG p. 225) each
    double the range and explicitly do not stack with each other,
    so it doubles at most once however many sources apply.
    """
    wdef = weapon_definition(item)
    if wdef is None:
        return (20, 20)
    low = wdef.critical_range
    doubled = any(
        "keen" in str(prop).lower() for prop in item.get("properties", [])
    )
    if not doubled:
        from heroforge.rules.rules import get_rules

        registry = get_rules().feats
        for entry in character.feats:
            defn = registry.get(entry.get("name", ""))
            if not feat_applies_to_weapon(defn, entry.get("parameter"), item):
                continue
            if defn.weapon_effects.get(  # type: ignore[union-attr]
                "doubles_threat_range"
            ):
                doubled = True
                break
    if doubled:
        low = 21 - 2 * (21 - low)
    return (max(low, 2), 20)


# PHB Table 8-10, keyed (off_hand_is_light, has_twf_feat).
_TWF_PENALTIES = {
    (False, False): (-6, -10),
    (True, False): (-4, -8),
    (False, True): (-4, -4),
    (True, True): (-2, -2),
}


def _is_light(item: dict) -> bool:
    """
    Whether an off-hand weapon counts as light for PHB Table
    8-10.

    The far end of a double weapon does: fighting with both
    ends is "just as though the character were wielding a
    one-handed weapon and a light weapon" (PHB p. 113).
    """
    defn = weapon_definition(item)
    if defn is None:
        return False
    return defn.wield_class is WieldClass.LIGHT or defn.double


def two_weapon_penalty(
    character: "Character",
    item: dict,
    weapons: list[dict],
) -> int:
    """
    This weapon's two-weapon fighting penalty, or 0.

    Applies only to weapons declared part of a pairing via
    ``hand: primary`` / ``hand: off_hand``, because fighting with two
    weapons is a choice made per full attack rather than a
    property of carrying two.

    The primary penalty depends on the off-hand weapon. A
    character may declare more than one pairing, and nothing
    records which weapon pairs with which, so the primary is
    treated as light-handed only when every declared off-hand
    weapon is light.
    """
    hand = next(
        (s for s in (Stance.OFF_HAND, Stance.PRIMARY) if has_stance(item, s)),
        None,
    )
    if hand is None:
        return 0
    off_hands = [w for w in weapons if has_stance(w, Stance.OFF_HAND)]
    if not off_hands:
        return 0
    if hand is Stance.OFF_HAND:
        light = _is_light(item)
    else:
        light = all(_is_light(w) for w in off_hands)
    has_feat = character.has_feat("Two-Weapon Fighting")
    primary, off = _TWF_PENALTIES[(light, has_feat)]
    return primary if hand is Stance.PRIMARY else off


def stances_of(item: dict) -> tuple[Stance, ...]:
    """The stances a weapon slot declares, in a stable order."""
    declared = set(item.get("stances", []) or [])
    return tuple(s for s in Stance if s in declared)


def has_stance(item: dict, name: Stance) -> bool:
    return name in (item.get("stances", []) or [])


def weapon_stances(character: "Character", item: dict) -> list[str]:
    """
    How this weapon is being used, for the display name.

    A stance changes how the iterative sequence reads — which
    hand it is in, whether Rapid Shot is adding an attack, how
    much Power Attack is trading — so it belongs next to the
    weapon rather than buried in a breakdown.
    """
    out: list[str] = []
    for stance in stances_of(item):
        if stance is Stance.TWO_HANDED and not two_handed_applies(
            character, item
        ):
            continue
        if stance is Stance.FLURRY and not flurry_applies(character, item):
            continue
        if stance is Stance.RAPID_SHOT and not rapid_shot_applies(
            character, item
        ):
            continue
        out.append(_STANCE_LABELS[stance])
    for name, state in character._buff_states.items():
        if state.active and state.parameter is not None:
            out.append(f"{name}: {state.parameter}")
    return out


# PHB Table 3-10 (Medium) and Table 3-11 (Small and Large),
# p. 40-41. Indexed by the top of each level band.
_MONK_UNARMED_DAMAGE: tuple[tuple[int, dict[Size, str]], ...] = (
    (3, {Size.SMALL: "1d4", Size.MEDIUM: "1d6", Size.LARGE: "1d8"}),
    (7, {Size.SMALL: "1d6", Size.MEDIUM: "1d8", Size.LARGE: "2d6"}),
    (11, {Size.SMALL: "1d8", Size.MEDIUM: "1d10", Size.LARGE: "2d8"}),
    (15, {Size.SMALL: "1d10", Size.MEDIUM: "2d6", Size.LARGE: "3d6"}),
    (19, {Size.SMALL: "2d6", Size.MEDIUM: "2d8", Size.LARGE: "3d8"}),
    (20, {Size.SMALL: "2d8", Size.MEDIUM: "2d10", Size.LARGE: "4d8"}),
)

MONK_UNARMED_WEAPON = "Unarmed Strike"


def monk_unarmed_damage(
    effective_level: int,
    size: "Size | str",
) -> str | None:
    """
    A monk's unarmed strike damage at *effective_level*.

    Returns None below 1st level, which is how a character
    with no monk levels and no Monk's Belt is distinguished
    from one with them — such a character deals the plain
    weapon's damage instead.

    This is a printed table, not a formula, and the PHB gives
    it only for Small, Medium and Large. Anything else raises
    rather than guess. Levels past 20 hold at the last row.
    """
    if effective_level < 1:
        return None
    size = Size(size)
    row = _MONK_UNARMED_DAMAGE[-1][1]
    for top, candidate in _MONK_UNARMED_DAMAGE:
        if effective_level <= top:
            row = candidate
            break
    if size not in row:
        raise ValueError(
            f"Monk unarmed damage for a {size.value} monk is not "
            f"printed (PHB Tables 3-10 and 3-11 cover Small, "
            f"Medium and Large)."
        )
    return row[size]


def weapon_feature_names(item: dict) -> list[str]:
    """
    Display names for the class features designating this
    weapon, e.g. ["Weapon Bond"].

    The sheet lists these beside the weapon's item properties,
    because from the player's side a bonded weapon and an
    enchanted one both read as "what is special about this
    weapon".
    """
    return [
        str(key).replace("_", " ").title()
        for key in item.get("features", []) or []
    ]


def critical_multiplier(item: dict) -> int:
    """
    The multiplier of the end being used.

    The gnome hooked hammer's hook crits x4 where its head
    crits x3 (PHB p. 118).
    """
    defn = weapon_definition(item)
    if defn is None:
        return 2
    end = _end_of(item)
    if end is not None and end.critical_multiplier:
        return end.critical_multiplier
    return defn.critical_multiplier


def _end_of(item: dict) -> WeaponEnd | None:
    """
    The far end's stats, when this slot is the off end of an
    asymmetric double weapon.

    The gnome hooked hammer's hook and the dwarven urgrosh's
    spear head differ from the other end; the four symmetric
    double weapons have no separate description.
    """
    defn = weapon_definition(item)
    if defn is None or not has_stance(item, Stance.OFF_HAND):
        return None
    return defn.off_end


def damage_dice(character: "Character", item: dict) -> str:
    """
    This weapon's damage dice at the wielder's current size.

    An explicit ``damage_dice`` on the equipment entry wins:
    it is an author override for a weapon the rules data does
    not describe, and second-guessing its size would be wrong.
    """
    override = item.get("damage_dice", "")
    if override:
        return override
    defn = weapon_definition(item)
    if defn is None:
        return ""
    end = _end_of(item)
    if end is not None and end.damage_dice:
        return damage_dice_for_size(
            end.damage_dice,
            end.damage_dice_small or end.damage_dice,
            character.size,
        )
    # A monk's unarmed strike has its own table by level and
    # size, which replaces the weapon's printed damage rather
    # than modifying it.
    if defn.name == MONK_UNARMED_WEAPON:
        monk = monk_unarmed_damage(
            character.get("effective_monk_level_damage"),
            character.size,
        )
        if monk is not None:
            return monk
    return damage_dice_for_size(
        defn.damage_dice,
        defn.damage_dice_small or defn.damage_dice,
        character.size,
    )


def material_damage_entry(item: dict) -> BonusEntry | None:
    """
    A weapon material's damage adjustment, if any.

    Only alchemical silver has one. Its "minimum 1 point of
    damage" floor applies to the rolled total, not to this
    static line, so it is not modelled here.
    """
    from heroforge.rules.rules import get_rules

    name = item.get("material", "")
    if not name:
        return None
    mat = get_rules().materials.get(name)
    if mat is None or not mat.damage_adjust:
        return None
    return BonusEntry(
        value=mat.damage_adjust,
        bonus_type=BonusType.UNTYPED,
        source="material",
    )


# PHB p. 40: a flurry may use unarmed strikes or the special
# monk weapons, and nothing else.
FLURRY_WEAPONS: frozenset[str] = frozenset(
    {
        MONK_UNARMED_WEAPON,
        "Kama",
        "Nunchaku",
        "Quarterstaff",
        "Sai",
        "Shuriken",
        "Siangham",
    }
)


def flurry_penalty(character: "Character") -> int:
    """
    The penalty a flurry puts on every attack that round.

    -2 to begin with, easing to -1 at 5th level and gone at
    9th (PHB p. 40).
    """
    level = character.class_level_map.get("Monk", 0)
    if level >= 9:
        return 0
    if level >= 5:
        return -1
    return -2


def flurry_extra_attacks(character: "Character") -> int:
    """
    Extra attacks a flurry grants, both at full base attack.

    One, and a second from 11th level -- greater flurry.
    """
    return 2 if character.class_level_map.get("Monk", 0) >= 11 else 1


def flurry_applies(character: "Character", item: dict) -> bool:
    """
    Whether this weapon is being used in a flurry.

    Asked for on the weapon slot rather than inferred, because
    a flurry is a choice made per full attack. It is off while
    armoured: the ability reads "when unarmored".
    """
    if not has_stance(item, Stance.FLURRY):
        return False
    if not character.has_class_feature("flurry_of_blows"):
        return False
    return character.equipped_armor_category() is None


def rapid_shot_applies(character: "Character", item: dict) -> bool:
    """
    Whether this weapon is being fired with Rapid Shot.

    Asked for rather than inferred: the feat needs the full
    attack action, so holding it is not the same as using it.
    """
    if not has_stance(item, Stance.RAPID_SHOT):
        return False
    defn = weapon_definition(item)
    return bool(defn and defn.is_ranged and character.has_feat("Rapid Shot"))


def two_handed_applies(
    character: "Character",  # noqa: ARG001
    item: dict,
) -> bool:
    """
    Whether this weapon is being wielded in two hands for
    damage purposes.

    A two-handed weapon needs no asking -- two hands are
    required to use one at all. A one-handed weapon may be
    wielded in two by saying so. A light weapon gains nothing
    either way, and neither does a ranged weapon (PHB p. 113).

    Fighting with both ends of a double weapon is the other
    use, and it is one-handed-plus-light rather than
    two-handed: full Strength on one end, half on the other,
    and one and a half on neither.
    """
    defn = weapon_definition(item)
    if defn is None or defn.is_ranged:
        return False
    if has_stance(item, Stance.PRIMARY) or has_stance(item, Stance.OFF_HAND):
        return False
    if defn.wield_class is WieldClass.TWO_HANDED:
        return True
    return defn.wield_class is WieldClass.ONE_HANDED and has_stance(
        item, Stance.TWO_HANDED
    )


def off_hand_attack_count(character: "Character") -> int:
    """
    How many attacks an off-hand weapon gets.

    PHB p. 160: one extra attack with an off-hand weapon, not the
    full iterative sequence. Improved Two-Weapon Fighting adds a
    second at -5 and Greater Two-Weapon Fighting a third at -10.
    """
    if character.has_feat("Greater Two-Weapon Fighting"):
        return 3
    if character.has_feat("Improved Two-Weapon Fighting"):
        return 2
    return 1


def strength_damage_adjust(character: "Character", item: dict) -> int:
    """
    Correction from the full Strength bonus the damage line
    starts with.

    PHB p. 113: half in the off hand, one and a half in two
    hands, full otherwise. Only the bonus scales -- a penalty
    applies in full however the weapon is held.
    """
    defn = weapon_definition(item)
    if defn is not None and defn.is_ranged:
        return 0
    str_mod = character.get_ability_modifier(Ability.STR)
    if str_mod <= 0:
        return 0
    if has_stance(item, Stance.OFF_HAND):
        return (str_mod // 2) - str_mod
    if two_handed_applies(character, item):
        return (str_mod + str_mod // 2) - str_mod
    return 0


def _enhancement_entry(item: dict) -> BonusEntry | None:
    """
    The weapon's own enhancement bonus.

    Masterwork grants +1 on attacks but does not stack with a
    magical enhancement bonus, so it only shows on a mundane
    weapon.
    """
    bonus = int(item.get("enhancement", 0))
    if not bonus and item.get("masterwork"):
        bonus = 1
    if not bonus:
        return None
    return BonusEntry(
        value=bonus,
        bonus_type=BonusType.ENHANCEMENT,
        source="enhancement",
    )


def _damage_enhancement_entry(item: dict) -> BonusEntry | None:
    """Masterwork adds nothing to damage; only a real enhancement does."""
    bonus = int(item.get("enhancement", 0))
    if not bonus:
        return None
    return BonusEntry(
        value=bonus,
        bonus_type=BonusType.ENHANCEMENT,
        source="enhancement",
    )


def _make_compute(
    base_key: str | None,
) -> "Callable[[dict[str, int], int], int]":
    def compute(inputs: dict[str, int], bonus_total: int) -> int:
        if base_key is None:
            return bonus_total
        return inputs.get(base_key, 0) + bonus_total

    return compute


def _make_swap_compute(
    base_key: str,
    ability: str,
) -> "Callable[[dict[str, int], int], int]":
    """Base line, with its Strength term replaced by *ability*."""

    def compute(inputs: dict[str, int], bonus_total: int) -> int:
        base = inputs.get(base_key, 0)
        base -= inputs.get("str_mod", 0)
        base += inputs.get(f"{ability}_mod", 0)
        return base + bonus_total

    return compute


def register_weapons_on_character(character: "Character") -> None:
    """
    Rebuild the per-weapon pools and nodes from equipped weapons.

    Replaces the whole set rather than merging, so unequipping a
    weapon drops its line instead of stranding it.
    """
    for key in [k for k in list(character._pools) if k.startswith("weapon_")]:
        character.remove_pool(key)

    weapons = character.equipment.get("weapons", []) or []
    for index, item in enumerate(weapons):
        ranged = _is_ranged(item)
        atk_key, dmg_key = weapon_pool_keys(index)
        atk_base = "attack_ranged" if ranged else "attack_melee"
        dmg_pool = "damage_ranged" if ranged else "damage_melee"
        for key, which in (
            (atk_key, WeaponLine.ATTACK),
            (dmg_key, WeaponLine.DAMAGE),
        ):
            pool = BonusPool(key)
            enh = (
                _enhancement_entry(item)
                if which is WeaponLine.ATTACK
                else _damage_enhancement_entry(item)
            )
            if enh is not None:
                pool.set_source("enhancement", [enh])
            for e in _feat_entries(character, item, which):
                pool.set_source(f"feat:{e.source}", [e])
            if which is WeaponLine.ATTACK:
                if rapid_shot_applies(character, item):
                    # -2 on every ranged attack that round, so it
                    # belongs on the line itself and not only on
                    # the sequence.
                    pool.set_source(
                        "rapid_shot",
                        [
                            BonusEntry(
                                value=-2,
                                bonus_type=BonusType.UNTYPED,
                                source="rapid_shot",
                            )
                        ],
                    )
                if not is_proficient_with_weapon(
                    character, weapon_definition(item)
                ):
                    pool.set_source(
                        "nonproficient",
                        [
                            BonusEntry(
                                value=-4,
                                bonus_type=BonusType.UNTYPED,
                                source="nonproficient",
                            )
                        ],
                    )
                if flurry_applies(character, item):
                    penalty = flurry_penalty(character)
                    if penalty:
                        # Applies to every attack that round,
                        # so it belongs on the line and not
                        # only on the sequence.
                        pool.set_source(
                            "flurry_of_blows",
                            [
                                BonusEntry(
                                    value=penalty,
                                    bonus_type=BonusType.UNTYPED,
                                    source="flurry_of_blows",
                                )
                            ],
                        )
                twf = two_weapon_penalty(character, item, weapons)
                if twf:
                    pool.set_source(
                        "two_weapon_fighting",
                        [
                            BonusEntry(
                                value=twf,
                                bonus_type=BonusType.UNTYPED,
                                source="two_weapon_fighting",
                            )
                        ],
                    )
            else:
                mat = material_damage_entry(item)
                if mat is not None:
                    pool.set_source("material", [mat])
                half = strength_damage_adjust(character, item)
                if half:
                    pool.set_source(
                        "strength_hands",
                        [
                            BonusEntry(
                                value=half,
                                bonus_type=BonusType.UNTYPED,
                                source="strength_hands",
                            )
                        ],
                    )
            character.add_pool(pool)
            if which is WeaponLine.ATTACK:
                # attack_melee/_ranged are nodes, so the weapon
                # line takes the whole computed line as its base.
                # An ability override (Weapon Finesse) subtracts
                # the ability the base line used and adds the
                # substitute, so the graph still drives both.
                override = attack_ability_override(character, item)
                if override and not ranged:
                    inputs = [atk_base, "str_mod", f"{override}_mod"]
                    pools = [key]
                    compute = _make_swap_compute(atk_base, override)
                else:
                    inputs, pools = [atk_base], [key]
                    compute = _make_compute(atk_base)
            else:
                # Damage has no single node: the Strength bonus
                # is its own node and the rest is pools, so the
                # weapon line sums both. Strength does not add to
                # ranged damage.
                inputs = [] if ranged else ["damage_str_bonus"]
                pools = [key, dmg_pool, "damage_all"]
                compute = _make_compute(None if ranged else "damage_str_bonus")
            character._graph.register_node(
                StatNode(
                    key=key,
                    base=None,
                    inputs=inputs,
                    pools=pools,
                    compute=compute,
                    description=f"{item.get('base', '')} {which}",
                )
            )


def _validate_stances(
    character: "Character",
    item: dict,
    available: dict[str, str],
) -> None:
    """
    Check the stances one weapon slot declares.

    A stance the character cannot take, or two that cannot be
    held at once, is a data error: the sheet would otherwise
    drop it and quietly print a weaker weapon.
    """
    declared = set(item.get("stances", []) or [])
    unknown = declared - set(Stance)
    if unknown:
        raise ValueError(
            f"Unknown weapon stance(s) {sorted(unknown)!r}. "
            f"Known: {sorted(s.value for s in Stance)!r}."
        )
    for pair in _INCOMPATIBLE:
        if pair <= declared:
            raise ValueError(
                f"Stances {sorted(pair)!r} cannot be held at once "
                f"with the same weapon."
            )

    base = str(item.get("base", ""))
    defn = weapon_definition(item)

    if Stance.FLURRY in declared:
        if "flurry_of_blows" not in available:
            raise ValueError(
                "Weapon declares the flurry stance, but this "
                "character has no flurry of blows."
            )
        if base not in FLURRY_WEAPONS:
            raise ValueError(
                f"{base!r} cannot be used in a flurry: only unarmed "
                f"strikes and the special monk weapons can "
                f"(PHB p. 40)."
            )

    if Stance.RAPID_SHOT in declared:
        if not character.has_feat("Rapid Shot"):
            raise ValueError(
                "Weapon declares the rapid_shot stance, but this "
                "character does not have the Rapid Shot feat."
            )
        if defn is None or not defn.is_ranged:
            raise ValueError(
                f"{base!r} is not a ranged weapon, so it cannot take "
                f"the rapid_shot stance."
            )

    if (
        declared & {Stance.PRIMARY, Stance.OFF_HAND}
        and defn is not None
        and defn.wield_class is WieldClass.TWO_HANDED
        and not defn.double
    ):
        raise ValueError(
            f"{base!r} is two-handed and not a double weapon, so it "
            f"cannot be fought with as two weapons (PHB p. 113)."
        )

    if (
        Stance.TWO_HANDED in declared
        and defn is not None
        and (defn.is_ranged or defn.wield_class is WieldClass.LIGHT)
    ):
        raise ValueError(
            f"{base!r} gains nothing from two hands: a light or "
            f"ranged weapon adds the Strength bonus as though "
            f"held in one (PHB p. 113)."
        )


def validate_weapon_features(character: "Character") -> None:
    """
    Check every class feature a weapon slot designates.

    A name that is not a feature, or is a feature the
    character does not have, or is a feature that designates
    nothing, is a data error rather than something to ignore
    quietly: the sheet would simply drop it.
    """
    from heroforge.rules.rules import get_rules  # cycle; see docs

    classes = get_rules().classes
    available: dict[str, Designation] = {}
    for class_name, level in character.class_level_map.items():
        defn = classes.get(class_name)
        if defn is None:
            continue
        for feature in defn.class_features:
            if feature.level <= level:
                available[feature.feature] = feature.designates

    for item in character.equipment.get("weapons", []) or []:
        _validate_stances(character, item, available)
        for key in item.get("features", []) or []:
            if key not in available:
                raise ValueError(
                    f"Weapon names class feature {key!r}, which this "
                    f"character does not have."
                )
            if available[key] is not Designation.WEAPON:
                raise ValueError(
                    f"Class feature {key!r} does not designate a "
                    f"weapon, so a weapon cannot name it."
                )
