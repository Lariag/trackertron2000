"""The tracker GUI: a window over Tracker/track.py for the user. Left, the items with instant
filters; right, the selected item. Everything goes through the CLI (cli.py). A project launches it
with its tracker folder's tracker_gui.bat, which passes `--dir` (the folder; without it, the
TRACKER_DIR variable)."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QSettings, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut  # noqa: E402
from PySide6.QtWidgets import (QApplication, QFileDialog, QMainWindow, QMessageBox, QSplitter,  # noqa: E402
                               QWidget, QVBoxLayout)

from cli import CliError, Tracker  # noqa: E402
from dialogs import QuickAddDialog, ReportDialog  # noqa: E402
from item_list import ItemList  # noqa: E402
from item_view import ItemView  # noqa: E402
from theme import STYLESHEET  # noqa: E402

SHORTCUTS = "Ctrl+N new   Ctrl+F search   Ctrl+S save body   Ctrl+Enter note   Ctrl+Shift+D done   Alt+Up/Down move rank   F5 refresh"


class MainWindow(QMainWindow):

    def __init__(self, tracker):
        super().__init__()
        self.tracker = tracker
        self.setWindowTitle("Tracker")
        self.settings = QSettings("trackertron2000", "TrackerGui")

        self.items = ItemList(tracker)
        self.view = ItemView(tracker)
        self.split = QSplitter(Qt.Horizontal)
        for pane in (self.items, self.view):
            box = QWidget()
            layout = QVBoxLayout(box)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.addWidget(pane)
            self.split.addWidget(box)
        self.split.setStretchFactor(0, 2)
        self.split.setStretchFactor(1, 3)
        self.setCentralWidget(self.split)
        self.statusBar().showMessage(SHORTCUTS)

        self.items.selected.connect(self._on_selected)
        self.items.move_requested.connect(self._move_rank)
        self.items.new_requested.connect(self.new_item)
        self.items.export_requested.connect(self.export)
        self.items.report_requested.connect(lambda: ReportDialog(self, self.tracker).show())
        self.view.changed.connect(self.items.refresh)
        self.view.error.connect(lambda message: self.statusBar().showMessage(message, 6000))

        QShortcut(QKeySequence.New, self, activated=self.new_item)
        QShortcut(QKeySequence.Find, self, activated=self.items.focus_search)
        QShortcut(QKeySequence.Refresh, self, activated=self.items.refresh)

        self.restoreGeometry(self.settings.value("geometry", b""))
        self.split.restoreState(self.settings.value("split", b""))
        if not self.settings.contains("split"):
            self.split.setSizes([560, 840])
        self.items.refresh()

    def _on_selected(self, item_id):
        if not self.view.show_item(item_id, deleted=self.items.show_deleted.isChecked()):
            self.items.select(self.view.item["item_id"])  # the user cancelled leaving

    def new_item(self):
        subjects = [self.items.subject.itemText(i) for i in range(1, self.items.subject.count())]
        dialog = QuickAddDialog(self, subjects, default_type=self.view.item["type"] if self.view.item else "feature")
        if not dialog.exec():
            return
        try:
            item_id = self.tracker.add(**dialog.values())
        except CliError as error:
            QMessageBox.warning(self, "Tracker", str(error))
            return
        self.items.refresh()
        if not self.items.select(item_id):
            self.items.search.clear()
            for chip in list(self.items.type_chips.values()) + list(self.items.status_chips.values()):
                chip.setChecked(False)
            self.items.select(item_id)

    # Pick a folder, export into a new tracker_export_<timestamp> under it, offer to open it.
    def export(self):
        parent = QFileDialog.getExistingDirectory(self, "Export into...", self.settings.value("export_dir", ""))
        if not parent:
            return
        self.settings.setValue("export_dir", parent)
        try:
            folder = self.tracker.export(parent)
        except CliError as error:
            QMessageBox.warning(self, "Export", str(error))
            return
        self.statusBar().showMessage(f"Exported to {folder}", 8000)
        box = QMessageBox(QMessageBox.Information, "Export", f"Exported to\n{folder}", QMessageBox.Ok, self)
        open_button = box.addButton("Open folder", QMessageBox.ActionRole)
        box.exec()
        if box.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # Alt+Up/Down: one step in the ranked order (an unranked item enters it at the end).
    def _move_rank(self, item_id, delta):
        row = next((r for r in self.items.model.rows if r["item_id"] == item_id), None)
        if row is None or row["status"] not in ("open", "doing"):
            return
        ranked = [r for r in self.items.all_rows if r["rank"] is not None]
        position = row["rank"] if row["rank"] is not None else len(ranked) + 1
        target = max(1, position + delta)
        try:
            self.tracker.rank(item_id, target)
        except CliError as error:
            self.statusBar().showMessage(str(error), 6000)
            return
        self.items.refresh()
        self.items.select(item_id)
        self.view.reload()

    def closeEvent(self, event):
        if not self.view.confirm_leave():
            event.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("split", self.split.saveState())
        event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", help="the project's tracker folder (default: the TRACKER_DIR variable)")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow(Tracker(args.dir))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
