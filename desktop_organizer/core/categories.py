"""Group file extensions into human-friendly categories."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

OTHER = "Other"

CATEGORIES: dict[str, frozenset[str]] = {
    "Images": frozenset({
        "jpg", "jpeg", "png", "gif", "bmp", "webp", "tif", "tiff", "svg", "ico",
        "heic", "heif", "raw", "cr2", "nef", "arw", "psd", "ai", "xcf",
    }),
    "Documents": frozenset({
        "pdf", "doc", "docx", "odt", "rtf", "txt", "md", "tex", "pages", "epub",
    }),
    "Spreadsheets": frozenset({"xls", "xlsx", "xlsm", "ods", "csv", "tsv", "numbers"}),
    "Presentations": frozenset({"ppt", "pptx", "odp", "key"}),
    "Videos": frozenset({"mp4", "mkv", "mov", "avi", "wmv", "flv", "webm", "m4v", "mpg", "mpeg", "3gp"}),
    "Audio": frozenset({"mp3", "wav", "flac", "aac", "ogg", "m4a", "wma", "opus", "aiff"}),
    "Archives": frozenset({"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "iso"}),
    "Installers": frozenset({"exe", "msi", "msix", "appx", "dmg", "pkg", "deb", "rpm", "apk", "appimage"}),
    "Code": frozenset({
        "py", "js", "ts", "jsx", "tsx", "html", "htm", "css", "json", "xml", "yml", "yaml",
        "java", "c", "cpp", "h", "cs", "go", "rs", "rb", "php", "sh", "ps1", "bat", "sql",
        "dart", "kt", "swift", "ipynb",
    }),
    "Fonts": frozenset({"ttf", "otf", "woff", "woff2"}),
}

_BY_EXTENSION = {ext: name for name, exts in CATEGORIES.items() for ext in exts}


def normalize_extension(ext: str) -> str:
    return ext.strip().lower().lstrip(".")


def category_for(extension: str, custom: Mapping[str, Iterable[str]] | None = None) -> str:
    """Return the category for an extension given with or without the leading dot.

    User-defined categories in ``custom`` win over the built-in ones.
    """
    ext = normalize_extension(extension)
    for name, exts in (custom or {}).items():
        if ext in {normalize_extension(e) for e in exts}:
            return name
    return _BY_EXTENSION.get(ext, OTHER)
