#!/usr/bin/env python3
"""
ui/app.py
---------
Application entry point.

Run with:
    python3 -m ui.app
or:
    python3 ui/app.py
"""

import signal
import sys
import time
from types import FrameType

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from heroforge.ui.main_window import MainWindow


def _apply_style(app: QApplication) -> None:
    """Apply a clean, professional light style."""
    app.setStyle("Fusion")

    # Subtle light palette with blue accent
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(245, 245, 248))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(30, 30, 40))
    palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(240, 242, 248))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 220))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.Text, QColor(30, 30, 40))
    palette.setColor(QPalette.ColorRole.Button, QColor(235, 237, 245))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(30, 30, 40))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(220, 0, 0))
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 100, 220))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(63, 118, 226))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    app.setStyleSheet("""
        QTabWidget::pane {
            border: 1px solid #c8c8d8;
        }
        QTabBar::tab {
            padding: 5px 14px;
            background: #e8eaf6;
            border: 1px solid #c5cae9;
            border-bottom: none;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background: white;
            font-weight: bold;
        }
        QGroupBox {
            border: 1px solid #c8c8d8;
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 4px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
            color: #3949ab;
            font-weight: bold;
        }
        QScrollArea {
            border: none;
        }
        QTableWidget {
            gridline-color: #dde;
        }
        QHeaderView::section {
            background: #e8eaf6;
            border: 1px solid #c5cae9;
            padding: 3px 6px;
            font-weight: bold;
            color: #333;
        }
    """)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("HeroForge Anew")
    app.setOrganizationName("D&D Tools")
    _apply_style(app)

    window = MainWindow()
    window.show()

    # Ctrl+C handling: first press schedules a close
    # on the Qt event loop; second press within 2s
    # force-terminates via os._exit (bypasses Qt).
    _last_sigint = [0.0]

    def _sigint_handler(
        signum: int,
        frame: FrameType | None,
    ) -> None:
        import os

        where = f"{frame.f_code.co_name}" if frame is not None else "<unknown>"
        now = time.monotonic()
        if now - _last_sigint[0] < 2.0:
            print(
                f"\nForce quit (signal {signum} in {where}).",
                file=sys.stderr,
            )
            os._exit(1)
        _last_sigint[0] = now
        print(
            f"\nCaught signal {signum} in {where}; closing… "
            "press Ctrl+C again to force quit.",
            file=sys.stderr,
        )
        # Schedule close on the Qt event loop
        QTimer.singleShot(0, app.quit)

    signal.signal(signal.SIGINT, _sigint_handler)

    # Periodically wake the Python interpreter so signal handlers can run
    # (Qt's C++ event loop doesn't yield to Python on its own).
    _ticker = QTimer()
    _ticker.start(500)
    _ticker.timeout.connect(lambda: None)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
