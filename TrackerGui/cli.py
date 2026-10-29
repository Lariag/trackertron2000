"""The bridge to the tracker CLI: every read and write the GUI makes is one `track.py` call, the
reads with `--json`. Nothing here touches the database."""
import json
import os
import subprocess
import sys

# TrackerGui/cli.py -> Tracker/track.py, in the tracker repository
TRACK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Tracker", "track.py")

TYPES = ("spec", "feature", "bug", "debt", "problem")
STATUSES = ("draft", "open", "doing", "done", "dropped")
CLOSED = ("done", "dropped")


class CliError(Exception):
    """The CLI refused: its one-line message."""


class Tracker:
    """Runs the CLI; each method is one command."""

    # `folder` is the project's tracker folder; None leaves it to the CLI (the TRACKER_DIR variable).
    def __init__(self, folder=None):
        self.folder = folder

    # Run one command and return its stdout; a non-zero exit becomes a CliError with the stderr.
    def run(self, *args, as_json=False):
        command = [sys.executable, TRACK]
        if self.folder:
            command += ["--dir", self.folder]
        if as_json:
            command.append("--json")
        command += [str(arg) for arg in args]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode != 0:
            raise CliError(result.stderr.strip().removeprefix("track: ") or "unknown error")
        return result.stdout

    def query(self, *args):
        return json.loads(self.run(*args, as_json=True))

    # --- reads ---
    def next(self, n=50):
        return self.query("next", "-n", n)

    def list(self, deleted=False):
        return self.query("list", "--deleted" if deleted else "--all")

    # The ids of the items matching a search, by the CLI's rule (same scope as `list`).
    def search_ids(self, query, deleted=False):
        rows = self.query("list", "--deleted" if deleted else "--all", "--search", query)
        return {row["item_id"] for row in rows}

    # One item; every read of it also carries the texts with their references expanded (`#12
    # «Title»`): `expanded_body` and each note's `expanded_text`, for the rendered views.
    # The ids of the live items with an unanswered question (`questions`).
    def open_question_ids(self):
        return {row["item_id"] for row in self.query("questions")}

    def show(self, item_id, version=None, deleted=False):
        args = ["show", item_id, "--expand"]
        if version is not None:
            args += ["--version", version]
        if deleted:
            args.append("--deleted")
        return self.query(*args)

    def history(self, item_id):
        return self.query("history", item_id)

    def sections(self, item_id):
        return self.query("sections", item_id)

    def subjects(self):
        return self.query("subjects")

    # The statistics (`report` is always JSON).
    def report(self):
        return json.loads(self.run("report"))

    # --- writes ---
    def add(self, type_, title, subject="", status="open", body="", rank=None):
        args = ["add", type_, title, "--status", status]
        if subject:
            args += ["--subject", subject]
        if body:
            args += ["--body", body]
        if rank:
            args += ["--rank", rank]
        return int(self.run(*args).strip().lstrip("#"))

    def set(self, item_id, **fields):
        return self.run("set", item_id, *(f"{k}={v}" for k, v in fields.items()))

    def note(self, item_id, text):
        return self.run("note", item_id, text)

    def close(self, item_id, note=None):
        return self.run("close", item_id, *([note] if note else []))

    def drop(self, item_id, note=None):
        return self.run("drop", item_id, *([note] if note else []))

    def delete(self, item_id):
        return self.run("delete", item_id)

    def restore(self, item_id):
        return self.run("restore", item_id)

    def rank(self, item_id, position):
        return self.run("rank", item_id, position)

    # Export the items as markdown files into a new folder under `parent`; returns the folder.
    def export(self, parent):
        return self.run("export", parent).strip()

    # Add a subsection at the end of the body, or at the end of section `after`.
    def add_section(self, item_id, title, level, body="", after=None):
        args = ["add-section", item_id, title, "--level", level]
        if body:
            args += ["--body", body]
        if after:
            args += ["--after", after]
        return self.run(*args)
