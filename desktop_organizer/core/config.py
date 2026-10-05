"""User settings, persisted as JSON in the app data folder."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from desktop_organizer.core.categories import normalize_extension
from desktop_organizer.core.paths import app_data_dir, display_name, known_folder_key, resolve_folder, same_path
from desktop_organizer.core.structure import PatternError, validate
from desktop_organizer.core.user_rules import Rule


class SortMode(str, Enum):
    """Ready-made folder structures. Anything else is a custom pattern."""

    TYPE = "type"
    CATEGORY = "category"
    DATE = "date"
    DATE_TYPE = "date_type"
    DATE_CATEGORY = "date_category"

    @property
    def pattern(self) -> str:
        return _PRESET_PATTERNS[self]

    @property
    def label(self) -> str:
        return _PRESET_LABELS[self]


_PRESET_PATTERNS = {
    SortMode.TYPE: "{type}",
    SortMode.CATEGORY: "{category}",
    SortMode.DATE: "{year}/{month}",
    SortMode.DATE_TYPE: "{year}/{month}/{type}",
    SortMode.DATE_CATEGORY: "{year}/{month}/{category}",
}
_PRESET_LABELS = {
    SortMode.TYPE: "File type",
    SortMode.CATEGORY: "Category",
    SortMode.DATE: "Year / Month",
    SortMode.DATE_TYPE: "Year / Month / File type",
    SortMode.DATE_CATEGORY: "Year / Month / Category",
}

DEFAULT_PATTERN = SortMode.DATE_TYPE.pattern

# Shortcuts are usually on the Desktop on purpose, so they stay put by default.
DEFAULT_EXCLUDED_EXTENSIONS = [".lnk", ".url"]
DEFAULT_EXCLUDED_NAMES = ["desktop.ini", "thumbs.db", ".ds_store"]
THEMES = ("system", "light", "dark")


class AutoMode(str, Enum):
    """When a folder is organized without the user clicking Organize."""

    OFF = "off"
    WATCH = "watch"    # as soon as new files arrive (and finish downloading)
    HOURLY = "hourly"
    DAILY = "daily"

    @property
    def label(self) -> str:
        return {
            AutoMode.OFF: "Off",
            AutoMode.WATCH: "When new files arrive",
            AutoMode.HOURLY: "Every hour",
            AutoMode.DAILY: "Every day",
        }[self]


def describe_pattern(pattern: str) -> str:
    """'Year / Month / File type' for presets, otherwise the pattern itself."""
    for mode in SortMode:
        if mode.pattern == pattern:
            return mode.label
    return f"Custom: {pattern}"


@dataclass
class FolderProfile:
    """A folder the user organizes, optionally with its own structure."""

    path: str  # a known name like "downloads", or an absolute path
    pattern: str | None = None  # None means use Settings.pattern
    auto: AutoMode = AutoMode.OFF

    @property
    def location(self) -> Path:
        return resolve_folder(self.path)

    @property
    def name(self) -> str:
        return display_name(self.path)


@dataclass
class Settings:
    pattern: str = DEFAULT_PATTERN
    folders: list[FolderProfile] = field(default_factory=lambda: [FolderProfile("desktop")])
    # e.g. {"Invoices": ["pdf"], "Design": ["fig", "sketch"]}; these win over the built-in categories.
    custom_categories: dict[str, list[str]] = field(default_factory=dict)
    excluded_extensions: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDED_EXTENSIONS))
    excluded_names: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDED_NAMES))
    skip_hidden: bool = True
    theme: str = "system"  # system | light | dark
    # Checked in order before the folder's structure; the first match wins.
    rules: list[Rule] = field(default_factory=list)
    minimize_to_tray: bool = True
    notifications: bool = True

    # --- folders -------------------------------------------------------------

    def find_folder(self, folder: Path) -> FolderProfile | None:
        return next((f for f in self.folders if same_path(f.location, folder)), None)

    def pattern_for(self, folder: Path) -> str:
        profile = self.find_folder(folder)
        return profile.pattern if profile and profile.pattern else self.pattern

    def add_folder(self, spec: str, pattern: str | None = None) -> FolderProfile:
        """Add (or update) a folder. Known names like 'downloads' are kept as names so
        they keep working if Windows moves the folder (e.g. into OneDrive)."""
        key = known_folder_key(spec)
        stored = key or str(resolve_folder(spec).resolve())
        profile = FolderProfile(stored, validate(pattern) if pattern else None)
        existing = self.find_folder(profile.location)
        if existing:
            profile.auto = existing.auto
            self.folders[self.folders.index(existing)] = profile
        else:
            self.folders.append(profile)
        return profile

    def remove_folder(self, spec: str) -> bool:
        existing = self.find_folder(resolve_folder(spec))
        if existing:
            self.folders.remove(existing)
        return existing is not None

    # --- categories -----------------------------------------------------------

    def set_category(self, name: str, extensions: list[str]) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Category name can't be empty.")
        exts = sorted({normalize_extension(e) for e in extensions if normalize_extension(e)})
        if not exts:
            raise ValueError("Give at least one file extension, e.g. pdf.")
        # An extension can only belong to one custom category.
        for other, other_exts in list(self.custom_categories.items()):
            if other != name:
                remaining = [e for e in other_exts if normalize_extension(e) not in exts]
                if remaining:
                    self.custom_categories[other] = remaining
                else:
                    del self.custom_categories[other]
        self.custom_categories[name] = exts

    def remove_category(self, name: str) -> bool:
        return self.custom_categories.pop(name, None) is not None

    # --- exclusions -----------------------------------------------------------

    def is_extension_excluded(self, path: Path) -> bool:
        excluded = {normalize_extension(e) for e in self.excluded_extensions}
        return normalize_extension(path.suffix) in excluded and bool(path.suffix)

    def is_name_excluded(self, path: Path) -> bool:
        return path.name.lower() in {n.lower() for n in self.excluded_names}

    # --- persistence ----------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "folders": [{"path": f.path, "pattern": f.pattern, "auto": f.auto.value} for f in self.folders],
            "custom_categories": self.custom_categories,
            "excluded_extensions": self.excluded_extensions,
            "excluded_names": self.excluded_names,
            "skip_hidden": self.skip_hidden,
            "theme": self.theme,
            "rules": [r.to_dict() for r in self.rules],
            "minimize_to_tray": self.minimize_to_tray,
            "notifications": self.notifications,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        defaults = cls()
        pattern = data.get("pattern")
        if pattern is None and "sort_mode" in data:  # settings written by 0.2.0
            try:
                pattern = SortMode(data["sort_mode"]).pattern
            except ValueError:
                pattern = None
        folders = []
        for item in data.get("folders", [{"path": "desktop"}]):
            if isinstance(item, dict) and item.get("path"):
                folders.append(FolderProfile(
                    str(item["path"]), _valid_or_none(item.get("pattern")), _auto_mode(item.get("auto"))
                ))
        return cls(
            pattern=_valid_or_none(pattern) or defaults.pattern,
            folders=folders,
            custom_categories={
                str(k): [str(e) for e in v]
                for k, v in dict(data.get("custom_categories", {})).items()
                if isinstance(v, list)
            },
            excluded_extensions=list(data.get("excluded_extensions", defaults.excluded_extensions)),
            excluded_names=list(data.get("excluded_names", defaults.excluded_names)),
            skip_hidden=bool(data.get("skip_hidden", defaults.skip_hidden)),
            theme=data.get("theme") if data.get("theme") in THEMES else defaults.theme,
            rules=[Rule.from_dict(r) for r in data.get("rules", []) if isinstance(r, dict)],
            minimize_to_tray=bool(data.get("minimize_to_tray", defaults.minimize_to_tray)),
            notifications=bool(data.get("notifications", defaults.notifications)),
        )

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or settings_path()
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, AttributeError):
            return cls()

    def save(self, path: Path | None = None) -> None:
        path = path or settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def _valid_or_none(pattern: object) -> str | None:
    if not isinstance(pattern, str):
        return None
    try:
        return validate(pattern)
    except PatternError:
        return None


def _auto_mode(value: object) -> AutoMode:
    try:
        return AutoMode(value)
    except ValueError:
        return AutoMode.OFF
