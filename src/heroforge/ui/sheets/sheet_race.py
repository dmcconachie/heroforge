"""
ui/sheets/sheet_race.py
-----------------------
Race and template selection tab.

Top half: race list + detail panel.
Bottom half: applied templates list + template picker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QSplitter,
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

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Top: Race selection ─────────────
        race_widget = QWidget()
        race_layout = QVBoxLayout(race_widget)
        race_layout.setContentsMargins(0, 0, 0, 0)
        race_layout.addWidget(QLabel("<b>Race</b>"))

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter races...")
        self._filter.textChanged.connect(self._apply_filter)
        race_layout.addWidget(self._filter)

        row = QHBoxLayout()
        self._list = QListWidget()
        self._all_names = sorted(app_state.race_registry.all_names())
        self._list.addItems(self._all_names)
        self._list.currentTextChanged.connect(self._on_race_selected)
        row.addWidget(self._list, stretch=1)

        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMaximumWidth(280)
        row.addWidget(self._detail, stretch=1)
        race_layout.addLayout(row)
        splitter.addWidget(race_widget)

        # ── Bottom: Templates ───────────────
        tpl_widget = QWidget()
        tpl_layout = QVBoxLayout(tpl_widget)
        tpl_layout.setContentsMargins(0, 0, 0, 0)
        tpl_layout.addWidget(QLabel("<b>Templates</b>"))

        # Active templates summary
        self._active_tpl_label = QLabel("")
        self._active_tpl_label.setWordWrap(True)
        self._active_tpl_label.setStyleSheet("color: #1565c0; padding: 2px 0;")
        tpl_layout.addWidget(self._active_tpl_label)

        # Filter
        self._tpl_filter = QLineEdit()
        self._tpl_filter.setPlaceholderText("Filter templates...")
        self._tpl_filter.textChanged.connect(self._apply_tpl_filter)
        tpl_layout.addWidget(self._tpl_filter)

        tpl_row = QHBoxLayout()

        # Template list (left)
        self._tpl_list = QListWidget()
        self._all_tpl_names = sorted(app_state.template_registry.all_names())
        self._tpl_list.addItems(self._all_tpl_names)
        self._tpl_list.currentTextChanged.connect(self._on_tpl_list_selected)
        tpl_row.addWidget(self._tpl_list, stretch=1)

        # Template detail + controls (right)
        right_col = QVBoxLayout()
        self._tpl_detail = QTextEdit()
        self._tpl_detail.setReadOnly(True)
        self._tpl_detail.setMaximumWidth(280)
        right_col.addWidget(self._tpl_detail)

        # Applied indicator
        self._tpl_applied = QLabel("")
        self._tpl_applied.setStyleSheet("color: #1b5e20; font-weight: bold;")
        right_col.addWidget(self._tpl_applied)

        # Level spin for partial templates
        level_row = QHBoxLayout()
        self._tpl_level_label = QLabel("Level:")
        level_row.addWidget(self._tpl_level_label)
        self._tpl_level_spin = QSpinBox()
        self._tpl_level_spin.setRange(1, 10)
        self._tpl_level_spin.setFixedWidth(50)
        level_row.addWidget(self._tpl_level_spin)
        level_row.addStretch()
        right_col.addLayout(level_row)

        # Apply / Remove buttons
        btn_row = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._on_add_template)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._on_remove_template)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        right_col.addLayout(btn_row)

        tpl_row.addLayout(right_col, stretch=1)
        tpl_layout.addLayout(tpl_row)

        splitter.addWidget(tpl_widget)
        layout.addWidget(splitter)

        self._select_current()
        self._refresh_active_label()
        self._on_tpl_list_selected("")

    # ── Race selection ──────────────────────

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

    # ── Template management ─────────────────

    def _apply_tpl_filter(self, text: str) -> None:
        self._tpl_list.clear()
        needle = text.lower()
        for name in self._all_tpl_names:
            if needle in name.lower():
                self._tpl_list.addItem(name)

    def _on_tpl_list_selected(self, name: str) -> None:
        if not name:
            self._tpl_detail.clear()
            self._tpl_applied.setText("")
            self._tpl_level_label.hide()
            self._tpl_level_spin.hide()
            return

        defn = self._state.template_registry.get(name)
        if defn is None:
            self._tpl_detail.clear()
            return

        # Show/hide level spin
        if defn.partially_applicable and defn.max_level > 0:
            self._tpl_level_label.show()
            self._tpl_level_spin.show()
            self._tpl_level_spin.setRange(1, defn.max_level)
            # Pre-fill current level if applied
            app = self._find_applied(name)
            if app and app.level > 0:
                self._tpl_level_spin.setValue(app.level)
            else:
                self._tpl_level_spin.setValue(defn.max_level)
        else:
            self._tpl_level_label.hide()
            self._tpl_level_spin.hide()

        # Applied indicator
        app = self._find_applied(name)
        if app:
            lbl = "Applied"
            if app.level > 0:
                lbl += f" (level {app.level})"
            self._tpl_applied.setText(lbl)
        else:
            self._tpl_applied.setText("")

        # Detail
        lines = [
            f"<b>{defn.name}</b>",
            f"Source: {defn.source_book}  |  "
            f"CR: {defn.cr_adjustment}  |  "
            f"LA: {defn.la_adjustment}",
        ]
        if defn.ability_modifiers:
            mods = ", ".join(
                f"{'+' if m.value > 0 else ''}{m.value} {m.ability.upper()}"
                for m in defn.ability_modifiers
            )
            lines.append(f"<b>Ability Mods:</b> {mods}")
        if defn.natural_armor_bonus:
            lines.append(f"Natural Armor: +{defn.natural_armor_bonus}")
        if defn.type_change:
            lines.append(f"Type: {defn.type_change}")
        if defn.grants_feats:
            lines.append("Feats: " + ", ".join(defn.grants_feats))
        if defn.special_qualities:
            lines.append("")
            lines.append("<b>Special:</b>")
            for sq in defn.special_qualities[:6]:
                lines.append(f"  {sq}")
        if defn.partially_applicable:
            lines.append(f"<i>Partial (max level {defn.max_level})</i>")
        self._tpl_detail.setHtml("<br>".join(lines))

    def _find_applied(self, name: str) -> object | None:
        for app in self._state.character.templates:
            if app.template_name == name:
                return app
        return None

    def _on_add_template(self) -> None:
        item = self._tpl_list.currentItem()
        if item is None:
            return
        name = item.text()
        defn = self._state.template_registry.get(name)
        if defn is None:
            return

        from heroforge.engine.templates import (
            apply_template,
        )

        level = 0
        if defn.partially_applicable and defn.max_level > 0:
            level = self._tpl_level_spin.value()

        apply_template(defn, self._state.character, level=level)
        self._refresh_active_label()
        self._on_tpl_list_selected(name)

    def _on_remove_template(self) -> None:
        item = self._tpl_list.currentItem()
        if item is None:
            return
        name = item.text()
        defn = self._state.template_registry.get(name)
        if defn is None:
            return

        from heroforge.engine.templates import (
            remove_template,
        )

        remove_template(defn, self._state.character)
        self._refresh_active_label()
        self._on_tpl_list_selected(name)

    # ── Refresh ─────────────────────────────

    def _refresh_active_label(self) -> None:
        apps = self._state.character.templates
        if not apps:
            self._active_tpl_label.setText("None applied")
            return
        parts = []
        for app in apps:
            lbl = app.template_name
            if app.level > 0:
                lbl += f" (lvl {app.level})"
            parts.append(lbl)
        self._active_tpl_label.setText("Active: " + ", ".join(parts))

    def refresh(
        self,
        changed_keys: set[str] | None = None,
    ) -> None:
        self._select_current()
        self._refresh_active_label()
        item = self._tpl_list.currentItem()
        name = item.text() if item else ""
        self._on_tpl_list_selected(name)
