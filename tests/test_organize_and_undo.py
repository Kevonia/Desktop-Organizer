from datetime import datetime

from desktop_organizer.cli import main

from .conftest import make_file


def test_organize_moves_files(folder, organizer):
    make_file(folder, "notes.txt", datetime(2025, 2, 1))
    result = organizer.organize(folder)
    assert len(result.moved) == 1
    assert not (folder / "notes.txt").exists()
    assert (folder / "2025" / "02-February" / "txt" / "notes.txt").read_text() == "x"


def test_duplicate_names_get_suffix(folder, organizer):
    target = folder / "2025" / "03-March" / "txt"
    target.mkdir(parents=True)
    (target / "notes.txt").write_text("old")
    make_file(folder, "notes.txt", content="new")

    organizer.organize(folder)
    assert (target / "notes.txt").read_text() == "old"
    assert (target / "notes_1.txt").read_text() == "new"


def test_undo_restores_files_and_removes_created_folders(folder, organizer):
    make_file(folder, "a.txt")
    make_file(folder, "b.pdf")
    organizer.organize(folder)

    result = organizer.undo_last()
    assert result is not None and not result.failed
    assert sorted(p.name for p in folder.iterdir()) == ["a.txt", "b.pdf"]
    assert organizer.history.last_undoable_run() is None


def test_undo_keeps_folders_that_existed_before(folder, organizer):
    existing = folder / "2025" / "03-March" / "txt"
    existing.mkdir(parents=True)
    (existing / "keep.txt").write_text("k")
    (folder / "2025" / "empty-but-mine").mkdir()
    make_file(folder, "a.txt")

    organizer.organize(folder)
    organizer.undo_last()
    assert (existing / "keep.txt").exists()
    assert (folder / "2025" / "empty-but-mine").is_dir()


def test_undo_does_not_overwrite_new_file_with_same_name(folder, organizer):
    make_file(folder, "a.txt", content="original")
    organizer.organize(folder)
    (folder / "a.txt").write_text("newer")

    organizer.undo_last()
    assert (folder / "a.txt").read_text() == "newer"
    assert (folder / "a (restored 1).txt").read_text() == "original"


def test_undo_reports_files_the_user_moved_elsewhere(folder, organizer, tmp_path):
    make_file(folder, "a.txt")
    make_file(folder, "b.txt")
    result = organizer.organize(folder)
    moved_a = next(dst for src, dst in result.moved if src.name == "a.txt")
    moved_a.rename(tmp_path / "elsewhere.txt")

    undo = organizer.undo_last()
    assert [p.name for p in folder.iterdir() if p.is_file()] == ["b.txt"]
    assert len(undo.failed) == 1
    # Partially undone runs stay undoable so the user can retry.
    assert organizer.history.last_undoable_run() is not None


def test_undo_with_nothing_to_undo(organizer):
    assert organizer.undo_last() is None


def test_history_lists_runs(folder, organizer):
    make_file(folder, "a.txt")
    organizer.organize(folder)
    runs = organizer.history.runs()
    assert len(runs) == 1 and runs[0].move_count == 1 and runs[0].can_undo


def test_cli_end_to_end(folder, capsys):
    make_file(folder, "a.txt")
    assert main(["preview", str(folder)]) == 0
    assert "a.txt -> 2025/03-March/txt/" in capsys.readouterr().out
    assert (folder / "a.txt").exists()

    assert main(["organize", str(folder), "--mode", "category", "--yes"]) == 0
    assert (folder / "Documents" / "a.txt").exists()

    assert main(["undo", "--yes"]) == 0
    assert (folder / "a.txt").exists()
    assert not (folder / "Documents").exists()


def test_cli_saved_folders_and_custom_structure(tmp_path):
    docs = tmp_path / "Docs"
    docs.mkdir()
    make_file(docs, "plan.pdf")
    assert main(["folders", "add", str(docs), "--pattern", "Work/{category}/{year}"]) == 0
    assert main(["categories", "add", "Plans", "pdf"]) == 0
    assert main(["organize", "--all", "--yes"]) == 0
    assert (docs / "Work" / "Plans" / "2025" / "plan.pdf").exists()


def test_cli_refuses_project_folder_without_force(folder, capsys):
    (folder / "Dockerfile").write_text("FROM python")
    make_file(folder, "a.txt")
    assert main(["organize", str(folder), "--yes"]) == 1
    assert (folder / "a.txt").exists()
    assert main(["organize", str(folder), "--yes", "--force"]) == 0
    assert not (folder / "a.txt").exists()


def test_cli_rejects_bad_pattern(folder, capsys):
    assert main(["preview", str(folder), "--pattern", "{nope}"]) == 1
    assert "Unknown placeholder" in capsys.readouterr().out
