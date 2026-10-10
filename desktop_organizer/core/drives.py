"""USB drives, memory cards and network folders: what kind of drive a folder is on,
and whether it is plugged in right now."""

from __future__ import annotations

import sys
import time
from pathlib import Path

FIXED, REMOVABLE, NETWORK, OPTICAL, UNKNOWN = "fixed", "removable", "network", "optical", "unknown"
EXTERNAL = (REMOVABLE, NETWORK)

# A disconnected network share can take seconds to time out, so answers are remembered briefly.
_CONNECTED_TTL = 15.0
_connected: dict[str, tuple[float, bool]] = {}

_WINDOWS_TYPES = {2: REMOVABLE, 3: FIXED, 4: NETWORK, 5: OPTICAL, 6: FIXED}
_MOUNT_ROOTS = ("/Volumes/", "/media/", "/mnt/", "/run/media/")


def drive_root(path: Path) -> Path:
    """'E:\\' for a USB drive, '\\\\nas\\photos\\' for a network share, '/' elsewhere."""
    return Path(Path(path).anchor or "/")


def drive_type(path: Path) -> str:
    anchor = Path(path).anchor
    if sys.platform == "win32":
        if anchor.startswith("\\\\"):
            return NETWORK
        try:
            import ctypes

            kind = ctypes.windll.kernel32.GetDriveTypeW(anchor)
        except (OSError, AttributeError):
            return UNKNOWN
        return _WINDOWS_TYPES.get(kind, UNKNOWN)
    text = str(path)
    return REMOVABLE if text.startswith(_MOUNT_ROOTS) else FIXED


def is_external(path: Path) -> bool:
    return drive_type(path) in EXTERNAL


def is_connected(path: Path) -> bool:
    """True if the drive (or network share) that ``path`` lives on is available."""
    root = drive_root(path)
    key = str(root).lower()
    now = time.monotonic()
    cached = _connected.get(key)
    if cached and now - cached[0] < _CONNECTED_TTL:
        return cached[1]
    try:
        available = root.exists()
    except OSError:
        available = False
    _connected[key] = (now, available)
    return available


def forget() -> None:
    """Drop remembered answers, e.g. after the user plugs a drive in and clicks Refresh."""
    _connected.clear()


def label(path: Path) -> str:
    name = str(drive_root(path)).rstrip("\\") or "/"
    if drive_type(path) == NETWORK:
        return f"The network folder {name}"
    return f"The drive {name}"


def missing_message(path: Path) -> str:
    """Why ``path`` isn't there, in words a person can act on."""
    if not is_connected(path):
        what = "reconnect to the network" if drive_type(path) == NETWORK else "plug it in"
        return f"{label(path)} isn't connected. {what.capitalize()} and it will show up here."
    return f"{path} no longer exists. It may have been moved or renamed."
