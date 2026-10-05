"""Send files to the Recycle Bin / Trash instead of deleting them, so they can be restored."""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


def send_to_trash(paths: list[Path]) -> list[tuple[Path, str]]:
    """Move each path to the trash. Returns (path, reason) for any that failed."""
    failed = []
    for path in paths:
        try:
            if not path.exists():
                raise FileNotFoundError("file no longer exists")
            if sys.platform == "win32":
                _windows_recycle(path)
            elif sys.platform == "darwin":
                _move_into(path, Path.home() / ".Trash")
            else:
                _freedesktop_trash(path)
        except OSError as exc:
            failed.append((path, exc.strerror or str(exc)))
    return failed


def _windows_recycle(path: Path) -> None:
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    fo_delete = 3
    flags = 0x0040 | 0x0010 | 0x0004 | 0x0400  # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
    operation = SHFILEOPSTRUCTW(
        hwnd=None, wFunc=fo_delete, pFrom=str(path.resolve()) + "\0", pTo=None, fFlags=flags,
    )
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted or path.exists():
        raise OSError(f"Windows couldn't move it to the Recycle Bin (code {result}).")


def _move_into(path: Path, trash_dir: Path) -> Path:
    trash_dir.mkdir(parents=True, exist_ok=True)
    target = trash_dir / path.name
    counter = 1
    while target.exists():
        target = trash_dir / f"{path.stem} {counter}{path.suffix}"
        counter += 1
    shutil.move(str(path), str(target))
    return target


def _freedesktop_trash(path: Path) -> None:
    base = Path.home() / ".local" / "share" / "Trash"
    target = _move_into(path, base / "files")
    info = base / "info"
    info.mkdir(parents=True, exist_ok=True)
    (info / f"{target.name}.trashinfo").write_text(
        f"[Trash Info]\nPath={quote(str(path.resolve()))}\nDeletionDate={datetime.now():%Y-%m-%dT%H:%M:%S}\n",
        encoding="utf-8",
    )
