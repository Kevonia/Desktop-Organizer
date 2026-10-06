import os
from datetime import datetime
from pathlib import Path

import pytest

from desktop_organizer.core import History, Organizer, Settings, paths, recycle_bin


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Never let tests touch the real settings, history, Desktop, Downloads, etc."""
    monkeypatch.setenv("DESKTOP_ORGANIZER_HOME", str(tmp_path / "appdata"))
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    def fake_known_folder(key: str) -> Path:
        path = fake_home / paths.KNOWN_FOLDERS[key][1]
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(paths, "known_folder", fake_known_folder)
    # Never list or restore from the real Recycle Bin.
    monkeypatch.setattr(recycle_bin, "bin_folders", lambda: [])
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: fake_home))


@pytest.fixture
def folder(tmp_path) -> Path:
    path = tmp_path / "Desktop"
    path.mkdir()
    return path


@pytest.fixture
def organizer(tmp_path) -> Organizer:
    return Organizer(settings=Settings(), history=History(tmp_path / "history.db"))


def make_file(folder: Path, name: str, when: datetime = datetime(2025, 3, 14, 12, 0), content: str = "x") -> Path:
    path = folder / name
    path.write_text(content)
    ts = when.timestamp()
    os.utime(path, (ts, ts))
    return path
