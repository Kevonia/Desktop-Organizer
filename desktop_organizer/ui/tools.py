"""Rule builder and duplicate finder windows."""

from __future__ import annotations

import copy
import dataclasses
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_organizer.core import Organizer, rules, trash
from desktop_organizer.core.duplicates import DuplicateGroup, find_duplicates
from desktop_organizer.core.structure import TOKENS
from desktop_organizer.core.user_rules import Condition, ConditionKind, Rule, RuleAction, RuleError
from desktop_organizer.ui.worker import Task


class RulesDialog(QDialog):
    """Create rules like 'name contains invoice AND type is pdf -> Finance/Invoices/{year}'."""

    def __init__(self, organizer: Organizer, folder: Path | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rules")
        self.setMinimumSize(900, 560)
        self.organizer = organizer
        self.folder = folder
        self.rules: list[Rule] = copy.deepcopy(organizer.settings.rules)
        self._loading = False

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Rules are checked from top to bottom before the folder's structure. "
            "The first rule that matches a file decides where it goes."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        splitter = QSplitter()
        splitter.addWidget(self._build_list())
        splitter.addWidget(self._build_editor())
        splitter.setSizes([260, 640])
        layout.addWidget(splitter, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._reload_list(0)

    # --- list of rules ------------------------------------------------------------

    def _build_list(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._load_rule)
        self.list.itemChanged.connect(self._on_toggle)
        layout.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, slot in (("Add", self._add_rule), ("Delete", self._delete_rule),
                           ("Up", lambda: self._move(-1)), ("Down", lambda: self._move(1))):
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
        layout.addLayout(row)
        return panel

    def _reload_list(self, select: int) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for rule in self.rules:
            item = QListWidgetItem(rule.name or "(unnamed)")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if rule.enabled else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        self.list.blockSignals(False)
        if self.rules:
            self.list.setCurrentRow(min(max(select, 0), len(self.rules) - 1))
        self._load_rule(self.list.currentRow())

    def _on_toggle(self, item: QListWidgetItem) -> None:
        row = self.list.row(item)
        if 0 <= row < len(self.rules):
            self.rules[row].enabled = item.checkState() == Qt.CheckState.Checked
            self._update_matches()

    def _add_rule(self) -> None:
        self.rules.append(Rule(
            name=f"Rule {len(self.rules) + 1}",
            conditions=[Condition(ConditionKind.NAME_CONTAINS, "")],
            destination="{category}",
        ))
        self._reload_list(len(self.rules) - 1)
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _delete_rule(self) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self.rules):
            del self.rules[row]
            self._reload_list(row)

    def _move(self, step: int) -> None:
        row = self.list.currentRow()
        target = row + step
        if 0 <= row < len(self.rules) and 0 <= target < len(self.rules):
            self.rules[row], self.rules[target] = self.rules[target], self.rules[row]
            self._reload_list(target)

    # --- editor -------------------------------------------------------------------

    def _build_editor(self) -> QWidget:
        self.editor = QWidget()
        layout = QVBoxLayout(self.editor)
        layout.setContentsMargins(8, 0, 0, 0)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._store)
        form.addRow("Name", self.name_edit)

        self.match_combo = QComboBox()
        self.match_combo.addItem("all of these are true", True)
        self.match_combo.addItem("any of these is true", False)
        self.match_combo.currentIndexChanged.connect(self._store)
        form.addRow("When", self.match_combo)
        layout.addLayout(form)

        self.conditions_box = QVBoxLayout()
        layout.addLayout(self.conditions_box)
        add_condition = QPushButton("+ Add condition")
        add_condition.clicked.connect(lambda: self._add_condition_row(Condition(ConditionKind.NAME_CONTAINS, "")))
        row = QHBoxLayout()
        row.addWidget(add_condition)
        row.addStretch()
        layout.addLayout(row)

        form2 = QFormLayout()
        self.action_combo = QComboBox()
        self.action_combo.addItem("Move to", RuleAction.MOVE.value)
        self.action_combo.addItem("Leave in place", RuleAction.SKIP.value)
        self.action_combo.currentIndexChanged.connect(self._store)
        form2.addRow("Then", self.action_combo)

        self.destination_edit = QLineEdit()
        self.destination_edit.setPlaceholderText("Finance/Invoices/{year}")
        self.destination_edit.setToolTip("Placeholders: " + ", ".join(f"{{{t}}}" for t in TOKENS))
        self.destination_edit.textChanged.connect(self._store)
        form2.addRow("Folder", self.destination_edit)

        self.scope_combo = QComboBox()
        self.scope_combo.addItem("All folders", None)
        for profile in self.organizer.settings.folders:
            self.scope_combo.addItem(f"Only {profile.name}", profile.path)
        self.scope_combo.currentIndexChanged.connect(self._store)
        form2.addRow("Applies to", self.scope_combo)
        layout.addLayout(form2)

        self.error = QLabel()
        self.error.setObjectName("Error")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        self.matches = QLabel()
        self.matches.setObjectName("Muted")
        self.matches.setWordWrap(True)
        layout.addWidget(self.matches)
        layout.addStretch()
        return self.editor

    def _current(self) -> Rule | None:
        row = self.list.currentRow()
        return self.rules[row] if 0 <= row < len(self.rules) else None

    def _load_rule(self, row: int) -> None:
        rule = self._current()
        self.editor.setEnabled(rule is not None)
        self._loading = True
        while self.conditions_box.count():
            widget = self.conditions_box.takeAt(0).widget()
            if widget:
                widget.setParent(None)  # off-screen now, not just when Qt gets round to deleting it
                widget.deleteLater()
        if rule is not None:
            self.name_edit.setText(rule.name)
            self.match_combo.setCurrentIndex(0 if rule.match_all else 1)
            for condition in rule.conditions:
                self._add_condition_row(condition)
            self.action_combo.setCurrentIndex(self.action_combo.findData(rule.action.value))
            self.destination_edit.setText(rule.destination)
            scope = self.scope_combo.findData(rule.folders[0]) if rule.folders else 0
            self.scope_combo.setCurrentIndex(max(scope, 0))
        self._loading = False
        self._update_matches()

    def _add_condition_row(self, condition: Condition) -> None:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        kind = QComboBox()
        for k in ConditionKind:
            kind.addItem(k.label, k.value)
        kind.setCurrentIndex(kind.findData(condition.kind.value))
        value = QLineEdit(condition.value)
        remove = QPushButton("Remove")
        layout.addWidget(kind)
        layout.addWidget(value, 1)
        layout.addWidget(remove)
        kind.currentIndexChanged.connect(self._store)
        value.textChanged.connect(self._store)
        remove.clicked.connect(lambda: (row.setParent(None), row.deleteLater(), self._store()))
        row.kind, row.value = kind, value
        self.conditions_box.addWidget(row)
        self._store()

    def _store(self, *_) -> None:
        rule = self._current()
        if rule is None or self._loading:
            return
        rule.name = self.name_edit.text()
        rule.match_all = bool(self.match_combo.currentData())
        rule.conditions = []
        for i in range(self.conditions_box.count()):
            row = self.conditions_box.itemAt(i).widget()
            if row is not None and hasattr(row, "kind"):
                rule.conditions.append(Condition(ConditionKind(row.kind.currentData()), row.value.text()))
        rule.action = RuleAction(self.action_combo.currentData())
        rule.destination = self.destination_edit.text()
        scope = self.scope_combo.currentData()
        rule.folders = [scope] if scope else []
        self.destination_edit.setEnabled(rule.action is RuleAction.MOVE)
        item = self.list.currentItem()
        if item is not None:
            self.list.blockSignals(True)
            item.setText(rule.name or "(unnamed)")
            self.list.blockSignals(False)
        self._update_matches()

    def _update_matches(self) -> None:
        rule = self._current()
        self.error.setText("")
        self.matches.setText("")
        if rule is None:
            return
        try:
            candidate = copy.deepcopy(rule)
            candidate.validate()
        except RuleError as exc:
            self.error.setText(str(exc))
            return
        if self.folder is None or not self.folder.is_dir():
            return
        candidate.enabled = True
        with_rule = dataclasses.replace(self.organizer.settings, rules=[candidate])
        planned = rules.plan(self.folder, with_rule)
        if candidate.action is RuleAction.SKIP:
            without = rules.plan(self.folder, dataclasses.replace(self.organizer.settings, rules=[]))
            skipped = len(without) - len(planned)
            self.matches.setText(f"Would leave {skipped} file(s) in {self.folder.name} where they are.")
            return
        hits = [m for m in planned if m.rule == candidate.name]
        names = ", ".join(m.source.name for m in hits[:5]) + (" ..." if len(hits) > 5 else "")
        self.matches.setText(f"Matches {len(hits)} file(s) in {self.folder.name}" + (f": {names}" if hits else "."))

    def _save(self) -> None:
        for index, rule in enumerate(self.rules):
            try:
                rule.validate()
            except RuleError as exc:
                self.list.setCurrentRow(index)
                QMessageBox.warning(self, "Check this rule", str(exc))
                return
        self.organizer.settings.rules = self.rules
        self.organizer.settings.save()
        self.accept()


