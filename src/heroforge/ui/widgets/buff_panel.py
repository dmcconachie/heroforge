"""
ui/widgets/buff_panel.py
------------------------
The Buffs panel.

Shows all registered buffs (spells, conditions, conditional feats) in a
scrollable list.  Each row has:
  [Checkbox] [Buff Name] [CL SpinBox] [Param SpinBox]

Activating a checkbox calls character.toggle_buff() and emits buffs_changed
so the sheet refreshes.

Buffs are grouped into sections: Active / Spells / Conditions / Feat Stances.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
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
    from heroforge.engine.character import Character
    from heroforge.engine.effects import (
        BuffDefinition,
        BuffRegistry,
    )


class _BuffRow(QWidget):
    """One row in the buff panel."""

    toggled = pyqtSignal(str, bool, int, int)  # name, active, cl, parameter

    def __init__(
        self,
        defn: BuffDefinition,
        character: Character,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._defn = defn
        self._character = character

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(6)

        self._check = QCheckBox()
        state = character.get_buff_state(defn.name)
        self._check.setChecked(state.active if state else False)

        name_lbl = QLabel(defn.name)
        name_lbl.setFixedWidth(180)
        name_lbl.setToolTip(defn.note)

        layout.addWidget(self._check)
        layout.addWidget(name_lbl)

        # CL spinner (only for CL-scaling buffs)
        self._cl_spin: QSpinBox | None = None
        if defn.requires_caster_level:
            cl_lbl = QLabel("CL:")
            cl_lbl.setStyleSheet("color: #666; font-size: 10px;")
            self._cl_spin = QSpinBox()
            self._cl_spin.setRange(1, 30)
            self._cl_spin.setFixedWidth(46)
            self._cl_spin.setValue((state.caster_level or 1) if state else 1)
            self._cl_spin.setToolTip("Caster level")
            layout.addWidget(cl_lbl)
            layout.addWidget(self._cl_spin)

        # Parameter spinner (only for parameterized feats like Power Attack)
        self._param_spin: QSpinBox | None = None
        # Check if this is a parameterized feat (buff was built from a feat)
        if self._has_parameter(defn.name, character):
            param_lbl = QLabel("Pts:")
            param_lbl.setStyleSheet("color: #666; font-size: 10px;")
            self._param_spin = QSpinBox()
            self._param_spin.setRange(1, 20)
            self._param_spin.setFixedWidth(46)
            current_param = (state.parameter or 1) if state else 1
            self._param_spin.setValue(current_param)
            self._param_spin.setToolTip(
                "Trade value (e.g. Power Attack points)"
            )
            layout.addWidget(param_lbl)
            layout.addWidget(self._param_spin)

        layout.addStretch()

        self._check.stateChanged.connect(self._on_toggle)

    def _has_parameter(self, buff_name: str, character: Character) -> bool:
        """Check if this buff came from a parameterized feat."""
        # The buff was registered with a note containing "param" or
        # we check the feat registry if available
        state = character.get_buff_state(buff_name)
        return state and state.parameter is not None

    def _on_toggle(self, state: int) -> None:
        active = state == Qt.CheckState.Checked.value
        cl = self._cl_spin.value() if self._cl_spin else 0
        param = self._param_spin.value() if self._param_spin else 0
        self.toggled.emit(self._defn.name, active, cl, param)

    def update_from_character(self, character: Character) -> None:
        """Refresh check state without triggering re-toggle."""
        state = character.get_buff_state(self._defn.name)
        if state:
            self._check.blockSignals(True)
            self._check.setChecked(state.active)
            self._check.blockSignals(False)
            if self._cl_spin and state.caster_level:
                self._cl_spin.blockSignals(True)
                self._cl_spin.setValue(state.caster_level)
                self._cl_spin.blockSignals(False)


class _SectionLabel(QLabel):
    """Section header in the buff list."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(f"  {text}", parent)
        f = self.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() - 1)
        self.setFont(f)
        self.setStyleSheet(
            "background: #e8eaf6; color: #333; padding: 3px 2px;"
            "border-top: 1px solid #c5cae9;"
        )
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )


class BuffPanel(QWidget):
    """
    Scrollable panel listing all buffs.

    buffs_changed is emitted after any toggle so the sheet can refresh stats.
    """

    buffs_changed = pyqtSignal()

    def __init__(
        self,
        buff_registry: BuffRegistry,
        character: Character,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = buff_registry
        self._character = character
        self._rows: dict[str, _BuffRow] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

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

    def _populate(self) -> None:
        """Build the buff list from the registry, grouped by category."""
        from heroforge.engine.effects import BuffCategory

        sections: dict[str, list[BuffDefinition]] = {
            "Spells": [],
            "Conditions": [],
            "Feat Stances": [],
            "Other": [],
        }

        for name in sorted(self._registry.all_names()):
            defn = self._registry.require(name)
            if defn.category == BuffCategory.CONDITION:
                sections["Conditions"].append(defn)
            elif defn.category == BuffCategory.FEAT:
                sections["Feat Stances"].append(defn)
            elif defn.category == BuffCategory.SPELL:
                sections["Spells"].append(defn)
            else:
                sections["Other"].append(defn)

        for section_name, defns in sections.items():
            if not defns:
                continue
            self._list_layout.addWidget(_SectionLabel(section_name))
            for defn in defns:
                row = _BuffRow(defn, self._character, self)
                row.toggled.connect(self._on_buff_toggled)
                self._rows[defn.name] = row
                self._list_layout.addWidget(row)

    def _on_buff_toggled(
        self, name: str, active: bool, cl: int, parameter: int
    ) -> None:
        """Handle a buff checkbox toggle."""
        char = self._character

        # Ensure buff is registered on character if not already
        if name not in char._buff_states:
            defn = self._registry.require(name)
            pairs = defn.pool_entries(cl or 0, char)
            char.register_buff_definition(name, pairs)

        # For parameterized feats, rebuild the entries with new parameter
        if parameter > 0:
            # If the buff came from a parameterized feat, rebuild entries
            # with the new parameter value before toggling
            defn = self._registry.get(name)
            if defn is not None and defn.requires_caster_level is False:
                # Try to find in feat registry via the parent app
                pass  # Full param rebuild handled by the feat system

        char.toggle_buff(
            name,
            active,
            caster_level=cl if cl > 0 else None,
            parameter=parameter if parameter > 0 else None,
        )
        self.buffs_changed.emit()

    def refresh(self, character: Character) -> None:
        """Update all row states from character."""
        self._character = character
        for _name, row in self._rows.items():
            row.update_from_character(character)
