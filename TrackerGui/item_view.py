"""The right pane: one item, in one of two modes (Ctrl+E switches). View mode, the default, only
reads: the body and the notes rendered, with every reference carrying its title, and every field and
writing action locked in its place. Edit mode writes: header fields save as soon as they are
committed, the body is a plain editor that saves on Ctrl+S (or when leaving the item or the mode,
after asking), notes are added with Ctrl+Enter, and the actions (done, drop, delete...) are one
click each. In both, the sections outline jumps to a heading."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter,
                               QTextEdit, QToolButton, QVBoxLayout, QWidget)

from cli import CLOSED, CliError, STATUSES, TYPES
from dialogs import AddSectionDialog, HistoryDialog


def heading(text):
    return QLabel(text, objectName="heading")


# The marks of the notes pane: a coloured emoji for each state, so a question and its answer stand out.
OPEN_QUESTION = "\u2753"  # red question mark
ANSWERED_QUESTION = "\u2705"  # green check mark
ANSWER = "\U0001F4AC"  # speech balloon


# One note as the notes pane shows it: the date, the mark of a question or an answer, the text with
# its references expanded.
def note_markdown(note):
    if note["question"] and note["answered_by"]:
        mark = f"{ANSWERED_QUESTION} *Question {note['id']}, answered in {note['answered_by']}* — "
    elif note["question"]:
        mark = f"{OPEN_QUESTION} *Question {note['id']}, open* — "
    elif note["answers"]:
        mark = f"{ANSWER} *Answer {note['id']} to {', '.join(str(i) for i in note['answers'])}* — "
    else:
        mark = ""
    return f"**{note['date']}** — {mark}{note['expanded_text']}"


class ItemView(QWidget):
    """Shows and edits one item through the tracker. Emits `changed()` after any write so the list
    can refresh, and `error(message)` for the status bar."""

    changed = Signal()
    error = Signal(str)

    def __init__(self, tracker):
        super().__init__()
        self.tracker = tracker
        self.item = None
        self.editing = False
        self._loading = False
        self._build()
        self.show_item(None)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Title line: id, title, actions.
        top = QHBoxLayout()
        self.id_label = QLabel(objectName="muted")
        self.id_label.setFont(QFont("Consolas", 14))
        top.addWidget(self.id_label)
        self.title = QLineEdit(objectName="title", placeholderText="Title")
        self.title.editingFinished.connect(lambda: self._set_field("title", self.title.text().strip()))
        top.addWidget(self.title, 1)
        self.edit_toggle = QToolButton(text="Edit  Ctrl+E", checkable=True,
                                       toolTip="Switch between viewing the item (rendered) and editing it")
        self.edit_toggle.toggled.connect(self._toggle_mode)
        top.addWidget(self.edit_toggle)
        self.done_button = QPushButton("Done", objectName="primary", toolTip="Close as done (Ctrl+Shift+D)")
        self.done_button.clicked.connect(lambda: self._close("done"))
        self.drop_button = QPushButton("Drop", toolTip="Close as dropped")
        self.drop_button.clicked.connect(lambda: self._close("dropped"))
        self.delete_button = QPushButton("Delete", objectName="danger", toolTip="Logical delete: hidden, history kept")
        self.delete_button.clicked.connect(self._delete)
        self.restore_button = QPushButton("Restore")
        self.restore_button.clicked.connect(self._restore)
        self.history_button = QPushButton("History")
        self.history_button.clicked.connect(self._history)
        for button in (self.done_button, self.drop_button, self.restore_button, self.delete_button, self.history_button):
            top.addWidget(button)
        layout.addLayout(top)

        # Field line: type, status, subject, rank, dates.
        fields = QHBoxLayout()
        fields.setSpacing(8)
        self.type = QComboBox()
        self.type.addItems(TYPES)
        self.type.currentTextChanged.connect(lambda value: self._set_field("type", value))
        self.status = QComboBox()
        self.status.addItems(STATUSES)
        self.status.currentTextChanged.connect(lambda value: self._set_field("status", value))
        self.subject = QLineEdit(placeholderText="subject")
        self.subject.setMaximumWidth(140)
        self.subject.editingFinished.connect(lambda: self._set_field("subject", self.subject.text().strip()))
        self.rank = QSpinBox(toolTip="Position in the next order; 0 = backlog", specialValueText="backlog")
        self.rank.setRange(0, 999)
        self.rank.editingFinished.connect(self._set_rank)
        self.dates = QLabel(objectName="muted")
        for label, widget in (("type", self.type), ("status", self.status), ("subject", self.subject), ("rank", self.rank)):
            fields.addWidget(heading(label.upper()))
            fields.addWidget(widget)
        fields.addStretch()
        fields.addWidget(self.dates)
        layout.addLayout(fields)

        # Body: outline | editor | preview, then notes below.
        body_split = QSplitter(Qt.Horizontal)
        outline_box = QWidget()
        outline_layout = QVBoxLayout(outline_box)
        outline_layout.setContentsMargins(0, 0, 0, 0)
        outline_layout.setSpacing(4)
        outline_head = QHBoxLayout()
        outline_head.addWidget(heading("SECTIONS"))
        outline_head.addStretch()
        self.add_section_button = QToolButton(text="+", toolTip="Add a subsection")
        self.add_section_button.clicked.connect(self._add_section)
        outline_head.addWidget(self.add_section_button)
        outline_layout.addLayout(outline_head)
        self.outline = QListWidget()
        self.outline.itemClicked.connect(self._jump_to_section)
        outline_layout.addWidget(self.outline)
        body_split.addWidget(outline_box)

        self.editor_box = QWidget()
        editor_layout = QVBoxLayout(self.editor_box)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(4)
        editor_head = QHBoxLayout()
        editor_head.addWidget(heading("BODY"))
        self.dirty_label = QLabel("unsaved", objectName="muted")
        editor_head.addWidget(self.dirty_label)
        editor_head.addStretch()
        self.save_button = QPushButton("Save  Ctrl+S", objectName="primary")
        self.save_button.clicked.connect(self.save_body)
        editor_head.addWidget(self.save_button)
        editor_layout.addLayout(editor_head)
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Consolas", 11))
        self.editor.setTabStopDistance(28)
        self.editor.textChanged.connect(self._on_body_edited)
        editor_layout.addWidget(self.editor)
        body_split.addWidget(self.editor_box)

        # The rendered body, in view mode; the editor takes its place in edit mode.
        self.preview = QTextEdit(readOnly=True)
        body_split.addWidget(self.preview)
        body_split.setStretchFactor(0, 0)
        body_split.setStretchFactor(1, 1)
        body_split.setStretchFactor(2, 1)
        body_split.setSizes([160, 900, 900])

        notes_box = QWidget()
        notes_layout = QVBoxLayout(notes_box)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.setSpacing(4)
        notes_layout.addWidget(heading("NOTES"))
        self.notes = QTextEdit(readOnly=True)
        notes_layout.addWidget(self.notes, 1)
        self.note_row = QWidget()
        note_row = QHBoxLayout(self.note_row)
        note_row.setContentsMargins(0, 0, 0, 0)
        self.note_input = QPlainTextEdit(placeholderText="Add a note...  Ctrl+Enter")
        self.note_input.setMaximumHeight(60)
        note_row.addWidget(self.note_input, 1)
        add_note = QPushButton("Add note")
        add_note.clicked.connect(self.add_note)
        note_row.addWidget(add_note)
        notes_layout.addWidget(self.note_row)

        main_split = QSplitter(Qt.Vertical)
        main_split.addWidget(body_split)
        main_split.addWidget(notes_box)
        main_split.setStretchFactor(0, 3)
        main_split.setStretchFactor(1, 1)
        layout.addWidget(main_split, 1)

        QShortcut(QKeySequence.Save, self, activated=self.save_body)
        QShortcut(QKeySequence("Ctrl+Return"), self.note_input, activated=self.add_note)
        QShortcut(QKeySequence("Ctrl+Shift+D"), self, activated=lambda: self._close("done"))
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self.edit_toggle.toggle)

    # --- loading ---

    # Show an item (None clears the pane); the pending body is offered for saving first.
    def show_item(self, item_id, deleted=False):
        if not self.confirm_leave():
            return False
        self.item = None
        if item_id is not None:
            try:
                self.item = self.tracker.show(item_id, deleted=deleted)
            except CliError as error:
                self.error.emit(str(error))
        self._fill()
        return True

    def reload(self):
        if self.item:
            self.show_item(self.item["item_id"], deleted=bool(self.item["deleted"]))

    def _fill(self):
        self._loading = True
        item = self.item
        self.setEnabled(item is not None)
        if item is None:
            self.id_label.setText("")
            self.title.setText("")
            self.editor.setPlainText("")
            self.preview.setMarkdown("")
            self.notes.setMarkdown("")
            self.outline.clear()
            self.dates.setText("")
            self._apply_mode()
            self._loading = False
            self._set_dirty(False)
            return
        self.id_label.setText(f"#{item['item_id']}")
        self.title.setText(item["title"])
        self.type.setCurrentText(item["type"])
        self.status.setCurrentText(item["status"])
        self.subject.setText(item["subject"])
        self.rank.setValue(item["rank"] or 0)
        closed = f"   closed {item['closed']}" if item["closed"] else ""
        deleted = "   DELETED" if item["deleted"] else ""
        self.dates.setText(f"created {item['created']}{closed}   v{item['version']} {item['changed']}{deleted}")
        self.editor.setPlainText(item["body"])
        self.preview.setMarkdown(item["expanded_body"])
        self.notes.setMarkdown("\n\n".join(note_markdown(n) for n in item["notes"]) or "*No notes yet.*")
        self.notes.moveCursor(QTextCursor.End)
        self._refresh_outline()
        self.restore_button.setVisible(bool(item["deleted"]))
        for button in (self.done_button, self.drop_button, self.delete_button):
            button.setVisible(not item["deleted"])
        self._apply_mode()
        self._loading = False
        self._set_dirty(False)

    # Show and enable what the mode allows: in view mode the rendered body and the notes, every
    # field and writing action locked in its place; in edit mode the editor instead of the rendered
    # body, the note input, and every field and action the item's state allows.
    def _apply_mode(self):
        self.editor_box.setVisible(self.editing)
        self.preview.setVisible(not self.editing)
        self.note_row.setVisible(self.editing)
        item = self.item
        editing = self.editing and item is not None
        self.title.setReadOnly(not editing)
        for widget in (self.type, self.status, self.subject, self.add_section_button, self.delete_button, self.restore_button):
            widget.setEnabled(editing)
        self.rank.setEnabled(editing and item["status"] in ("open", "doing"))
        self.done_button.setEnabled(editing and item["status"] not in CLOSED)
        self.drop_button.setEnabled(editing and item["status"] not in CLOSED)

    # Switch modes; leaving edit mode with an unsaved body asks first, and cancelling stays.
    def _toggle_mode(self, editing):
        if not editing and not self.confirm_leave():
            self.edit_toggle.blockSignals(True)
            self.edit_toggle.setChecked(True)
            self.edit_toggle.blockSignals(False)
            return
        self.editing = editing
        self._fill()

    def _refresh_outline(self):
        self.outline.clear()
        try:
            for section in self.tracker.sections(self.item["item_id"]):
                self.outline.addItem("    " * (section["level"] - 1) + section["title"])
                self.outline.item(self.outline.count() - 1).setData(Qt.UserRole, section)
        except CliError as error:
            self.error.emit(str(error))

    # --- body ---

    def _on_body_edited(self):
        if self._loading:
            return
        self._set_dirty(self.editor.toPlainText() != self.item["body"])

    def _set_dirty(self, dirty):
        self.dirty = dirty
        self.dirty_label.setVisible(dirty)
        self.save_button.setEnabled(dirty)

    def save_body(self):
        if not self.item or not self.dirty:
            return True
        return self._write(lambda: self.tracker.set(self.item["item_id"], body=self.editor.toPlainText()))

    # Ask about an unsaved body before leaving the item; False when the user cancels.
    def confirm_leave(self):
        if not self.item or not getattr(self, "dirty", False):
            return True
        answer = QMessageBox.question(self, "Unsaved body", f"Save the body of #{self.item['item_id']}?",
                                      QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self.save_body()
        self.dirty = False
        return True

    def _jump_to_section(self, entry):
        section = entry.data(Qt.UserRole)
        if not self.editing:
            self._scroll_preview_to(section)
            return
        needle = "#" * section["level"] + " " + section["title"]
        text = self.editor.toPlainText()
        position = text.find(needle)
        if position < 0:
            return
        cursor = self.editor.textCursor()
        cursor.setPosition(position)
        self.editor.setTextCursor(cursor)
        self.editor.centerCursor()
        self.editor.setFocus()

    # Scroll the rendered body so that a section's heading is at the top.
    def _scroll_preview_to(self, section):
        block = self.preview.document().begin()
        while block.isValid():
            if block.blockFormat().headingLevel() == section["level"] and block.text().strip() == section["title"]:
                self.preview.setTextCursor(QTextCursor(block))
                bar = self.preview.verticalScrollBar()
                bar.setValue(bar.value() + self.preview.cursorRect().top())
                return
            block = block.next()

    def _add_section(self):
        if not self.item or not self.confirm_leave():
            return
        existing = [self.outline.item(i).data(Qt.UserRole)["title"] for i in range(self.outline.count())]
        dialog = AddSectionDialog(self, existing)
        if dialog.exec():
            values = dialog.values()
            self._write(lambda: self.tracker.add_section(self.item["item_id"], **values))

    # --- fields, notes, actions ---

    def _set_field(self, field, value):
        if self._loading or not self.item or self.item[field] == value:
            return
        self._write(lambda: self.tracker.set(self.item["item_id"], **{field: value}))

    def _set_rank(self):
        if self._loading or not self.item or (self.item["rank"] or 0) == self.rank.value():
            return
        self._write(lambda: self.tracker.rank(self.item["item_id"], self.rank.value()))

    def add_note(self):
        text = self.note_input.toPlainText().strip()
        if not self.item or not text:
            return
        if self._write(lambda: self.tracker.note(self.item["item_id"], text)):
            self.note_input.clear()

    def _close(self, status):
        if not self.editing or not self.item or self.item["status"] in CLOSED:
            return
        note = self.note_input.toPlainText().strip()
        action = self.tracker.close if status == "done" else self.tracker.drop
        if self._write(lambda: action(self.item["item_id"], note or None)):
            self.note_input.clear()

    def _delete(self):
        if self.item and QMessageBox.question(self, "Delete", f"Delete #{self.item['item_id']}? It can be restored.") == QMessageBox.Yes:
            self._write(lambda: self.tracker.delete(self.item["item_id"]))

    def _restore(self):
        if self.item:
            self._write(lambda: self.tracker.restore(self.item["item_id"]))

    def _history(self):
        if self.item:
            HistoryDialog(self, self.tracker, self.item["item_id"]).exec()

    # Run one write, reload the item and tell the window; False (and a message) when the CLI refused.
    def _write(self, action):
        try:
            action()
        except CliError as error:
            self.error.emit(str(error))
            QMessageBox.warning(self, "Tracker", str(error))
            self._fill()
            return False
        self.dirty = False
        self.item = self.tracker.show(self.item["item_id"], deleted=True)
        self._fill()
        self.changed.emit()
        return True
