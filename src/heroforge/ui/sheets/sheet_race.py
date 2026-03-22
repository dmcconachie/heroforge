"""
ui/sheets/sheet_race.py
-----------------------
Race selection tab.  Two-pane layout: race list (left,
searchable) + detail panel (right).  Selecting a race
immediately applies it to the character.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from heroforge.ui.app_state import AppState


class SheetRace(QWidget):
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

        layout.addWidget(QLabel("<b>Select Race</b>"))

        # Filter bar
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter races...")
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)

        row = QHBoxLayout()

        # Race list
        self._list = QListWidget()
        self._all_names = sorted(app_state.race_registry.all_names())
        self._list.addItems(self._all_names)
        self._list.currentTextChanged.connect(self._on_race_selected)
        row.addWidget(self._list, stretch=1)

        # Detail panel
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMaximumWidth(280)
        row.addWidget(self._detail, stretch=1)

        layout.addLayout(row)

        # Pre-select current race
        self._select_current()

    def _select_current(self) -> None:
        current = self._state.character.race
        if current:
            items = self._list.findItems(current, Qt.MatchFlag.MatchExactly)
            if items:
                self._building = True
                self._list.setCurrentItem(items[0])
                self._building = False
                self._show_detail(current)

    def _apply_filter(self, text: str) -> None:
        self._list.clear()
        needle = text.lower()
        for name in self._all_names:
            if needle in name.lower():
                self._list.addItem(name)

    def _on_race_selected(self, name: str) -> None:
        self._show_detail(name)
        if self._building or not name:
            return
        defn = self._state.race_registry.get(name)
        if defn is None:
            return
        from heroforge.engine.classes_races import (
            apply_race,
            remove_race,
        )

        c = self._state.character
        old = c.race
        if old == name:
            return
        if old:
            old_defn = self._state.race_registry.get(old)
            if old_defn:
                remove_race(old_defn, c)
        apply_race(defn, c)

    def _show_detail(self, name: str) -> None:
        defn = self._state.race_registry.get(name)
        if defn is None:
            self._detail.clear()
            return
        lines = [
            f"<b>{defn.name}</b>",
            f"Source: {defn.source_book}",
            f"Size: {defn.size}  |  Speed: {defn.base_speed} ft",
            "",
        ]
        if defn.ability_modifiers:
            mods = ", ".join(
                f"{'+' if m.value > 0 else ''}{m.value} {m.ability.upper()}"
                for m in defn.ability_modifiers
            )
            lines.append(f"<b>Ability Mods:</b> {mods}")
        if defn.darkvision:
            lines.append(f"Darkvision {defn.darkvision} ft")
        if defn.low_light_vision:
            lines.append("Low-light vision")
        if defn.weapon_familiarity:
            wf = ", ".join(defn.weapon_familiarity)
            lines.append(f"Weapon familiarity: {wf}")
        lines.append("")
        lines.append("<b>Racial Traits:</b>")
        for trait in defn.racial_traits[:6]:
            lines.append(f"  {trait}")
        self._detail.setHtml("<br>".join(lines))

    def refresh(
        self,
        changed_keys: set[str] | None = None,
    ) -> None:
        self._select_current()
