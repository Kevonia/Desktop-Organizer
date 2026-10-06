import os
from pathlib import Path

import pytest

from desktop_organizer.core.safety import UnsafeFolderError, ensure_allowed, warnings


def test_normal_folder_is_allowed(folder):
    ensure_allowed(folder)
    assert warnings(folder) == []


@pytest.mark.parametrize("marker", [".git", "Dockerfile", "docker-compose.yml", "package.json", "App.sln"])
def test_project_folders_warn(folder, marker):
    (folder / marker).write_text("")
    [message] = warnings(folder)
    assert marker in message


def test_forbidden_folders():
    with pytest.raises(UnsafeFolderError):
        ensure_allowed(Path(Path.home().anchor))
    with pytest.raises(UnsafeFolderError):
        ensure_allowed(Path.home())
    if os.name == "nt":
        with pytest.raises(UnsafeFolderError):
            ensure_allowed(Path(os.environ["SystemRoot"]))


def test_missing_folder(tmp_path):
    with pytest.raises(UnsafeFolderError):
        ensure_allowed(tmp_path / "nope")
