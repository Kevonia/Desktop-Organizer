"""Decide where each file should go. Pure planning - nothing is moved here."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from desktop_organizer.core.config import Settings
from desktop_organizer.core.dates import file_date
from desktop_organizer.core.scanner import scan
from desktop_organizer.core.structure import render
from desktop_organizer.core.user_rules import RuleAction, first_match


@dataclass(frozen=True)
class PlannedMove:
    source: Path
    target_dir: Path
    root: Path
    rule: str | None = None  # name of the user rule that decided this move, if any

    @property
    def relative_target(self) -> Path:
        return self.target_dir.relative_to(self.root)


def plan(
    folder: Path,
    settings: Settings,
    pattern: str | None = None,
    min_age_seconds: float = 0,
) -> list[PlannedMove]:
    """Build the list of moves for every eligible file in ``folder``.

    User rules are checked first; files no rule matches use the folder's structure.
    ``pattern`` overrides that structure (for one-off runs). ``min_age_seconds`` skips
    files modified more recently than that, e.g. ones still being written.
    """
    pattern = pattern or settings.pattern_for(folder)
    rules = [r for r in settings.rules if r.enabled]
    now = time.time()
    moves = []
    for path in scan(folder, settings):
        try:
            st = path.stat()
            if min_age_seconds and now - st.st_mtime < min_age_seconds:
                continue
            when = file_date(path, st)
            rule = first_match(rules, folder, path, st.st_size, when)
            if rule is not None and rule.action is RuleAction.SKIP:
                continue
            target = rule.destination if rule is not None else pattern
            subpath = render(target, path, when, st.st_size, settings.custom_categories)
        except OSError:
            continue
        moves.append(PlannedMove(source=path, target_dir=folder / subpath, root=folder,
                                 rule=rule.name if rule else None))
    return moves
