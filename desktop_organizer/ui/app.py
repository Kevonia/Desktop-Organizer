"""GUI entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6 import QtSvg  # noqa: F401 - makes PyInstaller bundle SVG support for the icon
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from desktop_organizer import APP_NAME, __version__
from desktop_organizer.core import Organizer, shell, startup
from desktop_organizer.core.logs import log, setup_logging
from desktop_organizer.ui import theme
from desktop_organizer.ui.errors import install_error_handler
from desktop_organizer.ui.main_window import MainWindow
from desktop_organizer.ui.single_instance import SHOW, SingleInstance

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
    request = shell.parse_args(argv)  # from the File Explorer right-click menu
    message = "\t".join(request) if request else SHOW
    app = QApplication(argv)
    # The window may be hidden in the tray; quitting is handled by MainWindow.
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("DesktopOrganizer")
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))

    # Already running (maybe hidden in the tray)? Bring that copy forward instead.
    instance = SingleInstance()
    if instance.notify_running(message):
        return 0
    instance.listen()

    setup_logging()
    install_error_handler()

    organizer = Organizer()
    theme.apply_theme(app, organizer.settings.theme)
    app.styleHints().colorSchemeChanged.connect(
        lambda _: organizer.settings.theme == "system" and theme.apply_theme(app, "system")
    )

    window = MainWindow(organizer)
    instance.activated.connect(window.show_window)
    instance.messageReceived.connect(window.handle_message)
    if not (minimized and window.tray is not None) or request:
        window.show()
    if request:
        QTimer.singleShot(0, lambda: window.handle_message(message))
    elif not organizer.settings.welcome_shown and not minimized:
        QTimer.singleShot(300, window.show_welcome)
    try:
        shell.refresh()  # keep the Explorer menu pointing at this copy after an update or a move
    except OSError as exc:
        log.warning("Couldn't update the File Explorer menu: %s", exc)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
