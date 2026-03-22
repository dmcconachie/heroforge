"""
ui/dialogs/class_dialog.py
--------------------------
Dialog to set class levels from a list of known classes.
Supports multiclassing: add multiple class entries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

    from heroforge.ui.app_state import AppState


class ClassDialog(QDialog):
    def __init__(
        self,
        app_state: AppState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = app_state
        self._entries: list[tuple[str, int]] = []

        self.setWindowTitle("Set Class Levels")
        self.resize(460, 360)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Current class list
        current_box = QGroupBox("Current Classes")
        cb_layout = QVBoxLayout(current_box)
        self._class_list = QListWidget()
        cb_layout.addWidget(self._class_list)
        rm_btn = QPushButton("Remove Selected")
        rm_btn.clicked.connect(self._remove_selected)
        cb_layout.addWidget(rm_btn)
        layout.addWidget(current_box)

        # Add class row
        add_box = QGroupBox("Add / Update Class")
        ab_layout = QHBoxLayout(add_box)

        self._class_combo = QComboBox()
        for name in sorted(app_state.class_registry.all_names()):
            self._class_combo.addItem(name)
        ab_layout.addWidget(QLabel("Class:"))
        ab_layout.addWidget(self._class_combo, stretch=1)

        self._level_spin = QSpinBox()
        self._level_spin.setRange(1, 20)
        self._level_spin.setValue(1)
        ab_layout.addWidget(QLabel("Level:"))
        ab_layout.addWidget(self._level_spin)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_class)
        ab_layout.addWidget(add_btn)
        layout.addWidget(add_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Populate from current character
        for cl in app_state.character.class_levels:
            self._entries.append((cl.class_name, cl.level))
            self._class_list.addItem(f"{cl.class_name} {cl.level}")

    def _add_class(self) -> None:
        name = self._class_combo.currentText()
        level = self._level_spin.value()
        # Update or add
        for i, (cn, _) in enumerate(self._entries):
            if cn == name:
                self._entries[i] = (name, level)
                self._class_list.item(i).setText(f"{name} {level}")
                return
        self._entries.append((name, level))
        self._class_list.addItem(f"{name} {level}")

    def _remove_selected(self) -> None:
        row = self._class_list.currentRow()
        if row >= 0:
            self._class_list.takeItem(row)
            self._entries.pop(row)

    def _on_accept(self) -> None:
        if not self._entries:
            self.reject()
            return
        class_reg = self._state.class_registry
        class_levels = []
        for class_name, level in self._entries:
            defn = class_reg.get(class_name)
            if defn:
                cl = defn.make_class_level(level)
            else:
                # Unknown class — build a default ClassLevel
                from heroforge.engine.character import ClassLevel

                cl = ClassLevel(
                    class_name=class_name,
                    level=level,
                    hp_rolls=[8] * level,
                    bab_contribution=level,
                    fort_contribution=2 + level // 2,
                    ref_contribution=level // 3,
                    will_contribution=level // 3,
                )
            class_levels.append(cl)
        self._state.character.set_class_levels(class_levels)
        self.accept()
