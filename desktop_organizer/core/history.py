"""SQLite log of every move, so any run can be undone."""

from __future__ import annotations

import os
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from desktop_organizer.core.paths import app_data_dir, same_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    folder      TEXT NOT NULL,
    structure   TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    undone_at   TEXT
);
CREATE TABLE IF NOT EXISTS moves (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    source      TEXT NOT NULL,
    destination TEXT NOT NULL,
    undone      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS created_dirs (
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    path        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_moves_run ON moves(run_id);
"""


@dataclass
class RunInfo:
    id: int
    folder: Path
    structure: str
    started_at: datetime
    finished_at: datetime | None
    undone_at: datetime | None
    move_count: int

    @property
    def can_undo(self) -> bool:
        return self.undone_at is None and self.move_count > 0


@dataclass
class UndoResult:
    run_id: int
    restored: list[tuple[Path, Path]] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)


class History:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or app_data_dir() / "history.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # A short-lived connection per call keeps this safe to use from worker threads.
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def start_run(self, folder: Path, structure: str) -> int:
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "INSERT INTO runs (folder, structure, started_at) VALUES (?, ?, ?)",
                (str(folder), structure, _now()),
            )
            return int(cur.lastrowid)

    def record_move(self, run_id: int, source: Path, destination: Path) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO moves (run_id, source, destination) VALUES (?, ?, ?)",
                (run_id, str(source), str(destination)),
            )

    def record_created_dir(self, run_id: int, path: Path) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("INSERT INTO created_dirs (run_id, path) VALUES (?, ?)", (run_id, str(path)))

    def finish_run(self, run_id: int) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE runs SET finished_at = ? WHERE id = ?", (_now(), run_id))

    def runs(self, limit: int = 50) -> list[RunInfo]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT r.*, COUNT(m.id) AS move_count
                FROM runs r LEFT JOIN moves m ON m.run_id = r.id AND m.undone = 0
                GROUP BY r.id ORDER BY r.id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_run_info(row) for row in rows]

    def get_run(self, run_id: int) -> RunInfo | None:
        return next((r for r in self.runs(limit=-1) if r.id == run_id), None)

    def find_moves(self, query: str, limit: int = 200) -> list[tuple[Path, Path, datetime, bool]]:
        """Moves whose file name contains ``query``: (source, destination, when, undone), newest first."""
        needle = f"%{query.strip()}%"
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """SELECT m.source, m.destination, m.undone, r.started_at
                   FROM moves m JOIN runs r ON r.id = m.run_id
                   WHERE m.destination LIKE ? ORDER BY m.id DESC LIMIT ?""",
                (needle, limit * 4),
            ).fetchall()
        needle_lower = query.strip().lower()
        results = []
        for row in rows:
            destination = Path(row["destination"])
            # LIKE also matched folder names; keep only file-name matches.
            if needle_lower in destination.name.lower() or needle_lower in Path(row["source"]).name.lower():
                results.append((Path(row["source"]), destination,
                                datetime.fromisoformat(row["started_at"]), bool(row["undone"])))
            if len(results) >= limit:
                break
        return results

    def moves_for_run(self, run_id: int) -> list[tuple[Path, Path, bool]]:
        """Every move in a run, in order: (source, destination, undone)."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT source, destination, undone FROM moves WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        return [(Path(r["source"]), Path(r["destination"]), bool(r["undone"])) for r in rows]

    def trail(self, path: Path, max_hops: int = 20) -> list[tuple[Path, Path, datetime]]:
        """How the organizer moved a file to ``path``, oldest move first: (source, destination, when).

        Empty if the organizer didn't put the file there (or that move was undone).
        """
        hops: list[tuple[Path, Path, datetime]] = []
        target, before = str(path), None
        with closing(self._connect()) as conn:
            for _ in range(max_hops):
                row = conn.execute(
                    """SELECT m.id, m.source, m.destination, r.started_at
                       FROM moves m JOIN runs r ON r.id = m.run_id
                       WHERE m.destination = ? COLLATE NOCASE AND m.undone = 0
                         AND (? IS NULL OR m.id < ?)
                       ORDER BY m.id DESC LIMIT 1""",
                    (target, before, before),
                ).fetchone()
                if row is None:
                    break
                hops.append((Path(row["source"]), Path(row["destination"]),
                             datetime.fromisoformat(row["started_at"])))
                target, before = row["source"], row["id"]
        return list(reversed(hops))

    def last_run_time(self, folder: Path) -> datetime | None:
        """When ``folder`` was last organized (manually or automatically)."""
        return next((r.started_at for r in self.runs(limit=200) if same_path(r.folder, folder)), None)

    def stats(self) -> tuple[int, int]:
        """(files organized and still in place, runs) across all history."""
        with closing(self._connect()) as conn:
            files = conn.execute("SELECT COUNT(*) FROM moves WHERE undone = 0").fetchone()[0]
            runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        return int(files), int(runs)

    def last_undoable_run(self) -> RunInfo | None:
        return next((r for r in self.runs() if r.can_undo), None)

    def undo(self, run_id: int) -> UndoResult:
        """Move every file from ``run_id`` back where it came from, newest move first."""
        result = UndoResult(run_id=run_id)
        with closing(self._connect()) as conn:
            moves = conn.execute(
                "SELECT id, source, destination FROM moves WHERE run_id = ? AND undone = 0 ORDER BY id DESC",
                (run_id,),
            ).fetchall()
            created = [Path(r["path"]) for r in conn.execute(
                "SELECT path FROM created_dirs WHERE run_id = ?", (run_id,)
            )]

        for move in moves:
            source, destination = Path(move["source"]), Path(move["destination"])
            try:
                if not destination.exists():
                    raise FileNotFoundError("file is no longer where it was moved to")
                restore_to = _free_path(source)
                restore_to.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(restore_to))
            except OSError as exc:
                result.failed.append((destination, _describe(exc)))
                continue
            with closing(self._connect()) as conn, conn:
                conn.execute("UPDATE moves SET undone = 1 WHERE id = ?", (move["id"],))
            result.restored.append((destination, restore_to))

        # Remove folders this run created, deepest first, but only if they are now empty.
        for directory in sorted(created, key=lambda p: len(p.parts), reverse=True):
            try:
                os.rmdir(directory)
            except OSError:
                pass

        if not result.failed:
            with closing(self._connect()) as conn, conn:
                conn.execute("UPDATE runs SET undone_at = ? WHERE id = ?", (_now(), run_id))
        return result


def _free_path(path: Path) -> Path:
    """Return ``path`` or, if something now occupies it, ``name (restored N).ext``."""
    if not path.exists():
        return path
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem} (restored {counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _describe(exc: OSError) -> str:
    return exc.strerror or str(exc)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _run_info(row: sqlite3.Row) -> RunInfo:
    return RunInfo(
        id=row["id"],
        folder=Path(row["folder"]),
        structure=row["structure"],
        started_at=datetime.fromisoformat(row["started_at"]),
        finished_at=_parse(row["finished_at"]),
        undone_at=_parse(row["undone_at"]),
        move_count=row["move_count"],
    )
