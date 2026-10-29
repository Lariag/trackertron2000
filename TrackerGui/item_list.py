"""The left pane: the items as a table with filters (search, type and status chips, subject,
open questions, closed/deleted) and two orders: by id, or the "next" order with rank moves. The search is the
CLI's (`list --search`), asked a moment after typing stops; the other filters are instant."""
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLineEdit,
                               QTableView, QToolButton, QVBoxLayout, QWidget)

from cli import STATUSES, TYPES
from theme import MUTED, STATUS_COLORS, TYPE_COLORS, color

COLUMNS = ("rank", "id", "type", "status", "subject", "title")


class ItemModel(QAbstractTableModel):
    """The rows shown, already filtered; one dict per item as the CLI's JSON gives it."""

    def __init__(self):
        super().__init__()
        self.rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return "#" if COLUMNS[section] == "id" else COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        row = self.rows[index.row()]
        column = COLUMNS[index.column()]
        if role == Qt.DisplayRole:
            if column == "rank":
                return "" if row["rank"] is None else str(row["rank"])
            if column == "id":
                return str(row["item_id"])
            return row[column]
        if role == Qt.ForegroundRole:
            if column == "type":
                return color(row["type"], TYPE_COLORS)
            if column == "status":
                return color(row["status"], STATUS_COLORS)
            if column in ("id", "rank", "subject"):
                return QColor(MUTED)
            if row["status"] in ("done", "dropped"):
                return QColor(MUTED)
        if role == Qt.TextAlignmentRole and column in ("rank", "id"):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def item_id_at(self, row_index):
        return self.rows[row_index]["item_id"] if 0 <= row_index < len(self.rows) else None


