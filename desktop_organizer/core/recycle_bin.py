"""Read the Windows Recycle Bin and put items back where they came from.

Each deleted item is a pair of files in ``<drive>:\\$Recycle.Bin\\<user SID>``:
``$I<id>`` holds the original path, size and deletion time; ``$R<id>`` is the
file (or folder) itself. Restoring moves ``$R`` back and removes ``$I``.
"""

from __future__ import annotations

import shutil
import struct
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

_FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class RecycledItem:
    original_path: Path
    deleted_at: datetime
    size: int
    info_file: Path
    data_path: Path

    @property
    def name(self) -> str:
        return self.original_path.name

    @property
    def is_folder(self) -> bool:
        return self.data_path.is_dir()


def parse_info(data: bytes) -> tuple[Path, int, datetime]:
    """Decode a ``$I`` file: (original path, size in bytes, deletion time)."""
    if len(data) < 24:
        raise ValueError("too short")
    version, size, filetime = struct.unpack_from("<qqq", data, 0)
    if version == 1:  # Windows Vista to 8.1: fixed 260-character path
        raw = data[24:24 + 520]
    elif version == 2:  # Windows 10 and 11: length-prefixed path
        (length,) = struct.unpack_from("<i", data, 24)
        raw = data[28:28 + length * 2]
    else:
        raise ValueError(f"unknown version {version}")
    path = raw.decode("utf-16-le", errors="replace").split("\x00", 1)[0]
    utc = _FILETIME_EPOCH + timedelta(microseconds=max(filetime, 0) // 10)
    try:
        deleted = utc.astimezone().replace(tzinfo=None)
    except (OSError, OverflowError, ValueError):  # dates Windows can't convert, e.g. a zeroed time
        deleted = utc.replace(tzinfo=None)
    return Path(path), size, deleted


def bin_folders() -> list[Path]:
    """This user's Recycle Bin folders on every fixed drive (other users' are not readable)."""
    if sys.platform != "win32":
        return []
    folders = []
    for drive in _fixed_drives():
        base = Path(f"{drive}:\\$Recycle.Bin")
        try:
            children = list(base.iterdir())
        except OSError:
            continue
        for child in children:
            try:
                if child.is_dir() and any(p.name.startswith("$I") for p in child.iterdir()):
                    folders.append(child)
            except OSError:  # another user's bin
                continue
    return folders


def list_items(folders: list[Path] | None = None) -> list[RecycledItem]:
    """Everything in the Recycle Bin, most recently deleted first."""
    items = []
    for folder in bin_folders() if folders is None else folders:
        try:
            infos = [p for p in folder.iterdir() if p.name.startswith("$I")]
        except OSError:
            continue
        for info in infos:
            data_path = info.with_name("$R" + info.name[2:])
            if not data_path.exists():
                continue
            try:
                original, size, deleted = parse_info(info.read_bytes())
            except (OSError, ValueError, struct.error):
                continue
            items.append(RecycledItem(original, deleted, size, info, data_path))
    return sorted(items, key=lambda i: i.deleted_at, reverse=True)


def restore(item: RecycledItem) -> Path:
    """Put an item back at its original location. If that name is taken, add ' (recovered N)'."""
    target = _free(item.original_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(item.data_path), str(target))
    item.info_file.unlink(missing_ok=True)
    return target


def _free(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem} (recovered {counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _fixed_drives() -> list[str]:
    import ctypes

    mask = ctypes.windll.kernel32.GetLogicalDrives()
    drives = []
    for i in range(26):
        if mask & (1 << i):
            letter = chr(ord("A") + i)
            if ctypes.windll.kernel32.GetDriveTypeW(f"{letter}:\\") == 3:  # DRIVE_FIXED
                drives.append(letter)
    return drives


def make_info(original: Path, size: int, deleted: datetime) -> bytes:
    """Build a Windows 10-style ``$I`` file (used by tests)."""
    path = str(original) + "\x00"
    filetime = int((deleted.astimezone(timezone.utc) - _FILETIME_EPOCH).total_seconds() * 10_000_000)
    return struct.pack("<qqqi", 2, size, filetime, len(path)) + path.encode("utf-16-le")
