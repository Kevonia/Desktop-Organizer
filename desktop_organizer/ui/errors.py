"""Show unexpected errors as a friendly dialog instead of the app vanishing."""

from __future__ import annotations

import sys
import threading
import traceback

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from desktop_organizer import APP_NAME
from desktop_organizer.core.logs import describe_environment, log, log_dir


def install_error_handler() -> None:
    sys.excepthook = handle_exception
    threading.excepthook = lambda args: handle_exception(args.exc_type, args.exc_value, args.exc_traceback)


def handle_exception(exc_type, exc_value, exc_tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log.error("Unexpected error\n%s", details)
    if QApplication.instance() is None:
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    show_error_dialog(f"{describe_environment()}\n\n{details}")


def show_error_dialog(details: str) -> None:
    box = QMessageBox(QApplication.activeWindow())
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(APP_NAME)
    box.setText("Something went wrong.")
    box.setInformativeText(
        "No files were lost: every move is recorded and can be undone from History. "
        "If this keeps happening, copy the details and include them when you report the problem."
    )
    box.setDetailedText(details)
    copy = box.addButton("Copy details", QMessageBox.ButtonRole.ActionRole)
    logs = box.addButton("Open log folder", QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Close)
    box.exec()
    if box.clickedButton() is copy:
        QGuiApplication.clipboard().setText(details)
    elif box.clickedButton() is logs:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir())))
