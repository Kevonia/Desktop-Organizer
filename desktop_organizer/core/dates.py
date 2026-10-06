"""Work out which date a file belongs to."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path


def file_date(path: Path, st: os.stat_result | None = None) -> datetime:
    """Return the earliest trustworthy date for a file.

    st_ctime is only the creation time on Windows; on macOS/Linux it is the last
    metadata change, which is why the original script misfiled files there.
    Copying a file resets its creation time but keeps its modification time, so
    the earlier of the two is the better guess at when the content was made.
    """
    st = st or path.stat()
    created = getattr(st, "st_birthtime", None)
    if created is None and sys.platform == "win32":
        created = st.st_ctime
    timestamp = min(created, st.st_mtime) if created else st.st_mtime
    return datetime.fromtimestamp(timestamp)
