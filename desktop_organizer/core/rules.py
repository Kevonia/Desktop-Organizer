"""Decide where each file should go. Pure planning - nothing is moved here."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from desktop_organizer.core import safety
from desktop_organizer.core.config import Settings
from desktop_organizer.core.dates import file_date
from desktop_organizer.core.paths import same_path
from desktop_organizer.core.scanner import scan
from desktop_organizer.core.structure import render, render_name
from desktop_organizer.core.user_rules import RuleAction, first_match


@dataclass(frozen=True)
class PlannedMove:
    source: Path
    target_dir: Path
    root: Path  # the folder the structure is built in: the source folder, or a chosen destination
    rule: str | None = None  # name of the user rule that decided this move, if any
    new_name: str | None = None  # set when the file is renamed as it moves

    @property
    def relative_target(self) -> Path:
        return self.target_dir.relative_to(self.root)

    @property
    def target_name(self) -> str:
        return self.new_name or self.source.name


def plan(
    folder: Path,
    settings: Settings,
    pattern: str | None = None,
    min_age_seconds: float = 0,
    rename: str | None = None,
) -> list[PlannedMove]:
    """Build the list of moves for every eligible file in ``folder``.

    User rules are checked first; files no rule matches use the folder's structure.
    ``pattern`` overrides that structure (for one-off runs). ``min_age_seconds`` skips
    files modified more recently than that, e.g. ones still being written. ``rename``
    overrides the folder's rename template. Raises DriveNotConnectedError when the
    folder's destination is on a drive that isn't plugged in.
    """
    pattern = pattern or settings.pattern_for(folder)
    rename = rename if rename is not None else settings.rename_for(folder)
    base = settings.destination_for(folder)
    if not same_path(base, folder):
        safety.ensure_destination(base)
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
            template = (rule.rename if rule is not None and rule.rename else None) or rename
            new_name = render_name(template, path, when, st.st_size, settings.custom_categories) if template else None
        except OSError:
            continue
        moves.append(PlannedMove(source=path, target_dir=base / subpath, root=base,
                                 rule=rule.name if rule else None,
                                 new_name=new_name if new_name and new_name != path.name else None))
    return moves
