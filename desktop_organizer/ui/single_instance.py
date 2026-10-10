"""Keep one copy of the app running; a second launch brings the first one forward,
passing along what it was asked to do (e.g. from the File Explorer menu)."""

from __future__ import annotations

import getpass
import weakref

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SHOW = "show"


def default_key() -> str:
    # Per user, so two people signed in to one PC each get their own copy.
    return f"DesktopOrganizer-{getpass.getuser()}"


class SingleInstance(QObject):
    """Call ``notify_running()`` first; if it returns False, call ``listen()``."""

    activated = Signal()
    messageReceived = Signal(str)  # e.g. "organize\tC:\\Users\\me\\Downloads"

    def __init__(self, key: str | None = None, parent=None):
        super().__init__(parent)
        self.key = key or default_key()
        self.server: QLocalServer | None = None

    def notify_running(self, message: str = SHOW, timeout_ms: int = 500) -> bool:
        """Pass ``message`` to an already-running copy. True if one answered."""
        socket = QLocalSocket()
        socket.connectToServer(self.key)
        if not socket.waitForConnected(timeout_ms):
            return False
        socket.write(message.encode("utf-8") + b"\n")
        socket.flush()
        socket.waitForBytesWritten(timeout_ms)
        # Hanging up first can lose the message on Windows, so let the running copy close
        # the connection once it has read it.
        if not socket.waitForDisconnected(timeout_ms):
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
            if connection.state() == QLocalSocket.LocalSocketState.UnconnectedState:
                self._handle(bytes(connection.readAll()))
                connection.deleteLater()
                continue
            # A weak reference: holding ``self`` here would keep it alive in a cycle through Qt
            # and let it be torn down at a bad moment later.
            me = weakref.ref(self)
            state = {"data": bytearray(), "handled": False}
            connection.readyRead.connect(lambda c=connection, s=state: me() and me()._read(c, s))
            connection.disconnected.connect(lambda c=connection, s=state: me() and me()._closed(c, s))

    def _read(self, connection: QLocalSocket, state: dict) -> None:
        state["data"].extend(bytes(connection.readAll()))
        if b"\n" in state["data"] and not state["handled"]:
            state["handled"] = True
            self._handle(bytes(state["data"]).split(b"\n", 1)[0])
            connection.disconnectFromServer()  # tells the other copy it can exit

    def _closed(self, connection: QLocalSocket, state: dict) -> None:
        if not state["handled"]:
            state["handled"] = True
            state["data"].extend(bytes(connection.readAll()))
            self._handle(bytes(state["data"]))
        connection.deleteLater()

    def _handle(self, data: bytes) -> None:
        message = data.decode("utf-8", "replace").strip() or SHOW
        self.activated.emit()
        if message != SHOW:
            self.messageReceived.emit(message)
