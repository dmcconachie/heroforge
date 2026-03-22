"""
ui/widgets/ability_block.py
---------------------------
The six ability score rows (STR/DEX/CON/INT/WIS/CHA).

Each row shows:
  [Ability Name]  [Score SpinBox]  [Modifier Label]

When a score changes the widget emits ability_changed(ability, new_score)
and the main sheet re-reads all derived stats.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from heroforge.ui.widgets.common import (
    CompactSpinBox,
    ModifierLabel,
    SectionHeader,
)

_ABILITIES = [
    ("STR", "str"),
    ("DEX", "dex"),
    ("CON", "con"),
    ("INT", "int"),
    ("WIS", "wis"),
    ("CHA", "cha"),
]


class AbilityBlock(QWidget):
    """
    Shows all six ability scores and their modifiers.
    Emits ability_changed(ability_abbrev: str, new_score: int) when edited.
    """

    ability_changed = pyqtSignal(str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(SectionHeader("Ability Scores"))

        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 0)

        # Header row
        for col, text in enumerate(("", "Score", "Mod")):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #666; font-size: 10px;")
            grid.addWidget(lbl, 0, col)

        self._spinboxes: dict[str, CompactSpinBox] = {}
        self._mod_labels: dict[str, ModifierLabel] = {}

        for row, (label, ability) in enumerate(_ABILITIES, start=1):
            name_lbl = QLabel(label)
            name_lbl.setFixedWidth(32)
            name_lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            name_lbl.setStyleSheet("font-weight: bold;")

            spin = CompactSpinBox(value=10)
            spin.setToolTip(
                f"Base {label} score (before racial/template modifiers)"
            )
            mod = ModifierLabel(0)
            mod.setFixedWidth(36)

            # Wire change signal
            spin.valueChanged.connect(
                lambda val, ab=ability: self._on_score_changed(ab, val)
            )

            self._spinboxes[ability] = spin
            self._mod_labels[ability] = mod

            grid.addWidget(name_lbl, row, 0)
            grid.addWidget(spin, row, 1)
            grid.addWidget(mod, row, 2)

        layout.addLayout(grid)
        layout.addStretch()

    def _on_score_changed(self, ability: str, value: int) -> None:
        mod = (value - 10) // 2
        self._mod_labels[ability].set_value(mod)
        self.ability_changed.emit(ability, value)

    def set_score(self, ability: str, score: int) -> None:
        """Update score display (called when character changes externally)."""
        spin = self._spinboxes.get(ability)
        if spin:
            spin.blockSignals(True)
            spin.setValue(score)
            spin.blockSignals(False)
            mod = (score - 10) // 2
            self._mod_labels[ability].set_value(mod)

    def set_all_scores(self, scores: dict[str, int]) -> None:
        for ability, score in scores.items():
            self.set_score(ability, score)
