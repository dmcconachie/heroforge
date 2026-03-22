"""
ui/sheets/sheet_notes.py
------------------------
Free-form notes tab bound to character.notes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from heroforge.ui.app_state import AppState


class SheetNotes(QWidget):
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

        self._edit = QTextEdit()
        self._edit.setPlaceholderText("Character notes...")
        self._edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._edit)

    def _on_text_changed(self) -> None:
        if self._building:
            return
        self._state.character.notes = self._edit.toPlainText()

    def refresh(
        self,
        changed_keys: set[str] | None = None,
    ) -> None:
        self._building = True
        text = self._state.character.notes
        if self._edit.toPlainText() != text:
            self._edit.setPlainText(text)
        self._building = False
