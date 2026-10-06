"""Carry out a plan, logging each move so it can be undone."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from desktop_organizer.core.history import History
from desktop_organizer.core.rules import PlannedMove

ProgressCallback = Callable[[int, int, PlannedMove], None]


@dataclass
class RunResult:
    run_id: int
    moved: list[tuple[Path, Path]] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)


def execute(
    moves: list[PlannedMove],
    history: History,
    root: Path,
    structure: str,
    progress: ProgressCallback | None = None,
) -> RunResult:
    run_id = history.start_run(root, structure)
    result = RunResult(run_id=run_id)
    total = len(moves)

    for index, move in enumerate(moves, start=1):
        if progress:
            progress(index, total, move)
        try:
            if not move.source.exists():
                raise FileNotFoundError("file no longer exists")
            for directory in _missing_dirs(move.target_dir, root):
                directory.mkdir()
                history.record_created_dir(run_id, directory)
            destination = unique_destination(move.target_dir, move.source.name)
            shutil.move(str(move.source), str(destination))
        except OSError as exc:
            result.failed.append((move.source, exc.strerror or str(exc)))
            continue
        # Logged per file so a crash mid-run still leaves everything undoable.
        history.record_move(run_id, move.source, destination)
        result.moved.append((move.source, destination))

    history.finish_run(run_id)
    return result


def unique_destination(target_dir: Path, name: str) -> Path:
    """Return ``target_dir/name``, appending _1, _2... if that name is taken."""
    candidate = target_dir / name
    stem, suffix = Path(name).stem, Path(name).suffix
    counter = 1
    while candidate.exists():
        candidate = target_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def _missing_dirs(target: Path, root: Path) -> list[Path]:
    """Directories between ``root`` and ``target`` that don't exist yet, outermost first."""
    missing = []
    current = target
    while current != root and not current.exists():
        missing.append(current)
        current = current.parent
    return list(reversed(missing))
