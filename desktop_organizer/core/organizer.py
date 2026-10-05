"""Single entry point the CLI and the GUI both talk to."""

from __future__ import annotations

from pathlib import Path

from desktop_organizer.core import mover, rules, safety
from desktop_organizer.core.config import FolderProfile, Settings
from desktop_organizer.core.history import History, UndoResult
from desktop_organizer.core.mover import ProgressCallback, RunResult
from desktop_organizer.core.paths import desktop_dir
from desktop_organizer.core.rules import PlannedMove


class Organizer:
    def __init__(self, settings: Settings | None = None, history: History | None = None):
        self.settings = settings or Settings.load()
        self.history = history or History()

    def folders(self) -> list[FolderProfile]:
        return list(self.settings.folders)

    def check(self, folder: Path) -> list[str]:
        """Raise UnsafeFolderError for forbidden folders; return warnings the user should confirm."""
        safety.ensure_allowed(folder)
        return safety.warnings(folder)

    def pattern_for(self, folder: Path) -> str:
        return self.settings.pattern_for(folder)

    def preview(self, folder: Path | None = None, pattern: str | None = None) -> list[PlannedMove]:
        return rules.plan(folder or desktop_dir(), self.settings, pattern)

    def organize(
        self,
        folder: Path | None = None,
        moves: list[PlannedMove] | None = None,
        pattern: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> RunResult:
        folder = folder or desktop_dir()
        safety.ensure_allowed(folder)
        pattern = pattern or self.settings.pattern_for(folder)
        if moves is None:
            moves = rules.plan(folder, self.settings, pattern)
        return mover.execute(moves, self.history, folder, pattern, progress)

    def undo(self, run_id: int) -> UndoResult:
        return self.history.undo(run_id)

    def undo_last(self) -> UndoResult | None:
        run = self.history.last_undoable_run()
        return self.history.undo(run.id) if run else None
