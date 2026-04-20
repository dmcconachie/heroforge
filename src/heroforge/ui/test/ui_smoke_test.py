"""
ui/test/ui_smoke_test.py
------------------------
Smoke tests for the UI layer.

TODO: revisit whether a single smoke file is the right
shape, or whether to split across
main_window_test.py / sheets/*_test.py / widgets/*_test.py.

These tests construct the main window and individual sheet
widgets using Qt's offscreen platform, verifying that:
  - All widgets instantiate without AttributeError
    or other crashes
  - Basic interactions (typing, clicking) don't raise
  - The ChangeNotifier is wired correctly between
    Character and UI

Requires: QT_QPA_PLATFORM=offscreen (set via conftest.py).

Runs single-process (no xdist) — Qt requires one
QApplication per process.
"""

from __future__ import annotations

import pytest

from heroforge.ui.app_state import AppState
from heroforge.ui.main_window import MainWindow

# Force all tests in this module into a single xdist group so they
# run in one worker process sharing the session-scoped QApplication.
pytestmark = pytest.mark.xdist_group("qt")


def _force_close(window: MainWindow) -> None:
    """Close a MainWindow without triggering the 'unsaved changes' dialog."""
    window._modified = False
    window.close()


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture()
def app_state() -> AppState:
    """Fully initialised AppState with rules + blank char."""
    state = AppState()
    state.load_rules()
    state.new_character()
    return state


# ===========================================================================
# MainWindow construction
# ===========================================================================


@pytest.mark.usefixtures("qapp")
class TestMainWindowSmoke:
    def test_main_window_constructs(self) -> None:
        """MainWindow.__init__ completes without error."""
        window = MainWindow()
        assert window is not None
        _force_close(window)

    def test_main_window_has_tab_widget(self) -> None:
        window = MainWindow()
        assert window._tabs is not None
        assert window._tabs.count() >= 3
        _force_close(window)


# ===========================================================================
# Sheet1 — Summary
# ===========================================================================


@pytest.mark.usefixtures("qapp")
class TestSheet1Smoke:
    def test_sheet1_constructs(self, app_state: AppState) -> None:
        from heroforge.ui.sheets.sheet1_summary import Sheet1Summary

        sheet = Sheet1Summary(app_state)
        assert sheet is not None

    def test_sheet1_refresh(self, app_state: AppState) -> None:
        from heroforge.ui.sheets.sheet1_summary import Sheet1Summary

        sheet = Sheet1Summary(app_state)
        sheet.refresh()

    def test_sheet1_name_change_notifies(self, app_state: AppState) -> None:
        """Typing a name fires on_change with identity:name key."""
        from heroforge.ui.sheets.sheet1_summary import Sheet1Summary

        sheet = Sheet1Summary(app_state)

        received: list[set] = []
        app_state.character.on_change.subscribe(
            lambda keys: received.append(keys)
        )

        sheet._name_field.value = "Aldric Vane"

        assert any("identity:name" in keys for keys in received)


# ===========================================================================
# Sheet2 — Skills
# ===========================================================================


@pytest.mark.usefixtures("qapp")
class TestSheet2Smoke:
    def test_sheet2_constructs(self, app_state: AppState) -> None:
        from heroforge.ui.sheets.sheet2_skills import Sheet2Skills

        sheet = Sheet2Skills(app_state)
        assert sheet is not None

    def test_sheet2_refresh(self, app_state: AppState) -> None:
        from heroforge.ui.sheets.sheet2_skills import Sheet2Skills

        sheet = Sheet2Skills(app_state)
        sheet.refresh()


# ===========================================================================
# Sheet3 — Feats
# ===========================================================================


@pytest.mark.usefixtures("qapp")
class TestSheet3Smoke:
    def test_sheet3_constructs(self, app_state: AppState) -> None:
        from heroforge.ui.sheets.sheet3_feats import Sheet3Feats

        sheet = Sheet3Feats(app_state)
        assert sheet is not None

    def test_sheet3_refresh(self, app_state: AppState) -> None:
        from heroforge.ui.sheets.sheet3_feats import Sheet3Feats

        sheet = Sheet3Feats(app_state)
        sheet.refresh()

    def test_sheet3_filter_method_exists_and_works(
        self, app_state: AppState
    ) -> None:
        """Typing in the filter field updates the feat list without error."""
        from heroforge.ui.sheets.sheet3_feats import Sheet3Feats

        sheet = Sheet3Feats(app_state)
        sheet._filter_edit.setText("Dodge")

    def test_sheet3_filter_narrows_list(self, app_state: AppState) -> None:
        from heroforge.ui.sheets.sheet3_feats import Sheet3Feats

        sheet = Sheet3Feats(app_state)

        total_count = sheet._avail_list.count()
        sheet._filter_edit.setText("Power Attack")
        filtered_count = sheet._avail_list.count()

        assert filtered_count < total_count
        assert filtered_count >= 1


# ===========================================================================
# ChangeNotifier wiring — MainWindow level
# ===========================================================================


@pytest.mark.usefixtures("qapp")
class TestNotifierWiring:
    def test_main_window_subscribes_to_on_change(self) -> None:
        """MainWindow wires up to character.on_change."""
        window = MainWindow()
        notifier = window._state.character.on_change
        assert len(notifier._listeners) >= 1
        _force_close(window)

    def test_stat_change_does_not_crash_main_window(self) -> None:
        """Changing an ability score fires notifications through to the UI."""
        window = MainWindow()
        window._state.character.set_ability_score("str", 18)
        _force_close(window)
