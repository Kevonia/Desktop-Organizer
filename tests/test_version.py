import re

import pytest

from desktop_organizer import __version__
from desktop_organizer.cli import main
from desktop_organizer.core.version import Version, current, is_newer


def test_parse_and_format():
    assert str(Version.parse("v1.2")) == "1.2.0"
    assert Version.parse("10.0.3") > Version.parse("9.9.9")
    with pytest.raises(ValueError):
        Version.parse("1.x")


@pytest.mark.parametrize("part, expected", [("patch", "1.2.4"), ("minor", "1.3.0"), ("major", "2.0.0")])
def test_bump(part, expected):
    assert str(Version.parse("1.2.3").bump(part)) == expected


def test_current_version_is_valid_and_comparable():
    assert str(current()) == __version__
    assert current() >= Version(1, 0, 0)
    assert is_newer("99.0.0") and not is_newer(__version__)


def test_changelog_has_entry_for_current_version():
    from pathlib import Path

    changelog = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(rf"^## \[{re.escape(__version__)}\]", changelog, re.MULTILINE)


def test_cli_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert __version__ in capsys.readouterr().out
