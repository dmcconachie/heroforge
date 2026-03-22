"""
engine/spellcasting.py
----------------------
Spell slot computation, bonus spells, spell save DCs,
and spells-known tables for D&D 3.5e.

Public API:
  base_slots_per_day(class_name, class_level)
  bonus_spells(ability_modifier)
  slots_per_day(class_name, class_level, ability_score)
  spells_known(class_name, class_level)
  spell_save_dc(ability_modifier, spell_level)
"""

from __future__ import annotations

from math import floor

# ---------------------------------------------------------
# Spell slot tables: class -> level -> [slots by spell lvl]
# Index 0 = cantrips, 1 = 1st level, etc.
# None means the class cannot cast that spell level yet.
# ---------------------------------------------------------

# fmt: off
_WIZARD_SLOTS: dict[int, list[int | None]] = {
    1:  [3,1,None,None,None,None,None,None,None,None],
    2:  [4,2,None,None,None,None,None,None,None,None],
    3:  [4,2,1,None,None,None,None,None,None,None],
    4:  [4,3,2,None,None,None,None,None,None,None],
    5:  [4,3,2,1,None,None,None,None,None,None],
    6:  [4,3,3,2,None,None,None,None,None,None],
    7:  [4,4,3,2,1,None,None,None,None,None],
    8:  [4,4,3,3,2,None,None,None,None,None],
    9:  [4,4,4,3,2,1,None,None,None,None],
    10: [4,4,4,3,3,2,None,None,None,None],
    11: [4,4,4,4,3,2,1,None,None,None],
    12: [4,4,4,4,3,3,2,None,None,None],
    13: [4,4,4,4,4,3,2,1,None,None],
    14: [4,4,4,4,4,3,3,2,None,None],
    15: [4,4,4,4,4,4,3,2,1,None],
    16: [4,4,4,4,4,4,3,3,2,None],
    17: [4,4,4,4,4,4,4,3,2,1],
    18: [4,4,4,4,4,4,4,3,3,2],
    19: [4,4,4,4,4,4,4,4,3,3],
    20: [4,4,4,4,4,4,4,4,4,4],
}

_SORCERER_SLOTS: dict[int, list[int | None]] = {
    1:  [5,3,None,None,None,None,None,None,None,None],
    2:  [6,4,None,None,None,None,None,None,None,None],
    3:  [6,5,None,None,None,None,None,None,None,None],
    4:  [6,6,3,None,None,None,None,None,None,None],
    5:  [6,6,4,None,None,None,None,None,None,None],
    6:  [6,6,5,3,None,None,None,None,None,None],
    7:  [6,6,6,4,None,None,None,None,None,None],
    8:  [6,6,6,5,3,None,None,None,None,None],
    9:  [6,6,6,6,4,None,None,None,None,None],
    10: [6,6,6,6,5,3,None,None,None,None],
    11: [6,6,6,6,6,4,None,None,None,None],
    12: [6,6,6,6,6,5,3,None,None,None],
    13: [6,6,6,6,6,6,4,None,None,None],
    14: [6,6,6,6,6,6,5,3,None,None],
    15: [6,6,6,6,6,6,6,4,None,None],
    16: [6,6,6,6,6,6,6,5,3,None],
    17: [6,6,6,6,6,6,6,6,4,None],
    18: [6,6,6,6,6,6,6,6,5,3],
    19: [6,6,6,6,6,6,6,6,6,4],
    20: [6,6,6,6,6,6,6,6,6,6],
}

_SORCERER_KNOWN: dict[int, list[int | None]] = {
    1:  [4,2,None,None,None,None,None,None,None,None],
    2:  [5,2,None,None,None,None,None,None,None,None],
    3:  [5,3,None,None,None,None,None,None,None,None],
    4:  [6,3,1,None,None,None,None,None,None,None],
    5:  [6,4,2,None,None,None,None,None,None,None],
    6:  [7,4,2,1,None,None,None,None,None,None],
    7:  [7,5,3,2,None,None,None,None,None,None],
    8:  [8,5,3,2,1,None,None,None,None,None],
    9:  [8,5,4,3,2,None,None,None,None,None],
    10: [9,5,4,3,2,1,None,None,None,None],
    11: [9,5,5,4,3,2,None,None,None,None],
    12: [9,5,5,4,3,2,1,None,None,None],
    13: [9,5,5,4,4,3,2,None,None,None],
    14: [9,5,5,4,4,3,2,1,None,None],
    15: [9,5,5,4,4,4,3,2,None,None],
    16: [9,5,5,4,4,4,3,2,1,None],
    17: [9,5,5,4,4,4,3,3,2,None],
    18: [9,5,5,4,4,4,3,3,2,1],
    19: [9,5,5,4,4,4,3,3,3,2],
    20: [9,5,5,4,4,4,3,3,3,3],
}

