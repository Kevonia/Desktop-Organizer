"""Storage stats, ready-made setups, "where did this file come from?" and settings export/import."""

from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_organizer.core import Organizer, setups, transfer
from desktop_organizer.core.origin import FileOrigin, find_origin
from desktop_organizer.core.stats import DEFAULT_STALE_DAYS, FileEntry, FolderStats, collect, format_size
from desktop_organizer.ui.recover import fit_columns, reveal
from desktop_organizer.ui.worker import Task

PATH_ROLE = Qt.ItemDataRole.UserRole


class StatsDialog(QDialog):
    """What's taking up space in a folder, the biggest files, and files not used in a long time."""

    def __init__(self, organizer: Organizer, folder: Path | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Storage stats")
        self.setMinimumSize(900, 620)
        self.organizer = organizer
        self.folder = folder
        self.stats: FolderStats | None = None
        self.task: Task | None = None
        self._stop = False

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.folder_label = QLabel()
        self.folder_label.setObjectName("Muted")
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        choose = QPushButton("Choose folder...")
        choose.clicked.connect(self._choose_folder)
        top.addWidget(self.folder_label, 1)
        top.addWidget(choose)
        top.addWidget(QLabel("Not used in"))
        self.months = QSpinBox()
        self.months.setRange(1, 120)
        self.months.setValue(DEFAULT_STALE_DAYS // 30)
        self.months.setSuffix(" months")
        top.addWidget(self.months)
        self.scan_button = QPushButton("Scan")
        self.scan_button.setObjectName("Primary")
        self.scan_button.clicked.connect(self.scan)
        top.addWidget(self.scan_button)
        layout.addLayout(top)

        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)

        self.summary = QLabel("Choose a folder and press Scan. Nothing is moved or deleted.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.tabs = QTabWidget()
        self.categories = QTreeWidget()
        self.categories.setHeaderLabels(["Category", "Space used", "Share", "Files"])
        self.categories.setRootIsDecorated(False)
        fit_columns(self.categories, widths={0: 180, 2: 260}, stretch=2, fit=(1, 3))
        self.largest = self._file_tree()
        self.stale = self._file_tree()
        self.tabs.addTab(self.categories, "By category")
        self.tabs.addTab(self.largest, "Largest files")
        self.tabs.addTab(self.stale, "Not used lately")
        layout.addWidget(self.tabs, 1)

        bottom = QHBoxLayout()
        note = QLabel("'Not used' means not opened or changed. Windows doesn't always record when "
                      "a file was opened, so check before deleting anything.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        self.show_button = QPushButton("Show in folder")
        self.show_button.clicked.connect(self.show_selected)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        bottom.addWidget(note, 1)
        bottom.addWidget(self.show_button)
        bottom.addWidget(close)
        layout.addLayout(bottom)
        self.tabs.currentChanged.connect(lambda _: self._update_buttons())
        self._show_folder()

    def _file_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels(["Name", "Folder", "Size", "Last used"])
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        fit_columns(tree, widths={0: 240}, stretch=1, fit=(2, 3))
        tree.itemSelectionChanged.connect(self._update_buttons)
        tree.itemDoubleClicked.connect(lambda *_: self.show_selected())
        return tree

    def _show_folder(self) -> None:
        self.folder_label.setText(str(self.folder) if self.folder else "No folder chosen")
        self.scan_button.setEnabled(self.folder is not None)
        self._update_buttons()

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Folder to look at", str(self.folder or Path.home()))
        if path:
            self.folder = Path(path)
            self._show_folder()

    def scan(self, wait: bool = False) -> None:
        if self.folder is None or self.task is not None:
            return
        self._stop = False
        folder, days = self.folder, self.months.value() * 30
        custom = dict(self.organizer.settings.custom_categories)
        self.task = Task(lambda progress: collect(folder, custom, stale_days=days, progress=progress,
                                                  should_stop=lambda: self._stop), self)
        outcome: dict = {}
        self.task.progressed.connect(lambda done, _total, _name: self.progress.setFormat(f"Looked at {done:,} files..."))
        self.task.succeeded.connect(lambda stats: outcome.update(stats=stats))
        self.task.failed.connect(lambda message: outcome.update(error=message))
        self.task.finished.connect(lambda: self._finished(outcome))
        self.progress.setRange(0, 0)
        self.progress.setFormat("Looking at files...")
        self.progress.show()
        self.scan_button.setEnabled(False)
        self.task.start()
        if wait:
            self.task.wait()

    def _finished(self, outcome: dict) -> None:
        self.task = None
        self.progress.hide()
        self.scan_button.setEnabled(True)
        if "error" in outcome:
            QMessageBox.critical(self, "Scan failed", outcome["error"])
            return
        if "stats" in outcome:
            self.show_stats(outcome["stats"])

    def show_stats(self, stats: FolderStats) -> None:
        self.stats = stats
        months = max(stats.stale_days // 30, 1)
        text = (f"<b>{format_size(stats.total_size)}</b> in {stats.file_count:,} files and "
                f"{stats.folder_count:,} folders. "
                f"<b>{format_size(stats.stale_size)}</b> ({stats.stale_count:,} files) "
                f"hasn't been used in {months} month{'s' if months != 1 else ''}.")
        if stats.unreadable:
            text += f" {stats.unreadable:,} items couldn't be read."
        if stats.stopped:
            text += " (Stopped early.)"
        self.summary.setText(text)

        self.categories.clear()
        total = stats.total_size or 1
        for name, entry in stats.categories_by_size():
            item = QTreeWidgetItem([name, format_size(entry.size), "", f"{entry.count:,}"])
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.categories.addTopLevelItem(item)
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(round(entry.size / total * 1000))
            bar.setFormat(f"{entry.size / total:.0%}")
            bar.setMaximumHeight(16)
            self.categories.setItemWidget(item, 2, bar)
        self._fill(self.largest, stats.largest)
        self._fill(self.stale, stats.stale)
        self.tabs.setTabText(2, f"Not used in {months} month{'s' if months != 1 else ''}")
        self._update_buttons()

    def _fill(self, tree: QTreeWidget, entries: list[FileEntry]) -> None:
        tree.clear()
        for entry in entries:
            item = QTreeWidgetItem([entry.path.name, str(entry.path.parent), format_size(entry.size),
                                    entry.last_used.strftime("%Y-%m-%d")])
            item.setData(0, PATH_ROLE, str(entry.path))
            item.setToolTip(0, str(entry.path))
            item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tree.addTopLevelItem(item)

    def _selected(self) -> Path | None:
        tree = self.tabs.currentWidget()
        if tree not in (self.largest, self.stale):
            return None
        items = tree.selectedItems()
        return Path(items[0].data(0, PATH_ROLE)) if items else None

    def _update_buttons(self) -> None:
        self.show_button.setEnabled(self._selected() is not None)

    def show_selected(self) -> None:
        path = self._selected()
        if path is not None:
            reveal(path)

    def closeEvent(self, event) -> None:
        if self.task is not None:
            self._stop = True
            self.task.wait(5000)
        super().closeEvent(event)


class SetupsDialog(QDialog):
    """Pick a ready-made setup; it adds rules, categories and layouts to what's already there."""

    def __init__(self, organizer: Organizer, welcome: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Desktop Organizer" if welcome else "Ready-made setups")
        self.setMinimumSize(760, 440)
        self.organizer = organizer
        self.summary: transfer.ImportSummary | None = None

        layout = QVBoxLayout(self)
        intro = QLabel(
            ("<b>Welcome!</b> Pick the setup closest to how you work and you're ready to go. "
             "You'll see where every file will go before anything moves. " if welcome else "")
            + "A setup adds rules and layouts to your own; nothing is removed, and you can change "
              "everything afterwards."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        splitter = QSplitter()
        self.list = QListWidget()
        for setup in setups.SETUPS:
            item = QListWidgetItem(setup.name)
            item.setData(PATH_ROLE, setup.key)
            self.list.addItem(item)
        self.list.currentRowChanged.connect(self._show_setup)
        splitter.addWidget(self.list)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.details.setTextFormat(Qt.TextFormat.RichText)
        splitter.addWidget(self.details)
        splitter.setSizes([200, 540])
        layout.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.apply_button = QPushButton("Use this setup")
        self.apply_button.setObjectName("Primary")
        self.apply_button.clicked.connect(self.apply_selected)
        close = QPushButton("Skip for now" if welcome else "Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.list.setCurrentRow(0)

    def selected(self) -> setups.Setup | None:
        item = self.list.currentItem()
        return setups.get(item.data(PATH_ROLE)) if item else None

    def _show_setup(self, _row: int) -> None:
        setup = self.selected()
        if setup is None:
            self.details.setText("")
            return
        points = "".join(f"<li>{_escape(line)}</li>" for line in setup.details)
        self.details.setText(f"<h3>{_escape(setup.name)}</h3><p>{_escape(setup.summary)}</p><ul>{points}</ul>")

    def apply_selected(self) -> None:
        setup = self.selected()
        if setup is None:
            return
        settings = self.organizer.settings
        self.summary = setup.apply(settings)
        settings.save()
        self.report(f"{setup.name} setup added", "\n".join(self.summary.lines()))
        self.accept()

    def report(self, title: str, text: str) -> None:
        QMessageBox.information(self, title, text)


class OriginDialog(QDialog):
    """Where a file came from: where the organizer moved it from, and the website it was downloaded from."""

    def __init__(self, organizer: Organizer, path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Where did this file come from?")
        self.setMinimumWidth(620)
        self.origin: FileOrigin = find_origin(path, organizer.history)
        origin = self.origin

        layout = QVBoxLayout(self)
        title = QLabel(path.name)
        title.setObjectName("Title")
        title.setWordWrap(True)
        layout.addWidget(title)
        summary = QLabel(origin.summary())
        summary.setWordWrap(True)
        layout.addWidget(summary)

        form = QFormLayout()
        form.addRow("Now in", _selectable(str(path.parent)))
        if origin.moves:
            form.addRow("Originally in", _selectable(str(origin.original_path.parent)))
            if origin.original_path.name != path.name:
                form.addRow("Original name", _selectable(origin.original_path.name))
            form.addRow("Moved on", _selectable(f"{origin.moved_at:%Y-%m-%d %H:%M}"))
            if len(origin.moves) > 1:
                form.addRow("Times moved", _selectable(str(len(origin.moves))))
        if origin.download:
            if origin.download.referrer_url:
                form.addRow("Downloaded from page", _link(origin.download.referrer_url))
            if origin.download.host_url:
                form.addRow("File address", _link(origin.download.host_url))
        if origin.created:
            form.addRow("Created", _selectable(f"{origin.created:%Y-%m-%d %H:%M}"))
        if origin.modified:
            form.addRow("Last changed", _selectable(f"{origin.modified:%Y-%m-%d %H:%M}"))
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.original_button = QPushButton("Open original folder")
        self.original_button.setEnabled(bool(origin.moves) and origin.original_path.parent.is_dir())
        self.original_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(origin.original_path.parent))))
        show = QPushButton("Show file")
        show.setEnabled(path.exists())
        show.clicked.connect(lambda: reveal(path))
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(self.original_button)
        buttons.addWidget(show)
        buttons.addStretch()
        buttons.addWidget(close)
        layout.addLayout(buttons)


class TransferDialog(QDialog):
    """Choose which parts of the settings to export, or to take from an imported file."""

    def __init__(self, title: str, intro: str, available: list[str], action: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        label = QLabel(intro)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.boxes: dict[str, QCheckBox] = {}
        for part in available:
            box = QCheckBox(transfer.PART_LABELS[part])
            box.setChecked(True)
            box.toggled.connect(self._update)
            self.boxes[part] = box
            layout.addWidget(box)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.ok = self.buttons.addButton(action, QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._update()

    def parts(self) -> list[str]:
        return [part for part, box in self.boxes.items() if box.isChecked()]

    def _update(self) -> None:
        self.ok.setEnabled(bool(self.parts()))


def export_settings(organizer: Organizer, parent: QWidget) -> Path | None:
    dialog = TransferDialog(
        "Export settings",
        "Save these settings to a file you can share or import on another PC. "
        "Nothing personal is included besides folder locations.",
        list(transfer.PARTS), "Export...", parent,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    start = str(Path.home() / "Documents" / "Desktop Organizer settings.json")
    path, _ = QFileDialog.getSaveFileName(parent, "Export settings", start, "Settings file (*.json)")
    if not path:
        return None
    try:
        saved = transfer.export_file(organizer.settings, Path(path), dialog.parts())
    except OSError as exc:
        QMessageBox.warning(parent, "Export settings", f"Couldn't save the file: {exc.strerror or exc}")
        return None
    QMessageBox.information(parent, "Export settings", f"Saved to\n{saved}")
    return saved


def import_settings(organizer: Organizer, parent: QWidget, path: Path | None = None) -> transfer.ImportSummary | None:
    if path is None:
        chosen, _ = QFileDialog.getOpenFileName(parent, "Import settings", str(Path.home()),
                                                "Settings file (*.json)")
        if not chosen:
            return None
        path = Path(chosen)
    try:
        data = transfer.read_file(path)
    except transfer.TransferError as exc:
        QMessageBox.warning(parent, "Import settings", str(exc))
        return None
    available = transfer.parts_in(data)
    if not available:
        QMessageBox.information(parent, "Import settings", "This file has no settings in it.")
        return None
    dialog = TransferDialog(
        "Import settings",
        f"Add settings from {path.name}. Your own rules and folders are kept; "
        "rules with the same name are replaced.",
        available, "Import", parent,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    summary = transfer.apply(organizer.settings, data, dialog.parts())
    organizer.settings.save()
    QMessageBox.information(parent, "Import settings", "\n".join(summary.lines()))
    return summary


def _selectable(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _link(url: str) -> QLabel:
    # Only web addresses become links; anything else recorded in a download is shown as text.
    if not url.lower().startswith(("http://", "https://")):
        return _selectable(url)
    label = QLabel(f'<a href="{_escape(url)}">{_escape(url)}</a>')
    label.setWordWrap(True)
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    return label


def _escape(text: str) -> str:
    return html.escape(text)
