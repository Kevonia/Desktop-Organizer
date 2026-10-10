"""Headless tests for renaming, other destinations, drives, stats, setups, reports,
settings export/import, the Explorer menu hand-off and 'where did this come from?'."""

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from desktop_organizer.core import History, Organizer, Settings, drives, transfer  # noqa: E402
from desktop_organizer.ui import dialogs, insights  # noqa: E402
from desktop_organizer.ui.dialogs import HistoryDialog, RenameDialog  # noqa: E402
from desktop_organizer.ui.insights import OriginDialog, SetupsDialog, StatsDialog, TransferDialog  # noqa: E402
from desktop_organizer.ui.main_window import COL_TARGET, MainWindow  # noqa: E402
from desktop_organizer.ui.single_instance import SingleInstance  # noqa: E402
from desktop_organizer.ui.tools import RulesDialog  # noqa: E402

from .conftest import make_file  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, folder, tmp_path, monkeypatch):
    drives.forget()
    settings = Settings(folders=[])
    settings.add_folder(str(folder), "{type}")
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


def targets(win) -> dict[str, str]:
    return {win.tree.topLevelItem(i).text(0): win.tree.topLevelItem(i).text(COL_TARGET)
            for i in range(win.tree.topLevelItemCount())}


def test_rename_dialog_and_preview(window, folder):
    make_file(folder, "IMG_1.jpg")
    window.refresh_preview()
    assert window.rename_button.text() == "Keep names"

    dialog = RenameDialog(window.organizer, folder, None, window)
    assert dialog.template() is None and "keep their names" in dialog.preview.toPlainText()
    dialog._use("{date} {name}")
    assert "IMG_1.jpg  ->  2025-03-14 IMG_1.jpg" in dialog.preview.toPlainText()
    dialog.edit.setText("{oops}")
    assert "Unknown placeholder" in dialog.error.text()
    assert not dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled()

    window.set_rename("{date} {name}")
    assert window.rename_button.text() == "Rename: {date} {name}"
    assert targets(window) == {"IMG_1.jpg": "jpg/2025-03-14 IMG_1.jpg"}
    window.organize()
    wait(window)
    assert (folder / "jpg" / "2025-03-14 IMG_1.jpg").exists()


def test_put_files_in_another_folder(window, folder, tmp_path):
    make_file(folder, "a.txt")
    archive = tmp_path / "Archive"
    archive.mkdir()
    assert window.set_destination(str(archive))
    assert window.destination_button.text() == "Another folder: Archive"
    assert "files go to" in window.path_label.text()
    assert targets(window) == {"a.txt": "Archive/txt/"}
    window.organize()
    wait(window)
    assert (archive / "txt" / "a.txt").exists()

    assert window.set_destination(None)
    assert window.destination_button.text() == "This folder"


def test_system_folder_is_refused_as_destination(window, monkeypatch):
    shown = []
    monkeypatch.setattr("desktop_organizer.ui.main_window.QMessageBox.critical", lambda *a: shown.append(a[2]))
    assert not window.set_destination(os.environ.get("SystemRoot", "/usr"))
    assert shown and window.settings.folders[0].destination is None


def test_unplugged_drive_shows_waiting(window, folder, monkeypatch):
    make_file(folder, "a.txt")
    # An unplugged drive: the folder is gone and so is its drive.
    away = folder.with_name("unplugged")
    folder.rename(away)
    monkeypatch.setattr(drives, "is_connected", lambda path: False)
    window.refresh_all()
    assert "(not connected)" in window.folder_list.item(0).text()
    assert window.stack.currentWidget() is window.empty
    assert "Waiting for the drive" in window.empty.text()
    assert "isn't connected" in window.warning.text()

    away.rename(folder)
    monkeypatch.setattr(drives, "is_connected", lambda path: True)
    window._check_drives()  # the periodic check notices it's back
    assert "(not connected)" not in window.folder_list.item(0).text()
    assert targets(window) == {"a.txt": "txt/"}


def test_stats_dialog(window, folder):
    make_file(folder, "movie.mp4", content="x" * 4000)
    make_file(folder, "a.txt")
    dialog = StatsDialog(window.organizer, folder, window)
    dialog.scan(wait=True)
    for _ in range(100):
        QApplication.processEvents()
        if dialog.task is None:
            break
    assert dialog.stats is not None and dialog.stats.file_count == 2
    assert dialog.categories.topLevelItem(0).text(0) == "Videos"
    assert dialog.largest.topLevelItem(0).text(0) == "movie.mp4"
    dialog.tabs.setCurrentWidget(dialog.largest)
    dialog.largest.topLevelItem(0).setSelected(True)
    assert dialog.show_button.isEnabled()


def test_setups_dialog_and_welcome(window, monkeypatch):
    reported = []
    monkeypatch.setattr(SetupsDialog, "report", lambda self, title, text: reported.append(title))
    monkeypatch.setattr(SetupsDialog, "exec", lambda self: (self.list.setCurrentRow(1), self.apply_selected(),
                                                            QDialog.DialogCode.Accepted)[2])
    window.show_welcome()
    assert window.settings.welcome_shown is True
    assert reported == ["Freelancer setup added"]
    assert "Invoices" in [r.name for r in window.settings.rules]
    names = [window.folder_list.item(i).text() for i in range(window.folder_list.count())]
    assert "Downloads" in names


