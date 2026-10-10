"""Placeholders from inside files, renaming, content rules, other destinations and drives,
reports, storage stats, settings export/import, ready-made setups, file origins and the CLI."""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from desktop_organizer.core import (
    History,
    Organizer,
    Settings,
    content,
    drives,
    metadata,
    reports,
    rules,
    safety,
    setups,
    shell,
    transfer,
)
from desktop_organizer.core.auto import AutoOrganizer
from desktop_organizer.core.config import AutoMode, FolderProfile
from desktop_organizer.core.origin import find_origin
from desktop_organizer.core.stats import collect
from desktop_organizer.core.structure import PatternError, render, render_name, validate, validate_name
from desktop_organizer.core.user_rules import Condition, ConditionKind, Rule

from .conftest import make_file
from .fixtures import docx_with_text, flac_with_tags, jpeg_with_exif, m4a_with_tags, mp3_with_tags, pdf_with_text

WHEN = datetime(2025, 3, 14, 12, 0)


@pytest.fixture(autouse=True)
def fresh_caches():
    metadata.clear_cache()
    content.clear_cache()
    drives.forget()


def organizer_for(folder: Path, tmp_path: Path, **profile) -> Organizer:
    settings = Settings(folders=[FolderProfile(str(folder), **profile)])
    return Organizer(settings=settings, history=History(tmp_path / "h.db"))


# --- metadata placeholders ---------------------------------------------------------


def test_photo_date_and_camera_from_exif(tmp_path):
    photo = jpeg_with_exif(tmp_path / "IMG_0001.jpg")
    info = metadata.photo_info(photo)
    assert info.taken == datetime(2021, 7, 4, 10, 30) and info.camera == "Canon EOS R6"
    target = render("{photo_year}/{photo_month}/{camera}", photo, WHEN, 100)
    assert target == Path("2021", "07-July", "Canon EOS R6")


def test_camera_brand_is_added_when_the_model_lacks_it(tmp_path):
    photo = jpeg_with_exif(tmp_path / "a.jpg", make="samsung", model="SM-G991B")
    assert metadata.photo_info(photo).camera == "Samsung SM-G991B"


def test_photo_tokens_fall_back_to_the_file_date(folder):
    path = make_file(folder, "notes.txt")
    assert render("{photo_year}/{camera}", path, WHEN, 1) == Path("2025", "Unknown camera")


def test_music_tags_from_mp3_flac_and_m4a(tmp_path):
    mp3 = mp3_with_tags(tmp_path / "song.mp3")
    assert render("{artist}/{album}", mp3, WHEN, 1) == Path("Bob Marley", "Legend")
    compilation = mp3_with_tags(tmp_path / "comp.mp3", artist="Someone", album="Hits", album_artist="Various")
    assert metadata.audio_info(compilation).artist == "Various"
    assert metadata.audio_info(flac_with_tags(tmp_path / "a.flac")).album == "Pastel Blues"
    m4a = metadata.audio_info(m4a_with_tags(tmp_path / "a.m4a"))
    assert (m4a.artist, m4a.album) == ("Miles Davis", "Kind of Blue")


def test_untagged_or_broken_files_are_unknown(tmp_path):
    broken = tmp_path / "broken.mp3"
    broken.write_bytes(b"ID3\x03\x00\x00\x7f\x7f\x7f\x7f")
    assert render("{artist}", broken, WHEN, 1) == Path("Unknown artist")
    bad_photo = tmp_path / "bad.jpg"
    bad_photo.write_bytes(b"\xff\xd8\xff\xe1\x00")
    assert metadata.photo_info(bad_photo) is None


@pytest.mark.skipif(sys.platform != "win32", reason="Zone.Identifier is an NTFS feature")
def test_source_site_from_download_zone(folder):
    path = make_file(folder, "setup.exe")
    with open(f"{path}:Zone.Identifier", "w") as fh:
        fh.write("[ZoneTransfer]\nZoneId=3\nReferrerUrl=https://www.github.com/owner/repo\n"
                 "HostUrl=https://objects.githubusercontent.com/file.exe\n")
    assert render("{source}", path, WHEN, 1) == Path("github.com")
    assert render("{source}", make_file(folder, "local.txt"), WHEN, 1) == Path("Unknown source")


