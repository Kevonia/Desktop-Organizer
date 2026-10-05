"""Folder-structure patterns such as ``{year}/{month}/{type}`` that users can define themselves."""

from __future__ import annotations

import re
import string
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path

from desktop_organizer.core.categories import OTHER, category_for

# placeholder -> (description, example)
TOKENS: dict[str, tuple[str, str]] = {
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
}

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
        try:
            parsed = list(_FORMATTER.parse(segment))
        except ValueError:
            raise PatternError(f"Unmatched '{{' or '}}' in '{segment}'.") from None
        for literal, field, spec, conversion in parsed:
            bad = _INVALID_CHARS.search(literal)
            if bad:
                raise PatternError(f"Folder names can't contain '{bad.group()}'.")
            if field is None:
                continue
            if field not in TOKENS:
                raise PatternError(
                    f"Unknown placeholder '{{{field}}}'. Available: "
                    + ", ".join(f"{{{t}}}" for t in TOKENS)
                )
            if spec or conversion:
                raise PatternError(f"Write '{{{field}}}' without extra formatting.")
    return normalized


def render(
    pattern: str,
    path: Path,
    when: datetime,
    size: int,
    custom_categories: Mapping[str, Iterable[str]] | None = None,
) -> Path:
    """Return the relative folder a file belongs in under ``pattern``."""
    values = token_values(path, when, size, custom_categories)
    parts = []
    for segment in validate(pattern).split("/"):
        # Windows silently drops trailing dots/spaces, so strip them up front.
        name = segment.format_map(values).strip().rstrip(". ")
        if name:
            parts.append(name)
    return Path(*parts) if parts else Path(OTHER)


def example(pattern: str, custom_categories: Mapping[str, Iterable[str]] | None = None) -> str:
    """Where a sample file would land, for showing users what a pattern does."""
    target = render(pattern, Path("Report.pdf"), datetime(2025, 1, 5), 250_000, custom_categories)
    return f"{target.as_posix()}/Report.pdf"


def token_values(
    path: Path,
    when: datetime,
    size: int,
    custom_categories: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, str]:
    file_type = path.suffix.lower().lstrip(".") or NO_EXTENSION
    first = path.stem[:1].upper()
    values = {
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
    return {key: _safe(value) for key, value in values.items()}


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
