"""Keep the last few saved versions of files in folders the user protects."""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from collections.abc import Callable, Iterable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from desktop_organizer.core.paths import app_data_dir
from desktop_organizer.core.scanner import IN_PROGRESS_EXTENSIONS

DEFAULT_KEEP = 4
DEFAULT_MAX_MB = 50
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "$recycle.bin"}
# Editors' scratch files that change constantly and are never worth restoring.
SKIP_SUFFIXES = IN_PROGRESS_EXTENSIONS | {".lnk", ".url", ".swp", ".swx", ".lock", ".bak~"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    key     TEXT NOT NULL UNIQUE,   -- normalised path, used for lookups
    path    TEXT NOT NULL           -- path as the user sees it
);
CREATE TABLE IF NOT EXISTS versions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id  INTEGER NOT NULL REFERENCES files(id),
    blob     TEXT NOT NULL,
    mtime    REAL NOT NULL,
    size     INTEGER NOT NULL,
    digest   TEXT NOT NULL,
    saved_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_versions_file ON versions(file_id);
"""


@dataclass(frozen=True)
class FileVersion:
    id: int
    path: Path
    blob: Path
    modified: datetime
    size: int
    saved_at: datetime


@dataclass(frozen=True)
class VersionedFile:
    path: Path
    versions: int
    latest: datetime

    @property
    def exists(self) -> bool:
        return self.path.exists()


class VersionStore:
    def __init__(self, root: Path | None = None, keep: int = DEFAULT_KEEP, max_mb: int = DEFAULT_MAX_MB):
        self.root = root or app_data_dir() / "versions"
        self.blobs = self.root / "files"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "versions.db"
        self.keep = keep
        self.max_bytes = max_mb * 1_000_000
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- saving versions -----------------------------------------------------------

    def scan(self, folders: Iterable[Path], should_stop: Callable[[], bool] | None = None) -> int:
        """Save a version of every file changed since its last saved version. Returns how many."""
        latest = self._latest_mtimes()
        saved = 0
        for folder in folders:
            for path in self._walk(folder):
                if should_stop and should_stop():
                    return saved
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if latest.get(_key(path), -1) < mtime and self.snapshot(path):
                    saved += 1
        return saved

    def snapshot(self, path: Path) -> bool:
        """Save the file's current contents as a new version, unless nothing changed."""
        try:
            st = path.stat()
            if not path.is_file() or st.st_size > self.max_bytes:
                return False
            digest = _digest(path)
        except OSError:
            return False
        with closing(self._connect()) as conn, conn:
            file_id = self._file_id(conn, path)
            last = conn.execute(
                "SELECT digest FROM versions WHERE file_id = ? ORDER BY id DESC LIMIT 1", (file_id,)
            ).fetchone()
            if last is not None and last["digest"] == digest:
                # Same contents (e.g. the file was only touched): just remember the new time.
                conn.execute("UPDATE versions SET mtime = ? WHERE id = (SELECT MAX(id) FROM versions WHERE file_id = ?)",
                             (st.st_mtime, file_id))
                return False
            cur = conn.execute(
                "INSERT INTO versions (file_id, blob, mtime, size, digest, saved_at) VALUES (?, '', ?, ?, ?, ?)",
                (file_id, st.st_mtime, st.st_size, digest, _now()),
            )
            version_id = int(cur.lastrowid)
            blob = self.blobs / str(file_id) / f"{version_id}{path.suffix.lower()}"
            blob.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(path, blob)
            except OSError:
                conn.execute("DELETE FROM versions WHERE id = ?", (version_id,))
                return False
            conn.execute("UPDATE versions SET blob = ? WHERE id = ?", (str(blob), version_id))
            self._prune(conn, file_id)
        return True

    def _prune(self, conn: sqlite3.Connection, file_id: int) -> None:
        old = conn.execute(
            "SELECT id, blob FROM versions WHERE file_id = ? ORDER BY id DESC LIMIT -1 OFFSET ?",
            (file_id, self.keep),
        ).fetchall()
        for row in old:
            Path(row["blob"]).unlink(missing_ok=True)
            conn.execute("DELETE FROM versions WHERE id = ?", (row["id"],))

    # --- browsing and restoring ------------------------------------------------------

    def files(self, query: str = "") -> list[VersionedFile]:
        """Files that have saved versions, newest change first, optionally filtered by name."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """SELECT f.path, COUNT(v.id) AS n, MAX(v.saved_at) AS latest
                   FROM files f JOIN versions v ON v.file_id = f.id
                   GROUP BY f.id ORDER BY latest DESC"""
            ).fetchall()
        needle = query.strip().lower()
        return [
            VersionedFile(Path(r["path"]), r["n"], datetime.fromisoformat(r["latest"]))
            for r in rows if needle in Path(r["path"]).name.lower()
        ]

    def versions(self, path: Path) -> list[FileVersion]:
        """Saved versions of one file, newest first."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """SELECT v.* FROM versions v JOIN files f ON f.id = v.file_id
                   WHERE f.key = ? ORDER BY v.id DESC""", (_key(path),)
            ).fetchall()
        return [FileVersion(r["id"], path, Path(r["blob"]), datetime.fromtimestamp(r["mtime"]), r["size"],
                            datetime.fromisoformat(r["saved_at"])) for r in rows]

    def restore(self, version: FileVersion, target: Path | None = None) -> Path:
        """Copy a saved version back. The current file is saved first, so this can be reversed."""
        target = target or version.path
        # Copy it aside first: saving the current file below may prune this very version.
        staging = self.root / f"restoring-{version.id}{version.blob.suffix}"
        shutil.copy2(version.blob, staging)
        if target.exists():
            self.snapshot(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(target))
        # Record the restored contents as the newest version too.
        self.snapshot(target)
        return target

    def moved(self, source: Path, destination: Path) -> None:
        """Keep a file's history when the organizer moves it."""
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT id FROM files WHERE key = ?", (_key(source),)).fetchone()
            if row is None:
                return
            clash = conn.execute("SELECT id FROM files WHERE key = ?", (_key(destination),)).fetchone()
            if clash is not None:
                conn.execute("UPDATE versions SET file_id = ? WHERE file_id = ?", (row["id"], clash["id"]))
                conn.execute("DELETE FROM files WHERE id = ?", (clash["id"],))
            conn.execute("UPDATE files SET key = ?, path = ? WHERE id = ?",
                         (_key(destination), str(destination), row["id"]))

    def storage_used(self) -> int:
        with closing(self._connect()) as conn:
            return int(conn.execute("SELECT COALESCE(SUM(size), 0) FROM versions").fetchone()[0])

    def clear(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM versions")
            conn.execute("DELETE FROM files")
        shutil.rmtree(self.blobs, ignore_errors=True)
        self.blobs.mkdir(parents=True, exist_ok=True)

    # --- helpers -------------------------------------------------------------------

    def _latest_mtimes(self) -> dict[str, float]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT f.key, MAX(v.mtime) AS m FROM files f JOIN versions v ON v.file_id = f.id GROUP BY f.id"
            ).fetchall()
        return {r["key"]: r["m"] for r in rows}

    def _file_id(self, conn: sqlite3.Connection, path: Path) -> int:
        row = conn.execute("SELECT id FROM files WHERE key = ?", (_key(path),)).fetchone()
        if row:
            return int(row["id"])
        return int(conn.execute("INSERT INTO files (key, path) VALUES (?, ?)", (_key(path), str(path))).lastrowid)

    def _walk(self, folder: Path):
        own = os.path.normcase(str(self.root))
        for root, dirs, files in os.walk(folder):
            if os.path.normcase(root).startswith(own):
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith(".")]
            for name in files:
                if name.startswith(("~$", ".")) or name.endswith("~"):
                    continue
                path = Path(root, name)
                if path.suffix.lower() in SKIP_SUFFIXES or path.is_symlink():
                    continue
                yield path


def _key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def _digest(path: Path) -> str:
    digest = hashlib.blake2b(digest_size=20)
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
