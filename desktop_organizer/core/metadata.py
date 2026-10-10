"""Read what's recorded inside files: when a photo was taken, the camera, music tags,
and the website a download came from. Pure Python, read-only, and never fatal:
anything unreadable comes back as None.
"""

from __future__ import annotations

import os
import struct
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

TIFF_TYPES = {"tif", "tiff", "dng", "cr2", "nef", "arw", "orf", "rw2", "pef", "srw", "raf"}
JPEG_TYPES = {"jpg", "jpeg", "jpe", "jfif"}
AUDIO_TYPES = {"mp3", "flac", "m4a", "mp4", "aac", "ogg", "opus", "oga"}

_HEAD_BYTES = 1_000_000  # photo metadata sits near the start of the file


@dataclass(frozen=True)
class PhotoInfo:
    taken: datetime | None = None
    camera: str | None = None


@dataclass(frozen=True)
class AudioInfo:
    artist: str | None = None
    album: str | None = None


@dataclass(frozen=True)
class DownloadInfo:
    host_url: str | None = None      # where the file itself was downloaded from
    referrer_url: str | None = None  # the page that linked to it

    @property
    def site(self) -> str | None:
        """The website a person would recognise, e.g. 'github.com'."""
        for url in (self.referrer_url, self.host_url):
            host = _host(url)
            if host:
                return host
        return None


# --- cache --------------------------------------------------------------------------

_cache: dict[tuple[str, str], tuple[int, float, object]] = {}
_lock = threading.Lock()
_CACHE_LIMIT = 2000


def _cached(kind: str, path: Path, reader):
    try:
        st = path.stat()
    except OSError:
        return None
    key = (kind, os.path.normcase(str(path)))
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == st.st_size and hit[1] == st.st_mtime:
            return hit[2]
    try:
        value = reader(path)
    except (OSError, ValueError, struct.error, IndexError, UnicodeError):
        value = None
    with _lock:
        if len(_cache) >= _CACHE_LIMIT:
            _cache.clear()
        _cache[key] = (st.st_size, st.st_mtime, value)
    return value


def clear_cache() -> None:
    with _lock:
        _cache.clear()


# --- photos ---------------------------------------------------------------------------


def photo_info(path: Path) -> PhotoInfo | None:
    ext = path.suffix.lower().lstrip(".")
    if ext not in JPEG_TYPES and ext not in TIFF_TYPES:
        return None
    return _cached("photo", path, _read_photo)


def _read_photo(path: Path) -> PhotoInfo | None:
    with open(path, "rb") as fh:
        head = fh.read(_HEAD_BYTES)
    if head[:2] == b"\xff\xd8":
        tiff = _jpeg_exif(head)
    elif head[:4] in (b"II*\x00", b"MM\x00*") or head[:4] == b"IIRO" or head[:2] in (b"II", b"MM"):
        tiff = head
    elif head[:8] == b"FUJIFILM":  # RAF: an embedded JPEG holds the EXIF data
        offset = struct.unpack(">I", head[84:88])[0]
        tiff = _jpeg_exif(head[offset:])
    else:
        return None
    return _parse_tiff(tiff) if tiff else None


def _jpeg_exif(data: bytes) -> bytes | None:
    """Return the TIFF block inside a JPEG's APP1 'Exif' segment."""
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            return None
        marker = data[pos + 1]
        if marker in (0xD9, 0xDA):  # end of image / start of scan: no more metadata
            return None
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        segment = data[pos + 4:pos + 2 + length]
        if marker == 0xE1 and segment[:6] == b"Exif\x00\x00":
            return segment[6:]
        pos += 2 + length
    return None


def _parse_tiff(data: bytes) -> PhotoInfo | None:
    order = {b"II": "<", b"MM": ">"}.get(data[:2])
    if order is None:
        return None
    ifd0 = struct.unpack(order + "I", data[4:8])[0]
    tags = _read_ifd(data, order, ifd0)
    exif_offset = tags.get(0x8769)
    exif = _read_ifd(data, order, exif_offset) if isinstance(exif_offset, int) else {}
    taken = None
    for tag, source in ((0x9003, exif), (0x9004, exif), (0x0132, tags)):
        taken = _exif_date(source.get(tag))
        if taken:
            break
    camera = _camera_name(tags.get(0x010F), tags.get(0x0110))
    if taken is None and camera is None:
        return None
    return PhotoInfo(taken, camera)


