"""Update checks, logging, error handling and the single-instance lock."""

import json
import logging
import os
import urllib.error
import uuid

import pytest

from desktop_organizer.core import History, Organizer, Settings
from desktop_organizer.core.logs import log, log_file, setup_logging
from desktop_organizer.core.updates import UpdateError, check_for_update, parse_release

from .conftest import make_file

RELEASE = {
    "tag_name": "v1.4.0",
    "html_url": "https://github.com/Kevonia/Desktop-Organizer/releases/tag/v1.4.0",
    "body": "New things",
    "draft": False,
    "prerelease": False,
    "assets": [
        {"name": "DesktopOrganizer-1.4.0-portable.zip", "browser_download_url": "https://x/zip"},
        {"name": "DesktopOrganizer-1.4.0-Setup.exe", "browser_download_url": "https://x/setup"},
    ],
}


def fake(payload=None, error=None):
    def fetch(url, timeout):
        assert "api.github.com/repos/Kevonia/Desktop-Organizer/releases/latest" in url
        if error:
            raise error
        return json.dumps(payload).encode()
    return fetch


# --- updates -----------------------------------------------------------------------


def test_newer_release_is_offered_with_installer_link():
    info = check_for_update("1.2.0", fetch=fake(RELEASE))
    assert info.version == "1.4.0"
    assert info.download_url == "https://x/setup"
    assert info.notes == "New things"


def test_same_or_older_release_is_not_offered():
    assert check_for_update("1.4.0", fetch=fake(RELEASE)) is None
    assert check_for_update("2.0.0", fetch=fake(RELEASE)) is None


def test_drafts_prereleases_and_bad_tags_are_ignored():
    assert parse_release({**RELEASE, "prerelease": True}) is None
    assert parse_release({**RELEASE, "draft": True}) is None
    assert parse_release({**RELEASE, "tag_name": "nightly"}) is None


def test_no_release_published_yet_is_not_an_error():
    error = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
    assert check_for_update("1.0.0", fetch=fake(error=error)) is None


@pytest.mark.parametrize("error", [
    urllib.error.URLError("offline"),
    urllib.error.HTTPError("u", 500, "Server Error", {}, None),
    TimeoutError(),
])
def test_network_problems_become_friendly_errors(error):
    with pytest.raises(UpdateError):
        check_for_update("1.0.0", fetch=fake(error=error))


def test_garbage_answer_is_a_friendly_error():
    with pytest.raises(UpdateError):
        check_for_update("1.0.0", fetch=lambda url, timeout: b"<html>")


def test_update_settings_round_trip(tmp_path):
    path = tmp_path / "s.json"
    settings = Settings(check_updates=True, last_update_check="2026-10-01T09:00:00")
    settings.save(path)
    assert Settings.load(path) == settings
    assert Settings().check_updates is False  # never goes online unless asked


# --- logging -------------------------------------------------------------------------


def test_runs_and_undo_are_logged(folder, tmp_path):
    for handler in list(log.handlers):
        log.removeHandler(handler)
    path = setup_logging()
    make_file(folder, "a.txt")
    organizer = Organizer(settings=Settings(), history=History(tmp_path / "h.db"))
    organizer.organize(folder)
    organizer.undo_last()
    for handler in log.handlers:
        handler.flush()
    text = path.read_text(encoding="utf-8")
    assert "starting" in text and "moved 1 file(s)" in text and "restored 1 file(s)" in text
    assert path == log_file()
    for handler in list(log.handlers):
        handler.close()
        log.removeHandler(handler)


# --- GUI pieces ------------------------------------------------------------------------

pyside = pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_single_instance_hands_off_to_running_copy(app):
    from PySide6.QtWidgets import QApplication

    from desktop_organizer.ui.single_instance import SingleInstance

    key = f"DesktopOrganizerTest-{uuid.uuid4().hex[:8]}"
    first = SingleInstance(key)
    assert not first.notify_running(timeout_ms=200)  # nobody running yet
    assert first.listen()
    shown = []
    first.activated.connect(lambda: shown.append(True))

    second = SingleInstance(key)
    assert second.notify_running()
    for _ in range(50):
        QApplication.processEvents()
        if shown:
            break
    assert shown
    first.server.close()


def test_unexpected_error_is_logged_and_shown(app, monkeypatch):
    from desktop_organizer.ui import errors

    shown = []
    monkeypatch.setattr(errors, "show_error_dialog", lambda details: shown.append(details))
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = Capture()
    log.addHandler(handler)
    try:
        raise ValueError("boom")
    except ValueError as exc:
        errors.handle_exception(type(exc), exc, exc.__traceback__)
    finally:
        log.removeHandler(handler)
    assert "ValueError: boom" in shown[0] and "Desktop Organizer" in shown[0]
    assert any("boom" in r for r in records)


def test_update_flow_in_window(app, folder, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from desktop_organizer.ui import main_window
    from desktop_organizer.ui.main_window import MainWindow

    settings = Settings(folders=[])
    settings.add_folder(str(folder))
    win = MainWindow(Organizer(settings=settings, history=History(tmp_path / "h.db")))
    win.schedule_timer.stop()
    offered = []
    monkeypatch.setattr(win, "show_update", lambda info: offered.append(info.version))
    monkeypatch.setattr(main_window, "check_for_update", lambda: parse_release(RELEASE))

    # Automatic checks stay off until the user turns them on.
    win._auto_update_check()
    assert win.update_task is None

    win.settings.check_updates = True
    win._auto_update_check()
    win.update_task.wait(5000)
    for _ in range(50):
        QApplication.processEvents()
        if win.update_task is None:
            break
    assert offered == ["1.4.0"]
    assert win.settings.last_update_check

    # Checked recently: no new automatic check this week.
    win._auto_update_check()
    assert win.update_task is None
    win._quitting = True
    win.close()
