"""
ui/widgets/combat_stats.py
--------------------------
Displays all combat-relevant derived stats in a compact grid:
  AC / Touch AC / Flat-footed AC
  Fort / Ref / Will
  BAB / Initiative / Speed
  HP Max / SR
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QGridLayout,
    QVBoxLayout,
    QWidget,
)

from heroforge.ui.widgets.common import HRule, SectionHeader, StatDisplay

if TYPE_CHECKING:
    from heroforge.engine.character import Character


class CombatStats(QWidget):
    """Read-only display of all combat derived stats."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(SectionHeader("Combat"))
        layout.addWidget(HRule())

        # AC row
        ac_row = QGridLayout()
        ac_row.setSpacing(4)
        self._ac = StatDisplay("AC", 10)
        self._touch_ac = StatDisplay("Touch", 10)
        self._ff_ac = StatDisplay("Flat-foot", 10)
        ac_row.addWidget(self._ac, 0, 0)
        ac_row.addWidget(self._touch_ac, 0, 1)
        ac_row.addWidget(self._ff_ac, 0, 2)
        layout.addLayout(ac_row)

        # Saves row
        save_row = QGridLayout()
        save_row.setSpacing(4)
        self._fort = StatDisplay("Fort", 0)
        self._ref = StatDisplay("Ref", 0)
        self._will = StatDisplay("Will", 0)
        save_row.addWidget(self._fort, 0, 0)
        save_row.addWidget(self._ref, 0, 1)
        save_row.addWidget(self._will, 0, 2)
        layout.addLayout(save_row)

        # Attack / Initiative / Speed row
        atk_row = QGridLayout()
        atk_row.setSpacing(4)
        self._bab = StatDisplay("BAB", 0)
        self._initiative = StatDisplay("Initiative", 0)
        self._speed = StatDisplay("Speed", 30, sub_label="ft")
        atk_row.addWidget(self._bab, 0, 0)
        atk_row.addWidget(self._initiative, 0, 1)
        atk_row.addWidget(self._speed, 0, 2)
        layout.addLayout(atk_row)

        # HP / SR row
        hp_row = QGridLayout()
        hp_row.setSpacing(4)
        self._hp_max = StatDisplay("HP Max", 0)
        self._sr = StatDisplay("SR", 0)
        hp_row.addWidget(self._hp_max, 0, 0)
        hp_row.addWidget(self._sr, 0, 1)
        layout.addLayout(hp_row)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Update helpers
    # ------------------------------------------------------------------

    def refresh(self, character: Character) -> None:
        """Pull all values from the character and update displays."""

        self._ac.set_value(character.ac)
        # Touch AC = AC minus armor, shield, natural armor
        # Flat-footed = AC minus DEX contribution and dodge
        # For now approximate both from the pool breakdown
        touch = _compute_touch(character)
        ff = _compute_flatfooted(character)
        self._touch_ac.set_value(touch)
        self._ff_ac.set_value(ff)

        self._fort.set_value(character.fort)
        self._ref.set_value(character.ref)
        self._will.set_value(character.will)

        self._bab.set_value(character.bab)
        self._initiative.set_value(character.get("initiative"))
        self._speed.set_value(character.get("speed"))

        self._hp_max.set_value(character.hp_max)
        self._sr.set_value(character.get("sr"))


def _compute_touch(character: Character) -> int:
    """
    Touch AC = 10 + DEX mod + dodge bonuses + deflection bonuses.
    Excludes armor, shield, natural armor.
    """
    from heroforge.engine.bonus import BonusType

    ac_pool = character.get_pool("ac")
    if ac_pool is None:
        return 10 + character.dex_mod

    touch = 10 + character.get("ac_dex_contribution")
    active = ac_pool.active_entries(character)
    touch_types = {
        BonusType.DODGE,
        BonusType.DEFLECTION,
        BonusType.UNTYPED,
        BonusType.LUCK,
        BonusType.INSIGHT,
        BonusType.SACRED,
        BonusType.PROFANE,
        BonusType.MORALE,
        BonusType.COMPETENCE,
    }
    # Sum stacking types; take max of non-stacking per type
    from collections import defaultdict

    stacking = 0
    typed: dict = defaultdict(list)
    for e in active:
        if e.bonus_type in touch_types:
            if e.bonus_type in (BonusType.DODGE, BonusType.UNTYPED):
                stacking += e.value
            else:
                typed[e.bonus_type].append(e.value)
    for vals in typed.values():
        stacking += max(vals)
    return touch + stacking


def _compute_flatfooted(character: Character) -> int:
    """
    Flat-footed AC = 10 + armor + shield + natural armor + size + misc.
    Excludes DEX contribution and dodge bonuses.
    """
    from heroforge.engine.bonus import BonusType

    ac_pool = character.get_pool("ac")
    if ac_pool is None:
        return 10

    flat = 10
    active = ac_pool.active_entries(character)
    excluded = {BonusType.DODGE}

    from collections import defaultdict

    stacking = 0
    typed: dict = defaultdict(list)
    for e in active:
        if e.bonus_type in excluded:
            continue
        if e.bonus_type == BonusType.UNTYPED:
            stacking += e.value
        else:
            typed[e.bonus_type].append(e.value)
    for vals in typed.values():
        if vals:
            stacking += max(vals)
    return flat + stacking
