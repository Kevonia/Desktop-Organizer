"""Main window: saved folders on the left, a live preview of every move on the right."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_organizer import APP_NAME, __version__
from desktop_organizer.core import Organizer, PlannedMove, drives, reports, shell
from desktop_organizer.core.auto import AutoOrganizer
from desktop_organizer.core.config import AutoMode, FolderProfile
from desktop_organizer.core.dates import file_date
from desktop_organizer.core.history import UndoResult
from desktop_organizer.core.logs import log, log_dir
from desktop_organizer.core.mover import RunResult
from desktop_organizer.core.paths import KNOWN_FOLDERS, known_folder, resolve_folder, same_path
from desktop_organizer.core.safety import DriveNotConnectedError, UnsafeFolderError, ensure_destination
from desktop_organizer.core.updates import RELEASES_PAGE, UpdateError, UpdateInfo, check_for_update
from desktop_organizer.ui import theme
from desktop_organizer.ui.dialogs import (
    CategoriesDialog,
    HistoryDialog,
    RenameDialog,
    SettingsDialog,
    StructureCombo,
    save_report,
    section_label,
)
from desktop_organizer.ui.insights import (
    OriginDialog,
    SetupsDialog,
    StatsDialog,
    export_settings,
    import_settings,
)
from desktop_organizer.ui.recover import FIND, RECYCLE, VERSIONS, RecoverDialog
from desktop_organizer.ui.tools import DuplicatesDialog, RulesDialog
from desktop_organizer.ui.worker import Task

MOVE_ROLE = Qt.ItemDataRole.UserRole
SORT_ROLE = Qt.ItemDataRole.UserRole + 1
COL_FILE, COL_TARGET, COL_SIZE, COL_DATE, COL_RULE = range(5)
AUTO_CHECK_MS = 30_000
UPDATE_CHECK_EVERY = timedelta(days=7)
VERSION_CHECK_MS = 60_000


class SortableItem(QTreeWidgetItem):
    """Sorts size and date columns by value, not by their display text."""

    def __lt__(self, other: QTreeWidgetItem) -> bool:
        column = self.treeWidget().sortColumn() if self.treeWidget() else 0
        mine, theirs = self.data(column, SORT_ROLE), other.data(column, SORT_ROLE)
        if mine is not None and theirs is not None:
            return mine < theirs
        return self.text(column).lower() < other.text(column).lower()


class MainWindow(QMainWindow):
    def __init__(self, organizer: Organizer):
        super().__init__()
        self.organizer = organizer
        self.settings = organizer.settings
        self.moves: list[PlannedMove] = []
        self.task: Task | None = None
        self.auto = AutoOrganizer(organizer)
        self.auto_task: Task | None = None
        self.auto_paused = False
        self._drive_states: dict[str, str] = {}
        self._quitting = False
        self._told_about_tray = False

        self.setWindowTitle(APP_NAME)
        self.resize(1120, 700)
        self.setMinimumSize(820, 520)

        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(lambda _: self.refresh_timer.start())
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(600)
        self.refresh_timer.timeout.connect(self._auto_refresh)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_main(), 1)
        self.setCentralWidget(central)
        self._build_menus()

        # Auto-organize: react to new files in "watch" folders, and check schedules regularly.
        self.auto_watcher = QFileSystemWatcher(self)
        self.auto_watcher.directoryChanged.connect(lambda _: self.auto_timer.start())
        self.auto_timer = QTimer(self)
        self.auto_timer.setSingleShot(True)
        self.auto_timer.setInterval(3000)
        self.auto_timer.timeout.connect(self.run_auto)
        self.schedule_timer = QTimer(self)
        self.schedule_timer.setInterval(AUTO_CHECK_MS)
        self.schedule_timer.timeout.connect(self.run_auto)
        self.schedule_timer.timeout.connect(self._check_drives)
        self.schedule_timer.start()
        QTimer.singleShot(5000, self.run_auto)

        self.update_task: Task | None = None
        QTimer.singleShot(10_000, self._auto_update_check)

        # File versions: save changed files in protected folders about once a minute.
        self.version_task: Task | None = None
        self.version_timer = QTimer(self)
        self.version_timer.setInterval(VERSION_CHECK_MS)
        self.version_timer.timeout.connect(self.save_versions)
        self.version_timer.start()
        QTimer.singleShot(15_000, self.save_versions)

        self.tray = self._build_tray()
        self._reload_folders(select=0)
        self._update_undo()

    # --- layout ------------------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sidebar.setFixedWidth(240)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 16, 12, 12)

        layout.addWidget(section_label("Folders"))
        self.folder_list = QListWidget()
        self.folder_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.folder_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.folder_list.currentRowChanged.connect(self._on_folder_selected)
        layout.addWidget(self.folder_list, 1)

        self.add_folder_button = QPushButton("+ Add folder")
        self.add_folder_menu = QMenu(self)
        self.add_folder_menu.aboutToShow.connect(self._fill_add_menu)
        self.add_folder_button.setMenu(self.add_folder_menu)
        layout.addWidget(self.add_folder_button)

        layout.addSpacing(8)
        for text, slot in (("Find && recover", lambda: self.show_recover(FIND)),
                           ("Rules", self.show_rules), ("Find duplicates", self.show_duplicates),
                           ("Storage stats", self.show_stats), ("History", self.show_history),
                           ("Categories", self.show_categories), ("Settings", self.show_settings)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            layout.addWidget(button)
        return sidebar

    def _build_main(self) -> QWidget:
        main = QWidget()
        layout = QVBoxLayout(main)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("Title")
        self.path_label = QLabel()
        self.path_label.setObjectName("Muted")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        titles.addWidget(self.title)
        titles.addWidget(self.path_label)
        header.addLayout(titles, 1)
        self.open_button = QPushButton("Open folder")
        self.open_button.clicked.connect(self.open_current_folder)
        self.remove_folder_button = QPushButton("Remove from list")
        self.remove_folder_button.clicked.connect(self.remove_current_folder)
        header.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(self.remove_folder_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        self.warning = QLabel()
        self.warning.setObjectName("Warning")
        self.warning.setWordWrap(True)
        self.warning.hide()
        layout.addWidget(self.warning)

        structure_row = QHBoxLayout()
        structure_row.addWidget(QLabel("Arrange files by"))
        self.structure_combo = StructureCombo(self.organizer, allow_default=True)
        self.structure_combo.patternChosen.connect(self._on_structure_chosen)
        structure_row.addWidget(self.structure_combo)
        structure_row.addSpacing(16)
        structure_row.addWidget(QLabel("Auto-organize"))
        self.auto_combo = QComboBox()
        for mode in AutoMode:
            self.auto_combo.addItem(mode.label, mode.value)
        self.auto_combo.activated.connect(self._on_auto_chosen)
        structure_row.addWidget(self.auto_combo)
        structure_row.addStretch()
        layout.addLayout(structure_row)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Put files in"))
        self.destination_button = QPushButton()
        self.destination_button.setToolTip("Organize into this folder, or into another one, "
                                           "e.g. on a USB drive or network folder")
        self.destination_menu = QMenu(self)
        self.destination_menu.aboutToShow.connect(self._fill_destination_menu)
        self.destination_button.setMenu(self.destination_menu)
        target_row.addWidget(self.destination_button)
        target_row.addSpacing(16)
        target_row.addWidget(QLabel("File names"))
        self.rename_button = QPushButton()
        self.rename_button.setToolTip("Rename files as they're organized, e.g. put the date first")
        self.rename_button.clicked.connect(self.choose_rename)
        target_row.addWidget(self.rename_button)
        target_row.addStretch()
        layout.addLayout(target_row)

        filter_row = QHBoxLayout()
        self.select_all = QCheckBox("Select all")
        self.select_all.setTristate(False)
        self.select_all.clicked.connect(self._on_select_all)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter files...")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.select_all)
        filter_row.addWidget(self.filter_edit, 1)
        layout.addLayout(filter_row)

        self.stack = QStackedWidget()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "Moves to", "Size", "Date used", "Rule"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(COL_FILE, Qt.SortOrder.AscendingOrder)
        self.tree.itemChanged.connect(self._on_item_changed)
        header_view = self.tree.header()
        header_view.setStretchLastSection(False)
        header_view.resizeSection(COL_FILE, 300)
        header_view.setSectionResizeMode(COL_TARGET, QHeaderView.ResizeMode.Stretch)
        header_view.resizeSection(COL_SIZE, 90)
        header_view.resizeSection(COL_DATE, 110)
        header_view.resizeSection(COL_RULE, 120)
        self.empty = QLabel()
        self.empty.setObjectName("EmptyState")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.tree)
        self.stack.addWidget(self.empty)
        layout.addWidget(self.stack, 1)

        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)

        footer = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("Muted")
        footer.addWidget(self.status, 1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_all)
        self.undo_button = QPushButton("Undo last run")
        self.undo_button.clicked.connect(self.undo_last)
        self.organize_button = QPushButton("Organize")
        self.organize_button.setObjectName("Primary")
        self.organize_button.clicked.connect(self.organize)
        for button in (self.refresh_button, self.undo_button, self.organize_button):
            footer.addWidget(button)
        layout.addLayout(footer)
        return main

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self._action(file_menu, "Choose folder...", self.add_folder_from_dialog, QKeySequence.StandardKey.Open)
        file_menu.addSeparator()
        self._action(file_menu, "Export settings...", lambda: export_settings(self.organizer, self))
        self._action(file_menu, "Import settings...", self.import_settings)
        file_menu.addSeparator()
        self._action(file_menu, "Quit", self.quit_app, QKeySequence("Ctrl+Q"))

        actions = self.menuBar().addMenu("&Actions")
        self._action(actions, "Refresh preview", self.refresh_preview, QKeySequence.StandardKey.Refresh)
        self._action(actions, "Organize", self.organize, QKeySequence("Ctrl+Return"))
        self._action(actions, "Undo last run", self.undo_last, QKeySequence.StandardKey.Undo)
        actions.addSeparator()
        self._action(actions, "Export preview...", self.export_preview, QKeySequence("Ctrl+E"))

        tools = self.menuBar().addMenu("&Tools")
        self._action(tools, "Find a file", lambda: self.show_recover(FIND), QKeySequence("Ctrl+F"))
        self._action(tools, "File versions", lambda: self.show_recover(VERSIONS), QKeySequence("Ctrl+Shift+V"))
        self._action(tools, "Recover from Recycle Bin", lambda: self.show_recover(RECYCLE))
        tools.addSeparator()
        self._action(tools, "Rules", self.show_rules, QKeySequence("Ctrl+R"))
        self._action(tools, "Find duplicates", self.show_duplicates, QKeySequence("Ctrl+D"))
        self._action(tools, "Storage stats", self.show_stats, QKeySequence("Ctrl+I"))
        self._action(tools, "History", self.show_history, QKeySequence("Ctrl+H"))
        self._action(tools, "Categories", self.show_categories)
        self._action(tools, "Ready-made setups...", self.show_setups)
        self._action(tools, "Settings", self.show_settings, QKeySequence.StandardKey.Preferences)

        help_menu = self.menuBar().addMenu("&Help")
        self._action(help_menu, "Check for updates...", lambda: self.check_updates(quiet=False))
        self._action(help_menu, "Open log folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir()))))
        help_menu.addSeparator()
        self._action(help_menu, f"About {APP_NAME}", self.show_about)

    def _action(self, menu: QMenu, text: str, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    # --- folders -----------------------------------------------------------------

    @property
    def current_profile(self) -> FolderProfile | None:
        row = self.folder_list.currentRow()
        return self.settings.folders[row] if 0 <= row < len(self.settings.folders) else None

    def _reload_folders(self, select: int | None = None) -> None:
        current = self.folder_list.currentRow() if select is None else select
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self.folder_list.blockSignals(True)
        self.folder_list.clear()
        self._drive_states = {}
        for profile in self.settings.folders:
            auto = profile.auto is not AutoMode.OFF
            state = self._folder_state(profile)
            self._drive_states[profile.path] = state
            text = profile.name + ("  (auto)" if auto else "")
            if state != "ok":
                text += "  (not connected)" if state == "offline" else "  (missing)"
            item = QListWidgetItem(icon, text)
            item.setToolTip(str(profile.location) + (f"\nAuto-organize: {profile.auto.label}" if auto else ""))
            self.folder_list.addItem(item)
        self.folder_list.blockSignals(False)
        self._update_auto_watcher()
        if self.settings.folders:
            self.folder_list.setCurrentRow(min(max(current, 0), len(self.settings.folders) - 1))
        self._on_folder_selected(self.folder_list.currentRow())

    @staticmethod
    def _folder_state(profile: FolderProfile) -> str:
        """'ok', 'offline' (its USB or network drive isn't there) or 'missing'."""
        folder = profile.location
        if not drives.is_connected(folder):
            return "offline"
        if profile.destination and not drives.is_connected(profile.target):
            return "offline"
        return "ok" if folder.is_dir() else "missing"

    def _check_drives(self) -> None:
        """Notice USB and network drives being plugged in or removed."""
        states = {p.path: self._folder_state(p) for p in self.settings.folders}
        if states != self._drive_states:
            self._reload_folders()

    def _fill_add_menu(self) -> None:
        self.add_folder_menu.clear()
        saved = {str(f.location).lower() for f in self.settings.folders}
        for key, (_, label) in KNOWN_FOLDERS.items():
            path = known_folder(key)
            action = self.add_folder_menu.addAction(label, lambda k=key: self.add_folder(k))
            action.setEnabled(path.is_dir() and str(path).lower() not in saved)
        self.add_folder_menu.addSeparator()
        self.add_folder_menu.addAction("Choose another folder...", self.add_folder_from_dialog)

    def add_folder_from_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose a folder to organize", str(Path.home()))
        if path:
            self.add_folder(path)

    def add_folder(self, spec: str) -> bool:
        folder = resolve_folder(spec)
        try:
            warnings = self.organizer.check(folder)
        except UnsafeFolderError as exc:
            QMessageBox.critical(self, "Can't organize this folder", str(exc))
            return False
        if warnings and not self.confirm("Add this folder?", "\n\n".join(warnings) + "\n\nAdd it anyway?"):
            return False
        profile = self.settings.add_folder(spec)
        self.settings.save()
        self._reload_folders(select=self.settings.folders.index(profile))
        return True

    def remove_current_folder(self) -> None:
        profile = self.current_profile
        if profile is None:
            return
        if not self.confirm("Remove folder", f"Stop organizing {profile.name}? No files are moved or deleted."):
            return
        self.settings.folders.remove(profile)
        self.settings.save()
        self._reload_folders()

    def open_current_folder(self) -> None:
        if self.current_profile:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_profile.location)))

    def _on_folder_selected(self, row: int) -> None:
        profile = self.current_profile
        for path in self.watcher.directories():
            self.watcher.removePath(path)
        has_folder = profile is not None
        for widget in (self.structure_combo, self.auto_combo, self.open_button, self.remove_folder_button,
                       self.refresh_button, self.destination_button, self.rename_button):
            widget.setEnabled(has_folder)
        self._update_target_buttons()
        if not has_folder:
            self.title.setText("No folder selected")
            self.path_label.setText("Add a folder on the left to get started.")
            self.warning.hide()
            self._show_moves([])
            return

        folder = profile.location
        self.title.setText(profile.name)
        self.path_label.setText(str(folder) if not profile.destination
                                else f"{folder}   \u2192   files go to {profile.target}")
        self.structure_combo.set_pattern(profile.pattern, folder)
        self.auto_combo.setCurrentIndex(self.auto_combo.findData(profile.auto.value))
        if folder.is_dir():
            self.watcher.addPath(str(folder))
        self.refresh_preview()

    def _update_target_buttons(self) -> None:
        profile = self.current_profile
        if profile is None:
            self.destination_button.setText("This folder")
            self.rename_button.setText("Keep names")
            return
        self.destination_button.setText(
            f"Another folder: {profile.target.name or profile.target}" if profile.destination else "This folder")
        self.rename_button.setText(f"Rename: {profile.rename}" if profile.rename else "Keep names")

    def _fill_destination_menu(self) -> None:
        self.destination_menu.clear()
        profile = self.current_profile
        if profile is None:
            return
        here = self.destination_menu.addAction("This folder (in subfolders)", lambda: self.set_destination(None))
        here.setCheckable(True)
        here.setChecked(not profile.destination)
        if profile.destination:
            current = self.destination_menu.addAction(str(profile.target))
            current.setCheckable(True)
            current.setChecked(True)
            current.setEnabled(False)
        self.destination_menu.addSeparator()
        self.destination_menu.addAction("Choose another folder...", self.choose_destination)

    def choose_destination(self) -> None:
        profile = self.current_profile
        if profile is None:
            return
        start = str(profile.target if profile.destination else profile.location)
        path = QFileDialog.getExistingDirectory(self, "Where should organized files go?", start)
        if path:
            self.set_destination(path)

    def set_destination(self, spec: str | None) -> bool:
        """Send this folder's files somewhere else (None: back into the folder itself)."""
        profile = self.current_profile
        if profile is None:
            return False
        if spec is not None:
            target = resolve_folder(spec)
            if same_path(target, profile.location):
                spec = None
            else:
                try:
                    ensure_destination(target)
                except UnsafeFolderError as exc:
                    QMessageBox.critical(self, "Can't put files there", str(exc))
                    return False
                spec = str(target)
        profile.destination = spec
        self.settings.save()
        self._reload_folders()
        return True

    def choose_rename(self) -> None:
        profile = self.current_profile
        if profile is None:
            return
        dialog = RenameDialog(self.organizer, profile.location, profile.rename, self)
        if dialog.exec():
            self.set_rename(dialog.template())

    def set_rename(self, template: str | None) -> None:
        profile = self.current_profile
        if profile is None:
            return
        profile.rename = template
        self.settings.save()
        self._update_target_buttons()
        self.refresh_preview()

    def _on_structure_chosen(self, pattern: str | None) -> None:
        profile = self.current_profile
        if profile is None:
            return
        profile.pattern = pattern
        self.settings.save()
        self.refresh_preview()

    # --- preview -----------------------------------------------------------------

    def refresh_all(self) -> None:
        """Refresh button: look again for drives that were plugged in, then rebuild the preview."""
        drives.forget()
        self._check_drives()
        self.refresh_preview()

    def refresh_preview(self) -> None:
        profile = self.current_profile
        if profile is None or self._busy():
            return
        folder = profile.location
        self.warning.hide()
        try:
            warnings = self.organizer.check(folder)
        except DriveNotConnectedError as exc:
            self._set_warning(str(exc))
            self._show_moves([], empty_text="Waiting for the drive to be connected.")
            return
        except UnsafeFolderError as exc:
            self._set_warning(str(exc))
            self._show_moves([], empty_text="This folder can't be organized.")
            return
        if warnings:
            self._set_warning(" ".join(warnings))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        empty_text = None
        try:
            moves = self.organizer.preview(folder)
        except DriveNotConnectedError as exc:
            moves = []
            self._set_warning(f"Files from here go to {profile.target}. {exc}")
            empty_text = "Waiting for the destination drive to be connected."
        except UnsafeFolderError as exc:
            moves = []
            self._set_warning(str(exc))
            empty_text = "Choose another place to put the files."
        except OSError as exc:
            moves = []
            self._set_warning(f"Couldn't read this folder: {exc.strerror or exc}")
        finally:
            QApplication.restoreOverrideCursor()
        self._show_moves(moves, empty_text=empty_text)

    def _auto_refresh(self) -> None:
        if not self._busy() and self.isVisible():
            self.refresh_preview()

    def _show_moves(self, moves: list[PlannedMove], empty_text: str | None = None) -> None:
        self.moves = moves
        self.tree.blockSignals(True)
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        for index, move in enumerate(moves):
            item = SortableItem()
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(COL_FILE, Qt.CheckState.Checked)
            item.setData(COL_FILE, MOVE_ROLE, index)
            item.setText(COL_FILE, move.source.name)
            item.setToolTip(COL_FILE, str(move.source))
            item.setText(COL_TARGET, _target_text(move))
            item.setToolTip(COL_TARGET, str(move.target_dir / move.target_name))
            item.setText(COL_RULE, move.rule or "")
            try:
                st = move.source.stat()
                item.setText(COL_SIZE, _format_size(st.st_size))
                item.setData(COL_SIZE, SORT_ROLE, st.st_size)
                when = file_date(move.source, st)
                item.setText(COL_DATE, when.strftime("%Y-%m-%d"))
                item.setData(COL_DATE, SORT_ROLE, when.timestamp())
            except OSError:
                item.setData(COL_SIZE, SORT_ROLE, 0)
                item.setData(COL_DATE, SORT_ROLE, 0.0)
            item.setTextAlignment(COL_SIZE, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tree.addTopLevelItem(item)
        self.tree.setSortingEnabled(True)
        self.tree.blockSignals(False)

        if moves:
            self.stack.setCurrentWidget(self.tree)
        else:
            self.empty.setText(empty_text or "Nothing to organize here. This folder is already tidy.")
            self.stack.setCurrentWidget(self.empty)
        self._apply_filter()
        self._update_counts()

    def _items(self) -> list[QTreeWidgetItem]:
        return [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]

    def checked_moves(self) -> list[PlannedMove]:
        return [
            self.moves[item.data(COL_FILE, MOVE_ROLE)]
            for item in self._items()
            if item.checkState(COL_FILE) == Qt.CheckState.Checked
        ]

    def _apply_filter(self) -> None:
        needle = self.filter_edit.text().strip().lower()
        for item in self._items():
            text = f"{item.text(COL_FILE)} {item.text(COL_TARGET)}".lower()
            item.setHidden(bool(needle) and needle not in text)

    def _on_select_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.tree.blockSignals(True)
        for item in self._items():
            if not item.isHidden():
                item.setCheckState(COL_FILE, state)
        self.tree.blockSignals(False)
        self._update_counts()

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column == COL_FILE:
            self._update_counts()

    def _update_counts(self) -> None:
        total = len(self.moves)
        chosen = len(self.checked_moves())
        self.select_all.blockSignals(True)
        self.select_all.setChecked(total > 0 and chosen == total)
        self.select_all.setEnabled(total > 0)
        self.select_all.blockSignals(False)
        self.organize_button.setText(f"Organize {chosen} file{'s' if chosen != 1 else ''}" if chosen else "Organize")
        self.organize_button.setEnabled(chosen > 0 and not self._busy())
        if total:
            self.status.setText(f"{chosen} of {total} files selected")
        else:
            self.status.setText("")

    def _set_warning(self, text: str) -> None:
        self.warning.setText(text)
        self.warning.show()

    # --- organize & undo ---------------------------------------------------------

    def organize(self) -> None:
        profile = self.current_profile
        moves = self.checked_moves()
        if profile is None or not moves:
            return
        if self._busy():
            self.statusBar().showMessage("Auto-organize is running. Try again in a moment.", 4000)
            return
        folder = profile.location
        try:
            warnings = self.organizer.check(folder)
            self.organizer.check_destination(folder)
        except UnsafeFolderError as exc:
            QMessageBox.critical(self, "Can't organize this folder", str(exc))
            return
        if warnings and not self.confirm("Are you sure?", "\n\n".join(warnings) + "\n\nOrganize it anyway?"):
            return
        if not self.confirm(
            "Organize",
            f"Move {len(moves)} file{'s' if len(moves) != 1 else ''} in {profile.name}?\n\n"
            "You can undo this afterwards.",
        ):
            return
        self._start_task(lambda progress: self.organizer.organize(
            folder, moves, progress=lambda i, total, move: progress(i, total, move.source.name)
        ), on_done=self._organize_done, label="Organizing")

    def _organize_done(self, result: RunResult) -> None:
        self.refresh_preview()
        self._update_undo()
        self.statusBar().showMessage(f"Organized {len(result.moved)} files.", 8000)
        self.show_run_result(result)

    def undo_last(self) -> None:
        if self._busy():
            return
        run = self.organizer.history.last_undoable_run()
        if run is None:
            return
        when = run.started_at.strftime("%Y-%m-%d %H:%M")
        if not self.confirm("Undo", f"Put {run.move_count} files back where they were?\n\n{run.folder}\n{when}"):
            return
        self._start_task(lambda progress: self.organizer.undo(run.id), on_done=self._undo_done, label="Undoing")

    def _undo_done(self, result: UndoResult) -> None:
        self.refresh_preview()
        self._update_undo()
        self.statusBar().showMessage(f"Restored {len(result.restored)} files.", 8000)
        if result.failed:
            QMessageBox.warning(
                self, "Some files weren't restored",
                "\n".join(f"{p.name}: {reason}" for p, reason in result.failed[:15]),
            )

    def _update_undo(self) -> None:
        run = self.organizer.history.last_undoable_run()
        self.undo_button.setEnabled(run is not None and not self._busy())
        self.undo_button.setToolTip(
            f"Undo the run from {run.started_at:%Y-%m-%d %H:%M} in {run.folder}" if run else "Nothing to undo"
        )

    def _start_task(self, fn, on_done, label: str) -> None:
        self.task = Task(fn, self)
        outcome: dict = {}
        self.task.progressed.connect(lambda done, total, name: self._on_progress(label, done, total, name))
        self.task.succeeded.connect(lambda result: outcome.update(result=result))
        self.task.failed.connect(lambda message: outcome.update(error=message))
        # Handle the outcome only once the thread is done, so the window is no longer "busy".
        self.task.finished.connect(lambda: self._task_finished(outcome, on_done))
        self.progress.setRange(0, 0)
        self.progress.setFormat(f"{label}...")
        self.progress.show()
        self._set_controls_enabled(False)
        self.task.start()

    def _on_progress(self, label: str, done: int, total: int, name: str) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.progress.setFormat(f"{label} {done}/{total}: {name}")

    def _task_finished(self, outcome: dict, on_done) -> None:
        self.task = None
        self.progress.hide()
        self._set_controls_enabled(True)
        self._update_counts()
        self._update_undo()
        if "error" in outcome:
            QMessageBox.critical(self, "Something went wrong", outcome["error"])
        elif "result" in outcome:
            on_done(outcome["result"])

    def _busy(self) -> bool:
        return self.task is not None or self.auto_task is not None

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (self.folder_list, self.add_folder_button, self.remove_folder_button,
                       self.structure_combo, self.refresh_button, self.undo_button,
                       self.organize_button, self.tree, self.select_all,
                       self.destination_button, self.rename_button):
            widget.setEnabled(enabled)

    # --- dialogs (overridable in tests) -------------------------------------------

    def confirm(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(self, title, text)
        return answer == QMessageBox.StandardButton.Yes

    def show_run_result(self, result: RunResult) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Done")
        box.setIcon(QMessageBox.Icon.Warning if result.failed else QMessageBox.Icon.Information)
        box.setText(f"Organized {len(result.moved)} file{'s' if len(result.moved) != 1 else ''}.")
        if result.failed:
            box.setInformativeText(f"{len(result.failed)} couldn't be moved (they may be open in another app).")
            box.setDetailedText("\n".join(f"{p.name}: {reason}" for p, reason in result.failed))
        undo = box.addButton("Undo", QMessageBox.ButtonRole.ActionRole) if result.moved else None
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if undo is not None and box.clickedButton() is undo:
            self._start_task(lambda progress: self.organizer.undo(result.run_id),
                             on_done=self._undo_done, label="Undoing")

    def show_recover(self, tab: int) -> None:
        RecoverDialog(self.organizer, tab, self).exec()
        self.refresh_preview()

    def save_versions(self) -> None:
        """Background check of protected folders; does nothing until a folder is protected."""
        folders = self.organizer.version_folders()
        if not folders or self.version_task is not None:
            return
        self.version_task = Task(lambda progress: self.organizer.versions.scan(folders), self)
        self.version_task.failed.connect(lambda message: log.warning("Saving versions failed: %s", message))
        self.version_task.finished.connect(self._versions_saved)
        self.version_task.start()

    def _versions_saved(self) -> None:
        self.version_task = None

    def show_rules(self) -> None:
        folder = self.current_profile.location if self.current_profile else None
        if RulesDialog(self.organizer, folder, self).exec():
            self.refresh_preview()

    def show_duplicates(self) -> None:
        folder = self.current_profile.location if self.current_profile else None
        DuplicatesDialog(self.organizer, folder, self).exec()
        self.refresh_preview()

    def show_stats(self) -> None:
        folder = self.current_profile.location if self.current_profile else None
        StatsDialog(self.organizer, folder if folder and folder.is_dir() else None, self).exec()

    def show_setups(self, welcome: bool = False) -> None:
        if SetupsDialog(self.organizer, welcome=welcome, parent=self).exec():
            self._reload_folders()

    def show_welcome(self) -> None:
        """First launch: offer the ready-made setups once."""
        self.settings.welcome_shown = True
        self.settings.save()
        self.show_setups(welcome=True)

    def import_settings(self) -> None:
        if import_settings(self.organizer, self) is not None:
            self._reload_folders()

    def export_preview(self) -> None:
        profile = self.current_profile
        moves = self.checked_moves()
        if profile is None or not moves:
            QMessageBox.information(self, "Export preview", "There's nothing in the preview to export.")
            return
        report = reports.preview_report(profile.location, self.organizer.pattern_for(profile.location), moves)
        save_report(self, report, f"{profile.name} preview {datetime.now():%Y-%m-%d}")

    def show_origin(self, path: Path) -> None:
        OriginDialog(self.organizer, path, self).exec()

    def handle_message(self, message: str) -> None:
        """A request from another launch, e.g. the File Explorer menu: 'organize<TAB>path'."""
        command, _, value = message.partition("\t")
        self.show_window()
        if not value:
            return
        path = Path(value)
        if command == shell.ORGANIZE_FLAG.lstrip("-"):
            self.open_folder(path)
        elif command == shell.WHERE_FLAG.lstrip("-"):
            self.show_origin(path)

    def open_folder(self, path: Path) -> bool:
        """Show the preview for ``path``, adding it to the list first if needed. Nothing moves yet."""
        existing = self.settings.find_folder(path)
        if existing is not None:
            self.folder_list.setCurrentRow(self.settings.folders.index(existing))
            return True
        return self.add_folder(str(path))

    def show_history(self) -> None:
        dialog = HistoryDialog(self.organizer, self)
        dialog.changed.connect(self.refresh_preview)
        dialog.changed.connect(self._update_undo)
        dialog.exec()

    def show_categories(self) -> None:
        if CategoriesDialog(self.organizer, self).exec():
            self.refresh_preview()

    def show_settings(self) -> None:
        if SettingsDialog(self.organizer, self).exec():
            theme.apply_theme(QApplication.instance(), self.settings.theme)
            self._reload_folders()

    def show_about(self) -> None:
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> {__version__}<br>Keeps your folders tidy. Every run can be undone."
            "<p>Built with <a href='https://www.qt.io/qt-for-python'>Qt for Python (PySide6)</a>, "
            "used under the <a href='https://www.gnu.org/licenses/lgpl-3.0.html'>GNU LGPL v3</a>; "
            "its source is available from <a href='https://code.qt.io/'>code.qt.io</a>. "
            "Includes the <a href='https://www.python.org/'>Python</a> runtime under the "
            "<a href='https://docs.python.org/3/license.html'>PSF License</a>.</p>",
        )

    # --- updates -----------------------------------------------------------------

    def _auto_update_check(self) -> None:
        """Weekly background check, only if the user turned it on in Settings."""
        if not self.settings.check_updates:
            return
        try:
            last = datetime.fromisoformat(self.settings.last_update_check)
        except ValueError:
            last = None
        if last is None or datetime.now() - last >= UPDATE_CHECK_EVERY:
            self.check_updates(quiet=True)

    def check_updates(self, quiet: bool) -> None:
        if self.update_task is not None:
            return
        self.update_task = Task(lambda progress: check_for_update(), self)
        outcome: dict = {}
        self.update_task.succeeded.connect(lambda info: outcome.update(info=info))
        self.update_task.failed.connect(lambda message: outcome.update(error=message))
        self.update_task.finished.connect(lambda: self._update_checked(outcome, quiet))
        if not quiet:
            self.statusBar().showMessage("Checking for updates...")
        self.update_task.start()

    def _update_checked(self, outcome: dict, quiet: bool) -> None:
        self.update_task = None
        self.statusBar().clearMessage()
        self.settings.last_update_check = datetime.now().isoformat(timespec="seconds")
        self.settings.save()
        if "error" in outcome:
            log.warning("Update check failed: %s", outcome["error"])
            if not quiet:
                QMessageBox.warning(self, "Check for updates", outcome["error"])
            return
        info: UpdateInfo | None = outcome.get("info")
        if info is None:
            log.info("Update check: up to date")
            if not quiet:
                QMessageBox.information(self, "Check for updates", f"You have the latest version ({__version__}).")
            return
        log.info("Update check: %s is available", info.version)
        self.show_update(info)

    def show_update(self, info: UpdateInfo) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Update available")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(f"{APP_NAME} {info.version} is available. You have {__version__}.")
        box.setInformativeText("Download the installer and run it; your folders, rules and history are kept.")
        if info.notes:
            box.setDetailedText(info.notes)
        download = box.addButton("Download", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is download:
            QDesktopServices.openUrl(QUrl(info.download_url or info.page_url or RELEASES_PAGE))

    def closeEvent(self, event) -> None:
        if not self._quitting and self.tray is not None and self.settings.minimize_to_tray:
            # Keep running in the tray so auto-organize keeps working.
            event.ignore()
            self.hide()
            if not self._told_about_tray and self.settings.notifications:
                self._told_about_tray = True
                self.tray.showMessage(APP_NAME, "Still running in the tray. Right-click the icon to quit.",
                                      QSystemTrayIcon.MessageIcon.Information, 4000)
            return
        if self._busy():
            QMessageBox.information(self, APP_NAME, "Please wait until the current run finishes.")
            event.ignore()
            self._quitting = False
            return
        if self.version_task is not None:
            self.version_task.wait(10_000)
        if self.tray is not None:
            self.tray.hide()
        super().closeEvent(event)
        QApplication.quit()

    # --- tray & auto-organize ------------------------------------------------------

    def _build_tray(self) -> QSystemTrayIcon | None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        icon = QApplication.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        tray = QSystemTrayIcon(icon, self)
        tray.setToolTip(APP_NAME)
        menu = QMenu(self)
        menu.addAction(f"Open {APP_NAME}", self.show_window)
        menu.addAction("Run auto-organize now", lambda: self.run_auto(force=True))
        self.pause_action = menu.addAction("Pause auto-organize")
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self._set_paused)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_app)
        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: self.show_window() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        tray.messageClicked.connect(self.show_window)
        tray.show()
        return tray

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.refresh_preview()

    def quit_app(self) -> None:
        self._quitting = True
        self.close()

    def _set_paused(self, paused: bool) -> None:
        self.auto_paused = paused
        self.statusBar().showMessage("Auto-organize paused." if paused else "Auto-organize resumed.", 4000)

    def _on_auto_chosen(self, index: int) -> None:
        profile = self.current_profile
        data = self.auto_combo.itemData(index)
        if profile is None or data is None:
            return
        mode = AutoMode(data)
        if mode is not AutoMode.OFF and not self._allow_auto(profile):
            self.auto_combo.setCurrentIndex(self.auto_combo.findData(profile.auto.value))
            return
        profile.auto = mode
        self.settings.save()
        self._reload_folders()
        if mode is not AutoMode.OFF:
            self.statusBar().showMessage(
                f"{profile.name} will be organized {mode.label.lower()}. Files are moved once they "
                "finish downloading or saving.", 8000)
            self.run_auto()

    def _allow_auto(self, profile: FolderProfile) -> bool:
        try:
            warnings = self.organizer.check(profile.location)
        except UnsafeFolderError as exc:
            QMessageBox.critical(self, "Can't organize this folder", str(exc))
            return False
        return not warnings or self.confirm(
            "Auto-organize this folder?", "\n\n".join(warnings) + "\n\nTurn on auto-organize anyway?"
        )

    def _update_auto_watcher(self) -> None:
        if self.auto_watcher.directories():
            self.auto_watcher.removePaths(self.auto_watcher.directories())
        for profile in self.settings.folders:
            if profile.auto is AutoMode.WATCH and profile.location.is_dir():
                self.auto_watcher.addPath(str(profile.location))

    def run_auto(self, force: bool = False) -> None:
        if self._busy() or (self.auto_paused and not force) or not self.auto.auto_folders():
            return
        self.auto_task = Task(lambda progress: self.auto.run_due(), self)
        outcome: dict = {}
        self.auto_task.succeeded.connect(lambda results: outcome.update(results=results))
        self.auto_task.failed.connect(lambda message: outcome.update(error=message))
        self.auto_task.finished.connect(lambda: self._auto_finished(outcome))
        self.auto_task.start()

    def _auto_finished(self, outcome: dict) -> None:
        self.auto_task = None
        results = outcome.get("results") or []
        if not results:
            return
        moved = sum(len(r.moved) for _, r in results)
        where = ", ".join(p.name for p, _ in results)
        message = f"Moved {moved} file{'s' if moved != 1 else ''} in {where}."
        self.statusBar().showMessage(message, 8000)
        if self.tray is not None and self.settings.notifications:
            self.tray.showMessage(f"{APP_NAME}: auto-organized", message + " Open the app to undo.",
                                  QSystemTrayIcon.MessageIcon.Information, 5000)
        self.refresh_preview()
        self._update_undo()


def _target_text(move: PlannedMove) -> str:
    """'2025/03-March/' or, when renamed, '2025/03-March/2025-03-14 photo.jpg'."""
    text = move.relative_target.as_posix() + "/"
    if not same_path(move.root, move.source.parent):
        text = f"{move.root.name or move.root}/{text}"
    if move.new_name:
        text += move.new_name
    return text


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"
