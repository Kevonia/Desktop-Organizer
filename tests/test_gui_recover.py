"""Headless tests for the Find & recover window."""

import os
import time
from datetime import datetime

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop_organizer.core import History, Organizer, Settings  # noqa: E402
from desktop_organizer.core.recycle_bin import make_info  # noqa: E402
from desktop_organizer.core.versions import VersionStore  # noqa: E402
from desktop_organizer.ui.recover import FIND, RECYCLE, VERSIONS, RecoverDialog, RecycleTab  # noqa: E402

from .conftest import make_file  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def organizer(folder, tmp_path):
    settings = Settings(folders=[])
    settings.add_folder(str(folder))
    return Organizer(settings=settings, history=History(tmp_path / "h.db"), versions=VersionStore(tmp_path / "vs"))


def test_find_tab_shows_where_files_went(app, organizer, folder):
    make_file(folder, "Resume 2026.docx")
    organizer.organize(folder)
    dialog = RecoverDialog(organizer, FIND)
    results = dialog.find_tab.search_now("resume")
    assert len(results) == 1
    item = dialog.find_tab.tree.topLevelItem(0)
    assert item.text(0) == "Resume 2026.docx"
    assert item.text(1).endswith("docx") and item.text(2) == str(folder)
    assert "moved by the organizer" in dialog.find_tab.status.text()
    dialog.find_tab.tree.setCurrentItem(item)
    assert dialog.find_tab.open_button.isEnabled()


def test_find_tab_background_search(app, organizer, folder):
    make_file(folder, "holiday.jpg")
    dialog = RecoverDialog(organizer, FIND)
    dialog.find_tab.start_search("holiday")
    dialog.find_tab.task.wait(5000)
    for _ in range(50):
        QApplication.processEvents()
        if dialog.find_tab.task is None:
            break
    assert dialog.find_tab.tree.topLevelItemCount() == 1


def test_versions_tab_protect_scan_and_restore(app, organizer, tmp_path, monkeypatch):
    work = tmp_path / "Work"
    work.mkdir()
    doc = work / "budget.xlsx"
    doc.write_text("version A")
    dialog = RecoverDialog(organizer, VERSIONS)
    tab = dialog.versions_tab
    monkeypatch.setattr(tab, "confirm", lambda *a: True)
    monkeypatch.setattr("desktop_organizer.ui.recover.QMessageBox.information", lambda *a: None)

    assert tab.add_folder(str(work))
    tab.scan_task.wait(5000)
    QApplication.processEvents()
    assert organizer.settings.version_folders == [str(work.resolve())]

    doc.write_text("version B")
    later = time.time() + 5
    os.utime(doc, (later, later))
    organizer.versions.scan([work])
    tab.reload()
    assert tab.files.topLevelItemCount() == 1
    tab.files.setCurrentItem(tab.files.topLevelItem(0))
    assert tab.versions.topLevelItemCount() == 2

    tab.versions.setCurrentItem(tab.versions.topLevelItem(1))  # the older one
    tab.restore_selected()
    assert doc.read_text() == "version A"


def test_versions_tab_refuses_system_folders(app, organizer, monkeypatch):
    warned = []
    monkeypatch.setattr("desktop_organizer.ui.recover.QMessageBox.warning", lambda *a: warned.append(a))
    dialog = RecoverDialog(organizer, VERSIONS)
    from pathlib import Path

    assert not dialog.versions_tab.add_folder(Path.home().anchor)
    assert warned and organizer.settings.version_folders == []


def test_recycle_tab_restores_selected(app, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    original = tmp_path / "Docs" / "letter.docx"
    (bin_dir / "$IAB12.docx").write_bytes(make_info(original, 4, datetime(2026, 9, 30, 8, 0)))
    (bin_dir / "$RAB12.docx").write_text("text")
    tab = RecycleTab([bin_dir])
    reports = []
    tab.confirm = lambda text: True
    tab.report = lambda message: reports.append(message)
    tab.reload()
    assert tab.tree.topLevelItemCount() == 1
    assert "1 item" in tab.status.text()
    tab.filter.setText("nothing-matches")
    assert tab.tree.topLevelItemCount() == 0
    tab.filter.setText("letter")
    tab.tree.topLevelItem(0).setSelected(True)
    tab.restore_selected()
    assert original.read_text() == "text"
    assert "Restored 1 item" in reports[0]
    assert tab.status.text() == "The Recycle Bin is empty."


def test_main_window_saves_versions_in_background(app, organizer, tmp_path):
    from desktop_organizer.ui.main_window import MainWindow

    work = tmp_path / "Protected"
    work.mkdir()
    (work / "a.txt").write_text("x")
    organizer.settings.version_folders = [str(work)]
    win = MainWindow(organizer)
    win.schedule_timer.stop()
    win.version_timer.stop()
    win.save_versions()
    win.version_task.wait(5000)
    for _ in range(50):
        QApplication.processEvents()
        if win.version_task is None:
            break
    assert [f.path.name for f in organizer.versions.files()] == ["a.txt"]
    win._quitting = True
    win.close()


def test_recover_dialog_opens_on_each_tab(app, organizer):
    for tab in (FIND, VERSIONS, RECYCLE):
        dialog = RecoverDialog(organizer, tab)
        assert dialog.tabs.currentIndex() == tab
        dialog.close()
