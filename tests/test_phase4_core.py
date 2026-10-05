import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from desktop_organizer.core import startup, trash
from desktop_organizer.core.auto import AutoOrganizer
from desktop_organizer.core.config import AutoMode, Settings
from desktop_organizer.core.duplicates import find_duplicates
from desktop_organizer.core.rules import plan
from desktop_organizer.core.user_rules import Condition, ConditionKind, Rule, RuleAction, RuleError

from .conftest import make_file

K = ConditionKind


def rule(name, *conditions, action=RuleAction.MOVE, destination="Matched", match_all=True, folders=()):
    return Rule(name, [Condition(k, v) for k, v in conditions], match_all, action, destination,
                folders=list(folders))


# --- rules -----------------------------------------------------------------------


def test_rule_moves_matching_files_and_others_use_structure(folder):
    make_file(folder, "Invoice-0042.pdf", datetime(2025, 6, 1))
    make_file(folder, "notes.pdf", datetime(2025, 6, 1))
    settings = Settings(pattern="{type}")
    settings.rules = [rule("Invoices", (K.NAME_CONTAINS, "invoice"), (K.EXTENSION_IS, "pdf"),
                           destination="Finance/Invoices/{year}")]
    moves = {m.source.name: m for m in plan(folder, settings)}
    assert moves["Invoice-0042.pdf"].relative_target == Path("Finance", "Invoices", "2025")
    assert moves["Invoice-0042.pdf"].rule == "Invoices"
    assert moves["notes.pdf"].relative_target == Path("pdf") and moves["notes.pdf"].rule is None


def test_skip_rule_leaves_files_alone(folder):
    make_file(folder, "keep-me.txt")
    make_file(folder, "other.txt")
    settings = Settings()
    settings.rules = [rule("Pinned", (K.NAME_STARTS_WITH, "keep"), action=RuleAction.SKIP)]
    assert [m.source.name for m in plan(folder, settings)] == ["other.txt"]


def test_first_matching_rule_wins_and_disabled_rules_are_ignored(folder):
    make_file(folder, "IMG_001.jpg")
    settings = Settings()
    first = rule("First", (K.NAME_MATCHES, "img_*.jpg"), destination="A")
    second = rule("Second", (K.EXTENSION_IS, "jpg"), destination="B")
    settings.rules = [first, second]
    assert plan(folder, settings)[0].relative_target == Path("A")
    first.enabled = False
    assert plan(folder, settings)[0].relative_target == Path("B")


def test_match_any_size_and_age_conditions(folder):
    big = make_file(folder, "big.bin", datetime.now() - timedelta(days=40), content="x" * 2_000_000)
    now = datetime.now()
    when = datetime.fromtimestamp(big.stat().st_mtime)
    size = big.stat().st_size
    assert rule("r", (K.LARGER_THAN_MB, "1")).matches(big, size, when, now)
    assert not rule("r", (K.SMALLER_THAN_MB, "1")).matches(big, size, when, now)
    assert rule("r", (K.OLDER_THAN_DAYS, "30")).matches(big, size, when, now)
    assert not rule("r", (K.NEWER_THAN_DAYS, "30")).matches(big, size, when, now)
    any_rule = rule("r", (K.NAME_CONTAINS, "nope"), (K.LARGER_THAN_MB, "1"), match_all=False)
    assert any_rule.matches(big, size, when, now)


def test_rule_limited_to_a_folder(tmp_path):
    a, b = tmp_path / "A", tmp_path / "B"
    a.mkdir()
    b.mkdir()
    make_file(a, "x.txt")
    make_file(b, "x.txt")
    settings = Settings(pattern="{type}")
    settings.rules = [rule("Only A", (K.EXTENSION_IS, "txt"), destination="RuleHit", folders=[str(a)])]
    assert plan(a, settings)[0].relative_target == Path("RuleHit")
    assert plan(b, settings)[0].relative_target == Path("txt")


@pytest.mark.parametrize("bad", [
    Rule("", [Condition(K.NAME_CONTAINS, "x")], destination="A"),
    Rule("No conditions", [], destination="A"),
    Rule("Empty value", [Condition(K.NAME_CONTAINS, " ")], destination="A"),
    Rule("Bad number", [Condition(K.LARGER_THAN_MB, "big")], destination="A"),
    Rule("Bad destination", [Condition(K.NAME_CONTAINS, "x")], destination="../out"),
])
def test_invalid_rules(bad):
    with pytest.raises(RuleError):
        bad.validate()


def test_rules_and_auto_mode_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings()
    settings.rules = [rule("Invoices", (K.NAME_CONTAINS, "invoice"), destination="Finance")]
    settings.folders[0].auto = AutoMode.HOURLY
    settings.notifications = False
    settings.save(path)
    loaded = Settings.load(path)
    assert loaded == settings
    # Updating a folder's structure keeps its auto mode.
    loaded.add_folder("desktop", "{type}")
    assert loaded.folders[0].auto is AutoMode.HOURLY


