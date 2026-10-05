"""GUI entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6 import QtSvg  # noqa: F401 - makes PyInstaller bundle SVG support for the icon
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from desktop_organizer import APP_NAME, __version__
from desktop_organizer.core import Organizer, startup
from desktop_organizer.ui import theme
from desktop_organizer.ui.main_window import MainWindow

ICON_PATH = Path(__file__).resolve().parent.parent / "resources" / "icon.svg"


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        # Gives the app its own taskbar entry and icon instead of Python's.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DesktopOrganizer.App")
        except (OSError, AttributeError):
            pass

    argv = list(argv if argv is not None else sys.argv)
    minimized = startup.MINIMIZED_FLAG in argv
    app = QApplication(argv)
    # The window may be hidden in the tray; quitting is handled by MainWindow.
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("DesktopOrganizer")
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))

    organizer = Organizer()
    theme.apply_theme(app, organizer.settings.theme)
    app.styleHints().colorSchemeChanged.connect(
        lambda _: organizer.settings.theme == "system" and theme.apply_theme(app, "system")
    )

    window = MainWindow(organizer)
    if not (minimized and window.tray is not None):
        window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
