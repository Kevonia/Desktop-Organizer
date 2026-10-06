"""Semantic versions (MAJOR.MINOR.PATCH): parsing, comparing and bumping."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERN = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int = 0

    @classmethod
    def parse(cls, text: str) -> "Version":
        match = _PATTERN.match(text.strip())
        if not match:
            raise ValueError(f"'{text}' is not a version like 1.2.3")
        major, minor, patch = match.groups()
        return cls(int(major), int(minor), int(patch or 0))

    def bump(self, part: str) -> "Version":
        if part == "major":
            return Version(self.major + 1, 0, 0)
        if part == "minor":
            return Version(self.major, self.minor + 1, 0)
        if part == "patch":
            return Version(self.major, self.minor, self.patch + 1)
        raise ValueError(f"Unknown version part '{part}' (use major, minor or patch)")

    def windows_tuple(self) -> tuple[int, int, int, int]:
        """Four-part version Windows puts in an .exe's file properties."""
        return (self.major, self.minor, self.patch, 0)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def current() -> Version:
    from desktop_organizer import __version__

    return Version.parse(__version__)


def is_newer(candidate: str, than: str | None = None) -> bool:
    """True if ``candidate`` is a newer release than ``than`` (default: this app)."""
    return Version.parse(candidate) > (Version.parse(than) if than else current())
