from datetime import datetime
from pathlib import Path

import pytest

from desktop_organizer.core.structure import PatternError, example, render, size_group, validate

WHEN = datetime(2025, 11, 5)


def r(pattern: str, name: str = "Report.pdf", size: int = 10, custom=None) -> str:
    return render(pattern, Path(name), WHEN, size, custom).as_posix()


def test_all_tokens():
    assert r("{year}/{month}/{month_num}/{month_name}/{month_short}/{day}/{quarter}") == (
        "2025/11-November/11/November/Nov/05/Q4"
    )
    assert r("{type}/{category}/{size}/{first_letter}") == "pdf/Documents/Small/R"


def test_literal_text_and_backslashes():
    assert r("Sorted\\{category} - {year}") == "Sorted/Documents - 2025"


def test_custom_categories_used():
    assert r("{category}", custom={"Invoices": ["pdf"]}) == "Invoices"


def test_odd_file_names():
    assert r("{type}", name="README") == "no_extension"
    assert r("{first_letter}", name="_notes.txt") == "#"


def test_size_groups():
    assert [size_group(s) for s in (0, 5_000_000, 500_000_000, 5_000_000_000)] == [
        "Small", "Medium", "Large", "Huge",
    ]


@pytest.mark.parametrize(
    "pattern",
    ["", "   ", "{year}//{type}", "{nope}", "{year", "{year:04}", "../{year}", "a:b", "{type!r}"],
)
def test_invalid_patterns(pattern):
    with pytest.raises(PatternError):
        validate(pattern)


def test_validate_normalizes():
    assert validate(" /{year}\\{type}/ ") == "{year}/{type}"


def test_example():
    assert example("{category}/{year}") == "Documents/2025/Report.pdf"
