"""Organize folders automatically: when new files arrive, or every hour/day."""

from __future__ import annotations

from datetime import datetime, timedelta

from desktop_organizer.core import rules, safety
from desktop_organizer.core.config import AutoMode, FolderProfile
from desktop_organizer.core.mover import RunResult
from desktop_organizer.core.organizer import Organizer

# A file must be unchanged for this long before it is moved, so half-written
# downloads and files still being saved are left alone until they're done.
SETTLE_SECONDS = 10

INTERVALS = {AutoMode.HOURLY: timedelta(hours=1), AutoMode.DAILY: timedelta(days=1)}


class AutoOrganizer:
    def __init__(self, organizer: Organizer, settle_seconds: float = SETTLE_SECONDS):
        self.organizer = organizer
        self.settle_seconds = settle_seconds
        self._last_check: dict[str, datetime] = {}

    def auto_folders(self) -> list[FolderProfile]:
        return [f for f in self.organizer.settings.folders if f.auto is not AutoMode.OFF]

    def is_due(self, profile: FolderProfile, now: datetime | None = None) -> bool:
        if profile.auto is AutoMode.OFF:
            return False
        if profile.auto is AutoMode.WATCH:
            return True
        now = now or datetime.now()
        key = str(profile.location).lower()
        last = self._last_check.get(key)
        if last is None:
            last = self.organizer.history.last_run_time(profile.location)
        return last is None or now - last >= INTERVALS[profile.auto]

    def run(self, profile: FolderProfile, now: datetime | None = None) -> RunResult | None:
        """Organize the settled files in one folder. Returns None if nothing moved."""
        folder = profile.location
        self._last_check[str(folder).lower()] = now or datetime.now()
        try:
            safety.ensure_allowed(folder)
            moves = rules.plan(folder, self.organizer.settings, min_age_seconds=self.settle_seconds)
        except (safety.UnsafeFolderError, OSError):
            return None
        if not moves:
            return None
        result = self.organizer.organize(folder, moves)
        return result if result.moved else None

    def run_due(self, now: datetime | None = None) -> list[tuple[FolderProfile, RunResult]]:
        results = []
        for profile in self.auto_folders():
            if self.is_due(profile, now):
                result = self.run(profile, now)
                if result is not None:
                    results.append((profile, result))
        return results