class DuplicatesDialog(QDialog):
    """Find identical files and send the extra copies to the Recycle Bin."""

    def __init__(self, organizer: Organizer, folder: Path | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find duplicates")
        self.setMinimumSize(860, 560)
        self.organizer = organizer
        self.folder = folder
        self.groups: list[DuplicateGroup] = []
        self.task: Task | None = None
        self._stop = False
        self.send_to_trash = trash.send_to_trash

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.folder_label = QLabel()
        self.folder_label.setObjectName("Muted")
        choose = QPushButton("Choose folder...")
        choose.clicked.connect(self._choose_folder)
        self.recursive = QCheckBox("Include subfolders")
        self.recursive.setChecked(True)
        self.scan_button = QPushButton("Scan")
        self.scan_button.setObjectName("Primary")
        self.scan_button.clicked.connect(self.scan)
        top.addWidget(self.folder_label, 1)
        top.addWidget(choose)
        top.addWidget(self.recursive)
        top.addWidget(self.scan_button)
        layout.addLayout(top)

        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "Folder", "Modified"])
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.header().resizeSection(0, 300)
        self.tree.itemChanged.connect(lambda *_: self._update_summary())
        layout.addWidget(self.tree, 1)

        bottom = QHBoxLayout()
        self.summary = QLabel("Choose a folder and press Scan. Checked copies will be moved to the Recycle Bin.")
        self.summary.setObjectName("Muted")
        self.summary.setWordWrap(True)
        self.delete_button = QPushButton("Move selected to Recycle Bin")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self.delete_selected)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        bottom.addWidget(self.summary, 1)
        bottom.addWidget(self.delete_button)
        bottom.addWidget(close)
        layout.addLayout(bottom)
        self._show_folder()

    def _show_folder(self) -> None:
        self.folder_label.setText(str(self.folder) if self.folder else "No folder chosen")
        self.scan_button.setEnabled(self.folder is not None)

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Folder to check for duplicates",
                                                str(self.folder or Path.home()))
        if path:
            self.folder = Path(path)
            self._show_folder()

    def scan(self) -> None:
        if self.folder is None or self.task is not None:
            return
        self._stop = False
        folder, recursive = self.folder, self.recursive.isChecked()
        self.task = Task(lambda progress: find_duplicates(
            folder, recursive=recursive, progress=progress, should_stop=lambda: self._stop
        ), self)
        self.task.progressed.connect(self._on_progress)
        result: dict = {}
        self.task.succeeded.connect(lambda groups: result.update(groups=groups))
        self.task.failed.connect(lambda message: result.update(error=message))
        self.task.finished.connect(lambda: self._scan_finished(result))
        self.progress.setRange(0, 0)
        self.progress.setFormat("Looking for files...")
        self.progress.show()
        self.scan_button.setEnabled(False)
        self.task.start()

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.progress.setFormat(f"Comparing {done}/{total}: {name}")

    def _scan_finished(self, result: dict) -> None:
        self.task = None
        self.progress.hide()
        self.scan_button.setEnabled(True)
        if "error" in result:
            QMessageBox.critical(self, "Scan failed", result["error"])
            return
        self.show_groups(result.get("groups", []))

    def show_groups(self, groups: list[DuplicateGroup]) -> None:
        self.groups = groups
        self.tree.blockSignals(True)
        self.tree.clear()
        for group in groups:
            parent = QTreeWidgetItem([f"{len(group.files)} copies, {_size(group.size)} each", "", ""])
            parent.setFirstColumnSpanned(True)
            self.tree.addTopLevelItem(parent)
            for index, path in enumerate(group.files):
                child = QTreeWidgetItem([path.name, str(path.parent), _modified(path)])
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                # Keep the oldest copy by default; tick the rest.
                child.setCheckState(0, Qt.CheckState.Unchecked if index == 0 else Qt.CheckState.Checked)
                child.setData(0, Qt.ItemDataRole.UserRole, str(path))
                parent.addChild(child)
            parent.setExpanded(True)
        self.tree.blockSignals(False)
        self._update_summary()

    def checked_paths(self) -> list[Path]:
        paths = []
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.checkState(0) == Qt.CheckState.Checked:
                    paths.append(Path(child.data(0, Qt.ItemDataRole.UserRole)))
        return paths

    def _fully_checked_group(self) -> int | None:
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            if parent.childCount() and all(
                parent.child(j).checkState(0) == Qt.CheckState.Checked for j in range(parent.childCount())
            ):
                return i
        return None

    def _update_summary(self) -> None:
        if not self.groups:
            self.summary.setText("No duplicates found." if self.tree.topLevelItemCount() == 0 and
                                 self.folder_label.text() else "")
            self.delete_button.setEnabled(False)
            return
        checked = self.checked_paths()
        sizes = {str(p): g.size for g in self.groups for p in g.files}
        freed = sum(sizes.get(str(p), 0) for p in checked)
        wasted = sum(g.wasted for g in self.groups)
        self.summary.setText(
            f"{len(self.groups)} set{'s' if len(self.groups) != 1 else ''} of duplicates using "
            f"{_size(wasted)} extra. "
            f"{len(checked)} selected ({_size(freed)})."
        )
        self.delete_button.setEnabled(bool(checked))

    def delete_selected(self) -> None:
        group = self._fully_checked_group()
        if group is not None:
            QMessageBox.warning(self, "Keep one copy",
                                "Every copy in one of the sets is ticked. Untick the one you want to keep.")
            self.tree.scrollToItem(self.tree.topLevelItem(group))
            return
        paths = self.checked_paths()
        if not paths or not self.confirm(len(paths)):
            return
        failed = self.send_to_trash(paths)
        failed_set = {str(p) for p, _ in failed}
        removed = {str(p) for p in paths} - failed_set
        remaining = []
        for group in self.groups:
            files = [p for p in group.files if str(p) not in removed]
            if len(files) > 1:
                remaining.append(DuplicateGroup(group.size, files))
        self.show_groups(remaining)
        if failed:
            QMessageBox.warning(self, "Some files weren't moved",
                                "\n".join(f"{p.name}: {reason}" for p, reason in failed[:15]))

    def confirm(self, count: int) -> bool:
        answer = QMessageBox.question(
            self, "Move to Recycle Bin",
            f"Move {count} duplicate file{'s' if count != 1 else ''} to the Recycle Bin?\n"
            "You can restore them from there.",
        )
        return answer == QMessageBox.StandardButton.Yes

    def closeEvent(self, event) -> None:
        if self.task is not None:
            self._stop = True
            self.task.wait(5000)
        super().closeEvent(event)


def _size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _modified(path: Path) -> str:
    from datetime import datetime

    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return ""

