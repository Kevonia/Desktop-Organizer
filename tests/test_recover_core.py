import os
import time
from datetime import datetime
from pathlib import Path

import pytest

from desktop_organizer.core import History, Organizer, Settings
from desktop_organizer.core.recycle_bin import list_items, make_info, parse_info, restore
from desktop_organizer.core.search import search
from desktop_organizer.core.versions import VersionStore

from .conftest import make_file


def edit(path: Path, text: str, seconds_later: float) -> None:
    """Write new contents with a distinct, later modification time."""
    path.write_text(text)
    t = time.time() + seconds_later
    os.utime(path, (t, t))


# --- versions --------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    return VersionStore(tmp_path / "store", keep=4)


def test_keeps_only_the_last_four_versions(store, tmp_path):
    folder = tmp_path / "Work"
    folder.mkdir()
    doc = folder / "report.docx"
    for i in range(6):
        edit(doc, f"draft {i}", i)
        store.scan([folder])
    versions = store.versions(doc)
    assert len(versions) == 4
    assert [v.blob.read_text() for v in versions] == ["draft 5", "draft 4", "draft 3", "draft 2"]
    # Pruned copies are removed from disk too.
    assert len(list((store.blobs).rglob("*.docx"))) == 4


def test_unchanged_files_are_not_saved_again(store, tmp_path):
    folder = tmp_path / "Work"
    folder.mkdir()
    doc = folder / "notes.txt"
    edit(doc, "same", 0)
    assert store.scan([folder]) == 1
    assert store.scan([folder]) == 0
    edit(doc, "same", 5)  # touched, contents unchanged
    assert store.scan([folder]) == 0
    assert len(store.versions(doc)) == 1


def test_restore_old_version_and_it_can_be_reversed(store, tmp_path):
    folder = tmp_path / "Work"
    folder.mkdir()
    doc = folder / "plan.txt"
    for i, text in enumerate(["v1", "v2", "v3", "v4"]):
        edit(doc, text, i)
        store.scan([folder])
    oldest = store.versions(doc)[-1]
    assert oldest.blob.read_text() == "v1"
    store.restore(oldest)
    assert doc.read_text() == "v1"
    # The version that was current before the restore is still available.
    assert "v4" in [v.blob.read_text() for v in store.versions(doc)]


def test_deleted_file_can_be_brought_back(store, tmp_path):
    folder = tmp_path / "Work"
    folder.mkdir()
    doc = folder / "contract.pdf"
    edit(doc, "signed", 0)
    store.scan([folder])
    doc.unlink()
    [entry] = store.files("contract")
    assert not entry.exists
    store.restore(store.versions(entry.path)[0])
    assert doc.read_text() == "signed"


def test_skips_big_temp_and_hidden_files(tmp_path):
    store = VersionStore(tmp_path / "store", max_mb=1)
    folder = tmp_path / "Work"
    (folder / ".git").mkdir(parents=True)
    (folder / "big.bin").write_bytes(b"x" * 2_000_000)
    for name in ("~$doc.docx", "movie.crdownload", ".hidden", "shortcut.lnk"):
        (folder / name).write_text("x")
    (folder / ".git" / "config").write_text("x")
    (folder / "keep.txt").write_text("x")
    store.scan([folder])
    assert [f.path.name for f in store.files()] == ["keep.txt"]


def test_versions_follow_files_the_organizer_moves(folder, tmp_path):
    settings = Settings(version_folders=[str(folder)])
    organizer = Organizer(settings=settings, history=History(tmp_path / "h.db"),
                          versions=VersionStore(tmp_path / "store"))
    doc = make_file(folder, "essay.txt", content="first")
    organizer.versions.scan([folder])
    result = organizer.organize(folder)
    [(_, moved_to)] = result.moved
    assert len(organizer.versions.versions(moved_to)) == 1
    organizer.undo_last()
    assert len(organizer.versions.versions(doc)) == 1


def test_version_settings_round_trip_and_limits(tmp_path):
    path = tmp_path / "s.json"
    Settings(version_folders=["documents"], versions_to_keep=6).save(path)
    loaded = Settings.load(path)
    assert loaded.version_folders == ["documents"] and loaded.versions_to_keep == 6
    path.write_text('{"versions_to_keep": 999, "version_max_mb": "x"}')
    loaded = Settings.load(path)
    assert loaded.versions_to_keep == 20 and loaded.version_max_mb == 50


# --- recycle bin -----------------------------------------------------------------------


def fake_bin(tmp_path, name, original, content="data", deleted=datetime(2026, 9, 1, 14, 30)):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / f"$I{name}").write_bytes(make_info(original, len(content), deleted))
    (bin_dir / f"$R{name}").write_text(content)
    return bin_dir


def test_parse_windows_10_info_file(tmp_path):
    original = tmp_path / "Docs" / "Budget 2026.xlsx"
    path, size, deleted = parse_info(make_info(original, 1234, datetime(2026, 9, 1, 14, 30)))
    assert path == original and size == 1234
    assert deleted == datetime(2026, 9, 1, 14, 30)


def test_parse_windows_8_info_file():
    import struct
    raw = struct.pack("<qqq", 1, 10, 0) + "C:\\Old\\a.txt".encode("utf-16-le").ljust(520, b"\0")
    path, size, _ = parse_info(raw)
    assert str(path) == "C:\\Old\\a.txt" and size == 10


def test_list_and_restore_items(tmp_path):
    original = tmp_path / "Docs" / "letter.docx"
    bin_dir = fake_bin(tmp_path, "ABC123.docx", original)
    (bin_dir / "$IORPHAN.txt").write_bytes(make_info(tmp_path / "x.txt", 1, datetime.now()))  # no $R
    (bin_dir / "desktop.ini").write_text("x")
    [item] = list_items([bin_dir])
    assert item.name == "letter.docx" and item.original_path == original
    assert restore(item) == original
    assert original.read_text() == "data"
    assert list_items([bin_dir]) == []


def test_restore_never_overwrites(tmp_path):
    original = tmp_path / "Docs" / "letter.docx"
    original.parent.mkdir(parents=True)
    original.write_text("newer")
    bin_dir = fake_bin(tmp_path, "XYZ.docx", original, content="old")
    restored = restore(list_items([bin_dir])[0])
    assert restored.name == "letter (recovered 1).docx"
    assert original.read_text() == "newer" and restored.read_text() == "old"


# --- search ----------------------------------------------------------------------------


def test_search_finds_moved_and_existing_files(folder, organizer, tmp_path):
    make_file(folder, "Invoice March.pdf")
    make_file(folder, "notes.txt")
    organizer.organize(folder)
    (folder / "Old invoices").mkdir()
    make_file(folder / "Old invoices", "invoice-2019.pdf")

    results = search("invoice", organizer.history, [folder])
    names = {r.name: r for r in results}
    moved = names["Invoice March.pdf"]
    assert moved.moved_from == folder / "Invoice March.pdf"
    assert moved.exists and moved.path.parent.name == "pdf"
    assert names["invoice-2019.pdf"].moved_from is None
    assert "notes.txt" not in names
    # Each file appears once even though the moved file is also on disk.
    assert len(results) == 2


def test_search_after_undo_points_to_original_place(folder, organizer):
    make_file(folder, "photo.jpg")
    organizer.organize(folder)
    organizer.undo_last()
    [found] = search("photo", organizer.history, [])
    assert found.path == folder / "photo.jpg" and found.moved_from is None and found.exists


def test_empty_query_returns_nothing(organizer, folder):
    assert search("  ", organizer.history, [folder]) == []
