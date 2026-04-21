"""
ui/sheets/sheet2_skills.py
--------------------------
Sheet 2: Skills.

Shows a scrollable table of all skills with columns:
  Class?  |  Skill Name  |  Key Ability  |  Ranks  |  Misc  |  Total

Rank spinboxes are live-editable. The Total column updates automatically
when ability scores or buffs change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from heroforge.engine.skills import compute_skill_total

if TYPE_CHECKING:
    from heroforge.engine.skills import SkillDefinition
    from heroforge.ui.app_state import AppState

_HEADERS = ["CS", "Skill", "Ability", "Ranks", "Misc", "Total"]
_COL_CS = 0
_COL_NAME = 1
_COL_ABILITY = 2
_COL_RANKS = 3
_COL_MISC = 4
_COL_TOTAL = 5


class Sheet2Skills(QWidget):
    """Skills tab — scrollable skills table."""

    def __init__(
        self, app_state: AppState, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._state = app_state
        self._building = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Column headers explanation
        legend = QLabel(
            "CS = Class Skill   |   "
            "Ranks = invested skill points   |   "
            "Misc = feats, magic items, synergies, etc."
        )
        legend.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(legend)

        # Table
        skills = app_state.skill_registry.all_skills()
        self._table = QTableWidget(len(skills), len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)

        # Column widths
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_CS, 28)
        self._table.setColumnWidth(_COL_NAME, 180)
        self._table.setColumnWidth(_COL_ABILITY, 52)
        self._table.setColumnWidth(_COL_RANKS, 58)
        self._table.setColumnWidth(_COL_MISC, 44)
        self._table.setColumnWidth(_COL_TOTAL, 44)

        # Row height
        self._table.verticalHeader().setDefaultSectionSize(22)

        # Populate rows
        self._skill_list = skills
        self._rank_spinboxes: list[QSpinBox] = []

        for row, skill_def in enumerate(skills):
            self._fill_row(row, skill_def)

        layout.addWidget(self._table, stretch=1)
        self._building = False

    def _fill_row(self, row: int, skill_def: SkillDefinition) -> None:
        c = self._state.character

        # CS marker
        cs_item = QTableWidgetItem()
        cs_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        is_cs = self._is_class_skill(skill_def.name)
        cs_item.setText("●" if is_cs else "")
        cs_item.setForeground(QColor("#1565C0") if is_cs else QColor("#999"))
        self._table.setItem(row, _COL_CS, cs_item)

        # Skill name
        name_item = QTableWidgetItem(skill_def.name)
        if skill_def.trained_only:
            name_item.setForeground(QColor("#555"))
            name_item.setFont(_italic_font())
        self._table.setItem(row, _COL_NAME, name_item)

        # Ability
        ab_str = skill_def.ability.upper() if skill_def.ability else "—"
        ab_item = QTableWidgetItem(ab_str)
        ab_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        ab_item.setForeground(QColor("#444"))
        self._table.setItem(row, _COL_ABILITY, ab_item)

        # Ranks spinbox — embedded in cell via setCellWidget
        spin = QSpinBox()
        spin.setRange(0, 40)
        spin.setValue(c.skills.get(skill_def.name, 0))
        spin.setFrame(False)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.valueChanged.connect(
            lambda val, sn=skill_def.name: self._on_rank_changed(sn, val)
        )
        self._table.setCellWidget(row, _COL_RANKS, spin)
        self._rank_spinboxes.append(spin)

        # Misc (read-only)
        misc_item = QTableWidgetItem("0")
        misc_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, _COL_MISC, misc_item)

        # Total (read-only)
        total = self._compute_total(skill_def)
        total_item = QTableWidgetItem(_signed_str(total))
        total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        total_item.setFont(_bold_font())
        if total > 0:
            total_item.setForeground(QColor("#1b5e20"))
        self._table.setItem(row, _COL_TOTAL, total_item)

    def _compute_total(self, skill_def: SkillDefinition) -> int:
        result = compute_skill_total(self._state.character, skill_def)
        return result.total

    def _is_class_skill(self, skill_name: str) -> bool:
        from heroforge.rules.rules import get_rules

        c = self._state.character
        class_reg = get_rules().classes
        for cn in c.class_level_map:
            defn = class_reg.get(cn)
            if defn and skill_name in defn.class_skills:
                return True
        return False

    def _on_rank_changed(self, skill_name: str, ranks: int) -> None:
        if self._building:
            return
        from heroforge.engine.skills import set_skill_ranks

        set_skill_ranks(self._state.character, skill_name, ranks)
        self.refresh_totals()

    def refresh(self) -> None:
        """Full refresh — update ranks and totals from character."""
        c = self._state.character
        for row, skill_def in enumerate(self._skill_list):
            # Update ranks spinbox
            spin_widget = self._table.cellWidget(row, _COL_RANKS)
            if isinstance(spin_widget, QSpinBox):
                spin_widget.blockSignals(True)
                spin_widget.setValue(c.skills.get(skill_def.name, 0))
                spin_widget.blockSignals(False)
            # Update CS marker
            cs_item = self._table.item(row, _COL_CS)
            if cs_item:
                is_cs = self._is_class_skill(skill_def.name)
                cs_item.setText("●" if is_cs else "")
            # Update total
            self._refresh_total_cell(row, skill_def)

    def refresh_totals(self) -> None:
        """Refresh only the Total and Misc columns (after buff change)."""
        for row, skill_def in enumerate(self._skill_list):
            self._refresh_total_cell(row, skill_def)

    def _refresh_total_cell(self, row: int, skill_def: SkillDefinition) -> None:
        result = compute_skill_total(self._state.character, skill_def)
        total_item = self._table.item(row, _COL_TOTAL)
        misc_item = self._table.item(row, _COL_MISC)
        if total_item:
            total_item.setText(_signed_str(result.total))
            if result.total > 0:
                total_item.setForeground(QColor("#1b5e20"))
            elif result.total < 0:
                total_item.setForeground(QColor("#b71c1c"))
            else:
                total_item.setForeground(QColor("#444"))
        if misc_item:
            misc = result.misc_bonus + result.synergy_bonus
            misc_item.setText(f"{misc:+}" if misc else "0")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _signed_str(v: int) -> str:
    return f"+{v}" if v > 0 else str(v)


def _bold_font() -> QFont:
    f = QFont()
    f.setBold(True)
    return f


def _italic_font() -> QFont:
    f = QFont()
    f.setItalic(True)
    return f
