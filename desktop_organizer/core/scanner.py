"""Find the files in a folder that are eligible to be organized."""

from __future__ import annotations

import stat
from pathlib import Path

from desktop_organizer.core.config import Settings

_WINDOWS_HIDDEN = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0x2) | getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 0x4)


def scan(folder: Path, settings: Settings) -> list[Path]:
    """Return the top-level files in ``folder`` that should be moved, sorted by name.

    Subfolders are never touched, so files already organized stay where they are.
    """
    files = []
    for entry in folder.iterdir():
        try:
            if not entry.is_file() or entry.is_symlink():
                continue
            if is_skipped(entry, settings):
                continue
        except OSError:
            continue
        files.append(entry)
    return sorted(files, key=lambda p: p.name.lower())


def is_skipped(path: Path, settings: Settings) -> bool:
    name = path.name
    # Office lock files (~$report.docx) belong to an open document.
    if name.startswith("~$"):
        return True
    if settings.is_name_excluded(path) or settings.is_extension_excluded(path):
        return True
    if settings.skip_hidden and _is_hidden(path):
        return True
    return False


def _is_hidden(path: Path) -> bool:
    if path.name.startswith("."):
        return True
    attributes = getattr(path.stat(), "st_file_attributes", 0)
    return bool(attributes & _WINDOWS_HIDDEN)