# Cleric/Druid (full divine 0-9, same table)
_CLERIC_SLOTS: dict[int, list[int | None]] = {
    1:  [3,1,None,None,None,None,None,None,None,None],
    2:  [4,2,None,None,None,None,None,None,None,None],
    3:  [4,2,1,None,None,None,None,None,None,None],
    4:  [5,3,2,None,None,None,None,None,None,None],
    5:  [5,3,2,1,None,None,None,None,None,None],
    6:  [5,3,3,2,None,None,None,None,None,None],
    7:  [6,4,3,2,1,None,None,None,None,None],
    8:  [6,4,3,3,2,None,None,None,None,None],
    9:  [6,4,4,3,2,1,None,None,None,None],
    10: [6,4,4,3,3,2,None,None,None,None],
    11: [6,5,4,4,3,2,1,None,None,None],
    12: [6,5,4,4,3,3,2,None,None,None],
    13: [6,5,5,4,4,3,2,1,None,None],
    14: [6,5,5,4,4,3,3,2,None,None],
    15: [6,5,5,5,4,4,3,2,1,None],
    16: [6,5,5,5,4,4,3,3,2,None],
    17: [6,5,5,5,5,4,4,3,2,1],
    18: [6,5,5,5,5,4,4,3,3,2],
    19: [6,5,5,5,5,5,4,4,3,3],
    20: [6,5,5,5,5,5,4,4,4,4],
}

# Bard (arcane spontaneous 0-6)
_BARD_SLOTS: dict[int, list[int | None]] = {
    1:  [2,None,None,None,None,None,None],
    2:  [3,0,None,None,None,None,None],
    3:  [3,1,None,None,None,None,None],
    4:  [3,2,0,None,None,None,None],
    5:  [3,3,1,None,None,None,None],
    6:  [3,3,2,None,None,None,None],
    7:  [3,3,2,0,None,None,None],
    8:  [3,3,3,1,None,None,None],
    9:  [3,3,3,2,None,None,None],
    10: [3,3,3,2,0,None,None],
    11: [3,3,3,3,1,None,None],
    12: [3,3,3,3,2,None,None],
    13: [3,3,3,3,2,0,None],
    14: [4,3,3,3,3,1,None],
    15: [4,4,3,3,3,2,None],
    16: [4,4,4,3,3,2,0],
    17: [4,4,4,4,3,3,1],
    18: [4,4,4,4,4,3,2],
    19: [4,4,4,4,4,4,3],
    20: [4,4,4,4,4,4,4],
}

_BARD_KNOWN: dict[int, list[int | None]] = {
    1:  [4,None,None,None,None,None,None],
    2:  [5,2,None,None,None,None,None],
    3:  [6,3,None,None,None,None,None],
    4:  [6,3,2,None,None,None,None],
    5:  [6,4,3,None,None,None,None],
    6:  [6,4,3,None,None,None,None],
    7:  [6,4,4,2,None,None,None],
    8:  [6,4,4,3,None,None,None],
    9:  [6,4,4,3,None,None,None],
    10: [6,4,4,4,2,None,None],
    11: [6,4,4,4,3,None,None],
    12: [6,4,4,4,3,None,None],
    13: [6,4,4,4,4,2,None],
    14: [6,4,4,4,4,3,None],
    15: [6,4,4,4,4,3,None],
    16: [6,5,4,4,4,4,2],
    17: [6,5,5,4,4,4,3],
    18: [6,5,5,5,4,4,3],
    19: [6,5,5,5,5,4,4],
    20: [6,5,5,5,5,5,4],
}

