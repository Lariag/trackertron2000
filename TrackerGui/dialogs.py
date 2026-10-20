"""The dialogs: quick add (Enter creates), add section, history (versions with the old bodies)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLineEdit, QListWidget, QPlainTextEdit, QSpinBox,
                               QSplitter, QTextEdit, QVBoxLayout)

from cli import CliError, TYPES


class QuickAddDialog(QDialog):
    """Type, title, subject, optional body and "put it first"; Enter in the title creates it."""

    def __init__(self, parent, subjects, default_type="feature"):
        super().__init__(parent)
        self.setWindowTitle("New item")
        self.setMinimumWidth(520)
        form = QFormLayout(self)
        self.type = QComboBox()
        self.type.addItems(TYPES)
        self.type.setCurrentText(default_type)
        self.title = QLineEdit(placeholderText="What is it?")
        self.subject = QComboBox(editable=True)
        self.subject.addItems([""] + subjects)
        self.draft = QCheckBox("Draft (still being defined)")
        self.first = QCheckBox("Put it first in the next order")
        self.body = QPlainTextEdit(placeholderText="Body (markdown), optional: empty gives the type's sections, and any body must keep them")
        self.body.setMaximumHeight(140)
        form.addRow("Type", self.type)
        form.addRow("Title", self.title)
        form.addRow("Subject", self.subject)
        form.addRow("", self.draft)
        form.addRow("", self.first)
        form.addRow("Body", self.body)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.title.returnPressed.connect(self.accept)
        self.title.setFocus()

    def accept(self):
        if self.title.text().strip():
            super().accept()

    def values(self):
        return {"type_": self.type.currentText(), "title": self.title.text().strip(),
                "subject": self.subject.currentText().strip(),
                "status": "draft" if self.draft.isChecked() else "open",
                "body": self.body.toPlainText(), "rank": 1 if self.first.isChecked() else None}


# The heading level of an item's fixed sections; only deeper subsections can be added (the CLI
# refuses the rest).
SECTION_LEVEL = 2
# The deepest markdown heading.
MAX_LEVEL = 6


class AddSectionDialog(QDialog):
    """Title, level, where (at the end / at the end of one of the sections), optional content. Only
    subsections: an item's sections are fixed by its type."""

    def __init__(self, parent, existing):
        super().__init__(parent)
        self.setWindowTitle("Add subsection")
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        self.title = QLineEdit(placeholderText="Subsection title")
        self.level = QSpinBox()
        self.level.setRange(SECTION_LEVEL + 1, MAX_LEVEL)
        self.level.setValue(SECTION_LEVEL + 1)
        self.where = QComboBox()
        self.where.addItems(["At the end"] + [f"In: {title}" for title in existing])
        self.body = QPlainTextEdit(placeholderText="Content (markdown), optional")
        self.body.setMaximumHeight(140)
        form.addRow("Title", self.title)
        form.addRow("Level", self.level)
        form.addRow("Where", self.where)
        form.addRow("Content", self.body)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.title.returnPressed.connect(self.accept)
        self.title.setFocus()

    def accept(self):
        if self.title.text().strip():
            super().accept()

    def values(self):
        where = self.where.currentIndex()
        return {"title": self.title.text().strip(), "level": self.level.value(),
                "body": self.body.toPlainText(),
                "after": self.where.currentText().removeprefix("In: ") if where > 0 else None}


class HistoryDialog(QDialog):
    """Every version of an item on the left, the selected version's fields and body on the right."""

    def __init__(self, parent, tracker, item_id):
        super().__init__(parent)
        self.tracker = tracker
        self.item_id = item_id
        self.setWindowTitle(f"History of #{item_id}")
        self.resize(900, 600)
        layout = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        self.versions = QListWidget()
        self.versions.setFont(QFont("Consolas", 10))
        split.addWidget(self.versions)
        self.view = QTextEdit(readOnly=True)
        split.addWidget(self.view)
        split.setSizes([360, 540])
        layout.addWidget(split)
        try:
            for version in tracker.history(item_id):
                flag = "  DELETED" if version["deleted"] else ""
                self.versions.addItem(f"v{version['version']:<3} {version['changed']}  {version['type']:<8} "
                                      f"{version['status']:<7} {version['title']}{flag}")
                self.versions.item(self.versions.count() - 1).setData(Qt.UserRole, version["version"])
        except CliError as error:
            self.view.setPlainText(str(error))
        self.versions.currentItemChanged.connect(self._show_version)
        self.versions.setCurrentRow(self.versions.count() - 1)

    def _show_version(self, current, previous):
        if current is None:
            return
        try:
            item = self.tracker.show(self.item_id, version=current.data(Qt.UserRole), deleted=True)
        except CliError as error:
            self.view.setPlainText(str(error))
            return
        head = (f"**#{item['item_id']} v{item['version']}** — {item['type']} / {item['status']} / "
                f"{item['subject'] or '(no subject)'}  \n*{item['changed']}*\n\n# {item['title']}\n\n")
        self.view.setMarkdown(head + item["expanded_body"])
