"""Answer "where did this file come from?": earlier places the organizer moved it from,
and the website it was downloaded from."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from desktop_organizer.core import metadata
from desktop_organizer.core.dates import file_date
from desktop_organizer.core.history import History


@dataclass
class FileOrigin:
    path: Path
    moves: list[tuple[Path, Path, datetime]] = field(default_factory=list)  # oldest first
    download: metadata.DownloadInfo | None = None
    created: datetime | None = None
    modified: datetime | None = None

    @property
    def original_path(self) -> Path | None:
        """Where the file was before the organizer first moved it."""
        return self.moves[0][0] if self.moves else None

    @property
    def moved_at(self) -> datetime | None:
        return self.moves[-1][2] if self.moves else None

    def summary(self) -> str:
        lines = []
        if self.moves:
            first = self.original_path
            lines.append(f"Moved here by Desktop Organizer on {self.moved_at:%Y-%m-%d %H:%M}.")
            lines.append(f"It was originally in {first.parent}" + (
                f" (named {first.name})." if first.name != self.path.name else "."))
        else:
            lines.append("Desktop Organizer didn't move this file.")
        if self.download and (self.download.referrer_url or self.download.host_url):
            lines.append(f"Downloaded from {self.download.site or self.download.host_url}.")
        return " ".join(lines)


def find_origin(path: Path, history: History) -> FileOrigin:
    origin = FileOrigin(path=path, moves=history.trail(path), download=metadata.download_info(path))
    try:
        st = path.stat()
        origin.created = file_date(path, st)
        origin.modified = datetime.fromtimestamp(st.st_mtime)
    except OSError:
        pass
    return origin
