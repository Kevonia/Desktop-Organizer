"""Locate the user's standard folders and the app's data directory on each platform."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "DesktopOrganizer"

# Lets tests and development builds keep their data away from the real install.
DATA_DIR_ENV = "DESKTOP_ORGANIZER_HOME"

# name -> (Windows KNOWNFOLDERID, fallback folder name under the home directory)
KNOWN_FOLDERS: dict[str, tuple[str, str]] = {
    "desktop": ("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}", "Desktop"),
    "documents": ("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}", "Documents"),
    "downloads": ("{374DE290-123F-4565-9164-39C4925E467B}", "Downloads"),
    "pictures": ("{33E28130-4E1E-4676-835A-98395C3BC3BB}", "Pictures"),
    "music": ("{4BD8D571-6D19-48D3-BE97-422220080E43}", "Music"),
    "videos": ("{18989B1D-99B5-455B-841C-AB7C74E4DDFC}", "Movies" if sys.platform == "darwin" else "Videos"),
}
_ALIASES = {"docs": "documents", "download": "downloads", "photos": "pictures", "movies": "videos"}


def known_folder_key(spec: str) -> str | None:
    """Return the KNOWN_FOLDERS key for names like 'Downloads' or 'docs', else None."""
    key = spec.strip().lower()
    key = _ALIASES.get(key, key)
    return key if key in KNOWN_FOLDERS else None


def known_folder(key: str) -> Path:
    """Return a standard folder, following Windows redirects (e.g. to OneDrive)."""
    guid, fallback = KNOWN_FOLDERS[key]
    if sys.platform == "win32":
        path = _windows_known_folder(guid)
        if path is not None:
            return path
    return Path.home() / fallback


def desktop_dir() -> Path:
    return known_folder("desktop")


def resolve_folder(spec: str) -> Path:
    """Turn a saved folder spec (a known name like 'downloads', or a path) into a path."""
    key = known_folder_key(spec)
    if key:
        return known_folder(key)
    return Path(os.path.expandvars(spec)).expanduser()


def display_name(spec: str) -> str:
    key = known_folder_key(spec)
    if key:
        return KNOWN_FOLDERS[key][1]
    path = resolve_folder(spec)
    return path.name or str(path)


def same_path(a: Path, b: Path) -> bool:
    return _norm(a) == _norm(b)


def is_within(path: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath([_norm(path), _norm(parent)]) == _norm(parent)
    except ValueError:  # different drives on Windows
        return False


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def app_data_dir() -> Path:
    """Return (and create) the folder that holds settings and the undo history."""
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_DIR_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = (Path(xdg) if xdg else Path.home() / ".local" / "share") / APP_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def _windows_known_folder(guid: str) -> Path | None:
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", wintypes.BYTE * 8),
            ]

        folder_id = GUID.from_buffer_copy(uuid.UUID(guid).bytes_le)
        result = ctypes.c_wchar_p()
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(folder_id), 0, None, ctypes.byref(result)
        )
        try:
            if hr != 0 or not result.value:
                return None
            return Path(result.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(result)
    except (OSError, AttributeError, ValueError):
        return None
