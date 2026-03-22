"""
heroforge/ui/sheets/sheet3_feats.py
------------------------------------
Sheet 3: Feats.

Two-panel layout:
  Left:  Taken Feats — list of feats the character has, with Remove button.
  Right: Available Feats — full feat list with availability indicators,
         filterable by name, showing prereq details on hover.

Availability colours:
  ● green    AVAILABLE    — all prereqs met, not yet taken
  ● blue     TAKEN        — already selected
  ● yellow   CHAIN_PARTIAL — some prereq feats met but not all
  ● grey     UNAVAILABLE  — hard prereqs not met
  ★ gold     OVERRIDE     — DM override active
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from heroforge.engine.prerequisites import FeatAvailability

if TYPE_CHECKING:
    from heroforge.ui.app_state import AppState

# Colour palette for availability
_COLORS = {
    FeatAvailability.AVAILABLE: QColor("#1b5e20"),  # dark green
    FeatAvailability.TAKEN: QColor("#1565c0"),  # blue
    FeatAvailability.CHAIN_PARTIAL: QColor("#e65100"),  # orange
    FeatAvailability.UNAVAILABLE: QColor("#9e9e9e"),  # grey
    FeatAvailability.OVERRIDE: QColor("#f9a825"),  # gold
}

_BULLETS = {
    FeatAvailability.AVAILABLE: "●",
    FeatAvailability.TAKEN: "●",
    FeatAvailability.CHAIN_PARTIAL: "◑",
    FeatAvailability.UNAVAILABLE: "○",
    FeatAvailability.OVERRIDE: "★",
}


class Sheet3Feats(QWidget):
    """Feats tab — taken feats list on the left, feat picker on the right."""

    def __init__(
        self, app_state: AppState, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._state = app_state
        self._building = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: Taken Feats ────────────────────────────────────────────
        left_box = QGroupBox("Taken Feats")
        left_layout = QVBoxLayout(left_box)

        self._taken_list = QListWidget()
        self._taken_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._taken_list.currentItemChanged.connect(self._on_taken_selected)
        left_layout.addWidget(self._taken_list)

        btn_row = QHBoxLayout()
        self._remove_btn = QPushButton("Remove Feat")
        self._remove_btn.setEnabled(False)
        self._remove_btn.clicked.connect(self._on_remove_feat)
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch()
        left_layout.addLayout(btn_row)

        splitter.addWidget(left_box)

        # ── Right: Available Feats ────────────────────────────────────────
        right_box = QGroupBox("All Feats")
        right_layout = QVBoxLayout(right_box)

        # Filter bar
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Type feat name…")
        self._filter_edit.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._filter_edit)
        right_layout.addLayout(filter_row)

        # Legend
        legend = QLabel(
            "● Available  ● Taken  ◑ Partial chain"
            "  ○ Unavailable  ★ DM Override"
        )
        legend.setStyleSheet("color: #666; font-size: 10px;")
        right_layout.addWidget(legend)

        # Feat list
        self._avail_list = QListWidget()
        self._avail_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._avail_list.currentItemChanged.connect(self._on_avail_selected)
        self._avail_list.itemDoubleClicked.connect(self._on_add_feat)
        right_layout.addWidget(self._avail_list, stretch=2)

        # Detail panel
        right_layout.addWidget(QLabel("Details:"))
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMaximumHeight(130)
        self._detail.setStyleSheet("background: #fafafa; font-size: 11px;")
        right_layout.addWidget(self._detail)

        # Add button
        btn_row2 = QHBoxLayout()
        self._add_btn = QPushButton("Add Feat  ▶")
        self._add_btn.setEnabled(False)
        self._add_btn.clicked.connect(self._on_add_feat)
        btn_row2.addStretch()
        btn_row2.addWidget(self._add_btn)
        right_layout.addLayout(btn_row2)

        splitter.addWidget(right_box)
        splitter.setSizes([300, 500])

        layout.addWidget(splitter)

        self._building = False
        self.refresh()

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload both lists from the character."""
        if self._building:
            return
        self._refresh_taken()
        self._refresh_available()

    def _refresh_taken(self) -> None:
        self._taken_list.clear()
        for feat in self._state.character.feats:
            name = feat.get("name", "")
            if not name:
                continue
            item = QListWidgetItem(name)
            source = feat.get("source", "")
            if source:
                item.setToolTip(f"Source: {source}")
                item.setForeground(QBrush(QColor("#555")))
                item.setFont(_italic_font())
            self._taken_list.addItem(item)

    def _refresh_available(self) -> None:
        filter_text = self._filter_edit.text().lower()
        self._avail_list.clear()

        checker = getattr(self._state, "prereq_checker", None)
        feat_reg = self._state.feat_registry
        char = self._state.character

        for feat_name in feat_reg.all_names():
            if filter_text and filter_text not in feat_name.lower():
                continue

            if checker is not None:
                avail, details = checker.feat_availability(feat_name, char)
            else:
                # No checker — show all as available/taken
                taken = any(f.get("name") == feat_name for f in char.feats)
                avail = (
                    FeatAvailability.TAKEN
                    if taken
                    else FeatAvailability.AVAILABLE
                )
                details = []

            bullet = _BULLETS[avail]
            item = QListWidgetItem(f"{bullet}  {feat_name}")
            item.setData(Qt.ItemDataRole.UserRole, feat_name)
            item.setData(Qt.ItemDataRole.UserRole + 1, (avail, details))
            color = _COLORS[avail]
            item.setForeground(QBrush(color))
            if avail == FeatAvailability.TAKEN:
                item.setFont(_bold_font())
            elif avail == FeatAvailability.UNAVAILABLE:
                item.setFont(_light_font())

            self._avail_list.addItem(item)

    # ------------------------------------------------------------------
    # Filter handler
    # ------------------------------------------------------------------

    def _on_filter_changed(self, text: str) -> None:
        self._refresh_available()

    # ------------------------------------------------------------------
    # Selection handlers
    # ------------------------------------------------------------------

    def _on_taken_selected(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        has_selection = current is not None
        if has_selection:
            # Don't allow removing template-granted feats
            source = ""
            idx = self._taken_list.currentRow()
            if 0 <= idx < len(self._state.character.feats):
                source = self._state.character.feats[idx].get("source", "")
            self._remove_btn.setEnabled(not source.startswith("template:"))
        else:
            self._remove_btn.setEnabled(False)

    def _on_avail_selected(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            self._detail.clear()
            self._add_btn.setEnabled(False)
            return

        feat_name = current.data(Qt.ItemDataRole.UserRole)
        avail, details = current.data(Qt.ItemDataRole.UserRole + 1)

        self._add_btn.setEnabled(
            avail
            in (
                FeatAvailability.AVAILABLE,
                FeatAvailability.OVERRIDE,
            )
        )

        self._show_detail(feat_name, avail, details)

    def _show_detail(
        self,
        feat_name: str,
        avail: FeatAvailability,
        details: list,
    ) -> None:
        defn = self._state.feat_registry.get(feat_name)
        lines = [f"<b>{feat_name}</b>"]
        if defn:
            lines.append(f"<i>{defn.note}</i>" if defn.note else "")
            lines.append(f"Source: {defn.source_book}")
            kind_label = {
                "always_on": "Passive bonus (always active)",
                "conditional": "Conditional stance (Buffs panel)",
                "passive": "Passive / chain feat (no direct stat bonus)",
            }.get(defn.kind.value, defn.kind.value)
            lines.append(f"Kind: {kind_label}")
            if defn.parameter_spec:
                spec = defn.parameter_spec
                lines.append(
                    f"Parameter: {spec.label} ({spec.min}–{spec.max_formula})"
                )
        lines.append("")

        if avail == FeatAvailability.AVAILABLE:
            lines.append(
                "<span style='color:#1b5e20'>✔ All prerequisites met</span>"
            )
        elif avail == FeatAvailability.TAKEN:
            lines.append("<span style='color:#1565c0'>✔ Already taken</span>")
        elif avail == FeatAvailability.OVERRIDE:
            lines.append(
                "<span style='color:#f9a825'>★ DM Override active</span>"
            )
        elif details:
            lines.append("<b>Unmet prerequisites:</b>")
            for d in details[:8]:
                lines.append(f"  • {d.description}")
            if len(details) > 8:
                lines.append(f"  … and {len(details) - 8} more")

        self._detail.setHtml(
            "<br>".join(line for line in lines if line is not None)
        )

    # ------------------------------------------------------------------
    # Add / Remove
    # ------------------------------------------------------------------

    def _on_add_feat(self, *_: object) -> None:
        item = self._avail_list.currentItem()
        if item is None:
            return
        feat_name = item.data(Qt.ItemDataRole.UserRole)
        avail, _ = item.data(Qt.ItemDataRole.UserRole + 1)
        if avail not in (FeatAvailability.AVAILABLE, FeatAvailability.OVERRIDE):
            return

        defn = self._state.feat_registry.get(feat_name)
        self._state.character.add_feat(feat_name, defn)
        self._state.character.on_change.notify({feat_name})
        self.refresh()

    def _on_remove_feat(self) -> None:
        item = self._taken_list.currentItem()
        if item is None:
            return
        feat_name = item.text()
        defn = self._state.feat_registry.get(feat_name)
        self._state.character.remove_feat(feat_name, defn)
        self._state.character.on_change.notify({feat_name})
        self.refresh()


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------


def _bold_font() -> QFont:
    f = QFont()
    f.setBold(True)
    return f


def _italic_font() -> QFont:
    f = QFont()
    f.setItalic(True)
    return f


def _light_font() -> QFont:
    f = QFont()
    f.setWeight(QFont.Weight.Light)
    return f
