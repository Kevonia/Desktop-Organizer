"""Folder-structure patterns such as ``{year}/{month}/{type}`` that users can define themselves."""

from __future__ import annotations

import re
import string
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path

from desktop_organizer.core import metadata
from desktop_organizer.core.categories import OTHER, category_for

# placeholder -> (description, example)
TOKENS: dict[str, tuple[str, str]] = {
    "date": ("full date", "2025-01-05"),
    "year": ("4-digit year", "2025"),
    "month": ("month number and name", "01-January"),
    "month_num": ("month number", "01"),
    "month_name": ("month name", "January"),
    "month_short": ("short month name", "Jan"),
    "day": ("day of the month", "05"),
    "quarter": ("quarter of the year", "Q1"),
    "type": ("file extension", "pdf"),
    "category": ("file category", "Documents"),
    "size": ("size group: Small <1 MB, Medium <100 MB, Large <1 GB, Huge", "Small"),
    "first_letter": ("first letter of the file name", "R"),
    "photo_date": ("date a photo was taken (else the file date)", "2025-01-05"),
    "photo_year": ("year a photo was taken", "2025"),
    "photo_month": ("month a photo was taken", "01-January"),
    "camera": ("camera or phone that took a photo", "iPhone 13"),
    "artist": ("music artist (album artist if set)", "Bob Marley"),
    "album": ("music album", "Legend"),
    "source": ("website a download came from", "github.com"),
}

# Only allowed when renaming: the original name without its extension.
NAME_TOKENS: dict[str, tuple[str, str]] = {"name": ("original file name", "IMG_1234")}

UNKNOWN = {
    "camera": "Unknown camera",
    "artist": "Unknown artist",
    "album": "Unknown album",
    "source": "Unknown source",
}
# Read from inside the file, so only worked out when a pattern asks for them.
METADATA_TOKENS = frozenset({"photo_date", "photo_year", "photo_month", "camera", "artist", "album", "source"})

NO_EXTENSION = "no_extension"

# Characters Windows doesn't allow in folder names (macOS/Linux are more lenient).
_INVALID_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_FORMATTER = string.Formatter()


class PatternError(ValueError):
    """The pattern can't be used; the message is written for the end user."""


def validate(pattern: str) -> str:
    """Return the pattern normalized to '/' separators, or raise PatternError."""
    normalized = pattern.strip().replace("\\", "/").strip("/")
    if not normalized:
        raise PatternError("The folder structure is empty.")
    for segment in normalized.split("/"):
        if not segment.strip():
            raise PatternError("Remove the empty folder level ('//').")
        if segment.strip() in (".", ".."):
            raise PatternError("Folder levels can't be '.' or '..'.")
        _check_segment(segment, TOKENS, "Folder names")
    return normalized


def validate_name(template: str) -> str:
    """Check a rename template such as '{date} {name}'. Returns it trimmed, or raises PatternError."""
    template = template.strip()
    if not template:
        raise PatternError("The new name is empty.")
    if "/" in template or "\\" in template:
        raise PatternError("A file name can't contain '/' or '\\'.")
    _check_segment(template, {**TOKENS, **NAME_TOKENS}, "File names")
    return template


def _check_segment(segment: str, allowed: Mapping[str, object], what: str) -> None:
    try:
        parsed = list(_FORMATTER.parse(segment))
    except ValueError:
        raise PatternError(f"Unmatched '{{' or '}}' in '{segment}'.") from None
    for literal, field, spec, conversion in parsed:
        bad = _INVALID_CHARS.search(literal)
        if bad:
            raise PatternError(f"{what} can't contain '{bad.group()}'.")
        if field is None:
            continue
        if field not in allowed:
            raise PatternError(
                f"Unknown placeholder '{{{field}}}'. Available: " + ", ".join(f"{{{t}}}" for t in allowed)
            )
        if spec or conversion:
            raise PatternError(f"Write '{{{field}}}' without extra formatting.")


