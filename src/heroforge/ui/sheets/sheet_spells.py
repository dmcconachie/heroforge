"""
ui/sheets/sheet_spells.py
--------------------------
Spells tab — lists all SPELL-category buffs from the spell
registry as a scrollable checklist.  Each row has a toggle
checkbox and an optional caster-level spinbox.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from heroforge.engine.effects import BuffDefinition
    from heroforge.ui.app_state import AppState


# ---------------------------------------------------------------
# Row widget
# ---------------------------------------------------------------


class _SpellRow(QWidget):
    """One spell row: [checkbox] [name] [CL spinbox?]."""

    def __init__(
        self,
        defn: BuffDefinition,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.defn = defn

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(6)

        self.check = QCheckBox()
        name_lbl = QLabel(defn.name)
        name_lbl.setFixedWidth(200)
        if defn.note:
            name_lbl.setToolTip(defn.note)

        lay.addWidget(self.check)
        lay.addWidget(name_lbl)

        self.cl_spin: QSpinBox | None = None
        if defn.requires_caster_level:
            cl_lbl = QLabel("CL:")
            cl_lbl.setStyleSheet("color: #666; font-size: 10px;")
            self.cl_spin = QSpinBox()
            self.cl_spin.setRange(1, 30)
            self.cl_spin.setValue(1)
            self.cl_spin.setFixedWidth(46)
            self.cl_spin.setToolTip("Caster level")
            lay.addWidget(cl_lbl)
            lay.addWidget(self.cl_spin)

        lay.addStretch()


# ---------------------------------------------------------------
# Section header
# ---------------------------------------------------------------


class _SectionLabel(QLabel):
    """Bold section header inside the scroll list."""

    def __init__(
        self,
        text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"  {text}", parent)
        f = self.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() - 1)
        self.setFont(f)
        self.setStyleSheet(
            "background: #e8eaf6; color: #333;"
            "padding: 3px 2px;"
            "border-top: 1px solid #c5cae9;"
        )
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )


# ---------------------------------------------------------------
# SheetSpells
# ---------------------------------------------------------------


class SheetSpells(QWidget):
    """
    Spells tab.

    Displays all SPELL-category BuffDefinitions from the
    buff_registry as a scrollable checklist with toggle
    checkboxes and optional caster-level spinboxes.
    """

    def __init__(
        self,
        app_state: AppState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = app_state
        self._building = False
        self._rows: dict[str, _SpellRow] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(0)

        # Header
        hdr = QLabel("Spells")
        f = hdr.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 2)
        hdr.setFont(f)
        outer.addWidget(hdr)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        self._list_layout = QVBoxLayout(container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)

        self._populate()
        self._list_layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

    # -----------------------------------------------------------
    # Build rows
    # -----------------------------------------------------------

    def _populate(self) -> None:
        """Build spell rows grouped by source book."""
        from heroforge.engine.effects import BuffCategory

        spells = self._state.buff_registry.by_category(BuffCategory.SPELL)
        spells.sort(key=lambda d: d.name)

        # Group by source book
        groups: dict[str, list[BuffDefinition]] = {}
        for defn in spells:
            groups.setdefault(defn.source_book, []).append(defn)

        for book in sorted(groups):
            self._list_layout.addWidget(_SectionLabel(book))
            for defn in groups[book]:
                row = _SpellRow(defn, self)
                row.check.stateChanged.connect(self._make_toggle_handler(row))
                if row.cl_spin is not None:
                    row.cl_spin.valueChanged.connect(self._make_cl_handler(row))
                self._rows[defn.name] = row
                self._list_layout.addWidget(row)

    # -----------------------------------------------------------
    # Signal handlers (closures)
    # -----------------------------------------------------------

    def _make_toggle_handler(self, row: _SpellRow) -> Callable[[int], None]:
        """Return a slot bound to *row*."""

        def _handler(_state: int) -> None:
            if self._building:
                return
            self._toggle_spell(row)

        return _handler

    def _make_cl_handler(self, row: _SpellRow) -> Callable[[int], None]:
        """Return a slot for CL changes on *row*."""

        def _handler(_value: int) -> None:
            if self._building:
                return
            # Re-apply if already active
            state = self._state.character.get_buff_state(row.defn.name)
            if state and state.active:
                self._toggle_spell(row, force_active=True)

        return _handler

    # -----------------------------------------------------------
    # Buff toggling
    # -----------------------------------------------------------

    def _toggle_spell(
        self,
        row: _SpellRow,
        *,
        force_active: bool = False,
    ) -> None:
        """Toggle a spell buff on or off."""
        char = self._state.character
        defn = row.defn
        active = force_active or row.check.isChecked()
        cl = row.cl_spin.value() if row.cl_spin else 0

        # Register if not yet known
        if defn.name not in char._buff_states:
            pairs = defn.pool_entries(cl, char)
            char.register_buff_definition(defn.name, pairs)

        # If CL changed, update registered entries
        if active and cl:
            pairs = defn.pool_entries(cl, char)
            char._buff_entries[defn.name] = pairs

        char.toggle_buff(
            defn.name,
            active,
            caster_level=cl if cl > 0 else None,
        )

    # -----------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------

    def refresh(
        self,
        changed_keys: set[str] | None = None,
    ) -> None:
        """Sync checkbox/CL state from the character."""
        self._building = True
        try:
            char = self._state.character
            for name, row in self._rows.items():
                state = char.get_buff_state(name)
                row.check.blockSignals(True)
                row.check.setChecked(state.active if state else False)
                row.check.blockSignals(False)
                if row.cl_spin and state and state.caster_level:
                    row.cl_spin.blockSignals(True)
                    row.cl_spin.setValue(state.caster_level)
                    row.cl_spin.blockSignals(False)
        finally:
            self._building = False