def test_export_preview_and_history_run(window, folder, tmp_path, monkeypatch):
    make_file(folder, "a.txt")
    window.refresh_preview()
    out = tmp_path / "preview.csv"
    monkeypatch.setattr(dialogs.QFileDialog, "getSaveFileName", lambda *a: (str(out), "Spreadsheet (*.csv)"))
    monkeypatch.setattr(dialogs.QMessageBox, "information", lambda *a: None)
    window.export_preview()
    assert "a.txt" in out.read_text(encoding="utf-8-sig")

    window.organize()
    wait(window)
    history = HistoryDialog(window.organizer, window)
    history.table.selectRow(0)
    assert history.export_button.isEnabled()
    page = tmp_path / "run.html"
    monkeypatch.setattr(dialogs.QFileDialog, "getSaveFileName", lambda *a: (str(page), "Web page (*.html)"))
    history._export_selected()
    assert "a.txt" in page.read_text(encoding="utf-8")


def test_export_and_import_settings_windows(window, tmp_path, monkeypatch):
    monkeypatch.setattr(TransferDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(insights.QMessageBox, "information", lambda *a: None)
    out = tmp_path / "mine.json"
    monkeypatch.setattr(insights.QFileDialog, "getSaveFileName", lambda *a: (str(out), ""))
    window.settings.set_category("Design", ["psd"])
    assert insights.export_settings(window.organizer, window) == out

    window.settings.custom_categories = {}
    summary = insights.import_settings(window.organizer, window, out)
    assert summary is not None and window.settings.custom_categories == {"Design": ["psd"]}

    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    warned = []
    monkeypatch.setattr(insights.QMessageBox, "warning", lambda *a: warned.append(a[2]))
    assert insights.import_settings(window.organizer, window, bad) is None
    assert warned


def test_transfer_dialog_needs_a_part(app):
    dialog = TransferDialog("Export", "intro", list(transfer.PARTS), "Export")
    assert dialog.ok.isEnabled()
    for box in dialog.boxes.values():
        box.setChecked(False)
    assert not dialog.ok.isEnabled() and dialog.parts() == []


def test_explorer_requests(window, folder, tmp_path, monkeypatch):
    other = tmp_path / "Other"
    other.mkdir()
    make_file(other, "x.txt")
    window.handle_message(f"organize\t{other}")
    assert window.current_profile.location == other
    assert targets(window)  # preview shown, nothing moved
    assert (other / "x.txt").exists()

    window.handle_message(f"organize\t{folder}")  # already saved: just selected
    assert window.current_profile.location == folder

    shown = []
    monkeypatch.setattr(window, "show_origin", lambda path: shown.append(path))
    window.handle_message(f"where\t{other / 'x.txt'}")
    assert shown == [other / "x.txt"]


def test_origin_dialog(window, folder):
    make_file(folder, "report.pdf")
    window.organizer.organize(folder)
    dialog = OriginDialog(window.organizer, folder / "pdf" / "report.pdf", window)
    assert dialog.origin.original_path == folder / "report.pdf"
    assert dialog.original_button.isEnabled()
    fresh = OriginDialog(window.organizer, make_file(folder, "new.txt"), window)
    assert not fresh.original_button.isEnabled()


def test_rules_dialog_rename_field(window, folder):
    make_file(folder, "Invoice-1.pdf")
    dialog = RulesDialog(window.organizer, folder, window)
    dialog._add_rule()
    dialog.name_edit.setText("Invoices")
    dialog.conditions_box.itemAt(0).widget().value.setText("invoice")
    dialog.rename_edit.setText("{date} {name}")
    assert "(as 2025-03-14 Invoice-1.pdf)" in dialog.matches.text()
    dialog._save()
    assert window.settings.rules[0].rename == "{date} {name}"


def test_single_instance_passes_requests(app):
    key = f"DesktopOrganizerTest-{uuid.uuid4().hex[:8]}"
    first = SingleInstance(key)
    assert first.listen()
    received = []
    first.messageReceived.connect(received.append)
    # A real second launch: another process, as when File Explorer starts the app.
    script = ("from PySide6.QtCore import QCoreApplication\n"
              "from desktop_organizer.ui.single_instance import SingleInstance\n"
              "app = QCoreApplication([])\n"
              f"raise SystemExit(0 if SingleInstance({key!r}).notify_running("
              "'organize\\tC:\\\\Users\\\\me\\\\Downloads', 3000) else 1)\n")
    process = subprocess.Popen([sys.executable, "-c", script], cwd=Path(__file__).resolve().parent.parent)
    for _ in range(1000):
        QApplication.processEvents()
        if received and process.poll() is not None:
            break
        time.sleep(0.01)
    assert received == ["organize\tC:\\Users\\me\\Downloads"]
    assert process.wait(10) == 0
    first.server.close()


def test_settings_dialog_explorer_menu(window, monkeypatch):
    calls = []
    monkeypatch.setattr("desktop_organizer.core.startup.is_supported", lambda: True)
    monkeypatch.setattr("desktop_organizer.core.shell.is_enabled", lambda: False)
    monkeypatch.setattr("desktop_organizer.core.shell.set_enabled", lambda on: calls.append(on))
    dialog = dialogs.SettingsDialog(window.organizer, window)
    dialog.explorer_menu.setChecked(True)
    dialog._save()
    assert calls == [True]


def test_target_text_for_paths(window, folder):
    from desktop_organizer.core.rules import PlannedMove
    from desktop_organizer.ui.main_window import _target_text

    move = PlannedMove(folder / "a.txt", folder / "txt", folder)
    assert _target_text(move) == "txt/"
    elsewhere = Path(folder.parent / "Archive")
    assert _target_text(PlannedMove(folder / "a.txt", elsewhere / "txt", elsewhere, new_name="b.txt")) == \
        "Archive/txt/b.txt"
