"""
ui/sheets/sheet_equipment.py
----------------------------
Equipment management tab.  Displays a table of standard
equipment slots with editable Item Name and Notes columns.
Data is stored in character.equipment dict.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from heroforge.ui.app_state import AppState

EQUIPMENT_SLOTS: list[str] = [
    "Armor",
    "Shield",
    "Head",
    "Eyes",
    "Neck",
    "Shoulders",
    "Body",
    "Torso",
    "Arms",
    "Hands",
    "Ring 1",
    "Ring 2",
    "Waist",
    "Feet",
    "Weapon (Main)",
    "Weapon (Off-hand)",
]

_COL_SLOT = 0
_COL_NAME = 1
_COL_NOTES = 2


class SheetEquipment(QWidget):
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

        self._table = QTableWidget(len(EQUIPMENT_SLOTS), 3)
        self._table.setHorizontalHeaderLabels(["Slot", "Item Name", "Notes"])
        self._table.verticalHeader().setVisible(False)

        # Column sizing
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(
            _COL_SLOT,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            _COL_NAME,
            QHeaderView.ResizeMode.Stretch,
        )
        header.setSectionResizeMode(
            _COL_NOTES,
            QHeaderView.ResizeMode.Stretch,
        )

        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )

        # Populate slot column (read-only)
        for row, slot in enumerate(EQUIPMENT_SLOTS):
            item = QTableWidgetItem(slot)
            item.setFlags(item.flags() & ~item.flags().__class__.ItemIsEditable)
            self._table.setItem(row, _COL_SLOT, item)
            self._table.setItem(row, _COL_NAME, QTableWidgetItem(""))
            self._table.setItem(row, _COL_NOTES, QTableWidgetItem(""))

        self._table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self._table)

    # --------------------------------------------------------------
    # Sync UI -> model
    # --------------------------------------------------------------

    def _on_cell_changed(self, row: int, col: int) -> None:
        if self._building:
            return
        if col not in (_COL_NAME, _COL_NOTES):
            return

        slot = EQUIPMENT_SLOTS[row]
        equip = self._state.character.equipment
        entry = equip.setdefault(slot, {"name": "", "notes": ""})

        item = self._table.item(row, col)
        text = item.text() if item else ""

        if col == _COL_NAME:
            entry["name"] = text
        else:
            entry["notes"] = text

    # --------------------------------------------------------------
    # Refresh from model
    # --------------------------------------------------------------

    def refresh(
        self,
        changed_keys: set[str] | None = None,
    ) -> None:
        self._building = True
        equip = self._state.character.equipment
        for row, slot in enumerate(EQUIPMENT_SLOTS):
            entry = equip.get(slot, {})
            name = entry.get("name", "")
            notes = entry.get("notes", "")

            name_item = self._table.item(row, _COL_NAME)
            if name_item and name_item.text() != name:
                name_item.setText(name)

            notes_item = self._table.item(row, _COL_NOTES)
            if notes_item and notes_item.text() != notes:
                notes_item.setText(notes)
        self._building = False
