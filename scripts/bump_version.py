"""Bump the app version and roll CHANGELOG.md's "Unreleased" notes into a release.

    python scripts/bump_version.py patch      # 1.0.0 -> 1.0.1  (bug fixes)
    python scripts/bump_version.py minor      # 1.0.0 -> 1.1.0  (new features)
    python scripts/bump_version.py major      # 1.0.0 -> 2.0.0  (big/breaking changes)
    python scripts/bump_version.py 1.4.2      # set an exact version
    python scripts/bump_version.py --show     # print the current version
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from desktop_organizer.core.version import Version  # noqa: E402

INIT = ROOT / "desktop_organizer" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"
VERSION_LINE = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)


def read_version() -> Version:
    match = VERSION_LINE.search(INIT.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit(f"No __version__ line found in {INIT}")
    return Version.parse(match.group(1))


def write_version(version: Version) -> None:
    text = INIT.read_text(encoding="utf-8")
    INIT.write_text(VERSION_LINE.sub(f'__version__ = "{version}"', text), encoding="utf-8")


def release_changelog(version: Version) -> bool:
    """Turn '## [Unreleased]' into '## [x.y.z] - date' and start a fresh Unreleased section."""
    if not CHANGELOG.exists():
        return False
    text = CHANGELOG.read_text(encoding="utf-8")
    heading = "## [Unreleased]"
    if heading not in text:
        return False
    released = f"{heading}\n\n## [{version}] - {date.today().isoformat()}"
    CHANGELOG.write_text(text.replace(heading, released, 1), encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bump the Desktop Organizer version.")
    parser.add_argument("target", nargs="?", help="major, minor, patch, or an exact version like 1.2.0")
    parser.add_argument("--show", action="store_true", help="print the current version and exit")
    args = parser.parse_args(argv)

    old = read_version()
    if args.show or not args.target:
        print(old)
        return 0
    new = old.bump(args.target) if args.target in ("major", "minor", "patch") else Version.parse(args.target)
    if new <= old:
        raise SystemExit(f"New version {new} must be higher than {old}.")

    write_version(new)
    changelog = release_changelog(new)
    print(f"Version {old} -> {new}")
    print("CHANGELOG.md updated." if changelog else "Note: CHANGELOG.md has no [Unreleased] section to release.")
    print("\nNext steps:")
    print(f'  git commit -am "Release {new}"')
    print(f"  git tag v{new}")
    print("  python packaging/build.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
