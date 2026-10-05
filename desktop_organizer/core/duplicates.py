"""Find files with identical contents."""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Folders that are never worth scanning (and can be huge).
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "$recycle.bin", "system volume information"}
_CHUNK = 1024 * 1024
_HEAD = 64 * 1024


@dataclass
class DuplicateGroup:
    size: int
    files: list[Path]  # oldest first; the first is the one to keep by default

    @property
    def wasted(self) -> int:
        return self.size * (len(self.files) - 1)


def find_duplicates(
    folder: Path,
    recursive: bool = True,
    min_size: int = 1,
    progress: Callable[[int, int, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[DuplicateGroup]:
    """Group files by identical content, biggest space savings first.

    Files are compared by size, then by a hash of their first 64 KB, and only
    then hashed in full, so most files are never read completely.
    """
    by_size: dict[int, list[Path]] = defaultdict(list)
    for path in _walk(folder, recursive):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size >= min_size:
            by_size[size].append(path)

    candidates = [(size, paths) for size, paths in by_size.items() if len(paths) > 1]
    total = sum(len(paths) for _, paths in candidates)
    done = 0
    groups = []
    for size, paths in candidates:
        by_head: dict[bytes, list[Path]] = defaultdict(list)
        for path in paths:
            if should_stop and should_stop():
                return []
            done += 1
            if progress:
                progress(done, total, path.name)
            digest = _hash(path, limit=_HEAD)
            if digest is not None:
                by_head[digest].append(path)
        for same_head in by_head.values():
            if len(same_head) < 2:
                continue
            if size <= _HEAD:  # the head hash already covered the whole file
                full_groups = [same_head]
            else:
                by_full: dict[bytes, list[Path]] = defaultdict(list)
                for path in same_head:
                    digest = _hash(path)
                    if digest is not None:
                        by_full[digest].append(path)
                full_groups = [g for g in by_full.values() if len(g) > 1]
            for files in full_groups:
                groups.append(DuplicateGroup(size, sorted(files, key=_age_key)))
    return sorted(groups, key=lambda g: g.wasted, reverse=True)


def _walk(folder: Path, recursive: bool):
    if not recursive:
        for entry in folder.iterdir():
            if entry.is_file() and not entry.is_symlink():
                yield entry
        return
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            path = Path(root, name)
            if not path.is_symlink():
                yield path


def _hash(path: Path, limit: int | None = None) -> bytes | None:
    digest = hashlib.blake2b(digest_size=20)
    remaining = limit
    try:
        with open(path, "rb") as handle:
            while remaining is None or remaining > 0:
                chunk = handle.read(_CHUNK if remaining is None else min(_CHUNK, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                if remaining is not None:
                    remaining -= len(chunk)
    except OSError:
        return None
    return digest.digest()


def _age_key(path: Path) -> tuple[float, int, str]:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = float("inf")
    # Prefer keeping the oldest file, then the one with the shortest name ("photo.jpg" over "photo (1).jpg").
    return (mtime, len(path.name), path.name.lower())
