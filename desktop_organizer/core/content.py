"""Read the text inside documents so rules can match on it, e.g. 'contains Invoice #'.

PDFs are read with pypdf; Word, Excel, PowerPoint and OpenDocument files are zip
files of XML, so they need nothing extra. Only the first pages of big documents
are read, results are cached, and an unreadable file simply has no text.
"""

from __future__ import annotations

import html
import logging
import os
import re
import threading
import zipfile
from pathlib import Path

TEXT_TYPES = {"txt", "md", "csv", "tsv", "log", "json", "xml", "html", "htm", "ini", "yaml", "yml", "eml"}
OFFICE_TYPES = {"docx", "docm", "xlsx", "xlsm", "pptx", "pptm", "odt", "ods", "odp"}
SUPPORTED_TYPES = TEXT_TYPES | OFFICE_TYPES | {"pdf", "rtf"}

MAX_FILE_BYTES = 50_000_000
MAX_PDF_PAGES = 5
MAX_TEXT_BYTES = 2_000_000
MAX_CHARS = 300_000

_SPACE = re.compile(r"\s+")
_TAG = re.compile(r"<[^>]+>")
_PARAGRAPH_END = re.compile(r"</(?:w:p|a:p|text:p|text:h|si|row)>")
_RTF_CONTROL = re.compile(r"\\[a-zA-Z]+-?\d* ?|\\'[0-9a-fA-F]{2}|[{}]")

_cache: dict[str, tuple[int, float, str]] = {}
_lock = threading.Lock()
_CACHE_LIMIT = 500


def is_supported(path: Path) -> bool:
    return path.suffix.lower().lstrip(".") in SUPPORTED_TYPES


def contains(path: Path, needle: str) -> bool:
    """True if the text inside ``path`` contains ``needle`` (ignoring case and line breaks)."""
    wanted = normalize(needle)
    return bool(wanted) and wanted in text_of(path)


def normalize(text: str) -> str:
    return _SPACE.sub(" ", text).strip().lower()


def text_of(path: Path) -> str:
    """The file's text, lower-cased with whitespace collapsed. Empty if it can't be read."""
    if not is_supported(path):
        return ""
    try:
        st = path.stat()
    except OSError:
        return ""
    if st.st_size > MAX_FILE_BYTES:
        return ""
    key = os.path.normcase(str(path))
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == st.st_size and hit[1] == st.st_mtime:
            return hit[2]
    try:
        text = normalize(_extract(path))[:MAX_CHARS]
    except Exception:  # broken or encrypted documents are common; never fail a whole run
        text = ""
    with _lock:
        if len(_cache) >= _CACHE_LIMIT:
            _cache.clear()
        _cache[key] = (st.st_size, st.st_mtime, text)
    return text


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _extract(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext == "pdf":
        return _pdf_text(path)
    if ext in OFFICE_TYPES:
        return _office_text(path)
    raw = _read_head(path)
    text = _decode(raw)
    if ext == "rtf":
        return _RTF_CONTROL.sub(" ", text)
    if ext in ("html", "htm", "xml"):
        return html.unescape(_TAG.sub(" ", text))
    return text


def _read_head(path: Path) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(MAX_TEXT_BYTES)


def _decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", "ignore")
    return raw.decode("utf-8", "ignore")


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # damaged PDFs are noisy but harmless
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            return ""
    parts = []
    for page in reader.pages[:MAX_PDF_PAGES]:
        parts.append(page.extract_text() or "")
    return " ".join(parts)


def _office_text(path: Path) -> str:
    parts = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = info.filename
            if not _is_text_part(name) or info.file_size > MAX_TEXT_BYTES * 5:
                continue
            xml = archive.read(name).decode("utf-8", "ignore")
            xml = _PARAGRAPH_END.sub(" ", xml)
            parts.append(html.unescape(_TAG.sub("", xml)))
            if sum(len(p) for p in parts) > MAX_CHARS:
                break
    return " ".join(parts)


def _is_text_part(name: str) -> bool:
    return (
        name == "word/document.xml"
        or name == "xl/sharedStrings.xml"
        or (name.startswith("ppt/slides/slide") and name.endswith(".xml"))
        or name == "content.xml"
    )
