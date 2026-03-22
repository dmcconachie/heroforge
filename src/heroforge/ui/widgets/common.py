"""
ui/widgets/common.py
--------------------
Reusable widgets used across all tabs.

  LabeledField     — a QLabel + QLineEdit/QSpinBox in a row
  StatDisplay      — read-only stat display (value + optional modifier)
  SectionHeader    — styled bold separator label
  CompactSpinBox   — narrow SpinBox for stat scores
  ModifierLabel    — displays +N / -N with colour
  ToolTipButton    — small ? button that shows a tooltip popup
  HRule            — horizontal separator line
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Palette helpers
# ---------------------------------------------------------------------------

POSITIVE_COLOR = "#2a7d2a"  # dark green
NEGATIVE_COLOR = "#aa2222"  # dark red
NEUTRAL_COLOR = "#444444"  # grey


def _set_label_color(label: QLabel, color: str) -> None:
    label.setStyleSheet(f"color: {color};")


# ---------------------------------------------------------------------------
# SectionHeader
# ---------------------------------------------------------------------------


class SectionHeader(QLabel):
    """Bold, slightly larger label used as a section divider."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        font = self.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        self.setFont(font)
        self.setStyleSheet(
            "color: #222; padding-top: 4px; padding-bottom: 2px;"
        )


# ---------------------------------------------------------------------------
# HRule
# ---------------------------------------------------------------------------


class HRule(QFrame):
    """A thin horizontal separator line."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )


# ---------------------------------------------------------------------------
# ModifierLabel
# ---------------------------------------------------------------------------


class ModifierLabel(QLabel):
    """
    Displays an integer modifier in the form "+3" or "-2".
    Positive values shown in green, negative in red, zero in grey.
    """

    def __init__(self, value: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.font()
        font.setBold(True)
        self.setFont(font)
        self.set_value(value)

    def set_value(self, value: int) -> None:
        self._value = value
        if value > 0:
            self.setText(f"+{value}")
            _set_label_color(self, POSITIVE_COLOR)
        elif value < 0:
            self.setText(str(value))
            _set_label_color(self, NEGATIVE_COLOR)
        else:
            self.setText("±0")
            _set_label_color(self, NEUTRAL_COLOR)


# ---------------------------------------------------------------------------
# CompactSpinBox
# ---------------------------------------------------------------------------


class CompactSpinBox(QSpinBox):
    """A narrow SpinBox for ability scores (range 1–40 by default)."""

    def __init__(
        self,
        minimum: int = 1,
        maximum: int = 40,
        value: int = 10,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setValue(value)
        self.setFixedWidth(54)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)


# ---------------------------------------------------------------------------
# StatDisplay
# ---------------------------------------------------------------------------


class StatDisplay(QWidget):
    """
    Read-only display for a derived stat.

    Shows a bold value label and an optional smaller label below it.
    Used for AC, saves, BAB, HP, etc.
    """

    def __init__(
        self,
        label: str,
        value: int = 0,
        sub_label: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(1)

        self._name_label = QLabel(label)
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self._name_label.font()
        font.setPointSize(font.pointSize() - 1)
        self._name_label.setFont(font)
        self._name_label.setStyleSheet("color: #555;")

        self._value_label = QLabel(str(value))
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vfont = self._value_label.font()
        vfont.setBold(True)
        vfont.setPointSize(vfont.pointSize() + 3)
        self._value_label.setFont(vfont)

        layout.addWidget(self._name_label)
        layout.addWidget(self._value_label)

        if sub_label:
            self._sub_label = QLabel(sub_label)
            self._sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sfont = self._sub_label.font()
            sfont.setPointSize(sfont.pointSize() - 1)
            self._sub_label.setFont(sfont)
            self._sub_label.setStyleSheet("color: #777;")
            layout.addWidget(self._sub_label)
        else:
            self._sub_label = None

        # Subtle box border
        self.setStyleSheet(
            "StatDisplay { border: 1px solid #ccc; border-radius: 3px; "
            "background: #fafafa; }"
        )
        self.setFixedWidth(72)

    def set_value(self, value: int) -> None:
        self._value_label.setText(str(value))

    def set_sub_label(self, text: str) -> None:
        if self._sub_label:
            self._sub_label.setText(text)


# ---------------------------------------------------------------------------
# LabeledField
# ---------------------------------------------------------------------------


class LabeledField(QWidget):
    """A horizontal row: label on the left, editable field on the right."""

    text_changed = pyqtSignal(str)

    def __init__(
        self,
        label: str,
        value: str = "",
        read_only: bool = False,
        label_width: int = 90,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(6)

        lbl = QLabel(label)
        lbl.setFixedWidth(label_width)
        lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._edit = QLineEdit(value)
        self._edit.setReadOnly(read_only)
        if read_only:
            self._edit.setStyleSheet("background: #f0f0f0; color: #555;")
        self._edit.textChanged.connect(self.text_changed)

        layout.addWidget(lbl)
        layout.addWidget(self._edit)

    @property
    def value(self) -> str:
        return self._edit.text()

    @value.setter
    def value(self, v: str) -> None:
        self._edit.setText(v)


# ---------------------------------------------------------------------------
# ToolTipButton
# ---------------------------------------------------------------------------


class ToolTipButton(QPushButton):
    """A small '?' button that shows a tooltip when clicked."""

    def __init__(
        self,
        tooltip_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("?", parent)
        self._tip = tooltip_text
        self.setFixedSize(18, 18)
        self.setFlat(True)
        self.setStyleSheet(
            "QPushButton { color: #555; border: 1px solid #aaa; "
            "border-radius: 9px; font-size: 10px; }"
            "QPushButton:hover { background: #e8f0fe; }"
        )
        self.clicked.connect(self._show_tip)

    def _show_tip(self) -> None:
        QToolTip.showText(self.mapToGlobal(self.rect().bottomLeft()), self._tip)
