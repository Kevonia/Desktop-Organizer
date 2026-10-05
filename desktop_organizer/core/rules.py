"""Decide where each file should go. Pure planning - nothing is moved here."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from desktop_organizer.core.config import Settings
from desktop_organizer.core.dates import file_date
from desktop_organizer.core.scanner import scan
from desktop_organizer.core.structure import render


@dataclass(frozen=True)
class PlannedMove:
    source: Path
    target_dir: Path
    root: Path

    @property
    def relative_target(self) -> Path:
        return self.target_dir.relative_to(self.root)


def plan(folder: Path, settings: Settings, pattern: str | None = None) -> list[PlannedMove]:
    """Build the list of moves for every eligible file in ``folder``.

    ``pattern`` overrides the structure saved for that folder (for one-off runs).
    """
    pattern = pattern or settings.pattern_for(folder)
    moves = []
    for path in scan(folder, settings):
        try:
            st = path.stat()
            subpath = render(pattern, path, file_date(path, st), st.st_size, settings.custom_categories)
        except OSError:
            continue
        moves.append(PlannedMove(source=path, target_dir=folder / subpath, root=folder))
    return moves
