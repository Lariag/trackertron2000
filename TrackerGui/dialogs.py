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


class ReportDialog(QDialog):
    """The statistics of `track report` as plain text, one section after another; its own window."""

    def __init__(self, parent, tracker):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Report")
        self.resize(900, 750)
        layout = QVBoxLayout(self)
        view = QPlainTextEdit(readOnly=True, objectName="monospace")  # fixed columns: the stylesheet sets the font
        view.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(view)
        try:
            view.setPlainText(report_text(tracker.report()))
        except CliError as error:
            view.setPlainText(str(error))


# One table row: the label left-aligned, the cells right-aligned in columns of `width`.
def table_row(label, cells, width=9):
    return f"  {label:<10}" + "".join(f"{cell:>{width}}" for cell in cells)


# The units a duration is shown in, (symbol, minutes in one), largest first; below a minute, seconds.
DURATION_UNITS = (("d", 24 * 60), ("h", 60), ("m", 1))


# A duration given in minutes, in the largest unit it fills at least once, with up to one decimal: 25 m, 1.7 h, 3 d.
def duration_text(minutes):
    symbol, size = next(((symbol, size) for symbol, size in DURATION_UNITS if minutes >= size), ("s", 1 / 60))
    return f"{minutes / size:.1f}".removesuffix(".0") + " " + symbol


# A duration figure's rows (`all` then each type): count, imported, mean, median, mode, range.
def duration_rows(figure):
    lines = [table_row("", ("count", "imported", "mean", "median", "min", "max")) + "   mode"]
    for label, stats in [("all", figure["all"])] + list(figure["by_type"].items()):
        if not stats["count"]:
            lines.append(table_row(label, (0,)))
            continue
        # With no value occurring twice, every value is a mode: nothing to show.
        mode = ", ".join(duration_text(value) for value in stats["mode"]) if stats["mode_count"] > 1 else "no value repeats"
        often = "" if stats["mode_count"] == 1 else (
            f" ({stats['mode_count']} of {stats['count']})" if len(stats["mode"]) == 1 else f" ({stats['mode_count']} each)")
        lines.append(table_row(label, (stats["count"], stats["imported"])
                               + tuple(duration_text(stats[key]) for key in ("mean", "median", "min", "max")))
                     + f"   {mode}{often}")
    return lines


# The report as text: a heading per section, tables in fixed columns.
def report_text(report):
    lines = [f"Generated {report['generated']}"]
    section = lambda title: lines.extend(["", title, "-" * len(title)])

    section("IMPORT")
    found = report["import"]
    if found["detected"]:
        lines += [f"  Items brought in by the import that started the database, until {found['ended']}: {found['items']}",
                  f"  Already closed: {found['closed']} (in the totals, not in the times)",
                  f"  Open or draft: {found['open']} (their times run from the import)",
                  f"  Busiest minute of closings: {found['closings_peak']} in the import, {found['later_closings_peak']} since"]
    else:
        lines.append("  None detected")

    section("ITEMS")
    items = report["items"]
    statuses = list(items["by_status"])
    lines.append(table_row("", ["total"] + statuses))
    lines.append(table_row("all", [items["total"]] + list(items["by_status"].values())))
    for type_, counts in items["by_type"].items():
        lines.append(table_row(type_, [counts["total"]] + list(counts["by_status"].values())))
    lines.append(f"  Deleted: {items['deleted']}")

    section("COMPLETION TIMES (from first open or doing to closed)")
    for status, figure in report["completion"].items():
        lines += ["", f"  {status.capitalize()}"] + duration_rows(figure["time"])
        lines.append(f"  Not timed: {figure['imported_closed']} imported closed, {figure['recorded_closed']} recorded closed "
                     f"(closed right after being added), {figure['never_opened']} never opened")

    section("QUESTIONS")
    questions = report["questions"]
    lines.append(table_row("", ("total", "open", "answered")))
    lines.append(table_row("all", (questions["total"], questions["open"], questions["answered"])))
    for type_, counts in questions["by_type"].items():
        lines.append(table_row(type_, (counts["total"], counts["open"], counts["answered"])))
    lines.append(f"  Answered inside the import, not timed: {questions['answered_in_import']}")
    lines += ["", "  Time to answer"] + duration_rows(questions["time_to_answer"])
    lines += ["", "  Oldest open"]
    for question in questions["oldest_open"] or [None]:
        lines.append("    none" if question is None else
                     f"    note {question['note_id']:<5} #{question['item_id']:<5} {question['type']:<8} "
                     f"asked {question['asked']}  {duration_text(question['minutes']):>7} ago  {question['title']}")

    section("MOST VERSIONS")
    for item in report["most_versions"] or [None]:
        lines.append("  none" if item is None else
                     f"  {item['versions']:>4}  #{item['item_id']:<5} {item['type']:<8} {item['status']:<8} {item['title']}")

    section("DOING")
    for item in report["doing"] or [None]:
        lines.append("  none" if item is None else
                     f"  #{item['item_id']:<5} {item['type']:<8} since {item['since']}  {duration_text(item['minutes']):>7}  {item['title']}")
    return "\n".join(lines)
