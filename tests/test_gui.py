"""Smoke tests for the window, run headless."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop_organizer.core import History, Organizer, Settings  # noqa: E402
from desktop_organizer.ui import theme  # noqa: E402
from desktop_organizer.ui.dialogs import CategoriesDialog, HistoryDialog, SettingsDialog, StructureDialog  # noqa: E402
from desktop_organizer.ui.main_window import COL_FILE, MainWindow  # noqa: E402

from .conftest import make_file  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, folder, tmp_path, monkeypatch):
    settings = Settings(folders=[])
    settings.add_folder(str(folder))
    organizer = Organizer(settings=settings, history=History(tmp_path / "h.db"))
    theme.apply_theme(app, "dark")
    win = MainWindow(organizer)
    monkeypatch.setattr(win, "confirm", lambda *a: True)
    monkeypatch.setattr(win, "show_run_result", lambda result: None)
    yield win
    win.close()


def wait_for_task(win):
    task = win.task
    if task is not None:
        task.wait(10_000)
    for _ in range(50):
        QApplication.processEvents()
        if win.task is None:
            return
    raise AssertionError("task didn't finish")


def test_preview_organize_and_undo(window, folder):
    make_file(folder, "a.txt")
    make_file(folder, "b.pdf")
    window.refresh_preview()
    assert window.tree.topLevelItemCount() == 2
    assert window.organize_button.text() == "Organize 2 files"

    # Unchecked files stay put.
    item = next(i for i in window._items() if i.text(COL_FILE) == "b.pdf")
    item.setCheckState(COL_FILE, Qt.CheckState.Unchecked)
    assert window.organize_button.text() == "Organize 1 file"

    window.organize()
    wait_for_task(window)
    assert (folder / "2025" / "03-March" / "txt" / "a.txt").exists()
    assert (folder / "b.pdf").exists()
    assert window.tree.topLevelItemCount() == 1
    assert window.undo_button.isEnabled()

    window.undo_last()
    wait_for_task(window)
    assert (folder / "a.txt").exists()
    assert not (folder / "2025").exists()


def test_structure_change_updates_preview(window, folder):
    make_file(folder, "a.zip")
    window.refresh_preview()
    window._on_structure_chosen("{category}")
    assert window.tree.topLevelItem(0).text(1) == "Archives/"
    assert window.organizer.settings.folders[0].pattern == "{category}"


def test_add_known_and_remove_folders(window, tmp_path):
    other = tmp_path / "Other"
    other.mkdir()
    assert window.add_folder(str(other))
    assert window.folder_list.count() == 2 and window.folder_list.currentRow() == 1
    window.remove_current_folder()
    assert window.folder_list.count() == 1


def test_project_folder_shows_warning(window, folder):
    (folder / "Dockerfile").write_text("")
    window.refresh_preview()
    assert not window.warning.isHidden()
    assert "software project" in window.warning.text()


def test_filter_and_empty_state(window, folder):
    window.refresh_preview()
    assert window.stack.currentWidget() is window.empty
    make_file(folder, "alpha.txt")
    make_file(folder, "beta.txt")
    window.refresh_preview()
    window.filter_edit.setText("alp")
    hidden = [i.isHidden() for i in window._items()]
    assert sorted(hidden) == [False, True]


def test_dialogs_open(window, folder):
    make_file(folder, "a.txt")
    dialog = StructureDialog(window.organizer, folder, "{nope}")
    assert "Unknown placeholder" in dialog.error.text()
    dialog.edit.setText("{category}/{year}")
    assert "a.txt  ->  Documents/2025/" in dialog.preview.toPlainText()
    for cls in (CategoriesDialog, HistoryDialog, SettingsDialog):
        cls(window.organizer, window).close()