def test_file_contents_are_only_read_when_a_pattern_asks(folder, monkeypatch):
    path = make_file(folder, "a.jpg")
    monkeypatch.setattr(metadata, "photo_info", lambda p: pytest.fail("read the file needlessly"))
    assert render("{year}/{category}", path, WHEN, 1) == Path("2025", "Images")


# --- renaming ------------------------------------------------------------------------


def test_rename_templates_are_checked():
    assert validate_name("  {date} {name} ") == "{date} {name}"
    for bad in ("", "a/b", "{nope}", "x:y"):
        with pytest.raises(PatternError):
            validate_name(bad)
    with pytest.raises(PatternError):
        validate("{name}")  # only for file names, not folders


def test_render_name_keeps_extension(tmp_path):
    assert render_name("{date} {name}", Path("IMG_1.JPG"), WHEN, 1) == "2025-03-14 IMG_1.JPG"
    assert render_name("{photo_date} photo", jpeg_with_exif(tmp_path / "x.jpg"), WHEN, 1) == "2021-07-04 photo.jpg"


def test_organize_renames_and_undo_restores_the_name(folder, tmp_path):
    make_file(folder, "IMG_1.jpg")
    make_file(folder, "keep.txt")
    org = organizer_for(folder, tmp_path, pattern="{category}", rename="{date} {name}")
    org.settings.rules = [Rule("Texts", [Condition(ConditionKind.EXTENSION_IS, "txt")], destination="Text",
                               rename="note {name}")]
    moves = {m.source.name: m for m in org.preview(folder)}
    assert moves["IMG_1.jpg"].new_name == "2025-03-14 IMG_1.jpg"
    assert moves["keep.txt"].new_name == "note keep.txt"  # a rule's rename wins

    result = org.organize(folder)
    assert (folder / "Images" / "2025-03-14 IMG_1.jpg").exists()
    assert (folder / "Text" / "note keep.txt").exists()
    org.undo(result.run_id)
    assert (folder / "IMG_1.jpg").exists() and (folder / "keep.txt").exists()
    assert not (folder / "Images").exists()


def test_rename_clash_gets_a_number(folder, tmp_path):
    make_file(folder, "a.txt")
    make_file(folder, "b.txt")
    org = organizer_for(folder, tmp_path, pattern="{type}", rename="{date}")
    org.organize(folder)
    assert sorted(p.name for p in (folder / "txt").iterdir()) == ["2025-03-14.txt", "2025-03-14_1.txt"]


# --- content conditions ------------------------------------------------------------


def test_text_inside_pdf_word_and_text_files(folder):
    pdf = pdf_with_text(folder / "scan.pdf", "Invoice Number 42")
    docx = docx_with_text(folder / "letter.docx", "This Agree", "ment is made")
    txt = make_file(folder, "notes.txt", content="Payment\n   received, thanks")
    assert content.contains(pdf, "invoice number")
    assert content.contains(docx, "this agreement")
    assert content.contains(txt, "payment received")
    assert not content.contains(txt, "invoice")
    assert not content.contains(make_file(folder, "photo.jpg"), "x")


def test_content_rule_matches_and_reads_files_last(folder, tmp_path, monkeypatch):
    pdf_with_text(folder / "doc1.pdf", "Invoice Number 7")
    pdf_with_text(folder / "doc2.pdf", "Holiday plans")
    make_file(folder, "invoice-notes.txt", content="nothing")
    org = organizer_for(folder, tmp_path, pattern="{type}")
    org.settings.rules = [Rule("Invoices", [Condition(ConditionKind.CONTENT_CONTAINS, "invoice number"),
                                            Condition(ConditionKind.EXTENSION_IS, "pdf")],
                               destination="Invoices")]
    assert {m.source.name: m.rule for m in org.preview(folder)} == {
        "doc1.pdf": "Invoices", "doc2.pdf": None, "invoice-notes.txt": None}

    read = []
    real = content.contains
    monkeypatch.setattr(content, "contains", lambda p, n: (read.append(p.name), real(p, n))[1])
    org.preview(folder)
    assert "invoice-notes.txt" not in read  # the cheap 'type is pdf' check ruled it out first