def test_in_progress_downloads_are_never_moved(folder):
    make_file(folder, "movie.mp4.crdownload")
    make_file(folder, "song.part")
    make_file(folder, "done.zip")
    assert [m.source.name for m in plan(folder, Settings())] == ["done.zip"]


# --- auto-organize -------------------------------------------------------------------


def test_auto_waits_for_files_to_settle(folder, organizer):
    organizer.settings.folders = []
    profile = organizer.settings.add_folder(str(folder))
    profile.auto = AutoMode.WATCH
    fresh = folder / "just-downloaded.zip"
    fresh.write_text("x")  # modified right now
    make_file(folder, "older.zip")  # modified in 2025

    auto = AutoOrganizer(organizer, settle_seconds=60)
    [(_, result)] = auto.run_due()
    assert [src.name for src, _ in result.moved] == ["older.zip"]
    assert fresh.exists()

    old = time.time() - 120
    os.utime(fresh, (old, old))
    [(_, result)] = auto.run_due()
    assert [src.name for src, _ in result.moved] == ["just-downloaded.zip"]


def test_hourly_schedule(folder, organizer):
    organizer.settings.folders = []
    profile = organizer.settings.add_folder(str(folder))
    profile.auto = AutoMode.HOURLY
    auto = AutoOrganizer(organizer, settle_seconds=0)
    now = datetime.now()
    assert auto.is_due(profile, now)
    make_file(folder, "a.txt")
    assert len(auto.run_due(now)) == 1
    make_file(folder, "b.txt")
    assert auto.run_due(now + timedelta(minutes=30)) == []
    assert (folder / "b.txt").exists()
    assert len(auto.run_due(now + timedelta(minutes=61))) == 1
    assert not (folder / "b.txt").exists()


def test_off_folders_are_never_touched(folder, organizer):
    make_file(folder, "a.txt")
    organizer.settings.folders = []
    organizer.settings.add_folder(str(folder))
    assert AutoOrganizer(organizer, settle_seconds=0).run_due() == []
    assert (folder / "a.txt").exists()


def test_history_stats(folder, organizer):
    make_file(folder, "a.txt")
    make_file(folder, "b.txt")
    organizer.organize(folder)
    assert organizer.history.stats() == (2, 1)
    assert organizer.history.last_run_time(folder) is not None


# --- duplicates ----------------------------------------------------------------------


def test_find_duplicates(tmp_path):
    root = tmp_path / "dups"
    (root / "sub").mkdir(parents=True)
    (root / ".git").mkdir()
    big = "y" * 200_000
    make_file(root, "photo.jpg", datetime(2024, 1, 1), content=big)
    make_file(root / "sub", "photo (1).jpg", datetime(2025, 1, 1), content=big)
    make_file(root, "copy.jpg", datetime(2025, 2, 1), content=big)
    make_file(root, "same-size-different.jpg", content="z" * 200_000)
    make_file(root, "a.txt", content="hello")
    make_file(root, "b.txt", content="hello")
    make_file(root / ".git", "ignored.txt", content="hello")

    groups = find_duplicates(root)
    assert [len(g.files) for g in groups] == [3, 2]
    assert groups[0].files[0].name == "photo.jpg"  # oldest kept first
    assert groups[0].wasted == 400_000
    assert {p.name for p in groups[1].files} == {"a.txt", "b.txt"}
    assert [len(g.files) for g in find_duplicates(root, recursive=False)] == [2, 2]


# --- trash & startup ---------------------------------------------------------------


def test_trash_reports_missing_files(tmp_path):
    [(path, reason)] = trash.send_to_trash([tmp_path / "missing.txt"])
    assert path.name == "missing.txt" and reason


def test_move_into_trash_folder_avoids_name_clashes(tmp_path):
    bin_dir = tmp_path / "bin"
    first = make_file(tmp_path, "a.txt")
    trash._move_into(first, bin_dir)
    second = make_file(tmp_path, "a.txt")
    trash._move_into(second, bin_dir)
    assert sorted(p.name for p in bin_dir.iterdir()) == ["a 1.txt", "a.txt"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry")
def test_start_with_windows_toggle(monkeypatch):
    import winreg

    monkeypatch.setattr(startup, "RUN_KEY", r"Software\DesktopOrganizerTest")
    try:
        assert not startup.is_enabled()
        startup.set_enabled(True)
        assert startup.is_enabled()
        startup.set_enabled(False)
        assert not startup.is_enabled()
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\DesktopOrganizerTest")
        except OSError:
            pass
    assert startup.MINIMIZED_FLAG in startup.launch_command()
