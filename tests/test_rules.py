from datetime import datetime
from pathlib import Path

import pytest

from desktop_organizer.core.categories import OTHER, category_for
from desktop_organizer.core.config import Settings, SortMode
from desktop_organizer.core.rules import plan

from .conftest import make_file


@pytest.mark.parametrize(
    "mode, expected",
    [
        (SortMode.TYPE, Path("pdf")),
        (SortMode.CATEGORY, Path("Documents")),
        (SortMode.DATE, Path("2025", "01-January")),
        (SortMode.DATE_TYPE, Path("2025", "01-January", "pdf")),
        (SortMode.DATE_CATEGORY, Path("2025", "01-January", "Documents")),
    ],
)
def test_preset_structures(folder, mode, expected):
    make_file(folder, "Report.PDF", datetime(2025, 1, 5))
    [move] = plan(folder, Settings(pattern=mode.pattern))
    assert move.relative_target == expected


def test_category_lookup():
    assert category_for(".JPG") == "Images"
    assert category_for("xlsx") == "Spreadsheets"
    assert category_for("weird") == OTHER
    assert category_for("pdf", {"Invoices": ["PDF"]}) == "Invoices"


def test_plan_uses_modification_date_and_skips_folders(folder):
    make_file(folder, "photo.jpg", datetime(2024, 7, 1))
    (folder / "Existing Folder").mkdir()
    moves = plan(folder, Settings())
    assert [m.source.name for m in moves] == ["photo.jpg"]
    # Creation time is "now" for a freshly written file, so the older mtime must win.
    assert moves[0].relative_target == Path("2024", "07-July", "jpg")


def test_plan_skips_excluded_and_hidden(folder):
    make_file(folder, "keep.txt")
    make_file(folder, "Chrome.lnk")
    make_file(folder, "desktop.ini")
    make_file(folder, ".hidden")
    make_file(folder, "~$report.docx")
    assert [m.source.name for m in plan(folder, Settings())] == ["keep.txt"]


def test_custom_exclusions_accept_extension_without_dot(folder):
    make_file(folder, "a.txt")
    make_file(folder, "b.pdf")
    make_file(folder, "README")
    settings = Settings(excluded_extensions=["PDF"])
    assert [m.source.name for m in plan(folder, settings)] == ["a.txt", "README"]


def test_per_folder_structure(tmp_path):
    desktop, downloads = tmp_path / "Desktop", tmp_path / "Downloads"
    desktop.mkdir()
    downloads.mkdir()
    make_file(desktop, "a.txt")
    make_file(downloads, "b.zip")
    settings = Settings(folders=[])
    settings.add_folder(str(desktop))
    settings.add_folder(str(downloads), "{category}")
    assert plan(desktop, settings)[0].relative_target == Path("2025", "03-March", "txt")
    assert plan(downloads, settings)[0].relative_target == Path("Archives")


def test_add_folder_replaces_existing_and_keeps_known_names(tmp_path):
    settings = Settings(folders=[])
    settings.add_folder(str(tmp_path), "{type}")
    settings.add_folder(str(tmp_path), "{year}")
    assert len(settings.folders) == 1 and settings.folders[0].pattern == "{year}"
    assert settings.add_folder("Downloads").path == "downloads"
    assert settings.remove_folder(str(tmp_path))
    assert [f.path for f in settings.folders] == ["downloads"]


def test_extension_moves_between_custom_categories():
    settings = Settings()
    settings.set_category("Invoices", ["pdf", ".DOCX"])
    settings.set_category("Contracts", ["docx"])
    assert settings.custom_categories == {"Invoices": ["pdf"], "Contracts": ["docx"]}
    settings.set_category("Contracts", ["pdf"])
    assert settings.custom_categories == {"Contracts": ["pdf"]}


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(pattern="{category}/{year}", excluded_names=["x"])
    settings.add_folder("downloads", "{type}")
    settings.set_category("Invoices", ["pdf"])
    settings.save(path)
    assert Settings.load(path) == settings


def test_old_settings_are_migrated(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"sort_mode": "category"}')
    loaded = Settings.load(path)
    assert loaded.pattern == "{category}"
    assert [f.path for f in loaded.folders] == ["desktop"]


def test_invalid_saved_pattern_falls_back(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"pattern": "{nope}", "folders": [{"path": "downloads", "pattern": "../x"}]}')
    loaded = Settings.load(path)
    assert loaded.pattern == SortMode.DATE_TYPE.pattern
    assert loaded.folders[0].pattern is None


def test_corrupt_settings_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    assert Settings.load(path) == Settings()
