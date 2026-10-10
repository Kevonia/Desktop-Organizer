"""Tiny hand-built files with real metadata: photos with EXIF, tagged songs, a PDF and a Word file."""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path


def tiff_block(make: str, model: str, taken: str) -> bytes:
    """A little-endian TIFF/EXIF block with Make, Model and DateTimeOriginal."""
    make_b, model_b, date_b = (s.encode() + b"\x00" for s in (make, model, taken))
    ifd0 = 8
    ifd0_size = 2 + 3 * 12 + 4
    strings = ifd0 + ifd0_size
    make_at, model_at = strings, strings + len(make_b)
    exif_ifd = model_at + len(model_b)
    date_at = exif_ifd + 2 + 12 + 4
    out = b"II*\x00" + struct.pack("<I", ifd0)
    out += struct.pack("<H", 3)
    out += struct.pack("<HHII", 0x010F, 2, len(make_b), make_at)
    out += struct.pack("<HHII", 0x0110, 2, len(model_b), model_at)
    out += struct.pack("<HHII", 0x8769, 4, 1, exif_ifd)
    out += struct.pack("<I", 0)
    out += make_b + model_b
    out += struct.pack("<H", 1) + struct.pack("<HHII", 0x9003, 2, len(date_b), date_at) + struct.pack("<I", 0)
    out += date_b
    return out


def jpeg_with_exif(path: Path, make="Canon", model="Canon EOS R6", taken="2021:07:04 10:30:00") -> Path:
    tiff = tiff_block(make, model, taken)
    segment = b"Exif\x00\x00" + tiff
    data = b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 4) + b"\x00\x00"  # an APP0 first, like real cameras
    data += b"\xff\xe1" + struct.pack(">H", len(segment) + 2) + segment + b"\xff\xd9"
    path.write_bytes(data)
    return path


def _synchsafe(n: int) -> bytes:
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def mp3_with_tags(path: Path, artist="Bob Marley", album="Legend", album_artist: str | None = None) -> Path:
    frames = b""
    for frame_id, text in (("TPE1", artist), ("TALB", album), ("TPE2", album_artist)):
        if text is None:
            continue
        body = b"\x03" + text.encode("utf-8")
        frames += frame_id.encode() + struct.pack(">I", len(body)) + b"\x00\x00" + body
    path.write_bytes(b"ID3" + bytes([3, 0, 0]) + _synchsafe(len(frames)) + frames + b"\xff\xfb" + b"\x00" * 64)
    return path


def _vorbis(tags: dict[str, str]) -> bytes:
    vendor = b"test"
    out = struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", len(tags))
    for key, value in tags.items():
        entry = f"{key}={value}".encode()
        out += struct.pack("<I", len(entry)) + entry
    return out


def flac_with_tags(path: Path, artist="Nina Simone", album="Pastel Blues") -> Path:
    streaminfo = b"\x00" + (34).to_bytes(3, "big") + b"\x00" * 34
    comments = _vorbis({"ARTIST": artist, "ALBUM": album})
    block = bytes([0x80 | 4]) + len(comments).to_bytes(3, "big") + comments
    path.write_bytes(b"fLaC" + streaminfo + block)
    return path


def _atom(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body) + 8) + kind + body


def m4a_with_tags(path: Path, artist="Miles Davis", album="Kind of Blue") -> Path:
    def item(kind: bytes, text: str) -> bytes:
        return _atom(kind, _atom(b"data", struct.pack(">II", 1, 0) + text.encode()))

    ilst = _atom(b"ilst", item(b"\xa9ART", artist) + item(b"\xa9alb", album))
    meta = _atom(b"meta", b"\x00\x00\x00\x00" + _atom(b"hdlr", b"\x00" * 25) + ilst)
    moov = _atom(b"moov", _atom(b"mvhd", b"\x00" * 100) + _atom(b"udta", meta))
    path.write_bytes(_atom(b"ftyp", b"M4A \x00\x00\x00\x00") + _atom(b"mdat", b"\x00" * 32) + moov)
    return path


def pdf_with_text(path: Path, text: str) -> Path:
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)
    return path


def docx_with_text(path: Path, *runs: str) -> Path:
    body = "".join(f"<w:r><w:t>{run}</w:t></w:r>" for run in runs)
    xml = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body><w:p>{body}</w:p><w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p></w:body></w:document>")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return path
