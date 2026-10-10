"""Share rules, categories and layouts as a file, and bring them into another copy of the app.

Ready-made setups use the same format, so applying a setup and importing a file
behave the same way: existing settings are kept and merged with the new ones.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from desktop_organizer import APP_NAME, __version__
from desktop_organizer.core import safety
from desktop_organizer.core.config import (
    AutoMode,
    Settings,
    folder_from_dict,
    folder_to_dict,
    valid_name_or_none,
)
from desktop_organizer.core.paths import resolve_folder
from desktop_organizer.core.structure import PatternError, validate
from desktop_organizer.core.user_rules import Rule, RuleError

KIND = "desktop-organizer-settings"
FORMAT_VERSION = 1

RULES, CATEGORIES, LAYOUTS, EXCLUSIONS = "rules", "categories", "layouts", "exclusions"
PARTS = (RULES, CATEGORIES, LAYOUTS, EXCLUSIONS)
PART_LABELS = {
    RULES: "Rules",
    CATEGORIES: "Your categories",
    LAYOUTS: "Folders and their layouts",
    EXCLUSIONS: "Files never to move",
}


class TransferError(ValueError):
    """The file can't be imported; the message is written for the end user."""


@dataclass
class ImportSummary:
    rules_added: list[str] = field(default_factory=list)
    rules_replaced: list[str] = field(default_factory=list)
    rules_skipped: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    folders_added: list[str] = field(default_factory=list)
    folders_updated: list[str] = field(default_factory=list)
    folders_skipped: list[str] = field(default_factory=list)
    default_pattern: str | None = None
    exclusions_added: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.rules_added or self.rules_replaced or self.categories or self.folders_added
                    or self.folders_updated or self.default_pattern or self.exclusions_added)

    def lines(self) -> list[str]:
        out = []
        if self.rules_added:
            out.append(f"Added {_count(self.rules_added, 'rule')}: {', '.join(self.rules_added)}")
        if self.rules_replaced:
            out.append(f"Updated {_count(self.rules_replaced, 'rule')}: {', '.join(self.rules_replaced)}")
        if self.categories:
            out.append(f"Categories: {', '.join(self.categories)}")
        if self.default_pattern:
            out.append(f"Default layout: {self.default_pattern}")
        if self.folders_added:
            out.append(f"Added {_count(self.folders_added, 'folder')}: {', '.join(self.folders_added)}")
        if self.folders_updated:
            out.append(f"Updated {_count(self.folders_updated, 'folder')}: {', '.join(self.folders_updated)}")
        if self.exclusions_added:
            out.append(f"Added {self.exclusions_added} item(s) to 'never move'")
        if self.rules_skipped:
            out.append(f"Skipped {_count(self.rules_skipped, 'rule')} that couldn't be used: "
                       + ", ".join(self.rules_skipped))
        if self.folders_skipped:
            out.append("Skipped folders not found on this PC: " + ", ".join(self.folders_skipped))
        return out or ["Nothing new to add. Your settings already match."]


def export_data(settings: Settings, parts: tuple[str, ...] | list[str] = PARTS) -> dict:
    data: dict = {
        "kind": KIND,
        "format": FORMAT_VERSION,
        "app": f"{APP_NAME} {__version__}",
        "exported": datetime.now().isoformat(timespec="seconds"),
    }
    if RULES in parts:
        data["rules"] = [r.to_dict() for r in settings.rules]
    if CATEGORIES in parts:
        data["custom_categories"] = settings.custom_categories
    if LAYOUTS in parts:
        data["pattern"] = settings.pattern
        # Auto-organize stays off on the other PC until someone turns it on there.
        data["folders"] = [{**folder_to_dict(f), "auto": AutoMode.OFF.value} for f in settings.folders]
    if EXCLUSIONS in parts:
        data["excluded_extensions"] = settings.excluded_extensions
        data["excluded_names"] = settings.excluded_names
    return data


