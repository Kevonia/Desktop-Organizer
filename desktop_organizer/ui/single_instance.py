"""Keep one copy of the app running; a second launch brings the first one forward."""

from __future__ import annotations

import getpass

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def default_key() -> str:
    # Per user, so two people signed in to one PC each get their own copy.
    return f"DesktopOrganizer-{getpass.getuser()}"


class SingleInstance(QObject):
    """Call ``notify_running()`` first; if it returns False, call ``listen()``."""

    activated = Signal()

    def __init__(self, key: str | None = None, parent=None):
        super().__init__(parent)
        self.key = key or default_key()
        self.server: QLocalServer | None = None

    def notify_running(self, timeout_ms: int = 500) -> bool:
        """Ask an already-running copy to show itself. True if one answered."""
        socket = QLocalSocket()
        socket.connectToServer(self.key)
        if not socket.waitForConnected(timeout_ms):
            return False
        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(timeout_ms)
        socket.disconnectFromServer()
        return True

    def listen(self) -> bool:
        # A crashed copy can leave a stale server name behind; clear it first.
        QLocalServer.removeServer(self.key)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._on_connection)
        return self.server.listen(self.key)

    def _on_connection(self) -> None:
        while self.server is not None and self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            connection.disconnected.connect(connection.deleteLater)
        self.activated.emit()
