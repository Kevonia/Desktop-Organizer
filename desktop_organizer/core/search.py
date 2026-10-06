"""Find files by name: where the organizer moved them, and what's in the saved folders now."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from desktop_organizer.core.history import History

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "$recycle.bin"}
MAX_DEPTH = 8


@dataclass(frozen=True)
class FoundFile:
    path: Path                      # where the file is now (or should be)
    moved_from: Path | None = None  # set when the organizer moved it
    moved_at: datetime | None = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def exists(self) -> bool:
        return self.path.exists()


def search(
    query: str,
    history: History,
    folders: Iterable[Path],
    limit: int = 300,
    should_stop: Callable[[], bool] | None = None,
) -> list[FoundFile]:
    """Files whose name contains ``query``: organizer moves first, then other matches on disk."""
    query = query.strip()
    if not query:
        return []
    results: list[FoundFile] = []
    seen: set[str] = set()

    for source, destination, when, undone in history.find_moves(query, limit):
        # An undone move put the file back where it came from.
        current = source if undone else destination
        key = _key(current)
        if key in seen:
            continue
        seen.add(key)
        results.append(FoundFile(current, None if undone else source, when))

    needle = query.lower()
    for folder in folders:
        for path in _walk(folder):
            if should_stop and should_stop():
                return results
            if len(results) >= limit:
                return results
            if needle in path.name.lower() and _key(path) not in seen:
                seen.add(_key(path))
                results.append(FoundFile(path))
    return results


def _walk(folder: Path):
    base_depth = str(folder).count(os.sep)
    for root, dirs, files in os.walk(folder):
        if root.count(os.sep) - base_depth >= MAX_DEPTH:
            dirs[:] = []
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            yield Path(root, name)


def _key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))
