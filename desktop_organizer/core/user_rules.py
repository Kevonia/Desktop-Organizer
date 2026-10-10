"""User-defined rules such as "name contains invoice AND type is pdf -> Finance/Invoices"."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from desktop_organizer.core import content
from desktop_organizer.core.categories import normalize_extension
from desktop_organizer.core.paths import resolve_folder, same_path
from desktop_organizer.core.structure import PatternError, validate, validate_name


class ConditionKind(str, Enum):
    NAME_CONTAINS = "name_contains"
    NAME_STARTS_WITH = "name_starts_with"
    NAME_MATCHES = "name_matches"
    EXTENSION_IS = "extension_is"
    LARGER_THAN_MB = "larger_than_mb"
    SMALLER_THAN_MB = "smaller_than_mb"
    OLDER_THAN_DAYS = "older_than_days"
    NEWER_THAN_DAYS = "newer_than_days"
    CONTENT_CONTAINS = "content_contains"

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def is_slow(self) -> bool:
        """Needs to open the file, so it is checked after the other conditions."""
        return self is ConditionKind.CONTENT_CONTAINS

    @property
    def is_number(self) -> bool:
        return self in (ConditionKind.LARGER_THAN_MB, ConditionKind.SMALLER_THAN_MB,
                        ConditionKind.OLDER_THAN_DAYS, ConditionKind.NEWER_THAN_DAYS)


_LABELS = {
    ConditionKind.NAME_CONTAINS: "Name contains",
    ConditionKind.NAME_STARTS_WITH: "Name starts with",
    ConditionKind.NAME_MATCHES: "Name matches (e.g. IMG_*.jpg)",
    ConditionKind.EXTENSION_IS: "Type is (e.g. pdf, docx)",
    ConditionKind.LARGER_THAN_MB: "Larger than (MB)",
    ConditionKind.SMALLER_THAN_MB: "Smaller than (MB)",
    ConditionKind.OLDER_THAN_DAYS: "Older than (days)",
    ConditionKind.NEWER_THAN_DAYS: "Newer than (days)",
    ConditionKind.CONTENT_CONTAINS: "Text inside contains (PDF, Word, text)",
}


class RuleAction(str, Enum):
    MOVE = "move"
    SKIP = "skip"  # leave matching files where they are


class RuleError(ValueError):
    """A rule can't be used; the message is written for the end user."""


@dataclass
class Condition:
    kind: ConditionKind
    value: str

    def validate(self) -> None:
        if not self.value.strip():
            raise RuleError(f"'{self.kind.label}' needs a value.")
        if self.kind.is_number:
            try:
                if float(self.value) < 0:
                    raise ValueError
            except ValueError:
                raise RuleError(f"'{self.kind.label}' needs a number, not '{self.value}'.") from None

    def matches(self, path: Path, size: int, when: datetime, now: datetime) -> bool:
        name = path.name.lower()
        value = self.value.strip()
        kind = self.kind
        if kind is ConditionKind.NAME_CONTAINS:
            return value.lower() in name
        if kind is ConditionKind.NAME_STARTS_WITH:
            return name.startswith(value.lower())
        if kind is ConditionKind.NAME_MATCHES:
            return fnmatch.fnmatch(name, value.lower())
        if kind is ConditionKind.EXTENSION_IS:
            wanted = {normalize_extension(e) for e in value.replace(";", ",").split(",") if e.strip()}
            return normalize_extension(path.suffix) in wanted
        if kind is ConditionKind.CONTENT_CONTAINS:
            return content.contains(path, value)
        number = float(value)
        if kind is ConditionKind.LARGER_THAN_MB:
            return size > number * 1_000_000
        if kind is ConditionKind.SMALLER_THAN_MB:
            return size < number * 1_000_000
        age_days = (now - when).total_seconds() / 86_400
        if kind is ConditionKind.OLDER_THAN_DAYS:
            return age_days > number
        return age_days < number  # NEWER_THAN_DAYS


@dataclass
class Rule:
    name: str
    conditions: list[Condition] = field(default_factory=list)
    match_all: bool = True
    action: RuleAction = RuleAction.MOVE
    destination: str = ""  # a structure pattern, e.g. "Finance/Invoices/{year}"
    enabled: bool = True
    folders: list[str] = field(default_factory=list)  # folder specs it applies to; empty = all
    rename: str = ""  # a name template, e.g. "{date} {name}"; empty keeps the name

    def validate(self) -> None:
        if not self.name.strip():
            raise RuleError("Give the rule a name.")
        if not self.conditions:
            raise RuleError(f"Rule '{self.name}' needs at least one condition.")
        for condition in self.conditions:
            condition.validate()
        if self.action is RuleAction.MOVE:
            try:
                self.destination = validate(self.destination)
            except PatternError as exc:
                raise RuleError(f"Rule '{self.name}': {exc}") from None
            if self.rename.strip():
                try:
                    self.rename = validate_name(self.rename)
                except PatternError as exc:
                    raise RuleError(f"Rule '{self.name}' new name: {exc}") from None
            else:
                self.rename = ""

    def applies_to(self, folder: Path) -> bool:
        return not self.folders or any(same_path(resolve_folder(f), folder) for f in self.folders)

    def matches(self, path: Path, size: int, when: datetime, now: datetime | None = None) -> bool:
        if not self.enabled or not self.conditions:
            return False
        now = now or datetime.now()
        try:
            # Cheap checks first, so a file's contents are only read when they could decide the match.
            ordered = sorted(self.conditions, key=lambda c: c.kind.is_slow)
            results = (c.matches(path, size, when, now) for c in ordered)
            return all(results) if self.match_all else any(results)
        except ValueError:  # a number that no longer parses; treat as no match
            return False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "conditions": [{"kind": c.kind.value, "value": c.value} for c in self.conditions],
            "match_all": self.match_all,
            "action": self.action.value,
            "destination": self.destination,
            "enabled": self.enabled,
            "folders": list(self.folders),
            "rename": self.rename,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Rule":
        conditions = []
        for item in data.get("conditions", []):
            try:
                conditions.append(Condition(ConditionKind(item["kind"]), str(item.get("value", ""))))
            except (KeyError, ValueError, TypeError):
                continue
        try:
            action = RuleAction(data.get("action", "move"))
        except ValueError:
            action = RuleAction.MOVE
        return cls(
            name=str(data.get("name", "Rule")),
            conditions=conditions,
            match_all=bool(data.get("match_all", True)),
            action=action,
            destination=str(data.get("destination", "")),
            enabled=bool(data.get("enabled", True)),
            folders=[str(f) for f in data.get("folders", [])],
            rename=str(data.get("rename", "") or ""),
        )


def first_match(rules: list[Rule], folder: Path, path: Path, size: int, when: datetime) -> Rule | None:
    now = datetime.now()
    for rule in rules:
        if rule.applies_to(folder) and rule.matches(path, size, when, now):
            return rule
    return None
