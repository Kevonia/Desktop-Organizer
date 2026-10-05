"""Run slow file operations off the UI thread."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThread, Signal

ProgressFn = Callable[[int, int, str], None]


class Task(QThread):
    """Runs ``fn(progress)`` in a background thread and reports back via signals."""

    progressed = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[ProgressFn], object], parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn(lambda done, total, name: self.progressed.emit(done, total, name))
        except Exception as exc:  # shown to the user rather than crashing the app
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)