def fields_in(pattern: str) -> set[str]:
    """The placeholders a (valid) pattern or name template uses."""
    try:
        return {field for _, field, _, _ in _FORMATTER.parse(pattern) if field}
    except ValueError:
        return set()


def render(
    pattern: str,
    path: Path,
    when: datetime,
    size: int,
    custom_categories: Mapping[str, Iterable[str]] | None = None,
) -> Path:
    """Return the relative folder a file belongs in under ``pattern``."""
    values = token_values(path, when, size, custom_categories, fields_in(pattern))
    parts = []
    for segment in validate(pattern).split("/"):
        # Windows silently drops trailing dots/spaces, so strip them up front.
        name = segment.format_map(values).strip().rstrip(". ")
        if name:
            parts.append(name)
    return Path(*parts) if parts else Path(OTHER)


def render_name(
    template: str,
    path: Path,
    when: datetime,
    size: int,
    custom_categories: Mapping[str, Iterable[str]] | None = None,
) -> str:
    """The new file name under a rename template. The extension is always kept."""
    values = token_values(path, when, size, custom_categories, fields_in(template))
    values["name"] = _safe(path.stem)
    stem = validate_name(template).format_map(values).strip().rstrip(". ")
    return f"{stem}{path.suffix}" if stem else path.name


def example(pattern: str, custom_categories: Mapping[str, Iterable[str]] | None = None) -> str:
    """Where a sample file would land, for showing users what a pattern does."""
    target = render(pattern, Path("Report.pdf"), datetime(2025, 1, 5), 250_000, custom_categories)
    return f"{target.as_posix()}/Report.pdf"


def token_values(
    path: Path,
    when: datetime,
    size: int,
    custom_categories: Mapping[str, Iterable[str]] | None = None,
    fields: Iterable[str] | None = None,
) -> dict[str, str]:
    """Placeholder values for one file. File contents are only read for the ``fields`` asked for."""
    file_type = path.suffix.lower().lstrip(".") or NO_EXTENSION
    first = path.stem[:1].upper()
    values = {
        "date": when.strftime("%Y-%m-%d"),
        "year": str(when.year),
        "month": when.strftime("%m-%B"),
        "month_num": when.strftime("%m"),
        "month_name": when.strftime("%B"),
        "month_short": when.strftime("%b"),
        "day": when.strftime("%d"),
        "quarter": f"Q{(when.month - 1) // 3 + 1}",
        "type": file_type,
        "category": category_for(file_type, custom_categories),
        "size": size_group(size),
        "first_letter": first if first.isalnum() else "#",
    }
    wanted = METADATA_TOKENS.intersection(fields or ())
    if wanted:
        values.update(_metadata_values(path, when, wanted))
    return {key: _safe(value) for key, value in values.items()}


def _metadata_values(path: Path, when: datetime, wanted: set[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    if wanted & {"photo_date", "photo_year", "photo_month", "camera"}:
        photo = metadata.photo_info(path)
        taken = photo.taken if photo and photo.taken else when
        values["photo_date"] = taken.strftime("%Y-%m-%d")
        values["photo_year"] = str(taken.year)
        values["photo_month"] = taken.strftime("%m-%B")
        values["camera"] = (photo.camera if photo else None) or UNKNOWN["camera"]
    if wanted & {"artist", "album"}:
        audio = metadata.audio_info(path)
        values["artist"] = (audio.artist if audio else None) or UNKNOWN["artist"]
        values["album"] = (audio.album if audio else None) or UNKNOWN["album"]
    if "source" in wanted:
        download = metadata.download_info(path)
        values["source"] = (download.site if download else None) or UNKNOWN["source"]
    return values


def size_group(size: int) -> str:
    if size < 1_000_000:
        return "Small"
    if size < 100_000_000:
        return "Medium"
    if size < 1_000_000_000:
        return "Large"
    return "Huge"


def _safe(value: str) -> str:
    return _INVALID_CHARS.sub("_", value).replace("/", "_").replace("\\", "_")