class ItemList(QWidget):
    """Filters + table. Emits `selected(item_id)` (None when nothing) and `move_requested(item_id,
    delta)` for Alt+Up/Down in the next order. Call `refresh()` after any write."""

    selected = Signal(object)
    move_requested = Signal(int, int)
    new_requested = Signal()
    export_requested = Signal()
    report_requested = Signal()

    def __init__(self, tracker):
        super().__init__()
        self.tracker = tracker
        self.all_rows = []
        # Ids of the items with an unanswered question, from the CLI.
        self.question_ids = set()
        # Ids matching the search text, from the CLI; None while the search box is empty.
        self.search_ids = None
        self.model = ItemModel()
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.search = QLineEdit(placeholderText="Search: every word must appear in title, subject, body or notes  (Ctrl+F)")
        # One CLI call once typing pauses, not one per keystroke.
        self.search_timer = QTimer(self, singleShot=True, interval=250)
        self.search_timer.timeout.connect(self._run_search)
        self.search.textChanged.connect(self.search_timer.start)
        layout.addWidget(self.search)

        chips = QHBoxLayout()
        chips.setSpacing(4)
        self.type_chips = {name: self._chip(chips, name, TYPE_COLORS[name]) for name in TYPES}
        chips.addSpacing(10)
        self.status_chips = {name: self._chip(chips, name, STATUS_COLORS[name]) for name in STATUSES}
        chips.addStretch()
        layout.addLayout(chips)

        row = QHBoxLayout()
        row.setSpacing(4)
        self.subject = QComboBox()
        self.subject.setMinimumWidth(120)
        self.subject.currentIndexChanged.connect(self.apply_filters)
        row.addWidget(self.subject)
        self.order = QToolButton(text="Next order", checkable=True, checked=True,
                                 toolTip="Doing first, then open items by rank; the rest after, by id")
        self.order.toggled.connect(self.apply_filters)
        row.addWidget(self.order)
        self.only_questions = QToolButton(text="\u2753 Questions", checkable=True,
                                          toolTip="Only the items with an unanswered question, closed ones included")
        self.only_questions.toggled.connect(self.apply_filters)
        row.addWidget(self.only_questions)
        self.show_closed = QToolButton(text="Closed", checkable=True, toolTip="Include done and dropped items")
        self.show_closed.toggled.connect(self.apply_filters)
        row.addWidget(self.show_closed)
        self.show_deleted = QToolButton(text="Deleted", checkable=True, toolTip="The deleted items instead")
        self.show_deleted.toggled.connect(self.refresh)
        row.addWidget(self.show_deleted)
        row.addStretch()
        new = QToolButton(text="+ New", toolTip="New item (Ctrl+N)")
        new.clicked.connect(self.new_requested)
        row.addWidget(new)
        export = QToolButton(text="Export", toolTip="Write every item as markdown files into a folder you pick")
        export.clicked.connect(self.export_requested)
        row.addWidget(export)
        report = QToolButton(text="Report", toolTip="The statistics: totals, completion times, questions, top lists")
        report.clicked.connect(self.report_requested)
        row.addWidget(report)
        layout.addLayout(row)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COLUMNS.index("title"), QHeaderView.Stretch)
        header.setHighlightSections(False)
        self.table.selectionModel().currentRowChanged.connect(self._on_current_changed)
        layout.addWidget(self.table, 1)

        QShortcut(QKeySequence("Alt+Up"), self.table, activated=lambda: self._move(-1))
        QShortcut(QKeySequence("Alt+Down"), self.table, activated=lambda: self._move(1))

    def _chip(self, layout, name, colour):
        chip = QToolButton(text=name, checkable=True, objectName="chip")
        chip.setStyleSheet(f"QToolButton#chip:checked {{ background: {colour}; border-color: {colour}; color: #14161a; }}")
        chip.toggled.connect(self.apply_filters)
        layout.addWidget(chip)
        return chip

    # Reload everything from the CLI, keep the selection when the item is still shown.
    def refresh(self):
        keep = self.current_id()
        self.all_rows = self.tracker.list(deleted=self.show_deleted.isChecked())
        self.question_ids = self.tracker.open_question_ids()
        subjects = sorted({row["subject"] for row in self.all_rows if row["subject"]}, key=str.casefold)
        current = self.subject.currentText()
        self.subject.blockSignals(True)
        self.subject.clear()
        self.subject.addItems(["All subjects"] + subjects)
        if current in subjects:
            self.subject.setCurrentText(current)
        self.subject.blockSignals(False)
        self._run_search()
        if keep is not None:
            self.select(keep)

    # Ask the CLI which items match the search text, then filter.
    def _run_search(self):
        query = self.search.text().strip()
        self.search_ids = self.tracker.search_ids(query, deleted=self.show_deleted.isChecked()) if query else None
        self.apply_filters()

    # Filter and order the loaded rows; the search part uses the ids the CLI last returned.
    def apply_filters(self):
        types = {name for name, chip in self.type_chips.items() if chip.isChecked()}
        statuses = {name for name, chip in self.status_chips.items() if chip.isChecked()}
        subject = self.subject.currentText() if self.subject.currentIndex() > 0 else None
        rows = []
        for row in self.all_rows:
            if types and row["type"] not in types:
                continue
            if statuses and row["status"] not in statuses:
                continue
            if self.only_questions.isChecked() and row["item_id"] not in self.question_ids:
                continue
            # An open question is worth seeing even on a closed item.
            hide_closed = not statuses and not self.show_closed.isChecked() and not self.only_questions.isChecked()
            if hide_closed and row["status"] in ("done", "dropped"):
                continue
            if subject and row["subject"] != subject:
                continue
            if self.search_ids is not None and row["item_id"] not in self.search_ids:
                continue
            rows.append(row)
        if self.order.isChecked():
            rows.sort(key=lambda r: (r["status"] != "doing", r["rank"] is None, r["rank"] or 0, r["item_id"]))
        keep = self.current_id()
        self.model.set_rows(rows)
        if keep is not None and not self.select(keep):
            self.selected.emit(None)

    def current_id(self):
        return self.model.item_id_at(self.table.currentIndex().row())

    # Select an item by id; False when it is not in the shown rows.
    def select(self, item_id):
        for index, row in enumerate(self.model.rows):
            if row["item_id"] == item_id:
                self.table.selectRow(index)
                return True
        return False

    def _on_current_changed(self, current, previous):
        self.selected.emit(self.model.item_id_at(current.row()))

    def _move(self, delta):
        item_id = self.current_id()
        if item_id is not None and self.order.isChecked():
            self.move_requested.emit(item_id, delta)

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()
