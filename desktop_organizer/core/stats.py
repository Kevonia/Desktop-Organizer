"""Storage stats: what's taking up space in a folder, the biggest files, and files
nobody has opened or changed in a long time. Read-only."""

from __future__ import annotations

import heapq
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from desktop_organizer.core.categories import category_for
from desktop_organizer.core.search import SKIP_DIRS

MAX_DEPTH = 12
TOP_FILES = 100
DEFAULT_STALE_DAYS = 180


@dataclass(frozen=True)
class FileEntry:
    path: Path
    size: int
    last_used: datetime  # the later of last opened and last changed


@dataclass
class CategoryTotal:
    count: int = 0
    size: int = 0


@dataclass
class FolderStats:
    folder: Path
    stale_days: int
    total_size: int = 0
    file_count: int = 0
    folder_count: int = 0
    by_category: dict[str, CategoryTotal] = field(default_factory=dict)
    largest: list[FileEntry] = field(default_factory=list)
    stale: list[FileEntry] = field(default_factory=list)
    stale_size: int = 0
    stale_count: int = 0
    unreadable: int = 0
    stopped: bool = False

    def categories_by_size(self) -> list[tuple[str, CategoryTotal]]:
        return sorted(self.by_category.items(), key=lambda item: item[1].size, reverse=True)


def collect(
    folder: Path,
    custom_categories: Mapping[str, Iterable[str]] | None = None,
    stale_days: int = DEFAULT_STALE_DAYS,
    top: int = TOP_FILES,
    progress: Callable[[int, int, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    now: datetime | None = None,
) -> FolderStats:
    """Walk ``folder`` (and its subfolders) and add up what's in it."""
    now = now or datetime.now()
    cutoff = (now - timedelta(days=stale_days)).timestamp()
    result = FolderStats(folder=folder, stale_days=stale_days)
    largest: list[tuple[int, str, FileEntry]] = []
    stale: list[tuple[int, str, FileEntry]] = []
    base_depth = str(folder).rstrip(os.sep).count(os.sep)

    for root, dirs, files in os.walk(folder, onerror=lambda _: _count_unreadable(result)):
        if should_stop and should_stop():
            result.stopped = True
            break
        if root.count(os.sep) - base_depth >= MAX_DEPTH:
            dirs[:] = []
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith(".")]
        result.folder_count += len(dirs)
        for name in files:
            path = Path(root, name)
            try:
                st = path.stat()
            except OSError:
                result.unreadable += 1
                continue
            size = st.st_size
            used = max(st.st_atime, st.st_mtime)
            entry = FileEntry(path, size, datetime.fromtimestamp(used))
            result.file_count += 1
            result.total_size += size
            total = result.by_category.setdefault(category_for(path.suffix, custom_categories), CategoryTotal())
            total.count += 1
            total.size += size
            _keep_largest(largest, (size, str(path), entry), top)
            if used < cutoff:
                result.stale_count += 1
                result.stale_size += size
                _keep_largest(stale, (size, str(path), entry), top)
            if progress and result.file_count % 250 == 0:
                progress(result.file_count, 0, name)

    result.largest = [item[2] for item in sorted(largest, reverse=True)]
    result.stale = [item[2] for item in sorted(stale, reverse=True)]
    return result


def _keep_largest(heap: list, item: tuple, limit: int) -> None:
    if len(heap) < limit:
        heapq.heappush(heap, item)
    elif item[:2] > heap[0][:2]:
        heapq.heapreplace(heap, item)


def _count_unreadable(result: FolderStats) -> None:
    result.unreadable += 1


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"
