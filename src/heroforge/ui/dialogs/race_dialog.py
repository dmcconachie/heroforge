"""
ui/dialogs/race_dialog.py
-------------------------
Simple dialog to pick a race and apply it to the character.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QTextEdit,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

    from heroforge.ui.app_state import AppState


class RaceDialog(QDialog):
    def __init__(
        self,
        app_state: AppState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = app_state
        self.setWindowTitle("Choose Race")
        self.resize(500, 380)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Select a race:"))

        row = QHBoxLayout()

        # Race list
        self._list = QListWidget()
        for name in sorted(app_state.race_registry.all_names()):
            self._list.addItem(name)
        # Pre-select current race
        current = app_state.character.race
        if current:
            items = self._list.findItems(current, Qt.MatchFlag.MatchExactly)
            if items:
                self._list.setCurrentItem(items[0])
        self._list.currentTextChanged.connect(self._on_race_selected)
        row.addWidget(self._list, stretch=1)

        # Detail panel
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMaximumWidth(240)
        row.addWidget(self._detail, stretch=1)

        layout.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Show initial detail if race already selected
        if current:
            self._on_race_selected(current)

    def _on_race_selected(self, name: str) -> None:
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
            lines.append(
                f"Weapon familiarity: {', '.join(defn.weapon_familiarity)}"
            )
        lines.append("")
        lines.append("<b>Racial Traits:</b>")
        for trait in defn.racial_traits[:6]:  # show first 6
            lines.append(f"• {trait}")
        self._detail.setHtml("<br>".join(lines))

    def _on_accept(self) -> None:
        item = self._list.currentItem()
        if item is None:
            self.reject()
            return
        name = item.text()
        defn = self._state.race_registry.get(name)
        if defn is None:
            self.reject()
            return
        from heroforge.engine.classes_races import apply_race, remove_race

        # Remove old race first
        old_race = self._state.character.race
        if old_race:
            old_defn = self._state.race_registry.get(old_race)
            if old_defn:
                remove_race(old_defn, self._state.character)
        apply_race(defn, self._state.character)
        self.accept()