# --- destinations and drives ------------------------------------------------------


def test_organize_into_another_folder_and_undo(folder, tmp_path):
    make_file(folder, "a.txt")
    archive = tmp_path / "USB" / "Archive"
    org = organizer_for(folder, tmp_path, pattern="{type}", destination=str(archive))
    [move] = org.preview(folder)
    assert move.root == archive and move.relative_target == Path("txt")
    result = org.organize(folder)
    assert (archive / "txt" / "a.txt").exists() and not (folder / "a.txt").exists()
    org.undo(result.run_id)
    assert (folder / "a.txt").exists()
    assert not archive.exists()  # folders the run created are removed again


def test_destination_drive_unplugged(folder, tmp_path, monkeypatch):
    make_file(folder, "a.txt")
    archive = tmp_path / "USB" / "Archive"
    org = organizer_for(folder, tmp_path, destination=str(archive), auto=AutoMode.WATCH)
    monkeypatch.setattr(drives, "is_connected", lambda path: not str(path).startswith(str(archive)))
    monkeypatch.setattr(drives, "drive_root", lambda path: Path(path))
    with pytest.raises(safety.DriveNotConnectedError, match="isn't connected"):
        org.preview(folder)
    with pytest.raises(safety.DriveNotConnectedError):
        org.organize(folder)
    auto = AutoOrganizer(org, settle_seconds=0)
    assert auto.run(org.settings.folders[0]) is None  # skipped quietly, tried again later
    assert (folder / "a.txt").exists()


def test_unplugged_source_folder(tmp_path, monkeypatch):
    gone = tmp_path / "E-drive" / "Photos"
    monkeypatch.setattr(drives, "is_connected", lambda path: False)
    with pytest.raises(safety.DriveNotConnectedError):
        safety.ensure_allowed(gone)
    monkeypatch.setattr(drives, "is_connected", lambda path: True)
    with pytest.raises(safety.UnsafeFolderError, match="not a folder"):
        safety.ensure_allowed(gone)


def test_removable_drive_root_is_allowed(tmp_path, monkeypatch):
    root = Path(tmp_path.anchor)
    with pytest.raises(safety.UnsafeFolderError, match="root of a drive"):
        safety.ensure_allowed(root)
    monkeypatch.setattr(drives, "is_external", lambda path: True)
    safety.ensure_allowed(root)


def test_destination_cant_be_a_system_folder(tmp_path):
    with pytest.raises(safety.UnsafeFolderError):
        safety.ensure_destination(Path(sys.prefix) if sys.platform != "win32" else Path(r"C:\Windows\Temp\x"))


def test_folder_settings_round_trip(tmp_path):
    settings = Settings(folders=[FolderProfile("downloads", rename="{date} {name}", destination=str(tmp_path))])
    loaded = Settings.from_dict(json.loads(json.dumps(settings.to_dict())))
    assert loaded.folders[0].rename == "{date} {name}"
    assert loaded.folders[0].destination == str(tmp_path)
    assert Settings().welcome_shown is False
    assert Settings.from_dict({}).welcome_shown is True  # people upgrading have seen enough welcomes


# --- reports -----------------------------------------------------------------------


def test_preview_and_run_reports(folder, tmp_path):
    make_file(folder, "a & b.txt")
    org = organizer_for(folder, tmp_path, pattern="{type}", rename="new {name}")
    preview = reports.preview_report(folder, "{type}", org.preview(folder))
    csv_path = reports.save(preview, tmp_path / "preview.csv")
    lines = csv_path.read_text(encoding="utf-8-sig").splitlines()
    assert lines[0] == "File,From,To,New name,Rule"
    assert "a & b.txt" in lines[1] and "new a & b.txt" in lines[1]

    result = org.organize(folder)
    org.undo(result.run_id)
    html_path = reports.save(reports.run_report(org.history, result.run_id), tmp_path / "run")
    page = html_path.read_text(encoding="utf-8")
    assert html_path.suffix == ".html"
    assert "a &amp; b.txt" in page and "Undone" in page and "<table>" in page
    with pytest.raises(ValueError):
        reports.run_report(org.history, 999)


