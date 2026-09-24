"""
engine/movement.py
------------------
How a creature moves, and how fast.

Land speed is a stat: it has a base, things add to it, and
it is computed through the ``speed`` pool like any other
number. The other modes are not. A creature either has a
climb speed or it does not, and two sources of the same
mode do not add -- a spider climb cast twice is still 20
feet, the same way two concealment effects are not 40%.

So a mode is declared by a ``movement:`` block, in the same
places a ``defenses:`` block may appear:

    movement:
      climb: 20

and the best source of each mode wins.

A ``movement_bonus:`` block adds to modes a creature
already has, rather than granting one:

    movement_bonus:
      - modes: all
        bonus: 30
        bonus_type: enhancement
        max_multiple: 2

which is haste. It reaches every mode, does not stack with
another enhancement bonus to the same one, and caps at
twice the unhasted speed -- so a dwarf's 20 ft. becomes 40
rather than 50.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from heroforge.engine.bonus import BonusEntry, BonusType, aggregate
from heroforge.engine.effects import evaluate_formula
from heroforge.engine.enums import MovementMode

if TYPE_CHECKING:
    from heroforge.engine.character import Character


def _blocks(
    character: "Character",
) -> list[tuple[dict, int]]:
    """
    Every ``movement:`` block in force, with the caster
    level its formulas should see.
    """
    # Only get_rules has to be deferred: engine <- rules is a
    # cycle. See docs/plans/engine-rules-import-cycle.md.
    from heroforge.rules.rules import get_rules

    rules = get_rules()
    out: list[tuple[dict, int]] = []

    for buff_name in character.active_buffs():
        buff = rules.buffs.get(buff_name)
        if buff is None or not buff.movement:
            continue
        state = character.get_buff_state(buff_name)
        out.append((buff.movement, state.caster_level or 0 if state else 0))

    for entry in character.equipment.get("worn", []) or []:
        item = rules.magic_items.get(entry["name"])
        if item is not None and item.movement:
            out.append((item.movement, 0))

    for application in character.templates or ():
        template = rules.templates.get(application.template_name)
        if template is not None and template.movement:
            out.append((template.movement, 0))

    classes = rules.classes
    for class_name, level in character.class_level_map.items():
        defn = classes.get(class_name)
        if defn is None:
            continue
        for feature in defn.class_features:
            if feature.level <= level and feature.movement:
                out.append((feature.movement, 0))

    return out


def _bonus_blocks(
    character: "Character",
) -> list[tuple[list[dict], int]]:
    """Every ``movement_bonus:`` block in force."""
    # Only get_rules has to be deferred: engine <- rules is a
    # cycle. See docs/plans/engine-rules-import-cycle.md.
    from heroforge.rules.rules import get_rules

    rules = get_rules()
    out: list[tuple[list[dict], int]] = []

    for buff_name in character.active_buffs():
        buff = rules.buffs.get(buff_name)
        if buff is None or not buff.movement_bonus:
            continue
        state = character.get_buff_state(buff_name)
        out.append(
            (
                buff.movement_bonus,
                state.caster_level or 0 if state else 0,
            )
        )

    for entry in character.equipment.get("worn", []) or []:
        item = rules.magic_items.get(entry["name"])
        if item is not None and item.movement_bonus:
            out.append((item.movement_bonus, 0))

    for application in character.templates or ():
        template = rules.templates.get(application.template_name)
        if template is not None and template.movement_bonus:
            out.append((template.movement_bonus, 0))

    return out


def _entries_for(
    character: "Character", mode: MovementMode
) -> tuple[list[BonusEntry], int]:
    """
    Bonus entries applying to *mode*, and the tightest cap
    multiple any of them declares (0 for none).
    """
    entries: list[BonusEntry] = []
    cap = 0
    for block, caster_level in _bonus_blocks(character):
        for decl in block:
            modes = decl.get("modes", "all")
            if modes != "all" and mode not in {MovementMode(m) for m in modes}:
                continue
            raw = decl.get("bonus", 0)
            value = (
                evaluate_formula(
                    raw, character=character, caster_level=caster_level
                )
                if isinstance(raw, str)
                else int(raw)
            )
            if not value:
                continue
            entries.append(
                BonusEntry(
                    value=value,
                    bonus_type=BonusType(decl.get("bonus_type", "untyped")),
                    source=str(decl.get("source_label", "movement")),
                )
            )
            declared = int(decl.get("max_multiple", 0))
            if declared and (not cap or declared < cap):
                cap = declared
    return entries, cap


def collect_movement(
    character: "Character",
) -> dict[MovementMode, int]:
    """
    Every movement mode the character has, at its best
    speed.

    Land speed always appears, read off the ``speed`` pool.
    The rest appear only when something grants them.
    """
    # Land's bonuses live in the speed pool, so a movement
    # bonus has to be aggregated alongside them or two
    # enhancement bonuses would both count. The pool total
    # is backed out to get the unmodified speed, which is
    # also what a cap multiplies.
    pool = character.get_pool("speed")
    pool_entries = list(pool.active_entries(character)) if pool else []
    pool_total = pool.total(character) if pool else 0
    land_base = character.get("speed") - pool_total

    speeds: dict[MovementMode, int] = {
        MovementMode.LAND: land_base + aggregate(pool_entries, character),
    }

    for block, caster_level in _blocks(character):
        for mode, raw in block.items():
            value = (
                evaluate_formula(
                    raw, character=character, caster_level=caster_level
                )
                if isinstance(raw, str)
                else int(raw)
            )
            if value <= 0:
                continue
            key = MovementMode(mode)
            if value > speeds.get(key, 0):
                speeds[key] = value

    for mode in list(speeds):
        extra, cap = _entries_for(character, mode)
        if not extra:
            continue
        base = land_base if mode is MovementMode.LAND else speeds[mode]
        entries = extra + (pool_entries if mode is MovementMode.LAND else [])
        total = base + aggregate(entries, character)
        if cap:
            total = min(total, cap * base)
        speeds[mode] = total

    return speeds
