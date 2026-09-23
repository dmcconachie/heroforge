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
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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


def collect_movement(
    character: "Character",
) -> dict[MovementMode, int]:
    """
    Every movement mode the character has, at its best
    speed.

    Land speed always appears, read off the ``speed`` pool.
    The rest appear only when something grants them.
    """
    speeds: dict[MovementMode, int] = {
        MovementMode.LAND: character.get("speed"),
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

    return speeds
