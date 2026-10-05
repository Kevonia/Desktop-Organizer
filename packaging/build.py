"""Build the Windows app: DesktopOrganizer.exe, a portable zip and an installer.

    pip install -e .[build]
    python packaging/build.py              # exe + zip + installer (if Inno Setup is installed)
    python packaging/build.py --no-installer

Output goes to dist/:
    dist/DesktopOrganizer/                       the app folder (run DesktopOrganizer.exe)
    dist/DesktopOrganizer-<version>-portable.zip
    dist/DesktopOrganizer-<version>-Setup.exe
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from desktop_organizer import APP_NAME, __version__  # noqa: E402
from desktop_organizer.core.version import Version  # noqa: E402

PACKAGING = ROOT / "packaging"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
EXE_NAME = "DesktopOrganizer"
ICON_SVG = ROOT / "desktop_organizer" / "resources" / "icon.svg"
ICON_ICO = BUILD / "icon.ico"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

ISCC_CANDIDATES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
]

# Qt modules the app never uses; leaving them out keeps the download small.
EXCLUDES = [
    "tkinter", "unittest", "pydoc", "pytest",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.Qt3DCore", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtBluetooth", "PySide6.QtPositioning",
    "PySide6.QtSerialPort", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
]


def step(message: str) -> None:
    print(f"\n==> {message}", flush=True)


def make_icon() -> None:
    """Render the SVG logo into a multi-size Windows .ico (PNG-compressed entries)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 - needed for rendering
    renderer = QSvgRenderer(str(ICON_SVG))
    images = []
    for size in ICON_SIZES:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        images.append((size, bytes(data)))

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in images:
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    ICON_ICO.write_bytes(header + entries + blobs)


def write_version_file(version: Version) -> Path:
    """Windows file properties (right-click > Properties > Details) for the .exe."""
    v = version.windows_tuple()
    path = BUILD / "version_info.txt"
    path.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{APP_NAME}'),
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', '{EXE_NAME}'),
      StringStruct('OriginalFilename', '{EXE_NAME}.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")
    return path


def run_pyinstaller(version_file: Path) -> Path:
    import PyInstaller.__main__

    args = [
        str(PACKAGING / "launcher.py"),
        "--name", EXE_NAME,
        "--windowed",
        "--onedir",  # starts faster and trips antivirus less often than --onefile
        "--noconfirm",
        "--clean",
        "--icon", str(ICON_ICO),
        "--version-file", str(version_file),
        "--add-data", f"{ROOT / 'desktop_organizer' / 'resources'}{os.pathsep}desktop_organizer/resources",
        "--paths", str(ROOT),
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "pyinstaller"),
        "--specpath", str(BUILD),
    ]
    for module in EXCLUDES:
        args += ["--exclude-module", module]
    PyInstaller.__main__.run(args)
    return DIST / EXE_NAME


def make_zip(app_dir: Path, version: Version) -> Path:
    base = DIST / f"{EXE_NAME}-{version}-portable"
    return Path(shutil.make_archive(str(base), "zip", root_dir=DIST, base_dir=app_dir.name))


def make_installer(app_dir: Path, version: Version) -> Path | None:
    iscc = next((p for p in ISCC_CANDIDATES if p.is_file()), None) or shutil.which("ISCC")
    if not iscc:
        print("Inno Setup not found - skipping the installer. Install it with:")
        print("  winget install JRSoftware.InnoSetup")
        return None
    subprocess.run([
        str(iscc), "/Q",
        f"/DAppVersion={version}",
        f"/DSourceDir={app_dir}",
        f"/DOutputDir={DIST}",
        f"/DIconFile={ICON_ICO}",
        str(PACKAGING / "installer.iss"),
    ], check=True)
    return DIST / f"{EXE_NAME}-{version}-Setup.exe"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-installer", action="store_true", help="skip the Inno Setup installer")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        raise SystemExit("This build script makes Windows packages; run it on Windows.")

    version = Version.parse(__version__)
    print(f"Building {APP_NAME} {version}")
    BUILD.mkdir(exist_ok=True)
    DIST.mkdir(exist_ok=True)
    for old in DIST.glob(f"{EXE_NAME}-{version}-*"):
        old.unlink()

    step("Making icon")
    make_icon()
    step("Freezing the app with PyInstaller")
    app_dir = run_pyinstaller(write_version_file(version))
    step("Making portable zip")
    outputs = [app_dir / f"{EXE_NAME}.exe", make_zip(app_dir, version)]
    if not args.no_installer:
        step("Making installer")
        installer = make_installer(app_dir, version)
        if installer:
            outputs.append(installer)

    step("Done")
    for path in outputs:
        size = path.stat().st_size / 1_000_000
        print(f"  {path.relative_to(ROOT)}  ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
