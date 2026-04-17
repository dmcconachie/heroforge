"""
ui/sheets/sheet_class.py
------------------------
Per-level class selection tab.  Shows a level progression
table and lets the user add/remove levels, pick classes,
set HP rolls, and allocate skill points per level.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from heroforge.ui.widgets.common import (
    AutoCloseCombo,
)

if TYPE_CHECKING:
    from heroforge.ui.app_state import AppState


class SheetClass(QWidget):
    def __init__(
        self,
        app_state: AppState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = app_state
        self._building = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        layout.addWidget(QLabel("<b>Class Levels</b>"))

        # Level progression table
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(
            ["Lvl", "Class", "HP Roll", "Skill Pts"]
        )
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 40)
        self._table.setColumnWidth(2, 70)
        self._table.setColumnWidth(3, 80)
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        # Add / Remove buttons
        btn_row = QHBoxLayout()
        self._class_combo = AutoCloseCombo()
        self._class_combo.setMinimumWidth(120)
        self._hp_spin = QSpinBox()
        self._hp_spin.setRange(1, 12)
        self._hp_spin.setValue(10)
        self._hp_spin.setPrefix("HP: ")
        add_btn = QPushButton("Add Level")
        add_btn.clicked.connect(self._on_add_level)
        remove_btn = QPushButton("Remove Last")
        remove_btn.clicked.connect(self._on_remove_level)
        btn_row.addWidget(self._class_combo)
        btn_row.addWidget(self._hp_spin)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Skill allocation group
        self._skill_group = QGroupBox("Skill Allocation (select a level)")
        skill_layout = QVBoxLayout(self._skill_group)
        self._skill_table = QTableWidget()
        self._skill_table.setColumnCount(4)
        self._skill_table.setHorizontalHeaderLabels(
            ["Skill", "Class?", "Pts", "Total"]
        )
        sh = self._skill_table.horizontalHeader()
        sh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        sh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        sh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        sh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._skill_table.setColumnWidth(1, 50)
        self._skill_table.setColumnWidth(2, 60)
        self._skill_table.setColumnWidth(3, 60)
        skill_layout.addWidget(self._skill_table)
        self._budget_label = QLabel("Budget: —")
        skill_layout.addWidget(self._budget_label)
        layout.addWidget(self._skill_group)

        self._table.currentCellChanged.connect(self._on_level_selected)

        self._populate_class_combo()
        self.refresh()

    def _populate_class_combo(self) -> None:
        self._class_combo.clear()
        reg = self._state.class_registry
        base = []
        prestige = []
        for name in sorted(reg.all_names()):
            defn = reg.get(name)
            if defn and defn.is_prestige:
                prestige.append(name)
            elif defn:
                base.append(name)
        for name in base:
            self._class_combo.addItem(name)
        if prestige:
            self._class_combo.insertSeparator(self._class_combo.count())
            chk = self._state.prereq_checker
            c = self._state.character
            for name in prestige:
                label = name
                if chk is not None:
                    from heroforge.engine.prerequisites import (
                        FeatAvailability,
                    )

                    avail, _ = chk.prc_availability(name, c)
                    if avail == FeatAvailability.UNAVAILABLE:
                        label = f"{name} (locked)"
                self._class_combo.addItem(label, userData=name)

    def _on_add_level(self) -> None:
        idx = self._class_combo.currentIndex()
        cn = self._class_combo.itemData(idx)
        if cn is None:
            cn = self._class_combo.currentText()
        if not cn:
            return
        # Enforce max_level for prestige classes
        reg = self._state.class_registry
        defn = reg.get(cn)
        if defn and defn.is_prestige:
            current = self._state.character.class_level_map.get(cn, 0)
            if current >= defn.max_level:
                return
        hp = self._hp_spin.value()
        if defn:
            self._hp_spin.setMaximum(defn.hit_die)
        self._state.character.add_level(cn, hp)
        self.refresh()

    def _on_remove_level(self) -> None:
        self._state.character.remove_last_level()
        self.refresh()

    def _on_level_selected(
        self,
        row: int,
        _col: int,
        _prev_row: int,
        _prev_col: int,
    ) -> None:
        self._refresh_skill_panel(row)

    def _refresh_skill_panel(self, row: int) -> None:
        c = self._state.character
        if row < 0 or row >= len(c.levels):
            self._skill_group.setTitle("Skill Allocation (select a level)")
            self._skill_table.setRowCount(0)
            self._budget_label.setText("Budget: —")
            return

        lv = c.levels[row]
        char_level = row + 1
        budget = c.skill_points_for_level(char_level)
        spent = sum(lv.skill_ranks.values())
        self._skill_group.setTitle(
            f"Skills — Level {char_level} ({lv.class_name})"
        )
        self._budget_label.setText(f"Budget: {spent} / {budget} spent")

        # Determine class skills
        class_skills: set[str] = set()
        reg = self._state.class_registry
        defn = reg.get(lv.class_name)
        if defn:
            class_skills = set(defn.class_skills)

        # Build skill rows
        skill_reg = self._state.skill_registry
        all_skills = sorted(
            skill_reg.all_skills(),
            key=lambda s: s.name,
        )
        self._skill_table.blockSignals(True)
        self._skill_table.setRowCount(len(all_skills))
        for i, sd in enumerate(all_skills):
            # Name
            name_item = QTableWidgetItem(sd.name)
            name_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            self._skill_table.setItem(i, 0, name_item)
            # Class skill?
            is_cs = sd.name in class_skills
            cs_item = QTableWidgetItem("Y" if is_cs else "")
            cs_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            cs_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._skill_table.setItem(i, 1, cs_item)
            # Points at this level
            pts = lv.skill_ranks.get(sd.name, 0)
            pts_item = QTableWidgetItem(str(pts))
            pts_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._skill_table.setItem(i, 2, pts_item)
            # Total ranks
            total = c.skills.get(sd.name, 0)
            tot_item = QTableWidgetItem(str(total))
            tot_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tot_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._skill_table.setItem(i, 3, tot_item)
        self._skill_table.blockSignals(False)

    def refresh(self) -> None:
        self._building = True
        c = self._state.character
        levels = c.levels
        self._table.setRowCount(len(levels))
        for i, lv in enumerate(levels):
            # Level number
            num = QTableWidgetItem(str(i + 1))
            num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, 0, num)
            # Class name
            self._table.setItem(i, 1, QTableWidgetItem(lv.class_name))
            # HP roll
            hp = QTableWidgetItem(str(lv.hp_roll))
            hp.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, 2, hp)
            # Skill points
            budget = c.skill_points_for_level(i + 1)
            spent = sum(lv.skill_ranks.values())
            sp = QTableWidgetItem(f"{spent}/{budget}")
            sp.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, 3, sp)

        # Update hit die max based on combo
        cn = self._class_combo.currentText()
        if cn:
            reg = self._state.class_registry
            defn = reg.get(cn)
            if defn:
                self._hp_spin.setMaximum(defn.hit_die)

        self._building = False