# --- storage stats -------------------------------------------------------------------


def test_storage_stats(folder):
    make_file(folder, "big.mp4", content="x" * 5000)
    make_file(folder, "old.pdf", when=datetime(2015, 1, 1), content="x" * 300)
    (folder / "sub").mkdir()
    make_file(folder / "sub", "song.mp3", content="x" * 100)
    stats = collect(folder, stale_days=180, now=datetime(2025, 6, 1))
    assert stats.file_count == 3 and stats.folder_count == 1
    assert stats.total_size == 5400
    assert [e.path.name for e in stats.largest] == ["big.mp4", "old.pdf", "song.mp3"]
    assert stats.categories_by_size()[0][0] == "Videos"
    assert [e.path.name for e in stats.stale] == ["old.pdf"]  # the 2025 files count as recently used
    assert stats.stale_size == 300


# --- export / import and setups ------------------------------------------------------


def test_export_and_import_settings(tmp_path, folder):
    source = Settings(pattern="{category}/{year}", folders=[FolderProfile(str(folder), "{type}", AutoMode.WATCH,
                                                                          rename="{date} {name}")])
    source.rules = [Rule("Invoices", [Condition(ConditionKind.NAME_CONTAINS, "invoice")], destination="Money")]
    source.set_category("Design", ["psd", "fig"])
    path = transfer.export_file(source, tmp_path / "shared")
    assert path.suffix == ".json"

    target = Settings(folders=[])
    target.rules = [Rule("Invoices", [Condition(ConditionKind.NAME_CONTAINS, "bill")], destination="Old"),
                    Rule("Mine", [Condition(ConditionKind.NAME_CONTAINS, "x")], destination="X")]
    summary = transfer.apply(target, transfer.read_file(path))
    assert summary.rules_replaced == ["Invoices"] and [r.name for r in target.rules] == ["Invoices", "Mine"]
    assert target.rules[0].destination == "Money"
    assert target.custom_categories == {"Design": ["fig", "psd"]}
    assert target.pattern == "{category}/{year}"
    [profile] = target.folders
    assert profile.pattern == "{type}" and profile.rename == "{date} {name}"
    assert profile.auto is AutoMode.OFF  # never switched on by an import


def test_import_only_some_parts_and_skip_missing_folders(tmp_path):
    data = transfer.export_data(Settings(folders=[FolderProfile(str(tmp_path / "nowhere"))]))
    target = Settings(folders=[])
    summary = transfer.apply(target, data, [transfer.LAYOUTS])
    assert summary.folders_skipped and target.folders == []
    assert transfer.apply(Settings(), data, [transfer.CATEGORIES]).lines() == [
        "Nothing new to add. Your settings already match."]


def test_bad_import_files(tmp_path):
    for text, message in (("not json", "isn't a settings file"), ('{"kind": "other"}', "isn't a settings file"),
                          (json.dumps({"kind": transfer.KIND, "format": 99}), "newer version")):
        path = tmp_path / "bad.json"
        path.write_text(text)
        with pytest.raises(transfer.TransferError, match=message):
            transfer.read_file(path)


@pytest.mark.parametrize("setup", setups.SETUPS, ids=lambda s: s.key)
def test_every_setup_applies_cleanly(setup):
    settings = Settings(folders=[])
    summary = setup.apply(settings)
    assert not summary.rules_skipped and not summary.folders_skipped
    assert summary.rules_added and summary.folders_added
    for rule in settings.rules:
        rule.validate()


