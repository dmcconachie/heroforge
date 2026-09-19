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

from typing import TYPE_CHECKING

from heroforge.engine.bonus import BonusEntry, BonusPool, BonusType
from heroforge.engine.stat import StatNode

if TYPE_CHECKING:
    from typing import Callable

    from heroforge.engine.character import Character
    from heroforge.engine.equipment import WeaponDefinition
    from heroforge.engine.feats import FeatDefinition

ATTACK = "attack"
DAMAGE = "damage"


def weapon_pool_keys(index: int) -> tuple[str, str]:
    """(attack, damage) pool keys for the weapon at *index*."""
    return f"weapon_{index}_attack", f"weapon_{index}_damage"


def weapon_definition(item: dict) -> "WeaponDefinition | None":
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
        return wdef.wield_class == applies.get("wield_class")
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
    defn = weapon_definition(item)
    return bool(defn and defn.wield_class == "light")


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
    hand = item.get("hand", "")
    if hand not in ("primary", "off_hand"):
        return 0
    off_hands = [w for w in weapons if w.get("hand") == "off_hand"]
    if not off_hands:
        return 0
    if hand == "off_hand":
        light = _is_light(item)
    else:
        light = all(_is_light(w) for w in off_hands)
    has_feat = character.has_feat("Two-Weapon Fighting")
    primary, off = _TWF_PENALTIES[(light, has_feat)]
    return primary if hand == "primary" else off


_HAND_LABELS = {"primary": "TWF: Primary", "off_hand": "TWF: Off-hand"}


def weapon_stances(character: "Character", item: dict) -> list[str]:
    """
    How this weapon is being used, for the display name.

    A stance changes how the iterative sequence reads — which
    hand it is in, whether Rapid Shot is adding an attack, how
    much Power Attack is trading — so it belongs next to the
    weapon rather than buried in a breakdown.
    """
    out: list[str] = []
    label = _HAND_LABELS.get(item.get("hand", ""))
    if label:
        out.append(label)
    if rapid_shot_applies(character, item):
        out.append("Rapid Shot")
    for name, state in character._buff_states.items():
        if state.active and state.parameter is not None:
            out.append(f"{name}: {state.parameter}")
    return out


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


def rapid_shot_applies(character: "Character", item: dict) -> bool:
    """Rapid Shot shapes the full-attack sequence of a ranged weapon."""
    defn = weapon_definition(item)
    return bool(defn and defn.is_ranged and character.has_feat("Rapid Shot"))


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


def off_hand_strength_penalty(character: "Character", item: dict) -> int:
    """
    Correction applied to reach half Strength in the off hand.

    PHB p. 113: an off-hand weapon adds one-half the wielder's
    Strength bonus to damage. The damage line starts from the
    full bonus, so this subtracts the difference.
    """
    if item.get("hand") != "off_hand":
        return 0
    defn = weapon_definition(item)
    if defn is not None and defn.is_ranged:
        return 0
    from heroforge.engine.enums import Ability

    str_mod = character.get_ability_modifier(Ability.STR)
    if str_mod <= 0:
        return 0
    return (str_mod // 2) - str_mod


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
        for key, which in ((atk_key, ATTACK), (dmg_key, DAMAGE)):
            pool = BonusPool(key)
            enh = (
                _enhancement_entry(item)
                if which == ATTACK
                else _damage_enhancement_entry(item)
            )
            if enh is not None:
                pool.set_source("enhancement", [enh])
            for e in _feat_entries(character, item, which):
                pool.set_source(f"feat:{e.source}", [e])
            if which == ATTACK:
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
                half = off_hand_strength_penalty(character, item)
                if half:
                    pool.set_source(
                        "off_hand_strength",
                        [
                            BonusEntry(
                                value=half,
                                bonus_type=BonusType.UNTYPED,
                                source="off_hand_strength",
                            )
                        ],
                    )
            character.add_pool(pool)
            if which == ATTACK:
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
