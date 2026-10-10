"""Secondary windows: structure builder, categories, history and settings."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from desktop_organizer.core import Organizer, SortMode, reports, rules, shell, startup
from desktop_organizer.core.categories import CATEGORIES
from desktop_organizer.core.config import describe_pattern
from desktop_organizer.core.safety import UnsafeFolderError
from desktop_organizer.core.structure import (
    NAME_TOKENS,
    TOKENS,
    PatternError,
    example,
    render_name,
    validate,
    validate_name,
)

BUILD_OWN = "__build_own__"


class StructureDialog(QDialog):
    """Lets users type their own folder structure, with clickable placeholders and a live preview."""

    def __init__(self, organizer: Organizer, folder: Path | None, initial: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Build your own folder structure")
        self.setMinimumWidth(620)
        self.organizer = organizer
        self.folder = folder

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Type the folders you want, using <b>/</b> between levels. Click a placeholder to insert it. "
            "Plain text is kept as-is, e.g. <code>Work/{category}/{year}</code>."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.edit = QLineEdit(initial)
        self.edit.setPlaceholderText("{category}/{year}")
        layout.addWidget(self.edit)

        grid = QGridLayout()
        tokens = [("/", "Start a new folder level")] + [(f"{{{t}}}", f"{d} - e.g. {s}") for t, (d, s) in TOKENS.items()]
        for i, (text, tip) in enumerate(tokens):
            button = QPushButton(text)
            button.setObjectName("Token")
            button.setToolTip(tip)
            button.clicked.connect(lambda _=False, t=text: self._insert(t))
            grid.addWidget(button, i // 4, i % 4)
        layout.addLayout(grid)

        self.error = QLabel()
        self.error.setObjectName("Error")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        layout.addWidget(QLabel("Preview"))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(150)
        layout.addWidget(self.preview)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.edit.textChanged.connect(self._update)
        self._update()

    def pattern(self) -> str:
        return validate(self.edit.text())

    def _insert(self, text: str) -> None:
        self.edit.insert(text)
        self.edit.setFocus()

    def _update(self) -> None:
        ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        try:
            pattern = self.pattern()
        except PatternError as exc:
            self.error.setText(str(exc))
            self.preview.setPlainText("")
            ok_button.setEnabled(False)
            return
        self.error.setText("")
        ok_button.setEnabled(True)
        settings = self.organizer.settings
        lines = []
        if self.folder is not None and self.folder.is_dir():
            try:
                moves = rules.plan(self.folder, settings, pattern)
            except (OSError, UnsafeFolderError):
                moves = []
            for move in moves[:8]:
                lines.append(f"{move.source.name}  ->  {move.relative_target.as_posix()}/")
        if not lines:
            lines.append(example(pattern, settings.custom_categories))
        self.preview.setPlainText("\n".join(lines))


RENAME_PRESETS = (
    ("Date first", "{date} {name}"),
    ("Date taken first (photos)", "{photo_date} {name}"),
    ("Artist - name (music)", "{artist} - {name}"),
    ("Category and date", "{category} {date} {name}"),
)
RENAME_TOKENS = ("name", "date", "photo_date", "year", "month_num", "day", "category", "camera", "artist",
                 "album", "source")


class RenameDialog(QDialog):
    """Choose how files are renamed as they're organized, with a live before/after preview."""

    def __init__(self, organizer: Organizer, folder: Path | None, initial: str | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rename files")
        self.setMinimumWidth(640)
        self.organizer = organizer
        self.folder = folder

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Give files tidy names as they're organized. The extension is always kept, and "
            "<code>{name}</code> is the original name. Renames are undone with the rest of the run."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.enabled = QCheckBox("Rename files in this folder")
        self.enabled.setChecked(bool(initial))
        layout.addWidget(self.enabled)

        self.edit = QLineEdit(initial or RENAME_PRESETS[0][1])
        self.edit.setPlaceholderText("{date} {name}")
        layout.addWidget(self.edit)

        presets = QHBoxLayout()
        presets.addWidget(QLabel("Quick picks:"))
        for label, template in RENAME_PRESETS:
            button = QPushButton(label)
            button.setToolTip(template)
            button.clicked.connect(lambda _=False, t=template: self._use(t))
            presets.addWidget(button)
        presets.addStretch()
        layout.addLayout(presets)

        grid = QGridLayout()
        all_tokens = {**TOKENS, **NAME_TOKENS}
        for i, token in enumerate(RENAME_TOKENS):
            description, sample = all_tokens[token]
            button = QPushButton(f"{{{token}}}")
            button.setObjectName("Token")
            button.setToolTip(f"{description} - e.g. {sample}")
            button.clicked.connect(lambda _=False, t=token: self._insert(f"{{{t}}}"))
            grid.addWidget(button, i // 4, i % 4)
        layout.addLayout(grid)

        self.error = QLabel()
        self.error.setObjectName("Error")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        layout.addWidget(QLabel("Preview"))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(150)
        layout.addWidget(self.preview)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.enabled.toggled.connect(self._update)
        self.edit.textChanged.connect(self._update)
        self._update()

    def template(self) -> str | None:
        """The chosen template, or None to keep the original names."""
        return validate_name(self.edit.text()) if self.enabled.isChecked() else None

    def _use(self, template: str) -> None:
        self.enabled.setChecked(True)
        self.edit.setText(template)

    def _insert(self, text: str) -> None:
        self.enabled.setChecked(True)
        self.edit.insert(text)
        self.edit.setFocus()

    def _update(self) -> None:
        on = self.enabled.isChecked()
        self.edit.setEnabled(on)
        ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if not on:
            self.error.setText("")
            self.preview.setPlainText("Files keep their names.")
            ok_button.setEnabled(True)
            return
        try:
            template = self.template()
        except PatternError as exc:
            self.error.setText(str(exc))
            self.preview.setPlainText("")
            ok_button.setEnabled(False)
            return
        self.error.setText("")
        ok_button.setEnabled(True)
        settings = self.organizer.settings
        lines = []
        if self.folder is not None and self.folder.is_dir():
            try:
                moves = rules.plan(self.folder, settings, rename=template)
            except (OSError, UnsafeFolderError):
                moves = []
            for move in moves[:8]:
                lines.append(f"{move.source.name}  ->  {move.target_name}")
        if not lines:
            sample = Path("IMG_1234.jpg")
            lines.append(f"{sample.name}  ->  {render_name(template, sample, datetime(2025, 1, 5), 250_000)}")
        self.preview.setPlainText("\n".join(lines))


class StructureCombo(QComboBox):
    """Ready-made structures, the current custom one, and 'Build my own...'."""

    patternChosen = Signal(object)  # str, or None for "use the default"

    def __init__(self, organizer: Organizer, allow_default: bool, parent=None):
        super().__init__(parent)
        self.organizer = organizer
        self.allow_default = allow_default
        self._pattern: str | None = None
        self._folder: Path | None = None
        self.setMinimumWidth(260)
        self.activated.connect(self._on_activated)

    def set_pattern(self, pattern: str | None, folder: Path | None = None) -> None:
        self._pattern = pattern
        self._folder = folder
        self.clear()
        if self.allow_default:
            self.addItem(f"Default ({describe_pattern(self.organizer.settings.pattern)})", None)
        for mode in SortMode:
            self.addItem(mode.label, mode.pattern)
        if pattern and pattern not in [m.pattern for m in SortMode]:
            self.addItem(describe_pattern(pattern), pattern)
        self.addItem("Build my own...", BUILD_OWN)
        index = self.findData(pattern)
        self.setCurrentIndex(max(index, 0))

    def current_pattern(self) -> str | None:
        return self._pattern

    def _on_activated(self, index: int) -> None:
        data = self.itemData(index)
        if data == BUILD_OWN:
            start = self._pattern or self.organizer.settings.pattern
            dialog = StructureDialog(self.organizer, self._folder, start, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.set_pattern(dialog.pattern(), self._folder)
                self.patternChosen.emit(self._pattern)
            else:
                self.set_pattern(self._pattern, self._folder)
            return
        self._pattern = data
        self.patternChosen.emit(data)


class CategoriesDialog(QDialog):
    """Edit the user's own categories, e.g. Invoices = pdf."""

    def __init__(self, organizer: Organizer, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Your categories")
        self.setMinimumSize(560, 480)
        self.organizer = organizer

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Make your own categories for the <code>{category}</code> placeholder. "
            "They are checked before the built-in ones, so <i>Invoices = pdf</i> sends every PDF to Invoices."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Category folder", "Extensions (comma separated)"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        for name, exts in organizer.settings.custom_categories.items():
            self._add_row(name, ", ".join(exts))
        layout.addWidget(self.table)

        row = QHBoxLayout()
        add = QPushButton("Add category")
        add.clicked.connect(lambda: self._add_row("", ""))
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_selected)
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch()
        layout.addLayout(row)

        builtin = QLabel("Built-in categories")
        builtin.setObjectName("SectionLabel")
        layout.addWidget(builtin)
        text = QPlainTextEdit("\n".join(f"{n}: {', '.join(sorted(e))}" for n, e in CATEGORIES.items()))
        text.setReadOnly(True)
        text.setFixedHeight(130)
        layout.addWidget(text)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_row(self, name: str, exts: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        self.table.setItem(row, 1, QTableWidgetItem(exts))
        if not name:
            self.table.editItem(self.table.item(row, 0))

    def _remove_selected(self) -> None:
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def _save(self) -> None:
        settings = self.organizer.settings
        previous = dict(settings.custom_categories)
        settings.custom_categories = {}
        try:
            for row in range(self.table.rowCount()):
                name = (self.table.item(row, 0).text() if self.table.item(row, 0) else "").strip()
                exts = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
                if not name and not exts.strip():
                    continue
                if any(c in name for c in '<>:"/\\|?*'):
                    raise ValueError(f"'{name}' can't be used as a folder name.")
                settings.set_category(name, [e for e in exts.replace(";", ",").split(",")])
        except ValueError as exc:
            settings.custom_categories = previous
            QMessageBox.warning(self, "Check your categories", str(exc))
            return
        settings.save()
        self.accept()


class HistoryDialog(QDialog):
    """Past runs, with undo for any run that hasn't been undone yet."""

    changed = Signal()

    def __init__(self, organizer: Organizer, parent=None):
        super().__init__(parent)
        self.setWindowTitle("History")
        self.setMinimumSize(760, 420)
        self.organizer = organizer

        layout = QVBoxLayout(self)
        self.stats = QLabel()
        self.stats.setObjectName("Muted")
        layout.addWidget(self.stats)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["When", "Folder", "Structure", "Files", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._update_button)
        layout.addWidget(self.table)

        row = QHBoxLayout()
        self.undo_button = QPushButton("Undo this run")
        self.undo_button.clicked.connect(self._undo_selected)
        self.export_button = QPushButton("Export run...")
        self.export_button.setToolTip("Save a list of the files this run moved, as a spreadsheet or web page")
        self.export_button.clicked.connect(self._export_selected)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(self.undo_button)
        row.addWidget(self.export_button)
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)
        self._load()

    def _load(self) -> None:
        self.runs = self.organizer.history.runs(limit=200)
        files, runs = self.organizer.history.stats()
        self.stats.setText(f"{files} file{'s' if files != 1 else ''} organized in {runs} "
                           f"run{'s' if runs != 1 else ''} so far.")
        self.table.setRowCount(len(self.runs))
        for i, run in enumerate(self.runs):
            status = "Undone" if run.undone_at else ("Can undo" if run.can_undo else "-")
            for col, value in enumerate([
                run.started_at.strftime("%Y-%m-%d %H:%M"),
                str(run.folder),
                describe_pattern(run.structure),
                str(run.move_count),
                status,
            ]):
                self.table.setItem(i, col, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        self._update_button()

    def _selected(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        return self.runs[rows.pop()] if rows else None

    def _update_button(self) -> None:
        run = self._selected()
        self.undo_button.setEnabled(bool(run and run.can_undo))
        self.export_button.setEnabled(run is not None)

    def _export_selected(self) -> None:
        run = self._selected()
        if run is not None:
            save_report(self, reports.run_report(self.organizer.history, run.id),
                        f"Run {run.id} {run.started_at:%Y-%m-%d}")

    def _undo_selected(self) -> None:
        run = self._selected()
        if not run:
            return
        answer = QMessageBox.question(self, "Undo run", f"Put {run.move_count} files back where they were in {run.folder}?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = self.organizer.undo(run.id)
        self._load()
        self.changed.emit()
        message = f"Restored {len(result.restored)} files."
        if result.failed:
            message += f"\n{len(result.failed)} couldn't be restored:\n" + "\n".join(
                f"{p.name}: {reason}" for p, reason in result.failed[:10]
            )
        QMessageBox.information(self, "Undo", message)


class SettingsDialog(QDialog):
    def __init__(self, organizer: Organizer, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        self.organizer = organizer
        settings = organizer.settings

        form = QFormLayout()
        self.theme = QComboBox()
        for value, label in (("system", "Match system"), ("light", "Light"), ("dark", "Dark")):
            self.theme.addItem(label, value)
        self.theme.setCurrentIndex(max(self.theme.findData(settings.theme), 0))
        form.addRow("Theme", self.theme)

        self.structure = StructureCombo(organizer, allow_default=False)
        self.structure.set_pattern(settings.pattern)
        form.addRow("Default structure", self.structure)

        self.skip_hidden = QCheckBox("Leave hidden and system files alone")
        self.skip_hidden.setChecked(settings.skip_hidden)
        form.addRow("", self.skip_hidden)

        self.excluded_exts = QLineEdit(", ".join(settings.excluded_extensions))
        self.excluded_exts.setToolTip("Files with these extensions are never moved. Shortcuts (.lnk, .url) are here by default.")
        form.addRow("Never move types", self.excluded_exts)

        self.excluded_names = QLineEdit(", ".join(settings.excluded_names))
        form.addRow("Never move files named", self.excluded_names)

        self.tray = QCheckBox("Keep running in the system tray when the window is closed")
        self.tray.setToolTip("Needed for auto-organize to keep working after you close the window.")
        self.tray.setChecked(settings.minimize_to_tray)
        form.addRow("Background", self.tray)
        self.notifications = QCheckBox("Show a notification after auto-organizing")
        self.notifications.setChecked(settings.notifications)
        form.addRow("", self.notifications)
        self.start_with_windows = QCheckBox("Start when I sign in to Windows (in the tray)")
        self.start_with_windows.setChecked(startup.is_enabled())
        self.start_with_windows.setVisible(startup.is_supported())
        form.addRow("", self.start_with_windows)
        self.explorer_menu = QCheckBox("Add 'Organize with Desktop Organizer' and 'Where did this file "
                                       "come from?' to the right-click menu")
        self.explorer_menu.setToolTip("On Windows 11 these are under 'Show more options'.")
        self.explorer_menu.setChecked(shell.is_enabled())
        self.explorer_menu.setVisible(startup.is_supported())
        form.addRow("File Explorer", self.explorer_menu)
        self.check_updates = QCheckBox("Check for updates once a week (contacts GitHub)")
        self.check_updates.setChecked(settings.check_updates)
        form.addRow("Updates", self.check_updates)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        settings = self.organizer.settings
        settings.theme = self.theme.currentData()
        settings.pattern = self.structure.current_pattern() or settings.pattern
        settings.skip_hidden = self.skip_hidden.isChecked()
        settings.excluded_extensions = _split(self.excluded_exts.text())
        settings.excluded_names = _split(self.excluded_names.text())
        settings.minimize_to_tray = self.tray.isChecked()
        settings.notifications = self.notifications.isChecked()
        settings.check_updates = self.check_updates.isChecked()
        settings.save()
        if startup.is_supported() and self.start_with_windows.isChecked() != startup.is_enabled():
            try:
                startup.set_enabled(self.start_with_windows.isChecked())
            except OSError as exc:
                QMessageBox.warning(self, "Start with Windows", f"Couldn't change this setting: {exc}")
        if startup.is_supported() and self.explorer_menu.isChecked() != shell.is_enabled():
            try:
                shell.set_enabled(self.explorer_menu.isChecked())
            except OSError as exc:
                QMessageBox.warning(self, "File Explorer menu", f"Couldn't change this setting: {exc}")
        self.accept()


def save_report(parent, report: reports.Report, suggested: str) -> Path | None:
    """Ask where to save a report, then write it as CSV or HTML. Returns the saved path."""
    filters = ";;".join(reports.FORMATS.values())
    start = str(Path.home() / "Documents" / f"{_safe_file_name(suggested)}.html")
    path, chosen = QFileDialog.getSaveFileName(parent, "Export", start, filters)
    if not path:
        return None
    target = Path(path)
    if target.suffix.lower() not in reports.FORMATS:
        target = target.with_suffix(".csv" if "csv" in chosen else ".html")
    try:
        saved = reports.save(report, target)
    except OSError as exc:
        QMessageBox.warning(parent, "Export", f"Couldn't save the file: {exc.strerror or exc}")
        return None
    QMessageBox.information(parent, "Export", f"Saved {len(report.rows)} file(s) to\n{saved}")
    return saved


def _safe_file_name(text: str) -> str:
    return "".join("_" if c in '<>:"/\\|?*' else c for c in text).strip() or "Report"


def _split(text: str) -> list[str]:
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def section_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("SectionLabel")
    return label

