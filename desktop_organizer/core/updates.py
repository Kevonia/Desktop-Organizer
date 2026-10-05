"""Check GitHub Releases for a newer version. Only runs when the user asks or opts in."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from desktop_organizer import APP_NAME, __version__
from desktop_organizer.core.version import Version

REPO = "Kevonia/Desktop-Organizer"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"

Fetch = Callable[[str, float], bytes]


class UpdateError(Exception):
    """The check couldn't be completed; the message is written for the end user."""


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    page_url: str
    download_url: str | None  # the Setup.exe asset, when the release has one
    notes: str


def check_for_update(current: str = __version__, fetch: Fetch | None = None,
                     timeout: float = 8.0) -> UpdateInfo | None:
    """Return the latest release if it is newer than ``current``, else None."""
    fetch = fetch or _http_get
    try:
        data = json.loads(fetch(RELEASES_API, timeout))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:  # no release published yet
            return None
        raise UpdateError(f"GitHub answered with error {exc.code}. Try again later.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise UpdateError("Couldn't reach GitHub. Check your internet connection and try again.") from None
    except ValueError:
        raise UpdateError("GitHub sent an answer the app couldn't read.") from None
    info = parse_release(data)
    if info is None:
        return None
    return info if Version.parse(info.version) > Version.parse(current) else None


def parse_release(data: dict) -> UpdateInfo | None:
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = str(data.get("tag_name", ""))
    try:
        version = str(Version.parse(tag))
    except ValueError:
        return None
    download = None
    for asset in data.get("assets") or []:
        name = str(asset.get("name", ""))
        if name.lower().endswith("-setup.exe"):
            download = asset.get("browser_download_url")
            break
    return UpdateInfo(
        version=version,
        page_url=str(data.get("html_url") or RELEASES_PAGE),
        download_url=download,
        notes=str(data.get("body") or "").strip(),
    )


def _http_get(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{APP_NAME.replace(' ', '')}/{__version__}",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()