def test_photographer_setup_renames_pictures_by_date_taken():
    settings = Settings(folders=[])
    setups.get("photographer").apply(settings)
    pictures = next(f for f in settings.folders if f.path == "pictures")
    assert pictures.rename == "{photo_date} {name}" and pictures.pattern == "{photo_year}/{photo_month}"
    jpeg_with_exif(pictures.location / "IMG_9.jpg")
    [move] = rules.plan(pictures.location, settings)
    assert move.relative_target == Path("2021", "07-July") and move.new_name == "2021-07-04 IMG_9.jpg"


# --- where did this file come from? -----------------------------------------------


def test_origin_follows_every_move(folder, tmp_path):
    make_file(folder, "report.pdf")
    org = organizer_for(folder, tmp_path, pattern="{type}")
    first = org.organize(folder)
    moved = folder / "pdf" / "report.pdf"
    # Organizing again from the new place records a second hop.
    org.settings.add_folder(str(folder / "pdf"), "{year}")
    org.organize(folder / "pdf")
    final = folder / "pdf" / "2025" / "report.pdf"
    origin = find_origin(final, org.history)
    assert origin.original_path == folder / "report.pdf" and len(origin.moves) == 2
    assert "originally in" in origin.summary()
    assert find_origin(folder / "pdf" / "other.pdf", org.history).moves == []
    assert first.run_id and not moved.exists()


def test_shell_arguments():
    assert shell.parse_args(["app.exe", "--organize", "C:\\Users\\me\\Downloads"]) == (
        "organize", "C:\\Users\\me\\Downloads")
    assert shell.parse_args(["app.exe", "--where", '"C:\\a b.txt"']) == ("where", "C:\\a b.txt")
    assert shell.parse_args(["app.exe", "--minimized"]) is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry")
def test_shell_menu_entries_in_registry(monkeypatch):
    import winreg

    test_root = r"Software\DesktopOrganizerTests\Classes"
    monkeypatch.setattr(shell, "CLASSES", test_root)
    try:
        shell.set_enabled(True)
        assert shell.is_enabled()
        key = rf"{test_root}\Directory\shell\DesktopOrganizer.Organize\command"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
            command = winreg.QueryValueEx(handle, "")[0]
        assert command.endswith('--organize "%1"')
        shell.set_enabled(False)
        assert not shell.is_enabled()
    finally:
        shell.set_enabled(False)
        for sub in (r"Directory\Background\shell", r"Directory\shell", r"Directory\Background", "Directory",
                    r"Drive\shell", "Drive", r"*\shell", "*", ""):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{test_root}\{sub}".rstrip("\\"))
            except OSError:
                pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\DesktopOrganizerTests")
        except OSError:
            pass


# --- command line ----------------------------------------------------------------------


def test_cli_new_commands(folder, tmp_path, capsys):
    from desktop_organizer.cli import main

    make_file(folder, "IMG_1.jpg")
    assert main(["setups", "list"]) == 0
    assert "photographer" in capsys.readouterr().out
    assert main(["folders", "add", str(folder), "--pattern", "{type}", "--rename", "{date} {name}"]) == 0
    assert main(["preview", str(folder)]) == 0
    assert "(as 2025-03-14 IMG_1.jpg)" in capsys.readouterr().out
    assert main(["report", "preview", str(folder), "-o", str(tmp_path / "p.csv")]) == 0
    assert (tmp_path / "p.csv").exists()
    assert main(["organize", str(folder), "-y"]) == 0
    assert main(["report", "run", "-o", str(tmp_path / "r.html")]) == 0
    assert main(["where", str(folder / "jpg" / "2025-03-14 IMG_1.jpg")]) == 0
    assert "originally in" in capsys.readouterr().out
    assert main(["stats", str(folder)]) == 0
    assert "Images" in capsys.readouterr().out
    assert main(["settings", "export", str(tmp_path / "s.json"), "--only", "rules", "layouts"]) == 0
    assert main(["settings", "import", str(tmp_path / "s.json")]) == 0
    assert main(["setups", "apply", "nope"]) == 1
    assert main(["setups", "apply", "student"]) == 0
    assert "Student setup added" in capsys.readouterr().out
