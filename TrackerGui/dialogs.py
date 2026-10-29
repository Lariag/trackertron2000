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


# A table: the header cells (and `tail_header` over the tails) over rows of (label, cells, tail);
# labels left-aligned as wide as the widest, cells right-aligned in columns of `width`, tails after them.
def table(header, rows, width=9, tail_header=""):
    label_width = max([8] + [len(label) for label, _, _ in rows])
    line = lambda label, cells, tail: (f"  {label:<{label_width}}" + "".join(f"{cell:>{width}}" for cell in cells)
                                       + (f"   {tail}" if tail else "")).rstrip()
    return [line("", header, tail_header)] + [line(label, cells, tail) for label, cells, tail in rows]


# The units a duration is shown in, (symbol, minutes in one), largest first; below a minute, seconds.
DURATION_UNITS = (("d", 24 * 60), ("h", 60), ("m", 1))


# A duration given in minutes, in the largest unit it fills at least once, with up to one decimal: 25 m, 1.7 h, 3 d.
def duration_text(minutes):
    symbol, size = next(((symbol, size) for symbol, size in DURATION_UNITS if minutes >= size),
                        ("s", 1 / 60) if minutes > 0 else ("m", 1))
    return f"{minutes / size:.1f}".removesuffix(".0") + " " + symbol


# One row of a duration figure: count, imported, mean, median, min, max, then the mode.
def duration_row(label, stats):
    if not stats["count"]:
        return (label, (0,), "")
    # With no value occurring twice, every value is a mode: nothing to show.
    if stats["mode_count"] == 1:
        mode = "no value repeats"
    else:
        often = f"{stats['mode_count']} of {stats['count']}" if len(stats["mode"]) == 1 else f"{stats['mode_count']} each"
        mode = ", ".join(duration_text(value) for value in stats["mode"]) + f" ({often})"
    return (label, (stats["count"], stats["imported"]) + tuple(duration_text(stats[key]) for key in ("mean", "median", "min", "max")), mode)


# A duration figure's table: all, each type, then each subject.
def duration_table(figure):
    rows = [duration_row("all", figure["all"])] + [duration_row(type_, stats) for type_, stats in figure["by_type"].items()]
    if figure["by_subject"]:
        rows += [("by subject:", (), "")] + [duration_row(subject or "(none)", stats) for subject, stats in figure["by_subject"].items()]
    return table(("count", "imported", "mean", "median", "min", "max"), rows, tail_header="mode")


# A table of counts by status: the totals, then one row per key of `groups`.
def status_table(totals, groups):
    statuses = list(totals["by_status"])
    rows = [("all", [totals["total"]] + list(totals["by_status"].values()), "")]
    rows += [(name or "(none)", [counts["total"]] + list(counts["by_status"].values()), "") for name, counts in groups.items()]
    return table(["total"] + statuses, rows)


# An item of a list: its id, type and status, `detail`, then its title and subject.
def item_line(entry, detail):
    subject = f"  [{entry['subject']}]" if entry["subject"] else ""
    return f"  #{entry['item_id']:<5} {entry['type']:<8} {entry['status']:<8} {detail}  {entry['title']}{subject}"


# The lines of a list of items, or "none".
def item_lines(entries, detail):
    return [item_line(entry, detail(entry)) for entry in entries] or ["  none"]


# A list overall and by type (`all`, `by_type`), each under its own heading.
def typed_item_lines(lists, detail):
    lines = ["  All"] + item_lines(lists["all"], detail)
    for type_, entries in lists["by_type"].items():
        lines += ["", f"  {type_.capitalize()}"] + item_lines(entries, detail)
    return lines


# The report as text: a heading per section, tables in fixed columns, durations in readable units.
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
    lines += status_table(items, items["by_type"]) + ["", "  By subject"] + status_table(items, items["by_subject"])
    lines += ["", f"  Deleted: {items['deleted']}   Reopened after closing: {items['reopened']}",
              f"  Open or doing in the ranked list: {items['ranked']}, out of it: {items['unranked']}"]

    section("COMPLETION TIMES (from first open or doing to closed)")
    for status, figure in report["completion"].items():
        lines += ["", f"  {status.capitalize()}"] + duration_table(figure["time"])
        lines.append(f"  Not timed: {figure['imported_closed']} imported closed, {figure['recorded_closed']} recorded closed "
                     f"(closed right after being added), {figure['never_opened']} never opened")

    section("STATUS TIMES")
    steps = {"draft_to_open": "Draft to open (or doing)", "open_to_doing": "Open to doing", "doing_to_done": "Doing to done"}
    for name, step in report["status_times"].items():
        lines += ["", f"  {steps[name]}"] + duration_table(step["time"])
        lines.append(f"  Finished inside the import, not timed: {step['in_import']}")

    section("QUESTIONS")
    questions = report["questions"]
    keys = ("total", "open", "answered")
    lines += table(keys, [("all", [questions[key] for key in keys], "")]
                   + [(type_, [counts[key] for key in keys], "") for type_, counts in questions["by_type"].items()])
    lines.append(f"  Answered inside the import, not timed: {questions['answered_in_import']}")
    lines += ["", "  Time to answer"] + duration_table(questions["time_to_answer"])
    lines += ["", "  Open questions by item, oldest first"]
    lines += item_lines(questions["open_by_item"], lambda entry: f"{entry['open_questions']:>2} open, oldest note "
                        f"{entry['oldest_note_id']} asked {entry['oldest_asked']} ({duration_text(entry['minutes'])} ago)")

    section("OLDEST ITEMS NOT CLOSED (by creation; imported ones are older still)")
    lines += typed_item_lines(report["oldest_open"], lambda entry: f"created {entry['created']} "
                              f"{duration_text(entry['minutes']) + ' ago':>9}{' (imported)' if entry['imported'] else ''}")

    section("STALE ITEMS (not closed, by their last change or note)")
    lines += typed_item_lines(report["stale"], lambda entry: f"last change {entry['last_change']} {duration_text(entry['minutes']) + ' ago':>9}")

    section("MOST VERSIONS")
    lines += item_lines(report["most_versions"], lambda entry: f"{entry['versions']:>4} versions")

    section("MOST NOTES")
    lines += item_lines(report["most_notes"], lambda entry: f"{entry['notes']:>4} notes")

    section("DOING")
    lines += item_lines(report["doing"], lambda entry: f"since {entry['since']} ({duration_text(entry['minutes'])})")

    section("ACTIVITY BY DAY (not closed: drafts, open and doing at the end of the day)")
    fields = ("created", "closed", "asked", "answered", "not_closed")
    lines += table([field.replace("_", " ") for field in fields],
                   [(day["date"], [day[field] for field in fields], "") for day in report["activity"]], width=11)
    return "\n".join(lines)
