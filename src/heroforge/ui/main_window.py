"""
heroforge/ui/main_window.py
---------------------------
The main application window.

Tabs:
  1. Summary  — abilities, combat stats, identity, buffs
  2. Skills   — full skill table
  3. Feats    — taken feats, feat picker
  4. Spells   — spell buff toggles
  5. Equipment — equipment slots table

The MainWindow owns an AppState and passes it to each sheet.  When the
character's ChangeNotifier fires, MainWindow routes the changed keys to
the relevant tabs for partial refreshes.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from heroforge.ui.app_state import AppState
from heroforge.ui.sheets.sheet1_summary import Sheet1Summary
from heroforge.ui.sheets.sheet2_skills import Sheet2Skills
from heroforge.ui.sheets.sheet3_feats import Sheet3Feats
from heroforge.ui.sheets.sheet_class import SheetClass
from heroforge.ui.sheets.sheet_equipment import SheetEquipment
from heroforge.ui.sheets.sheet_notes import SheetNotes
from heroforge.ui.sheets.sheet_race import SheetRace
from heroforge.ui.sheets.sheet_spells import SheetSpells

if TYPE_CHECKING:
    from PyQt6.QtGui import QCloseEvent


class MainWindow(QMainWindow):
    """
    The top-level window.

    Lifecycle:
      1. __init__ creates the AppState and loads rules.
      2. _build_ui() creates all tabs.
      3. Character change notifications are wired to _on_stats_changed().
    """

    def __init__(self) -> None:
        super().__init__()
        self._current_path: Path | None = None
        self._modified = False

        self._state = AppState()
        self._state.load_rules()
        self._state.new_character()

        self._build_menu()
        self._build_ui()
        self._wire_notifications()
        self._update_title()

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready", 3000)

    # ------------------------------------------------------------------
    # Title bar
    # ------------------------------------------------------------------

    def _update_title(self) -> None:
        name = self._state.character.name or "Unnamed"
        path_part = (
            f" — {self._current_path.name}" if self._current_path else ""
        )
        mod_part = " *" if self._modified else ""
        self.setWindowTitle(f"HeroForge Anew — {name}{path_part}{mod_part}")

    def _mark_modified(self) -> None:
        if not self._modified:
            self._modified = True
            self._update_title()

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        # ── File ────────────────────────────────────────────────────────
        file_menu = menubar.addMenu("&File")

        new_action = QAction("&New Character", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self._on_new_character)
        file_menu.addAction(new_action)

        file_menu.addSeparator()

        open_action = QAction("&Open…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As…", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_action)

        export_action = QAction("Export &PDF…", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self._on_export_pdf)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        self._tabs.setDocumentMode(True)

        # Tab 0
        self._sheet1 = Sheet1Summary(self._state)
        self._tabs.addTab(self._sheet1, "Summary")
        # Tab 1
        self._race_tab = SheetRace(self._state)
        self._tabs.addTab(self._race_tab, "Race")
        # Tab 2
        self._class_tab = SheetClass(self._state)
        self._tabs.addTab(self._class_tab, "Class")
        # Tab 3
        self._sheet2 = Sheet2Skills(self._state)
        self._tabs.addTab(self._sheet2, "Skills")
        # Tab 4
        self._sheet3 = Sheet3Feats(self._state)
        self._tabs.addTab(self._sheet3, "Feats")
        # Tab 5
        self._spells_tab = SheetSpells(self._state)
        self._tabs.addTab(self._spells_tab, "Spells")
        # Tab 6
        self._equipment_tab = SheetEquipment(self._state)
        self._tabs.addTab(self._equipment_tab, "Equipment")
        # Tab 7
        self._notes_tab = SheetNotes(self._state)
        self._tabs.addTab(self._notes_tab, "Notes")

        layout.addWidget(self._tabs)
        self._tabs.currentChanged.connect(self._on_tab_changed)

    # ------------------------------------------------------------------
    # Change notifications
    # ------------------------------------------------------------------

    def _wire_notifications(self) -> None:
        self._state.character.on_change.subscribe(self._on_stats_changed)

    def _on_stats_changed(self, changed_keys: set[str]) -> None:
        self._mark_modified()
        if "identity:name" in changed_keys:
            self._update_title()
        current = self._tabs.currentIndex()
        if current == 0:
            self._sheet1.refresh()
        elif current == 1:
            self._race_tab.refresh(changed_keys)
        elif current == 2:
            self._class_tab.refresh(changed_keys)
        elif current == 3:
            ability_keys = {
                k
                for k in changed_keys
                if k.endswith("_mod") or k.endswith("_score")
            }
            if ability_keys or any(
                k.startswith("skill_") for k in changed_keys
            ):
                self._sheet2.refresh_totals()
        elif current == 4:
            self._sheet3.refresh()

    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------

    def _on_tab_changed(self, index: int) -> None:
        if index == 0:
            self._sheet1.refresh()
        elif index == 1:
            self._race_tab.refresh()
        elif index == 2:
            self._class_tab.refresh()
        elif index == 3:
            self._sheet2.refresh()
        elif index == 4:
            self._sheet3.refresh()
        elif index == 5:
            self._spells_tab.refresh()
        elif index == 6:
            self._equipment_tab.refresh()
        elif index == 7:
            self._notes_tab.refresh()

    # ------------------------------------------------------------------
    # File menu handlers
    # ------------------------------------------------------------------

    def _on_new_character(self) -> None:
        if self._modified and not self._confirm_discard():
            return
        self._unwire()
        self._state.new_character()
        self._current_path = None
        self._modified = False
        self._wire_notifications()
        self._rebuild_sheets()
        self._update_title()
        self._status.showMessage("New character created", 3000)

    def _on_open(self) -> None:
        if self._modified and not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Character",
            "",
            "Character Files (*.char.yaml);;All Files (*)",
        )
        if not path:
            return
        try:
            from heroforge.engine.persistence import load_character

            loaded = load_character(Path(path), self._state)
            self._unwire()
            self._state.set_character(loaded)
            self._current_path = Path(path)
            self._modified = False
            self._wire_notifications()
            self._rebuild_sheets()
            self._update_title()
            self._status.showMessage(f"Opened {Path(path).name}", 3000)
        except Exception as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))

    def _on_save(self) -> None:
        if self._current_path:
            self._do_save(self._current_path)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        default = (
            self._current_path.name
            if self._current_path
            else f"{self._state.character.name or 'character'}.char.yaml"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Character As",
            default,
            "Character Files (*.char.yaml);;All Files (*)",
        )
        if path:
            if not path.endswith(".char.yaml"):
                path += ".char.yaml"
            self._do_save(Path(path))

    def _do_save(self, path: Path) -> None:
        try:
            from heroforge.engine.persistence import save_character

            save_character(self._state.character, path)
            self._current_path = path
            self._modified = False
            self._update_title()
            self._status.showMessage(f"Saved to {path.name}", 3000)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))

    # ------------------------------------------------------------------
    # Close guard
    # ------------------------------------------------------------------

    def _on_export_pdf(self) -> None:
        default = (
            self._current_path.stem
            if self._current_path
            else (self._state.character.name or "character")
        )
        default += ".pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF", default, "PDF Files (*.pdf);;All Files (*)"
        )
        if not path:
            return
        if not path.endswith(".pdf"):
            path += ".pdf"
        try:
            from heroforge.export.renderer import render_pdf
            from heroforge.export.sheet_data import gather

            sheet_data = gather(self._state.character, self._state)
            render_pdf(sheet_data, path)
            self._status.showMessage(f"PDF exported to {Path(path).name}", 4000)
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._modified and not self._confirm_discard():
            event.ignore()
        else:
            event.accept()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _confirm_discard(self) -> bool:
        result = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard them?",
            QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        return result == QMessageBox.StandardButton.Discard

    def _unwire(self) -> None:
        with contextlib.suppress(Exception):
            self._state.character.on_change.unsubscribe(self._on_stats_changed)

    def _rebuild_sheets(self) -> None:
        """Refresh all sheet tabs after character change."""
        self._sheet1._buff_panel.refresh(self._state.character)
        self._sheet1.refresh()
        self._race_tab.refresh()
        self._class_tab.refresh()
        self._sheet2.refresh()
        self._sheet3.refresh()
        self._spells_tab.refresh()
        self._equipment_tab.refresh()
        self._notes_tab.refresh()