def _read_ifd(data: bytes, order: str, offset: int) -> dict[int, object]:
    """Tags in one TIFF directory. Only ASCII strings and LONG offsets are needed here."""
    tags: dict[int, object] = {}
    if offset <= 0 or offset + 2 > len(data):
        return tags
    count = struct.unpack(order + "H", data[offset:offset + 2])[0]
    for i in range(min(count, 500)):
        entry = offset + 2 + i * 12
        if entry + 12 > len(data):
            break
        tag, kind, n = struct.unpack(order + "HHI", data[entry:entry + 8])
        raw = data[entry + 8:entry + 12]
        if kind == 2:  # ASCII
            start = entry + 8 if n <= 4 else struct.unpack(order + "I", raw)[0]
            text = data[start:start + n].split(b"\x00", 1)[0]
            tags[tag] = text.decode("latin-1", "replace").strip()
        elif kind == 4 and n == 1:  # LONG
            tags[tag] = struct.unpack(order + "I", raw)[0]
        elif kind == 3 and n == 1:  # SHORT
            tags[tag] = struct.unpack(order + "H", raw[:2])[0]
    return tags


def _exif_date(value: object) -> datetime | None:
    if not isinstance(value, str) or len(value) < 19:
        return None
    try:
        when = datetime.strptime(value[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    return when if when.year >= 1900 else None


def _camera_name(make: object, model: object) -> str | None:
    make = make.strip() if isinstance(make, str) else ""
    model = model.strip() if isinstance(model, str) else ""
    if not model:
        return make or None
    brand = make.split()[0] if make else ""
    if brand and brand.lower() not in model.lower():
        if brand.isupper() or brand.islower():
            brand = brand.capitalize()
        return f"{brand} {model}"
    return model


# --- music --------------------------------------------------------------------------


def audio_info(path: Path) -> AudioInfo | None:
    if path.suffix.lower().lstrip(".") not in AUDIO_TYPES:
        return None
    return _cached("audio", path, _read_audio)


def _read_audio(path: Path) -> AudioInfo | None:
    with open(path, "rb") as fh:
        head = fh.read(10)
        fh.seek(0)
        if head[:3] == b"ID3":
            info = _id3v2(fh)
            if info:
                return info
        if head[:4] == b"fLaC":
            return _flac(fh)
        if head[4:8] == b"ftyp":
            return _mp4(fh)
        if head[:4] == b"OggS":
            return _ogg(fh)
        return _id3v1(fh)


def _tag_info(tags: dict[str, str]) -> AudioInfo | None:
    artist = tags.get("albumartist") or tags.get("artist")
    album = tags.get("album")
    if not artist and not album:
        return None
    return AudioInfo(artist or None, album or None)


def _id3_text(frame: bytes) -> str:
    if not frame:
        return ""
    encoding, body = frame[0], frame[1:]
    if encoding == 0:
        text = body.decode("latin-1")
    elif encoding == 1:
        text = body.decode("utf-16")
    elif encoding == 2:
        text = body.decode("utf-16-be")
    else:
        text = body.decode("utf-8", "replace")
    # Several values are separated by NULs; the first one is what people expect.
    return text.split("\x00", 1)[0].strip()


def _synchsafe(raw: bytes) -> int:
    return (raw[0] << 21) | (raw[1] << 14) | (raw[2] << 7) | raw[3]


_ID3_FRAMES = {
    "TPE1": "artist", "TPE2": "albumartist", "TALB": "album",
    "TP1": "artist", "TP2": "albumartist", "TAL": "album",
}


def _id3v2(fh) -> AudioInfo | None:
    header = fh.read(10)
    major, flags = header[3], header[5]
    data = fh.read(_synchsafe(header[6:10]))
    pos = 0
    if flags & 0x40:  # extended header
        size = _synchsafe(data[:4]) if major == 4 else struct.unpack(">I", data[:4])[0] + 4
        pos = size
    tags: dict[str, str] = {}
    id_len, head_len = (3, 6) if major == 2 else (4, 10)
    while pos + head_len <= len(data):
        frame_id = data[pos:pos + id_len].decode("latin-1", "replace")
        if not frame_id.strip("\x00"):
            break
        if major == 2:
            size = int.from_bytes(data[pos + 3:pos + 6], "big")
        elif major == 4:
            size = _synchsafe(data[pos + 4:pos + 8])
        else:
            size = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body = data[pos + head_len:pos + head_len + size]
        if frame_id in _ID3_FRAMES:
            tags[_ID3_FRAMES[frame_id]] = _id3_text(body)
        pos += head_len + size
    return _tag_info(tags)


def _id3v1(fh) -> AudioInfo | None:
    fh.seek(0, os.SEEK_END)
    if fh.tell() < 128:
        return None
    fh.seek(-128, os.SEEK_END)
    block = fh.read(128)
    if block[:3] != b"TAG":
        return None

    def field(start: int) -> str:
        return block[start:start + 30].split(b"\x00", 1)[0].decode("latin-1").strip()

    return _tag_info({"artist": field(33), "album": field(63)})


def _vorbis_comments(block: bytes) -> dict[str, str]:
    vendor_len = struct.unpack("<I", block[:4])[0]
    pos = 4 + vendor_len
    count = struct.unpack("<I", block[pos:pos + 4])[0]
    pos += 4
    tags: dict[str, str] = {}
    for _ in range(min(count, 1000)):
        length = struct.unpack("<I", block[pos:pos + 4])[0]
        text = block[pos + 4:pos + 4 + length].decode("utf-8", "replace")
        pos += 4 + length
        key, _, value = text.partition("=")
        key = key.lower().replace(" ", "")
        if key in ("artist", "albumartist", "album") and key not in tags:
            tags[key] = value.strip()
    return tags


def _flac(fh) -> AudioInfo | None:
    fh.seek(4)
    while True:
        header = fh.read(4)
        if len(header) < 4:
            return None
        last, kind = header[0] & 0x80, header[0] & 0x7F
        length = int.from_bytes(header[1:4], "big")
        if kind == 4:
            return _tag_info(_vorbis_comments(fh.read(length)))
        if last:
            return None
        fh.seek(length, os.SEEK_CUR)


def _ogg(fh) -> AudioInfo | None:
    # Comments live in the second packet, normally within the first few pages.
    data = fh.read(256_000)
    for marker in (b"\x03vorbis", b"OpusTags"):
        index = data.find(marker)
        if index >= 0:
            return _tag_info(_vorbis_comments(data[index + len(marker):]))
    return None


_MP4_KEYS = {b"\xa9ART": "artist", b"aART": "albumartist", b"\xa9alb": "album"}


def _mp4_atoms(fh, end: int):
    while fh.tell() + 8 <= end:
        start = fh.tell()
        size, kind = struct.unpack(">I4s", fh.read(8))
        header = 8
        if size == 1:
            size = struct.unpack(">Q", fh.read(8))[0]
            header = 16
        elif size == 0:
            size = end - start
        if size < header:
            return
        yield kind, start + header, start + size
        fh.seek(start + size)


def _mp4(fh) -> AudioInfo | None:
    fh.seek(0, os.SEEK_END)
    end = fh.tell()
    fh.seek(0)
    path = [b"moov", b"udta", b"meta", b"ilst"]
    body_start, body_end = 0, end
    for wanted in path:
        for kind, start, stop in _mp4_atoms(fh, body_end):
            if kind == wanted:
                body_start, body_end = start, stop
                if wanted == b"meta":
                    body_start += 4  # version and flags
                fh.seek(body_start)
                break
        else:
            return None
    tags: dict[str, str] = {}
    for kind, start, stop in list(_mp4_atoms(fh, body_end)):
        key = _MP4_KEYS.get(kind)
        if key is None:
            continue
        fh.seek(start)
        for inner, data_start, data_stop in _mp4_atoms(fh, stop):
            if inner == b"data":
                fh.seek(data_start + 8)  # type and locale
                tags[key] = fh.read(data_stop - data_start - 8).decode("utf-8", "replace").strip()
                break
    return _tag_info(tags)


# --- downloads ---------------------------------------------------------------------


def download_info(path: Path) -> DownloadInfo | None:
    """Where a download came from, from the 'Zone.Identifier' Windows attaches to downloads."""
    if sys.platform != "win32":
        return None
    return _cached("download", path, _read_zone)


def _read_zone(path: Path) -> DownloadInfo | None:
    try:
        with open(f"{path}:Zone.Identifier", encoding="utf-8", errors="replace") as fh:
            text = fh.read(8192)
    except OSError:
        return None
    values = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip().lower()] = value.strip()
    host, referrer = values.get("hosturl"), values.get("referrerurl")
    if not host and not referrer:
        return None
    return DownloadInfo(host or None, referrer or None)


def _host(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("blob:"):
        url = url[5:]
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https", "ftp") or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    return host[4:] if host.startswith("www.") else host