def export_file(settings: Settings, path: Path, parts: tuple[str, ...] | list[str] = PARTS) -> Path:
    if path.suffix.lower() != ".json":
        path = path.with_suffix(".json")
    path.write_text(json.dumps(export_data(settings, parts), indent=2), encoding="utf-8")
    return path


def read_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise TransferError(f"Couldn't open the file: {exc.strerror or exc}") from None
    except ValueError:
        raise TransferError("This isn't a settings file from Desktop Organizer.") from None
    if not isinstance(data, dict) or data.get("kind") != KIND:
        raise TransferError("This isn't a settings file from Desktop Organizer.")
    if int(data.get("format", 1)) > FORMAT_VERSION:
        raise TransferError("This file was made by a newer version of Desktop Organizer. Update the app first.")
    return data


def parts_in(data: dict) -> list[str]:
    """Which parts a file or setup contains, in display order."""
    keys = {RULES: "rules", CATEGORIES: "custom_categories", LAYOUTS: "folders", EXCLUSIONS: "excluded_names"}
    found = [part for part, key in keys.items() if key in data]
    if LAYOUTS not in found and "pattern" in data:
        found.append(LAYOUTS)
    return found


def apply(settings: Settings, data: dict, parts: tuple[str, ...] | list[str] = PARTS) -> ImportSummary:
    """Merge ``data`` into ``settings`` (not saved). Rules with the same name are replaced."""
    summary = ImportSummary()
    if RULES in parts:
        _apply_rules(settings, data.get("rules", []), summary)
    if CATEGORIES in parts:
        for name, exts in dict(data.get("custom_categories") or {}).items():
            try:
                settings.set_category(str(name), [str(e) for e in exts])
                summary.categories.append(str(name).strip())
            except (ValueError, TypeError):
                continue
    if LAYOUTS in parts:
        _apply_layouts(settings, data, summary)
    if EXCLUSIONS in parts:
        for key in ("excluded_extensions", "excluded_names"):
            current = getattr(settings, key)
            known = {item.lower() for item in current}
            for item in data.get(key, []) or []:
                if isinstance(item, str) and item.strip() and item.lower() not in known:
                    current.append(item.strip())
                    known.add(item.lower())
                    summary.exclusions_added += 1
    return summary


def _apply_rules(settings: Settings, items: list, summary: ImportSummary) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        rule = Rule.from_dict(item)
        try:
            rule.validate()
        except RuleError:
            summary.rules_skipped.append(rule.name)
            continue
        existing = next((i for i, r in enumerate(settings.rules) if r.name.lower() == rule.name.lower()), None)
        if existing is None:
            settings.rules.append(rule)
            summary.rules_added.append(rule.name)
        else:
            settings.rules[existing] = rule
            summary.rules_replaced.append(rule.name)


def _apply_layouts(settings: Settings, data: dict, summary: ImportSummary) -> None:
    pattern = data.get("pattern")
    if isinstance(pattern, str):
        try:
            pattern = validate(pattern)
        except PatternError:
            pattern = None
        if pattern and pattern != settings.pattern:
            settings.pattern = pattern
            summary.default_pattern = pattern
    for item in data.get("folders", []) or []:
        incoming = folder_from_dict(item)
        if incoming is None:
            continue
        folder = incoming.location
        try:
            safety.ensure_allowed(folder)
        except safety.UnsafeFolderError:
            summary.folders_skipped.append(incoming.path)
            continue
        existing = settings.find_folder(folder)
        profile = settings.add_folder(incoming.path, incoming.pattern)
        profile.rename = valid_name_or_none(incoming.rename) or (existing.rename if existing else None)
        if incoming.destination and resolve_folder(incoming.destination).is_dir():
            profile.destination = incoming.destination
        (summary.folders_updated if existing else summary.folders_added).append(profile.name)


def _count(items: list, word: str) -> str:
    return f"{len(items)} {word}{'s' if len(items) != 1 else ''}"
