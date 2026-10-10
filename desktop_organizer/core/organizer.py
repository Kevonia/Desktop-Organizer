"""Single entry point the CLI and the GUI both talk to."""

from __future__ import annotations

from pathlib import Path

from desktop_organizer.core import mover, rules, safety
from desktop_organizer.core.config import FolderProfile, Settings
from desktop_organizer.core.history import History, UndoResult
from desktop_organizer.core.logs import log
from desktop_organizer.core.mover import ProgressCallback, RunResult
from desktop_organizer.core.paths import desktop_dir, resolve_folder, same_path
from desktop_organizer.core.rules import PlannedMove
from desktop_organizer.core.versions import VersionStore


class Organizer:
    def __init__(self, settings: Settings | None = None, history: History | None = None,
                 versions: VersionStore | None = None):
        self.settings = settings or Settings.load()
        self.history = history or History()
        self._versions = versions

    @property
    def versions(self) -> VersionStore:
        """Version history for protected folders, created on first use."""
        if self._versions is None:
            self._versions = VersionStore()
        self._versions.keep = self.settings.versions_to_keep
        self._versions.max_bytes = self.settings.version_max_mb * 1_000_000
        return self._versions

    def version_folders(self) -> list[Path]:
        return [resolve_folder(f) for f in self.settings.version_folders if resolve_folder(f).is_dir()]

    def folders(self) -> list[FolderProfile]:
        return list(self.settings.folders)

    def check(self, folder: Path) -> list[str]:
        """Raise UnsafeFolderError for forbidden folders; return warnings the user should confirm."""
        safety.ensure_allowed(folder)
        return safety.warnings(folder)

    def pattern_for(self, folder: Path) -> str:
        return self.settings.pattern_for(folder)

    def check_destination(self, folder: Path) -> Path:
        """Where ``folder``'s files go. Raises UnsafeFolderError (or DriveNotConnectedError) if unusable."""
        base = self.settings.destination_for(folder)
        if not same_path(base, folder):
            safety.ensure_destination(base)
        return base

    def search_folders(self) -> list[Path]:
        """Saved folders, their destinations and protected folders that are available right now."""
        folders: list[Path] = []
        for profile in self.settings.folders:
            for path in (profile.location, profile.target):
                if path.is_dir() and not any(same_path(path, f) for f in folders):
                    folders.append(path)
        for path in self.version_folders():
            if not any(same_path(path, f) for f in folders):
                folders.append(path)
        return folders

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
        self.check_destination(folder)
        pattern = pattern or self.settings.pattern_for(folder)
        if moves is None:
            moves = rules.plan(folder, self.settings, pattern)
        result = mover.execute(moves, self.history, folder, pattern, progress)
        log.info("Run %d: moved %d file(s) in %s using %s", result.run_id, len(result.moved), folder, pattern)
        for source, reason in result.failed:
            log.warning("Run %d: couldn't move %s: %s", result.run_id, source, reason)
        self._carry_versions(result.moved)
        return result

    def undo(self, run_id: int) -> UndoResult:
        result = self.history.undo(run_id)
        log.info("Undo of run %d: restored %d file(s)", run_id, len(result.restored))
        for path, reason in result.failed:
            log.warning("Undo of run %d: couldn't restore %s: %s", run_id, path, reason)
        self._carry_versions(result.restored)
        return result

    def _carry_versions(self, pairs: list[tuple[Path, Path]]) -> None:
        """A moved file keeps its saved versions."""
        if not self.settings.version_folders or not pairs:
            return
        for source, destination in pairs:
            self.versions.moved(source, destination)

    def undo_last(self) -> UndoResult | None:
        run = self.history.last_undoable_run()
        return self.undo(run.id) if run else None
