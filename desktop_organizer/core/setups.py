"""Ready-made setups: rules, categories and layouts for a kind of user, applied in one click.

Each setup is written in the same format as an exported settings file, so it is
applied by ``transfer.apply`` and merges with whatever the user already has.
"""

from __future__ import annotations

from dataclasses import dataclass

from desktop_organizer.core import transfer
from desktop_organizer.core.config import Settings

RAW = "cr2, cr3, nef, arw, dng, raf, orf, rw2, pef, srw"
PHOTOS = "jpg, jpeg, heic, heif, png, tif, tiff"
VIDEOS = "mp4, mov, m4v, avi, mkv"
AUDIO = "mp3, flac, m4a, aac, ogg, opus, wav"


@dataclass(frozen=True)
class Setup:
    key: str
    name: str
    summary: str
    details: tuple[str, ...]  # plain-language list of what it changes
    data: dict

    def apply(self, settings: Settings) -> transfer.ImportSummary:
        return transfer.apply(settings, self.data)


def _rule(name: str, conditions: list[tuple[str, str]], destination: str = "", *, any_of: bool = False,
          skip: bool = False, folders: tuple[str, ...] = (), rename: str = "") -> dict:
    return {
        "name": name,
        "conditions": [{"kind": kind, "value": value} for kind, value in conditions],
        "match_all": not any_of,
        "action": "skip" if skip else "move",
        "destination": destination,
        "enabled": True,
        "folders": list(folders),
        "rename": rename,
    }


def _folder(path: str, pattern: str | None = None, rename: str | None = None) -> dict:
    return {"path": path, "pattern": pattern, "rename": rename, "auto": "off"}


SETUPS: tuple[Setup, ...] = (
    Setup(
        key="student",
        name="Student",
        summary="Assignments, readings and lecture slides each get their own place, sorted by year.",
        details=(
            "Files with assignment, homework or essay in the name go to School/Assignments/<year>",
            "Slides (PowerPoint, Keynote) go to School/Slides/<year>",
            "PDFs go to School/Readings/<year>",
            "Screenshots go to Screenshots/<year>/<month>",
            "Everything else: Category / Year, on the Desktop, Downloads and Documents",
        ),
        data={
            "kind": transfer.KIND,
            "format": transfer.FORMAT_VERSION,
            "rules": [
                _rule("Assignments", [("name_contains", "assignment"), ("name_contains", "homework"),
                                      ("name_contains", "essay")], "School/Assignments/{year}", any_of=True),
                _rule("Lecture slides", [("extension_is", "ppt, pptx, key, odp")], "School/Slides/{year}"),
                _rule("Readings", [("extension_is", "pdf")], "School/Readings/{year}"),
                _rule("Screenshots", [("name_starts_with", "screenshot")], "Screenshots/{year}/{month}"),
            ],
            "pattern": "{category}/{year}",
            "folders": [_folder("desktop"), _folder("downloads"), _folder("documents")],
        },
    ),
    Setup(
        key="freelancer",
        name="Freelancer",
        summary="Invoices, receipts and contracts are found by name or by the text inside them.",
        details=(
            "Invoices (by name, or 'invoice number' inside) go to Business/Invoices/<year>/<quarter>",
            "Receipts (by name, or 'payment received' inside) go to Business/Receipts/<year>/<quarter>",
            "Contracts and agreements go to Business/Contracts/<year>",
            "Design files (Photoshop, Illustrator, Figma, Sketch) go to Projects/Design/<year>",
            "Everything else: Category / Year / Month, on the Desktop, Downloads and Documents",
        ),
        data={
            "kind": transfer.KIND,
            "format": transfer.FORMAT_VERSION,
            "rules": [
                _rule("Invoices", [("name_contains", "invoice"), ("content_contains", "invoice number")],
                      "Business/Invoices/{year}/{quarter}", any_of=True),
                _rule("Receipts", [("name_contains", "receipt"), ("content_contains", "payment received")],
                      "Business/Receipts/{year}/{quarter}", any_of=True),
                _rule("Contracts", [("name_contains", "contract"), ("name_contains", "agreement"),
                                    ("content_contains", "this agreement")],
                      "Business/Contracts/{year}", any_of=True),
                _rule("Design files", [("extension_is", "psd, ai, fig, sketch, xd, indd")], "Projects/Design/{year}"),
            ],
            "custom_categories": {"Design": ["psd", "ai", "fig", "sketch", "xd", "indd"]},
            "pattern": "{category}/{year}/{month}",
            "folders": [_folder("desktop"), _folder("downloads"), _folder("documents")],
        },
    ),
    Setup(
        key="photographer",
        name="Photographer",
        summary="Photos are sorted by the date they were taken and renamed so they list in order.",
        details=(
            "Pictures: Year / Month the photo was taken, renamed to '<date taken> <name>'",
            "RAW files on the Desktop and in Downloads go to Photos/RAW/<year taken>/<camera>",
            "Photos on the Desktop and in Downloads go to Photos/<year taken>/<month taken>",
            "Videos on the Desktop and in Downloads go to Videos/<year>/<month>",
        ),
        data={
            "kind": transfer.KIND,
            "format": transfer.FORMAT_VERSION,
            "rules": [
                _rule("Camera RAW", [("extension_is", RAW)], "Photos/RAW/{photo_year}/{camera}",
                      folders=("desktop", "downloads")),
                _rule("Photos", [("extension_is", PHOTOS)], "Photos/{photo_year}/{photo_month}",
                      folders=("desktop", "downloads")),
                _rule("Videos", [("extension_is", VIDEOS)], "Videos/{year}/{month}",
                      folders=("desktop", "downloads")),
            ],
            "folders": [
                _folder("pictures", "{photo_year}/{photo_month}", "{photo_date} {name}"),
                _folder("desktop"),
                _folder("downloads"),
            ],
        },
    ),
    Setup(
        key="music",
        name="Music collector",
        summary="Songs are filed by artist and album using the tags inside each file.",
        details=(
            "Music: Artist / Album",
            "Songs on the Desktop and in Downloads go to Music/<artist>/<album>",
        ),
        data={
            "kind": transfer.KIND,
            "format": transfer.FORMAT_VERSION,
            "rules": [
                _rule("Songs", [("extension_is", AUDIO)], "Music/{artist}/{album}",
                      folders=("desktop", "downloads")),
            ],
            "folders": [_folder("music", "{artist}/{album}"), _folder("desktop"), _folder("downloads")],
        },
    ),
)


def get(key: str) -> Setup | None:
    key = key.strip().lower()
    return next((s for s in SETUPS if s.key == key or s.name.lower() == key), None)
