"""Headless tests for rules, duplicates, auto-organize and the tray."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop_organizer.core import History, Organizer, Settings  # noqa: E402
from desktop_organizer.core.config import AutoMode  # noqa: E402
from desktop_organizer.core.duplicates import find_duplicates  # noqa: E402
from desktop_organizer.core.user_rules import ConditionKind, RuleAction  # noqa: E402
from desktop_organizer.ui.dialogs import HistoryDialog, SettingsDialog  # noqa: E402
from desktop_organizer.ui.main_window import COL_RULE, MainWindow  # noqa: E402
from desktop_organizer.ui.tools import DuplicatesDialog, RulesDialog  # noqa: E402

from .conftest import make_file  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, folder, tmp_path, monkeypatch):
    settings = Settings(folders=[])
    settings.add_folder(str(folder))
    organizer = Organizer(settings=settings, history=History(tmp_path / "h.db"))
    win = MainWindow(organizer)
    win.schedule_timer.stop()
    monkeypatch.setattr(win, "confirm", lambda *a: True)
    monkeypatch.setattr(win, "show_run_result", lambda result: None)
    yield win
    win._quitting = True
    win.close()


def wait(win, attr="task"):
    task = getattr(win, attr)
    if task is not None:
        task.wait(10_000)
    for _ in range(100):
        QApplication.processEvents()
        if getattr(win, attr) is None:
            return
    raise AssertionError(f"{attr} didn't finish")


def test_auto_organize_watch_mode(window, folder):
    make_file(folder, "old.txt")
    window.auto.settle_seconds = 0
    window._on_auto_chosen(window.auto_combo.findData(AutoMode.WATCH.value))
    assert window.settings.folders[0].auto is AutoMode.WATCH
    assert "(auto)" in window.folder_list.item(0).text()
    assert str(folder) in window.auto_watcher.directories()
    wait(window, "auto_task")
    assert (folder / "2025" / "03-March" / "txt" / "old.txt").exists()
    assert window.undo_button.isEnabled()


def test_auto_respects_pause(window, folder):
    make_file(folder, "a.txt")
    window.auto.settle_seconds = 0
    window.settings.folders[0].auto = AutoMode.WATCH
    window.auto_paused = True
    window.run_auto()
    assert window.auto_task is None and (folder / "a.txt").exists()


def test_rules_dialog_creates_rule_and_preview_shows_it(window, folder):
    make_file(folder, "Invoice-1.pdf")
    make_file(folder, "photo.jpg")
    dialog = RulesDialog(window.organizer, folder, window)
    dialog._add_rule()
    dialog.name_edit.setText("Invoices")
    row = dialog.conditions_box.itemAt(0).widget()
    row.kind.setCurrentIndex(row.kind.findData(ConditionKind.NAME_CONTAINS.value))
    row.value.setText("invoice")
    dialog.destination_edit.setText("Finance/{year}")
    assert "Matches 1 file(s)" in dialog.matches.text()
    dialog._save()
    assert [r.name for r in window.settings.rules] == ["Invoices"]

    window.refresh_preview()
    rules_col = {window.tree.topLevelItem(i).text(0): window.tree.topLevelItem(i).text(COL_RULE)
                 for i in range(window.tree.topLevelItemCount())}
    assert rules_col == {"Invoice-1.pdf": "Invoices", "photo.jpg": ""}


def test_rules_dialog_rejects_invalid_rule(window, folder, monkeypatch):
    warned = []
    monkeypatch.setattr("desktop_organizer.ui.tools.QMessageBox.warning", lambda *a: warned.append(a[2]))
    dialog = RulesDialog(window.organizer, folder, window)
    dialog._add_rule()  # condition value left empty
    dialog._save()
    assert warned and window.settings.rules == []


def test_skip_rule_preview(window, folder):
    make_file(folder, "keep.txt")
    dialog = RulesDialog(window.organizer, folder, window)
    dialog._add_rule()
    dialog.conditions_box.itemAt(0).widget().value.setText("keep")
    dialog.action_combo.setCurrentIndex(dialog.action_combo.findData(RuleAction.SKIP.value))
    assert "Would leave 1 file(s)" in dialog.matches.text()


def test_duplicates_dialog_keeps_one_copy(window, folder, tmp_path, monkeypatch):
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        make_file(folder, name, content="same")
    dialog = DuplicatesDialog(window.organizer, folder, window)
    trashed = []
    dialog.send_to_trash = lambda paths: (trashed.extend(paths), [])[1]
    monkeypatch.setattr(dialog, "confirm", lambda count: True)
    warned = []
    monkeypatch.setattr("desktop_organizer.ui.tools.QMessageBox.warning", lambda *a: warned.append(a[2]))

    dialog.show_groups(find_duplicates(folder))
    assert len(dialog.checked_paths()) == 2  # oldest kept by default

    group = dialog.tree.topLevelItem(0)
    group.child(0).setCheckState(0, Qt.CheckState.Checked)  # tick every copy
    dialog.delete_selected()
    assert warned and trashed == []

    group.child(0).setCheckState(0, Qt.CheckState.Unchecked)
    dialog.delete_selected()
    assert len(trashed) == 2
    assert dialog.tree.topLevelItemCount() == 0


def test_close_hides_to_tray_when_available(window, monkeypatch):
    class FakeTray:
        def showMessage(self, *a):
            self.shown = True

        def hide(self):
            pass

    window.tray = FakeTray()
    window.show()
    window.close()
    assert window.isHidden() and not window._quitting
    window.settings.minimize_to_tray = False


def test_settings_and_history_dialogs(window, folder, monkeypatch):
    calls = []
    monkeypatch.setattr("desktop_organizer.core.startup.is_supported", lambda: True)
    monkeypatch.setattr("desktop_organizer.core.startup.is_enabled", lambda: False)
    monkeypatch.setattr("desktop_organizer.core.startup.set_enabled", lambda on: calls.append(on))
    dialog = SettingsDialog(window.organizer, window)
    dialog.notifications.setChecked(False)
    dialog.start_with_windows.setChecked(True)
    dialog._save()
    assert window.settings.notifications is False and calls == [True]

    make_file(folder, "a.txt")
    window.organizer.organize(folder)
    history = HistoryDialog(window.organizer, window)
    assert "1 file organized in 1 run" in history.stats.text()