# Paladin (divine prepared 1-4, starts at lvl 4)
_PALADIN_SLOTS: dict[int, list[int | None]] = {
    4:  [0,None,None,None],
    5:  [1,None,None,None],
    6:  [1,None,None,None],
    7:  [1,None,None,None],
    8:  [1,0,None,None],
    9:  [1,0,None,None],
    10: [1,1,None,None],
    11: [1,1,0,None],
    12: [1,1,1,None],
    13: [1,1,1,None],
    14: [2,1,1,0],
    15: [2,1,1,1],
    16: [2,2,1,1],
    17: [2,2,2,1],
    18: [3,2,2,1],
    19: [3,3,3,2],
    20: [3,3,3,3],
}

# Ranger (divine prepared 1-4, starts at lvl 4)
_RANGER_SLOTS: dict[int, list[int | None]] = {
    4:  [0,None,None,None],
    5:  [1,None,None,None],
    6:  [1,None,None,None],
    7:  [1,None,None,None],
    8:  [1,0,None,None],
    9:  [1,0,None,None],
    10: [1,1,None,None],
    11: [1,1,0,None],
    12: [1,1,1,None],
    13: [1,1,1,None],
    14: [2,1,1,0],
    15: [2,1,1,1],
    16: [2,2,1,1],
    17: [2,2,2,1],
    18: [3,2,2,1],
    19: [3,3,3,2],
    20: [3,3,3,3],
}
# fmt: on

_SLOT_TABLES: dict[str, dict[int, list]] = {
    "Wizard": _WIZARD_SLOTS,
    "Sorcerer": _SORCERER_SLOTS,
    "Cleric": _CLERIC_SLOTS,
    "Druid": _CLERIC_SLOTS,  # same table
    "Bard": _BARD_SLOTS,
    "Paladin": _PALADIN_SLOTS,
    "Ranger": _RANGER_SLOTS,
}

_KNOWN_TABLES: dict[str, dict[int, list]] = {
    "Sorcerer": _SORCERER_KNOWN,
    "Bard": _BARD_KNOWN,
}


def base_slots_per_day(class_name: str, class_level: int) -> list[int | None]:
    """
    Base spell slots per day (before bonus spells).

    Returns a list indexed by spell level.
    None means that spell level is unavailable.
    Returns empty list if class has no spell table.
    """
    table = _SLOT_TABLES.get(class_name)
    if table is None:
        return []
    # Clamp to max level in table
    max_lvl = max(table.keys())
    lvl = min(class_level, max_lvl)
    row = table.get(lvl)
    if row is None:
        return []
    return list(row)


def bonus_spells(ability_modifier: int) -> list[int]:
    """
    Bonus spells per day from ability score.

    Returns list indexed by spell level (0-9).
    Cantrips (0) never get bonus spells.
    Bonus spell of level N if modifier >= N.
    """
    result = [0] * 10  # levels 0-9
    for spell_lvl in range(1, 10):
        if ability_modifier >= spell_lvl:
            result[spell_lvl] = 1 + (ability_modifier - spell_lvl) // 4
    return result


def slots_per_day(
    class_name: str,
    class_level: int,
    ability_score: int,
) -> list[int | None]:
    """
    Total spell slots = base + bonus spells.

    Returns list indexed by spell level.
    None means unavailable at this level.
    """
    base = base_slots_per_day(class_name, class_level)
    if not base:
        return []
    mod = floor((ability_score - 10) / 2)
    bonuses = bonus_spells(mod)
    result: list[int | None] = []
    for i, b in enumerate(base):
        if b is None:
            result.append(None)
        elif i == 0:
            # Cantrips: no bonus spells
            result.append(b)
        elif i < len(bonuses):
            result.append(b + bonuses[i])
        else:
            result.append(b)
    return result


def spells_known(class_name: str, class_level: int) -> list[int | None]:
    """
    Spells known for spontaneous casters.

    Returns list indexed by spell level.
    None = unavailable. Empty list = N/A.
    """
    table = _KNOWN_TABLES.get(class_name)
    if table is None:
        return []
    max_lvl = max(table.keys())
    lvl = min(class_level, max_lvl)
    row = table.get(lvl)
    if row is None:
        return []
    return list(row)


def spell_save_dc(ability_modifier: int, spell_level: int) -> int:
    """Spell save DC = 10 + spell level + ability mod."""
    return 10 + spell_level + ability_modifier
