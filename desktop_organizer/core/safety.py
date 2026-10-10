"""Stop the organizer from rearranging folders where moving files would break things."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from desktop_organizer.core import drives
from desktop_organizer.core.paths import app_data_dir, is_within, same_path

# Files that mean "this is a code/Docker project": moving its files would break it.
PROJECT_MARKERS = (
    ".git", "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    "package.json", "pyproject.toml", "setup.py", "requirements.txt", "Cargo.toml", "go.mod",
    "pom.xml", "build.gradle", "pubspec.yaml", "composer.json", "Gemfile", "Makefile", "CMakeLists.txt",
)
PROJECT_SUFFIXES = (".sln", ".csproj")


class UnsafeFolderError(Exception):
    """Raised for folders the organizer must never rearrange."""


class DriveNotConnectedError(UnsafeFolderError):
    """The folder is on a USB or network drive that isn't available right now."""


def ensure_allowed(folder: Path) -> None:
    if not folder.is_dir():
        if not drives.is_connected(folder):
            raise DriveNotConnectedError(drives.missing_message(folder))
        raise UnsafeFolderError(f"{folder} is not a folder.")
    resolved = folder.resolve()
    # A USB stick or network share is often organized as a whole; a computer's own drive never is.
    if resolved.parent == resolved and not drives.is_external(resolved):
        raise UnsafeFolderError(f"{folder} is the root of a drive. Pick a folder inside it instead.")
    if same_path(resolved, Path.home()):
        raise UnsafeFolderError("That is your whole user folder. Pick a folder inside it, like Downloads.")
    for protected in _protected_dirs():
        if is_within(resolved, protected):
            raise UnsafeFolderError(f"{folder} is a system or app folder and can't be organized.")


def ensure_destination(destination: Path) -> None:
    """Check a folder files are sent to. It may not exist yet, but its drive must be there."""
    if not drives.is_connected(destination):
        raise DriveNotConnectedError(drives.missing_message(destination))
    existing = destination
    while not existing.exists() and existing.parent != existing:
        existing = existing.parent
    if existing.exists() and not existing.is_dir():
        raise UnsafeFolderError(f"{existing} is a file, so files can't be put inside it.")
    resolved = destination.resolve()
    if resolved.parent == resolved and not drives.is_external(resolved):
        raise UnsafeFolderError(f"{destination} is the root of a drive. Pick a folder inside it instead.")
    for protected in _protected_dirs():
        if is_within(resolved, protected):
            raise UnsafeFolderError(f"{destination} is a system or app folder, so files can't be put there.")


def warnings(folder: Path) -> list[str]:
    """Reasons to double-check before organizing ``folder``. Empty means it looks fine."""
    try:
        names = {entry.name for entry in folder.iterdir()}
    except OSError:
        return []
    found = [m for m in PROJECT_MARKERS if m in names]
    found += sorted(n for n in names if n.lower().endswith(PROJECT_SUFFIXES))
    if not found:
        return []
    return [
        f"This looks like a software project (found {', '.join(found[:3])}). "
        "Moving its files will probably break it."
    ]


def _protected_dirs() -> list[Path]:
    dirs = [app_data_dir()]
    if sys.platform == "win32":
        for var in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData"):
            value = os.environ.get(var)
            if value:
                dirs.append(Path(value))
    else:
        dirs += [Path(p) for p in ("/System", "/Library", "/Applications", "/usr", "/bin", "/sbin",
                                    "/etc", "/boot", "/dev", "/proc", "/sys")]
    return dirs
