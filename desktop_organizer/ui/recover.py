"""Find & recover: locate moved files, restore earlier versions, bring back deleted files."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_organizer.core import Organizer, recycle_bin, safety
from desktop_organizer.core.paths import display_name, known_folder_key, resolve_folder
from desktop_organizer.core.recycle_bin import RecycledItem
from desktop_organizer.core.search import FoundFile, search
from desktop_organizer.core.versions import FileVersion, VersionedFile
from desktop_organizer.ui.worker import Task

PATH_ROLE = Qt.ItemDataRole.UserRole
FIND, VERSIONS, RECYCLE = range(3)


class RecoverDialog(QDialog):
    def __init__(self, organizer: Organizer, tab: int = FIND, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find & recover")
        self.setMinimumSize(940, 600)
        self.tabs = QTabWidget()
        self.find_tab = FindTab(organizer)
        self.versions_tab = VersionsTab(organizer)
        self.recycle_tab = RecycleTab()
        self.tabs.addTab(self.find_tab, "Find a file")
        self.tabs.addTab(self.versions_tab, "File versions")
        self.tabs.addTab(self.recycle_tab, "Recycle Bin")
        self.tabs.currentChanged.connect(self._on_tab)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)
        self.tabs.setCurrentIndex(tab)
        self._on_tab(tab)

    def _on_tab(self, index: int) -> None:
        if index == VERSIONS:
            self.versions_tab.reload()
        elif index == RECYCLE:
            self.recycle_tab.reload()
        else:
            self.find_tab.search_edit.setFocus()

    def closeEvent(self, event) -> None:
        self.find_tab.stop()
        super().closeEvent(event)


# --- Find a file ---------------------------------------------------------------------


class FindTab(QWidget):
    def __init__(self, organizer: Organizer):
        super().__init__()
        self.organizer = organizer
        self.task: Task | None = None
        self._stop = False
        self._pending: str | None = None

        layout = QVBoxLayout(self)
        intro = QLabel("Type part of a file name. Files the organizer moved show where they went; "
                       "your saved folders are searched too.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("e.g. invoice, resume, IMG_2041")
        self.search_edit.setClearButtonEnabled(True)
        layout.addWidget(self.search_edit)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Where it is now", "Moved from", "Moved on"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        fit_columns(self.tree, widths={0: 220, 2: 240}, stretch=1, fit=(3,))
        self.tree.itemDoubleClicked.connect(lambda *_: self.open_selected())
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.tree, 1)

        row = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("Muted")
        self.open_button = QPushButton("Open")
        self.open_button.clicked.connect(self.open_selected)
        self.show_button = QPushButton("Show in folder")
        self.show_button.clicked.connect(self.show_selected)
        row.addWidget(self.status, 1)
        row.addWidget(self.open_button)
        row.addWidget(self.show_button)
        layout.addLayout(row)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(350)
        self.timer.timeout.connect(lambda: self.start_search(self.search_edit.text()))
        self.search_edit.textChanged.connect(lambda _: self.timer.start())
        self.search_edit.returnPressed.connect(lambda: self.start_search(self.search_edit.text()))
        self._update_buttons()

    def _folders(self) -> list[Path]:
        return self.organizer.search_folders()

    def search_now(self, query: str) -> list[FoundFile]:
        """Run a search on this thread (used by tests and for short queries)."""
        results = search(query, self.organizer.history, self._folders())
        self.show_results(query, results)
        return results

    def start_search(self, query: str) -> None:
        if not query.strip():
            self.show_results(query, [])
            return
        if self.task is not None:  # finish the current one first, then search again
            self._pending = query
            self._stop = True
            return
        self._stop = False
        self.status.setText("Searching...")
        folders = self._folders()
        self.task = Task(lambda progress: search(query, self.organizer.history, folders,
                                                 should_stop=lambda: self._stop), self)
        outcome: dict = {}
        self.task.succeeded.connect(lambda results: outcome.update(results=results))
        self.task.finished.connect(lambda: self._finished(query, outcome))
        self.task.start()

    def _finished(self, query: str, outcome: dict) -> None:
        self.task = None
        if self._pending is not None:
            pending, self._pending = self._pending, None
            self.start_search(pending)
            return
        self.show_results(query, outcome.get("results", []))

    def show_results(self, query: str, results: list[FoundFile]) -> None:
        self.tree.clear()
        muted = QBrush(QColor("#8a8f98"))
        for found in results:
            exists = found.exists
            where = str(found.path.parent) + ("" if exists else "   (no longer there)")
            item = QTreeWidgetItem([
                found.name, where,
                str(found.moved_from.parent) if found.moved_from else "",
                found.moved_at.strftime("%Y-%m-%d %H:%M") if found.moved_at else "",
            ])
            item.setData(0, PATH_ROLE, str(found.path))
            item.setToolTip(1, str(found.path))
            if not exists:
                for col in range(4):
                    item.setForeground(col, muted)
            self.tree.addTopLevelItem(item)
        if not query.strip():
            self.status.setText("")
        elif results:
            moved = sum(1 for r in results if r.moved_from)
            self.status.setText(f"{len(results)} found" + (f", {moved} moved by the organizer" if moved else ""))
        else:
            self.status.setText("Nothing found. Deleted files may be in the Recycle Bin or File versions tabs.")
        self._update_buttons()

    def _selected(self) -> Path | None:
        items = self.tree.selectedItems()
        return Path(items[0].data(0, PATH_ROLE)) if items else None

    def _update_buttons(self) -> None:
        path = self._selected()
        ok = bool(path and path.exists())
        self.open_button.setEnabled(ok)
        self.show_button.setEnabled(ok)

    def open_selected(self) -> None:
        path = self._selected()
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def show_selected(self) -> None:
        path = self._selected()
        if path and path.exists():
            reveal(path)

    def stop(self) -> None:
        self._stop = True
        if self.task is not None:
            self.task.wait(3000)


# --- File versions ---------------------------------------------------------------------


class VersionsTab(QWidget):
    def __init__(self, organizer: Organizer):
        super().__init__()
        self.organizer = organizer
        self.settings = organizer.settings

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Files in protected folders keep their last few saved versions, checked about once a minute "
            "while the app runs. Pick a file to see its versions and restore one. Deleted files can be "
            "brought back here too."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        setup = QHBoxLayout()
        self.folder_list = QListWidget()
        self.folder_list.setMaximumHeight(78)
        self.folder_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.folder_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        setup.addWidget(self.folder_list, 1)
        buttons = QVBoxLayout()
        self.add_button = QPushButton("Protect a folder...")
        self.add_button.clicked.connect(self.choose_folder)
        self.remove_button = QPushButton("Stop protecting")
        self.remove_button.clicked.connect(self.remove_folder)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        setup.addLayout(buttons)
        options = QVBoxLayout()
        keep_row = QHBoxLayout()
        keep_row.addWidget(QLabel("Keep"))
        self.keep = QSpinBox()
        self.keep.setRange(1, 20)
        self.keep.setValue(self.settings.versions_to_keep)
        self.keep.valueChanged.connect(self._keep_changed)
        keep_row.addWidget(self.keep)
        keep_row.addWidget(QLabel("versions of each file"))
        keep_row.addStretch()
        options.addLayout(keep_row)
        self.storage = QLabel()
        self.storage.setObjectName("Muted")
        options.addWidget(self.storage)
        actions = QHBoxLayout()
        self.save_now = QPushButton("Save versions now")
        self.save_now.clicked.connect(self.scan_now)
        self.clear_button = QPushButton("Delete all saved versions")
        self.clear_button.clicked.connect(self.clear_all)
        actions.addWidget(self.save_now)
        actions.addWidget(self.clear_button)
        options.addLayout(actions)
        setup.addLayout(options)
        layout.addLayout(setup)

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter files...")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(lambda _: self._load_files())
        layout.addWidget(self.filter)

        splitter = QSplitter()
        self.files = QTreeWidget()
        self.files.setHeaderLabels(["File", "Folder", "Versions", "Last saved"])
        self.files.setRootIsDecorated(False)
        self.files.setAlternatingRowColors(True)
        fit_columns(self.files, widths={0: 190}, stretch=1, fit=(2, 3))
        self.files.itemSelectionChanged.connect(self._load_versions)
        splitter.addWidget(self.files)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.versions = QTreeWidget()
        self.versions.setHeaderLabels(["Saved", "File changed", "Size"])
        self.versions.setRootIsDecorated(False)
        fit_columns(self.versions, widths={}, stretch=0, fit=(1, 2))
        self.versions.itemSelectionChanged.connect(self._update_buttons)
        right_layout.addWidget(self.versions, 1)
        version_buttons = QHBoxLayout()
        self.restore_button = QPushButton("Restore this version")
        self.restore_button.setObjectName("Primary")
        self.restore_button.clicked.connect(self.restore_selected)
        self.copy_button = QPushButton("Save a copy...")
        self.copy_button.clicked.connect(self.save_copy)
        self.open_button = QPushButton("Open")
        self.open_button.clicked.connect(self.open_version)
        version_buttons.addWidget(self.restore_button)
        version_buttons.addWidget(self.copy_button)
        version_buttons.addWidget(self.open_button)
        right_layout.addLayout(version_buttons)
        splitter.addWidget(right)
        splitter.setSizes([520, 380])
        layout.addWidget(splitter, 1)
        self.scan_task: Task | None = None
        self.reload()

    # folders --------------------------------------------------------------------------

    def reload(self) -> None:
        self.folder_list.clear()
        for spec in self.settings.version_folders:
            self.folder_list.addItem(f"{display_name(spec)}  -  {resolve_folder(spec)}")
        if not self.settings.version_folders:
            self.folder_list.addItem("No folders protected yet. Click \"Protect a folder...\" to start.")
        self.remove_button.setEnabled(bool(self.settings.version_folders))
        self.save_now.setEnabled(bool(self.settings.version_folders))
        self.storage.setText(f"Using {_size(self.organizer.versions.storage_used())} for saved versions")
        self._load_files()

    def choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose a folder to protect", str(Path.home()))
        if path:
            self.add_folder(path)

    def add_folder(self, spec: str) -> bool:
        folder = resolve_folder(spec)
        try:
            safety.ensure_allowed(folder)
        except safety.UnsafeFolderError as exc:
            QMessageBox.warning(self, "Can't protect this folder", str(exc))
            return False
        stored = known_folder_key(spec) or str(folder.resolve())
        if any(resolve_folder(f) == resolve_folder(stored) for f in self.settings.version_folders):
            return False
        self.settings.version_folders.append(stored)
        self.settings.save()
        self.reload()
        self.scan_now()
        return True

    def remove_folder(self) -> None:
        row = self.folder_list.currentRow()
        if 0 <= row < len(self.settings.version_folders):
            del self.settings.version_folders[row]
            self.settings.save()
            self.reload()

    def _keep_changed(self, value: int) -> None:
        self.settings.versions_to_keep = value
        self.settings.save()

    def scan_now(self, wait: bool = False) -> None:
        folders = self.organizer.version_folders()
        if not folders or self.scan_task is not None:
            return
        self.save_now.setEnabled(False)
        self.save_now.setText("Saving...")
        self.scan_task = Task(lambda progress: self.organizer.versions.scan(folders), self)
        self.scan_task.finished.connect(self._scan_finished)
        self.scan_task.start()
        if wait:
            self.scan_task.wait()

    def _scan_finished(self) -> None:
        self.scan_task = None
        self.save_now.setText("Save versions now")
        self.reload()

    def clear_all(self) -> None:
        answer = QMessageBox.question(self, "Delete all saved versions",
                                      "Delete every saved version? Your current files are not touched.")
        if answer == QMessageBox.StandardButton.Yes:
            self.organizer.versions.clear()
            self.reload()

    # files and versions -----------------------------------------------------------------

    def _load_files(self) -> None:
        self.files.clear()
        muted = QBrush(QColor("#8a8f98"))
        for entry in self.organizer.versions.files(self.filter.text()):
            entry: VersionedFile
            exists = entry.exists
            item = QTreeWidgetItem([
                entry.path.name + ("" if exists else "  (deleted)"),
                str(entry.path.parent), str(entry.versions), entry.latest.strftime("%Y-%m-%d %H:%M"),
            ])
            item.setData(0, PATH_ROLE, str(entry.path))
            if not exists:
                for col in range(4):
                    item.setForeground(col, muted)
            self.files.addTopLevelItem(item)
        self._load_versions()

    def _current_file(self) -> Path | None:
        items = self.files.selectedItems()
        return Path(items[0].data(0, PATH_ROLE)) if items else None

    def _load_versions(self) -> None:
        self.versions.clear()
        self._version_list: list[FileVersion] = []
        path = self._current_file()
        if path is not None:
            self._version_list = self.organizer.versions.versions(path)
            for index, version in enumerate(self._version_list):
                label = version.saved_at.strftime("%Y-%m-%d %H:%M") + ("  (newest)" if index == 0 else "")
                item = QTreeWidgetItem([label, version.modified.strftime("%Y-%m-%d %H:%M"), _size(version.size)])
                self.versions.addTopLevelItem(item)
        self._update_buttons()

    def _selected_version(self) -> FileVersion | None:
        index = self.versions.indexOfTopLevelItem(self.versions.currentItem()) if self.versions.currentItem() else -1
        return self._version_list[index] if 0 <= index < len(self._version_list) else None

    def _update_buttons(self) -> None:
        ok = self._selected_version() is not None
        for button in (self.restore_button, self.copy_button, self.open_button):
            button.setEnabled(ok)

    def restore_selected(self) -> None:
        version = self._selected_version()
        if version is None:
            return
        when = version.saved_at.strftime("%Y-%m-%d %H:%M")
        text = (f"Replace {version.path.name} with the version saved {when}?\n\n"
                "The current file is saved as a version first, so you can switch back."
                if version.path.exists() else f"Bring back {version.path.name} (saved {when})?")
        if not self.confirm("Restore version", text):
            return
        try:
            target = self.organizer.versions.restore(version)
        except OSError as exc:
            QMessageBox.warning(self, "Restore failed", f"Couldn't restore the file: {exc.strerror or exc}")
            return
        self._load_files()
        QMessageBox.information(self, "Restored", f"Restored {target.name} in {target.parent}.")

    def save_copy(self) -> None:
        version = self._selected_version()
        if version is None:
            return
        stamp = version.saved_at.strftime("%Y-%m-%d %H%M")
        suggested = version.path.with_name(f"{version.path.stem} ({stamp}){version.path.suffix}")
        target, _ = QFileDialog.getSaveFileName(self, "Save a copy of this version", str(suggested))
        if target:
            import shutil

            shutil.copy2(version.blob, target)

    def open_version(self) -> None:
        version = self._selected_version()
        if version is not None:
            # Opens the saved copy read-only in its usual app; edits there don't change the history.
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(version.blob)))

    def confirm(self, title: str, text: str) -> bool:
        return QMessageBox.question(self, title, text) == QMessageBox.StandardButton.Yes


# --- Recycle Bin -------------------------------------------------------------------------


class RecycleTab(QWidget):
    def __init__(self, folders: list[Path] | None = None):
        super().__init__()
        self.folders = folders  # None = this user's real Recycle Bin
        self.items: list[RecycledItem] = []

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Files you deleted normally wait in the Recycle Bin until it is emptied. Select them and click "
            "Restore to put them back where they were. Files deleted with Shift+Delete, or after the bin was "
            "emptied, can't be brought back here; try File versions if the folder was protected."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter by name or folder...")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(lambda _: self._show())
        layout.addWidget(self.filter)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Original location", "Deleted", "Size"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        fit_columns(self.tree, widths={0: 240}, stretch=1, fit=(2, 3))
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.tree, 1)

        row = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("Muted")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        open_bin = QPushButton("Open Recycle Bin")
        open_bin.clicked.connect(open_recycle_bin)
        open_bin.setVisible(sys.platform == "win32")
        self.restore_button = QPushButton("Restore selected")
        self.restore_button.setObjectName("Primary")
        self.restore_button.clicked.connect(self.restore_selected)
        row.addWidget(self.status, 1)
        row.addWidget(refresh)
        row.addWidget(open_bin)
        row.addWidget(self.restore_button)
        layout.addLayout(row)
        self._update_buttons()

    def reload(self) -> None:
        self.items = recycle_bin.list_items(self.folders)
        self._show()

    def _show(self) -> None:
        needle = self.filter.text().strip().lower()
        self.tree.clear()
        for index, entry in enumerate(self.items):
            if needle and needle not in str(entry.original_path).lower():
                continue
            item = QTreeWidgetItem([
                entry.name + ("  (folder)" if entry.is_folder else ""), str(entry.original_path.parent),
                entry.deleted_at.strftime("%Y-%m-%d %H:%M"), _size(entry.size),
            ])
            item.setData(0, PATH_ROLE, index)
            self.tree.addTopLevelItem(item)
        count = len(self.items)
        self.status.setText(f"{count} item{'s' if count != 1 else ''} in the Recycle Bin" if count
                            else "The Recycle Bin is empty.")
        self._update_buttons()

    def _selected(self) -> list[RecycledItem]:
        return [self.items[item.data(0, PATH_ROLE)] for item in self.tree.selectedItems()]

    def _update_buttons(self) -> None:
        self.restore_button.setEnabled(bool(self.tree.selectedItems()))

    def restore_selected(self) -> None:
        chosen = self._selected()
        if not chosen:
            return
        if not self.confirm(f"Put {len(chosen)} item{'s' if len(chosen) != 1 else ''} back where "
                            f"{'they were' if len(chosen) != 1 else 'it was'}?"):
            return
        restored, failed = [], []
        for entry in chosen:
            try:
                restored.append(recycle_bin.restore(entry))
            except OSError as exc:
                failed.append(f"{entry.name}: {exc.strerror or exc}")
        self.reload()
        message = f"Restored {len(restored)} item{'s' if len(restored) != 1 else ''}."
        if restored:
            message += "\n\n" + "\n".join(str(p) for p in restored[:10])
        if failed:
            message += "\n\nCouldn't restore:\n" + "\n".join(failed[:10])
        self.report(message)

    def confirm(self, text: str) -> bool:
        return QMessageBox.question(self, "Restore from Recycle Bin", text) == QMessageBox.StandardButton.Yes

    def report(self, message: str) -> None:
        QMessageBox.information(self, "Recycle Bin", message)


# --- helpers ---------------------------------------------------------------------------


def fit_columns(tree: QTreeWidget, widths: dict[int, int], stretch: int, fit: tuple[int, ...]) -> None:
    """Dates and sizes fit their contents; one column takes the spare room; long paths keep both ends."""
    header = tree.header()
    header.setStretchLastSection(False)
    tree.setTextElideMode(Qt.TextElideMode.ElideMiddle)
    for column, width in widths.items():
        header.resizeSection(column, width)
    header.setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
    for column in fit:
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)


def reveal(path: Path) -> None:
    """Open the file's folder with the file selected."""
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


def open_recycle_bin() -> None:
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "shell:RecycleBinFolder"])


def _size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"
