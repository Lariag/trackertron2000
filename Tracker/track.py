#!/usr/bin/env python3
"""The tracker CLI: specs, features, bugs, debt and potential problems in one SQLite database,
asked through short commands that print a few lines each. Everything a project's tracker needs
lives in its tracker folder (--dir or TRACKER_DIR); this code never writes outside it. tracker.md
is the reference; this file is the only thing that touches the database.

Nothing is ever overwritten or physically deleted: every change to an item inserts a new row in
`versions` (the latest is the item), a delete is a version flagged `deleted`, notes are append-only.
Only the rank order lives outside the versions (it is a position, not part of the document)."""
import argparse
import functools
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime

TYPES = ("spec", "feature", "bug", "debt", "problem")
STATUSES = ("draft", "open", "doing", "done", "dropped")
CLOSED = ("done", "dropped")
RANKABLE = ("open", "doing")
FIELDS = ("title", "type", "status", "subject", "rank", "body")
# The columns a version row carries; an update copies the latest row and changes some of these.
VERSIONED = ("type", "status", "subject", "title", "body", "closed", "deleted")
# What a version row says of its item, every column but the row's own id (which names no item).
VERSION_COLUMNS = ("item_id", "version", "changed") + VERSIONED

# Tools/Tracker/track.py: the project root is three levels up.
# The environment variable that names the tracker folder when --dir is not given.
DIR_VARIABLE = "TRACKER_DIR"
# The database's file inside the tracker folder; the dump and the sections file are named after it.
DB_NAME = "tracker.db"
# The tracker repository (Tracker/track.py: two levels up) and the templates `init` copies from it.
TOOL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(TOOL_ROOT, "Templates")
# The languages a tracker folder can be made in: its starting sections are Templates/sections.<language>.json.
LANGUAGES = ("en", "es")
# The files `init` copies into a tracker folder as they are: the launchers, the .gitignore and the
# project's log of the tracker's problems.
TEMPLATE_FILES = (".gitignore", "find-tracker.bat", "track.bat", "track.init.bat", "tracker_gui.bat", "known-issues.md")
# The project's configuration (its language), and the local file that says where the tracker
# repository is on this machine (read by find-tracker.bat).
CONFIG_NAME = "tracker.json"
TOOL_PATH_NAME = "tool-path.txt"
# The reference: how the tracker works and how to use it, printed by `guide`.
GUIDE = os.path.join(TOOL_ROOT, "tracker.md")

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id),
    version INTEGER NOT NULL,
    changed TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    closed TEXT,
    deleted INTEGER NOT NULL DEFAULT 0,
    UNIQUE (item_id, version)
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id),
    date TEXT NOT NULL,
    text TEXT NOT NULL
);
-- A note that is a question: open until a note answers it.
CREATE TABLE IF NOT EXISTS questions (
    note_id INTEGER PRIMARY KEY REFERENCES notes(id)
);
-- The note that answers a question note: a question has one answer, and one note can answer
-- several questions.
CREATE TABLE IF NOT EXISTS answers (
    question_id INTEGER PRIMARY KEY REFERENCES notes(id),
    note_id INTEGER NOT NULL REFERENCES notes(id)
);
CREATE TABLE IF NOT EXISTS ranks (
    item_id INTEGER PRIMARY KEY REFERENCES items(id),
    rank INTEGER NOT NULL
);
"""

# The latest version of every item, deleted or not, with its creation date and rank. Its columns are named: the
# version row's own id is not one of them, so no item row carries an `id` that is not the item's.
LATEST_VIEW = (
    "CREATE VIEW latest AS\n"
    f"    SELECT {', '.join('v.' + column for column in VERSION_COLUMNS)}, i.created, r.rank\n"
    "    FROM versions v\n"
    "    JOIN items i ON i.id = v.item_id\n"
    "    LEFT JOIN ranks r ON r.item_id = v.item_id\n"
    "    WHERE v.version = (SELECT MAX(version) FROM versions WHERE item_id = v.item_id)")


class TrackError(Exception):
    """A user-facing error: one line on stderr, exit code 1."""


# Dump path next to the database: the text copy that shows every change in git.
def dump_path(db_path):
    base, _ = os.path.splitext(db_path)
    return base + ".dump.sql"


# Open the database, rebuilding it from the dump when the db is missing and creating the schema
# when there is nothing at all.
def connect(db_path):
    fresh = not os.path.exists(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if fresh and os.path.exists(dump_path(db_path)):
        with open(dump_path(db_path), encoding="utf-8") as f:
            conn.executescript(f.read())
    conn.executescript(SCHEMA)
    ensure_latest_view(conn)
    return conn


# Create the `latest` view, or replace one of another definition (a database made when it was `v.*`, which put the
# version row's id in every item row); a current one is left alone, so a reading command writes nothing.
def ensure_latest_view(conn):
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'view' AND name = 'latest'").fetchone()
    if row is None or row["sql"] != LATEST_VIEW:
        conn.executescript(f"DROP VIEW IF EXISTS latest;\n{LATEST_VIEW};")


# How many times the dump is tried before giving up, and the wait between tries: a dump briefly
# locked by another program (an antivirus, the search indexer, the GUI reading it) frees up soon.
DUMP_ATTEMPTS = 5
DUMP_RETRY_SECONDS = 0.2


# Write `text` to `path` all at once: into a temporary file next to it, then swapped in, so the
# file is always either the old one or the new one, never half written. The temporary file never
# outlives a failure.
def write_atomically(path, text):
    fd, temp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)),
                                prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(temp, path)
    except OSError:
        if os.path.exists(temp):
            os.remove(temp)
        raise


# Rewrite the SQL dump after every change, so git history shows the ledger as text. Retried a few
# times; the last error is raised when every try failed.
def write_dump(conn, db_path):
    text = "".join(line + "\n" for line in conn.iterdump())
    for attempt in range(DUMP_ATTEMPTS):
        try:
            write_atomically(dump_path(db_path), text)
            return
        except OSError:
            if attempt == DUMP_ATTEMPTS - 1:
                raise
            time.sleep(DUMP_RETRY_SECONDS)


def today():
    return datetime.now().strftime("%Y-%m-%d")


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# The latest version of an item; deleted ones only when asked for.
def get_item(conn, item_id, include_deleted=False):
    row = conn.execute("SELECT * FROM latest WHERE item_id = ?", (item_id,)).fetchone()
    if row is None or (row["deleted"] and not include_deleted):
        raise TrackError(f"no item #{item_id}")
    return row


# Append a new version of an item: the latest row with `changes` applied.
def new_version(conn, item_id, changes):
    row = get_item(conn, item_id, include_deleted=True)
    values = {column: row[column] for column in VERSIONED}
    values.update(changes)
    if "body" in changes or "type" in changes:
        check_template(values["type"], values["body"])
    columns = ", ".join(VERSIONED)
    marks = ", ".join("?" for _ in VERSIONED)
    conn.execute(
        f"INSERT INTO versions (item_id, version, changed, {columns}) VALUES (?, ?, ?, {marks})",
        (item_id, row["version"] + 1, now(), *(values[column] for column in VERSIONED)))
    if "body" in changes:
        warn_references(conn, changes["body"], "body")


# An item id as the CLI receives it: bare (`42`) or as `add` prints it and a reference writes it
# (`#42`), so the output of one command is the input of the next.
ITEM_ID = re.compile(r"#?(\d+)")


# The argparse type of a list of note ids: `139` or `139,140`, without repeats.
def note_ids(text):
    parts = [part.strip() for part in text.split(",")]
    if not all(part.isdigit() for part in parts):
        raise argparse.ArgumentTypeError(f"invalid note ids '{text}' (expected 139 or 139,140)")
    return list(dict.fromkeys(int(part) for part in parts))


# The argparse type of every id argument: `42` or `#42` to 42, anything else refused.
def item_id(text):
    match = ITEM_ID.fullmatch(text.strip())
    if not match:
        raise argparse.ArgumentTypeError(f"invalid item id '{text}' (expected 42 or #42)")
    return int(match.group(1))


def check_type(value):
    if value not in TYPES:
        raise TrackError(f"unknown type '{value}' (one of {', '.join(TYPES)})")
    return value


def check_status(value):
    if value not in STATUSES:
        raise TrackError(f"unknown status '{value}' (one of {', '.join(STATUSES)})")
    return value


# The subject column's width for a set of rows: at least 12, and always wide enough to leave two
# spaces between the longest subject and the title, so a subject with spaces never runs into it.
def subject_width(rows):
    return max([12] + [len(row["subject"]) + 1 for row in rows])


# One item, one line: id, type, status, subject, title.
def format_line(row, prefix="", width=12):
    return (f"{prefix}#{row['item_id']:<4} {row['type']:<8} {row['status']:<7} "
            f"{row['subject']:<{width}} {row['title']}")


# Every note of every item joined into one text per item: {item_id: text}.
def notes_texts(conn):
    rows = conn.execute("SELECT item_id, group_concat(text, char(10)) AS notes_text FROM notes GROUP BY item_id").fetchall()
    return {row["item_id"]: row["notes_text"] for row in rows}


# The search rule, shared by the CLI and the GUI (which asks the CLI): every word of the query must
# appear, in any order and ignoring case, in the item's title, subject, body or notes.
def matches_search(row, notes_text, query):
    haystack = f"{row['title']} {row['subject']} {row['body']} {notes_text}".casefold()
    return all(word in haystack for word in query.casefold().split())


# An item reference is `#<digits>` not glued to a word or to another `#` (so `## Heading` and `C#1`
# are not references).
REFERENCE = re.compile(r"(?<![\w#&])#(\d+)\b")


# The ids a body mentions, in order of first appearance, without repeats.
def mentioned_ids(body):
    return list(dict.fromkeys(int(match) for match in REFERENCE.findall(body or "")))


# A warning on stderr: the command still succeeds.
def warn(text):
    print(f"track: warning: {text}", file=sys.stderr)


# Where an item mentions each id: {id: ["body"], ["notes"] or both}, in order of first mention.
def reference_places(row, notes_text):
    places = {}
    for place, text in (("body", row["body"]), ("notes", notes_text)):
        for item_id in mentioned_ids(text):
            places.setdefault(item_id, []).append(place)
    return places


# The references of a text with the fixed section each one sits in (None outside them, as in a
# note), in order, without repeats inside a section.
def located_references(text):
    lines, sections = parse_sections(text)
    top = [section for section in sections if section["level"] <= SECTION_LEVEL]
    found = []
    for index, line in enumerate(lines):
        # The section of a line is the last fixed section whose heading comes before it.
        section = next((s["title"] for s in reversed(top) if s["heading"] <= index), None)
        for item_id in mentioned_ids(line):
            if (section, item_id) not in found:
                found.append((section, item_id))
    return found


# What is wrong with each reference of a text, as (section, id, problem, about_section): a
# reference must be a live item, and one in the Specs section must be a spec (`about_section`
# says the problem comes from the section the reference sits in).
def reference_problems(conn, text):
    problems = []
    for section, item_id in located_references(text):
        row = conn.execute("SELECT type, deleted FROM latest WHERE item_id = ?", (item_id,)).fetchone()
        if row is None:
            problems.append((section, item_id, "does not exist", False))
        elif row["deleted"]:
            problems.append((section, item_id, "is deleted", False))
        elif section is not None and section == specs_section() and row["type"] != "spec":
            problems.append((section, item_id, f"is a {row['type']}, not a spec", True))
    return problems


# A text with each reference followed by what it names, `#12 «Title»`, `#12 (deleted)` or
# `#12 (missing)`, so a reader sees the item without looking it up. The title goes in «» so that a
# reference already in parentheses does not nest them.
def expand_references(conn, text):
    def expanded(match):
        row = conn.execute("SELECT title, deleted FROM latest WHERE item_id = ?", (int(match.group(1)),)).fetchone()
        if row is None or row["deleted"]:
            return f"{match.group(0)} ({'missing' if row is None else 'deleted'})"
        return f"{match.group(0)} «{row['title']}»"
    return REFERENCE.sub(expanded, text or "")


# A warning for each wrong reference in a text being written (`what`: "body" or "note").
def warn_references(conn, text, what):
    for section, item_id, problem, about_section in reference_problems(conn, text):
        where = f" in {section}" if about_section else ""
        warn(f"the {what} mentions #{item_id}{where}, which {problem}")


# With --json, print `data` (rows become dicts) as JSON instead of lines; tells the caller so.
def emit_json(args, data):
    if not args.json:
        return False
    if isinstance(data, list):
        data = [dict(row) if isinstance(row, sqlite3.Row) else row for row in data]
    elif isinstance(data, sqlite3.Row):
        data = dict(data)
    print(json.dumps(data, ensure_ascii=False))
    return True


# Give the ranked open/doing items consecutive ranks 1..k in their current order, dropping the
# rank of anything that can no longer hold one (closed, deleted).
def renumber(conn):
    conn.execute(
        "DELETE FROM ranks WHERE item_id NOT IN "
        "(SELECT item_id FROM latest WHERE deleted = 0 AND status IN (?, ?))", RANKABLE)
    rows = conn.execute("SELECT item_id FROM ranks ORDER BY rank, item_id").fetchall()
    for position, row in enumerate(rows, start=1):
        conn.execute("UPDATE ranks SET rank = ? WHERE item_id = ?", (position, row["item_id"]))


# Put the item at position `position` of the ranked list (0 = out of the list), shifting the rest.
def set_rank(conn, item_id, position):
    row = get_item(conn, item_id)
    if position < 0:
        raise TrackError("rank must be 0 (backlog) or a position from 1")
    conn.execute("DELETE FROM ranks WHERE item_id = ?", (item_id,))
    renumber(conn)
    if position == 0:
        return
    if row["status"] not in RANKABLE:
        raise TrackError(f"#{item_id} is {row['status']}; only open/doing items can be ranked")
    # Shift everything at or after the target position, then drop it in.
    conn.execute("UPDATE ranks SET rank = rank + 1 WHERE rank >= ?", (position,))
    conn.execute("INSERT INTO ranks (item_id, rank) VALUES (?, ?)", (item_id, position))
    renumber(conn)


# Move an item to done/dropped: closed date set, rank cleared, optional final note; warns when
# questions are left unanswered.
def close_item(conn, item_id, status, final_note):
    get_item(conn, item_id)
    new_version(conn, item_id, {"status": status, "closed": today()})
    renumber(conn)
    if final_note:
        add_note(conn, item_id, final_note)
    still_open = [f"note {row['note_id']}" for row in open_questions(conn, item_id)]
    if still_open:
        count = "an open question" if len(still_open) == 1 else f"{len(still_open)} open questions"
        warn(f"#{item_id} is closed with {count}: {', '.join(still_open)}")


# Append a note and return its id; its references are checked like a body's, as a warning.
def add_note(conn, item_id, text):
    cur = conn.execute("INSERT INTO notes (item_id, date, text) VALUES (?, ?, ?)", (item_id, now(), text))
    warn_references(conn, text, "note")
    return cur.lastrowid


# A note's text from the command line, a file or stdin; never empty.
def note_text(args):
    text = read_text(args.text, args.file)
    if not text:
        raise TrackError("empty note")
    return text


# An item's notes, oldest first, as dicts saying whether each is a question (`question`), which
# note answers it (`answered_by`) and which questions it answers (`answers`, a list).
def item_notes(conn, item_id):
    rows = conn.execute(
        "SELECT n.*, q.note_id IS NOT NULL AS question, a.note_id AS answered_by, "
        "(SELECT group_concat(b.question_id) FROM answers b WHERE b.note_id = n.id) AS answers "
        "FROM notes n LEFT JOIN questions q ON q.note_id = n.id LEFT JOIN answers a ON a.question_id = n.id "
        "WHERE n.item_id = ? ORDER BY n.id", (item_id,)).fetchall()
    return [dict(row, answers=sorted(int(i) for i in row["answers"].split(",")) if row["answers"] else [])
            for row in rows]


# The mark a question or an answer carries when a note is printed; nothing for a plain note.
def note_label(note):
    if note["question"]:
        state = f"answered in {note['answered_by']}" if note["answered_by"] else "open"
        return f" [question {note['id']}, {state}]"
    if note["answers"]:
        return f" [answer {note['id']} to {', '.join(str(i) for i in note['answers'])}]"
    return ""


# The unanswered questions of the live items (of one item, when given), oldest first, each with
# its item's fields.
def open_questions(conn, item_id=None):
    sql = ("SELECT l.*, n.id AS note_id, n.date AS asked, n.text FROM notes n "
           "JOIN questions q ON q.note_id = n.id JOIN latest l ON l.item_id = n.item_id "
           "WHERE l.deleted = 0 AND n.id NOT IN (SELECT question_id FROM answers)")
    params = ()
    if item_id is not None:
        sql, params = sql + " AND n.item_id = ?", (item_id,)
    return conn.execute(sql + " ORDER BY n.id", params).fetchall()


# Every line break as `\n`, wherever the text came from (Windows `\r\n`, old Mac `\r`).
def normalize_newlines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


# The name that means "standard input" wherever a text or a text's file is expected.
STDIN = "-"


# Whether a text given inline (`text`) or by file (`path`) comes from stdin: a file `-`, or an
# inline text that is exactly `-` (never meant literally, so it must not be stored as one).
def reads_stdin(text, path):
    return path == STDIN or (path is None and text == STDIN)


# A body/note from the command line, from a file (`path`), or from stdin when either is `-`, so
# multi-line text needs no temporary file. Line breaks normalized; text from a file or stdin also
# loses its trailing ones. Empty stdin is refused: it means the pipe failed, and storing it would
# silently empty the text.
def read_text(text, path):
    if reads_stdin(text, path):
        text = sys.stdin.read()
        if not text.strip():
            raise TrackError("empty stdin: nothing was written")
        path = STDIN
    elif path:
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
    return normalize_newlines(text or "").rstrip("\n") if path else normalize_newlines(text or "")


# Refuse a write when the item changed since the caller read it (`--if-version N`), so an edit
# made meanwhile (in the GUI, say) is never overwritten unseen.
def check_version(row, expected):
    if expected is not None and row["version"] != expected:
        raise TrackError(f"#{row['item_id']} is at v{row['version']}, not v{expected}: read it again")


# --- body sections: the markdown headings of a body ------------------------------------------

# A heading line split into (level, title); None for any other line.
def parse_heading(line):
    stripped = line.lstrip("#")
    level = len(line) - len(stripped)
    if 0 < level <= 6 and (stripped == "" or stripped[0] in " \t"):
        return level, stripped.strip()
    return None


# A title as the user typed it, with or without its `#`s, reduced to what is compared.
def normalize_title(title):
    heading = parse_heading(title.strip())
    return (heading[1] if heading else title.strip()).casefold()


# The sections of a body as dicts: level, title, heading line index, and the [start, end) line
# range of the content, which runs to the next heading of the same or a higher level (so a
# section's subsections are part of its content).
def parse_sections(body):
    lines = body.split("\n") if body else []
    sections = []
    for index, line in enumerate(lines):
        heading = parse_heading(line)
        if heading:
            sections.append({"level": heading[0], "title": heading[1], "heading": index,
                             "start": index + 1, "end": len(lines)})
    for position, section in enumerate(sections):
        for later in sections[position + 1:]:
            if later["level"] <= section["level"]:
                section["end"] = later["heading"]
                break
    return lines, sections


# The first section whose title matches, `#`s and case ignored; an error when there is none.
def find_section(sections, title):
    wanted = normalize_title(title)
    for section in sections:
        if section["title"].casefold() == wanted:
            return section
    raise TrackError(f"no section '{title}'")


# The content lines of a section, without the heading and without surrounding blank lines.
def section_content(lines, section):
    content = lines[section["start"]:section["end"]]
    while content and content[-1].strip() == "":
        content.pop()
    while content and content[0].strip() == "":
        content.pop(0)
    return content


# The body with one section's content replaced (heading kept); the new text stands alone with a
# blank line after it when another section follows.
def replace_section(lines, section, text):
    new_lines = text.split("\n") if text else []
    if section["end"] < len(lines):
        new_lines.append("")
    return "\n".join(lines[:section["start"]] + new_lines + lines[section["end"]:])


# The body with a section inserted at line `at`: `#`s to the level, the title, the content.
def insert_section(lines, at, level, title, text):
    new_lines = ["#" * level + " " + title] + (text.split("\n") if text else [])
    if at < len(lines):
        new_lines.append("")
    if at > 0 and lines[at - 1].strip() != "":
        new_lines.insert(0, "")
    return "\n".join(lines[:at] + new_lines + lines[at:])


# --- fixed sections: every type's body is the same sections, in the same order ----------------

# The heading level of the fixed sections; a deeper heading is a free subsection.
SECTION_LEVEL = 2
# The sections file of the database in use, set when the command starts (see `sections_path`).
SECTIONS_FILE = None


# The sections file next to the database: the sections of each type's body, in order, and the
# section whose references must be specs. They belong to the project (their titles are in its
# language), not to the tracker. A body has exactly its type's sections as its top-level sections
# (`##`), and nothing else before or at their level; only subsections (`###` and deeper) are free.
def sections_path(db_path):
    base, _ = os.path.splitext(db_path)
    return base + ".sections.json"


# The project's sections, read once and only when something needs them: {type: titles} and the
# Specs section's title (None when the project has none). A missing or broken file is an error.
@functools.lru_cache(maxsize=None)
def project_sections(path):
    if not os.path.exists(path):
        raise TrackError(f"no sections file {path}: it lists each type's sections (see Tracker.md)")
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
        sections, specs = config["sections"], config["specs_section"]
        # Every type with at least one title, every title a non-empty text and none repeated.
        valid = (set(sections) == set(TYPES)
                 and all(titles and all(isinstance(t, str) and t.strip() for t in titles)
                         and len(set(titles)) == len(titles) for titles in sections.values())
                 and (specs is None or isinstance(specs, str)))
        if not valid:
            raise ValueError(f"expected every type ({', '.join(TYPES)}) with its titles, and specs_section")
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise TrackError(f"bad sections file {path}: {error}")
    return {type_: tuple(titles) for type_, titles in sections.items()}, specs


# The fixed sections of a type, in order.
def type_sections(type_):
    return project_sections(SECTIONS_FILE)[0][type_]


# The section whose references must all be specs (what an item implements or is about), or None.
def specs_section():
    return project_sections(SECTIONS_FILE)[1]


# The body of a new item with no text: its type's sections, empty.
def template_body(type_):
    return "\n\n".join("#" * SECTION_LEVEL + " " + title for title in type_sections(type_))


# Why a body does not follow its type's sections, or None when it does.
def template_problem(type_, body):
    lines, sections = parse_sections(body)
    top = [section for section in sections if section["level"] <= SECTION_LEVEL]
    # Anything but blank lines before the first fixed section (text, a subsection) is outside them.
    first = top[0]["heading"] if top else len(lines)
    if any(line.strip() for line in lines[:first]):
        return "text before the first section"
    expected = ["#" * SECTION_LEVEL + " " + title for title in type_sections(type_)]
    found = ["#" * section["level"] + " " + section["title"] for section in top]
    if found != expected:
        return f"expected: {', '.join(expected)}; found: {', '.join(found) or 'no sections'}"
    return None


# Refuse a body that does not follow its type's sections.
def check_template(type_, body):
    problem = template_problem(type_, body)
    if problem:
        raise TrackError(f"the body does not follow the {type_} sections ({problem})")


# A section title as the user typed it, as the sections spell it; an error when no type has it.
def fixed_title(title):
    wanted = normalize_title(title)
    for titles in project_sections(SECTIONS_FILE)[0].values():
        for fixed in titles:
            if fixed.casefold() == wanted:
                return fixed
    raise TrackError(f"no type has a section '{title}'")


# One section of an item as text, or None when the item has no such section (its type has not,
# or its body is an old one that does not follow the sections).
def item_section(row, title):
    if title not in type_sections(row["type"]):
        return None
    lines, sections = parse_sections(row["body"])
    for section in sections:
        if section["level"] == SECTION_LEVEL and section["title"] == title:
            return "\n".join(section_content(lines, section))
    return None


# Print rows one line each, each followed by the content of section `title` when one is asked
# (with a blank line between items), or the rows with that section as JSON.
def print_rows(args, rows, prefix=lambda row: ""):
    title = fixed_title(args.section) if args.section else None
    if args.json:
        extra = (lambda row: {"section": item_section(row, title)}) if title else (lambda row: {})
        emit_json(args, [dict(row, **extra(row)) for row in rows])
        return
    width = subject_width(rows)
    for position, row in enumerate(rows):
        if title and position > 0:
            print()
        print(format_line(row, prefix(row), width))
        if not title:
            continue
        content = item_section(row, title)
        if title not in type_sections(row["type"]):
            print(f"(a {row['type']} has no section '{title}')")
        elif content is None:
            print(f"(no section '{title}')")
        elif content:
            print(content)


# --- commands ---------------------------------------------------------------------------------

def cmd_next(conn, args):
    rows = conn.execute(
        "SELECT * FROM latest WHERE deleted = 0 AND "
        "(status = 'doing' OR (status = 'open' AND rank IS NOT NULL)) "
        "ORDER BY status = 'doing' DESC, rank IS NULL, rank, item_id LIMIT ?", (args.n,)).fetchall()
    print_rows(args, rows, lambda row: f"{row['rank']:>2}. " if row["rank"] is not None else " -. ")
    return False


def cmd_list(conn, args):
    where, params = ["deleted = ?"], [1 if args.deleted else 0]
    if args.type:
        where.append("type = ?")
        params.append(check_type(args.type))
    if args.status:
        where.append("status = ?")
        params.append(check_status(args.status))
    elif not args.all:
        where.append("status NOT IN ('done', 'dropped')")
    if args.subject:
        where.append("subject = ? COLLATE NOCASE")
        params.append(args.subject)
    sql = "SELECT * FROM latest WHERE " + " AND ".join(where) + " ORDER BY item_id"
    rows = conn.execute(sql, params).fetchall()
    notes = notes_texts(conn)
    if args.search:
        rows = [row for row in rows if matches_search(row, notes.get(row["item_id"], ""), args.search)]
    if args.mentions is not None:
        rows = [row for row in rows if args.mentions in mentioned_ids(row["body"])]
    if args.json:
        # The notes' text rides along so a client can read it without one `show` per item.
        rows = [dict(row, notes_text=notes.get(row["item_id"], "")) for row in rows]
    print_rows(args, rows)
    return False


def cmd_show(conn, args):
    row = get_item(conn, args.id, include_deleted=args.deleted)
    if args.version is not None:
        old = conn.execute(
            f"SELECT {', '.join('v.' + column for column in VERSION_COLUMNS)}, i.created, NULL AS rank "
            "FROM versions v JOIN items i ON i.id = v.item_id "
            "WHERE v.item_id = ? AND v.version = ?", (args.id, args.version)).fetchone()
        if old is None:
            raise TrackError(f"#{args.id} has no version {args.version}")
        row = old
    notes = [dict(note) for note in item_notes(conn, args.id)]
    if args.expand:
        # Text output shows the expanded texts; JSON adds them beside the raw ones, which an editor needs.
        expanded_body = expand_references(conn, row["body"])
        for note in notes:
            note["expanded_text"] = expand_references(conn, note["text"])
        if args.json:
            row = dict(row, expanded_body=expanded_body)
        else:
            row = dict(row, body=expanded_body)
            notes = [dict(note, text=note["expanded_text"]) for note in notes]
    if emit_json(args, dict(row, notes=notes)):
        return False
    rank = f"  rank {row['rank']}" if row["rank"] is not None else ""
    closed = f"  closed {row['closed']}" if row["closed"] else ""
    deleted = "  DELETED" if row["deleted"] else ""
    print(f"#{row['item_id']} {row['type']} {row['status']}{rank}  [{row['subject']}]  {row['title']}{deleted}")
    print(f"created {row['created']}{closed}  v{row['version']} {row['changed']}")
    if row["body"]:
        print()
        print(row["body"])
    if notes:
        print()
        for note in notes:
            print(f"- {note['date']}{note_label(note)}: {note['text']}")
    return False


def cmd_history(conn, args):
    get_item(conn, args.id, include_deleted=True)
    rows = conn.execute(
        f"SELECT {', '.join(VERSION_COLUMNS)} FROM versions WHERE item_id = ? ORDER BY version", (args.id,)).fetchall()
    if emit_json(args, rows):
        return False
    width = subject_width(rows)
    for row in rows:
        deleted = "  DELETED" if row["deleted"] else ""
        print(f"v{row['version']:<3} {row['changed']}  {row['type']:<8} {row['status']:<7} "
              f"{row['subject']:<{width}} {row['title']}{deleted}")
    return False


# Both directions of an item's references: the items its body and notes mention, and the items
# whose body or notes mention it, each saying where (`in`). A mentioned id that is not a live item
# is listed as missing or deleted.
def cmd_refs(conn, args):
    if args.check:
        return check_references(conn, args)
    if args.id is None:
        raise TrackError("refs needs an id or --check")
    row = get_item(conn, args.id)
    notes = notes_texts(conn)
    mentions, missing = [], []
    for item_id, places in reference_places(row, notes.get(args.id, "")).items():
        target = conn.execute("SELECT * FROM latest WHERE item_id = ?", (item_id,)).fetchone()
        if target is None or target["deleted"]:
            missing.append({"item_id": item_id, "state": "missing" if target is None else "deleted", "in": places})
        else:
            mentions.append(dict(target, **{"in": places}))
    others = conn.execute("SELECT * FROM latest WHERE deleted = 0 AND item_id != ? ORDER BY item_id", (args.id,)).fetchall()
    mentioned_by = []
    for other in others:
        places = reference_places(other, notes.get(other["item_id"], "")).get(args.id)
        if places:
            mentioned_by.append(dict(other, **{"in": places}))
    if args.type:
        check_type(args.type)
        mentions = [r for r in mentions if r["type"] == args.type]
        mentioned_by = [r for r in mentioned_by if r["type"] == args.type]
    if emit_json(args, {"mentions": mentions, "missing": missing, "mentioned_by": mentioned_by}):
        return False
    # Only a reference that is not in the body says where it is: the body is the usual place.
    in_notes = lambda places: "" if "body" in places else "  (in notes)"
    width = subject_width(mentions + mentioned_by)
    print(f"#{args.id} mentions:")
    for target in mentions:
        print(format_line(target, "  ", width) + in_notes(target["in"]))
    for target in missing:
        where = "" if "body" in target["in"] else ", in notes"
        print(f"  #{target['item_id']:<4} ({target['state']}{where})")
    print(f"#{args.id} is mentioned by:")
    for other in mentioned_by:
        print(format_line(other, "  ", width) + in_notes(other["in"]))
    return False


# Every wrong reference in the bodies of the live items: missing, deleted, or not a spec in the
# Specs section. The notes are history and are never checked: a note that names an item deleted
# afterwards is not wrong.
def check_references(conn, args):
    rows = conn.execute("SELECT * FROM latest WHERE deleted = 0 ORDER BY item_id").fetchall()
    found = [(row, reference_problems(conn, row["body"])) for row in rows]
    found = [(row, problems) for row, problems in found if problems]
    if emit_json(args, [{"item_id": row["item_id"], "section": section, "ref": item_id, "problem": problem}
                        for row, problems in found for section, item_id, problem, _ in problems]):
        return False
    width = subject_width([row for row, _ in found])
    for row, problems in found:
        print(format_line(row, width=width))
        for section, item_id, problem, _ in problems:
            print(f"  {section or 'body'}: #{item_id} {problem}")
    return False


def cmd_add(conn, args):
    check_type(args.type)
    status = check_status(args.status)
    if status in CLOSED:
        raise TrackError("a new item cannot be done or dropped")
    body = read_text(args.body, args.body_file) or template_body(args.type)
    check_template(args.type, body)
    cur = conn.execute("INSERT INTO items (created) VALUES (?)", (today(),))
    item_id = cur.lastrowid
    conn.execute(
        "INSERT INTO versions (item_id, version, changed, type, status, subject, title, body) "
        "VALUES (?, 1, ?, ?, ?, ?, ?, ?)",
        (item_id, now(), args.type, status, args.subject or "", args.title, body))
    if args.rank:
        set_rank(conn, item_id, args.rank)
    warn_references(conn, body, "body")
    print(f"#{item_id}")
    return True


def cmd_sections(conn, args):
    if args.check:
        return check_sections(conn, args)
    if args.id is None:
        raise TrackError("sections needs an id or --check")
    _, sections = parse_sections(get_item(conn, args.id)["body"])
    if emit_json(args, [{"level": s["level"], "title": s["title"]} for s in sections]):
        return False
    for section in sections:
        print("#" * section["level"] + " " + section["title"])
    return False


# Every live item whose body does not follow its type's sections, with why; nothing when all do.
def check_sections(conn, args):
    rows = conn.execute("SELECT * FROM latest WHERE deleted = 0 ORDER BY item_id").fetchall()
    found = [(row, template_problem(row["type"], row["body"])) for row in rows]
    found = [(row, problem) for row, problem in found if problem]
    if emit_json(args, [{"item_id": row["item_id"], "type": row["type"], "title": row["title"],
                         "problem": problem} for row, problem in found]):
        return False
    width = subject_width([row for row, _ in found])
    for row, problem in found:
        print(format_line(row, width=width))
        print(f"  {problem}")
    return False


def cmd_section(conn, args):
    row = get_item(conn, args.id)
    lines, sections = parse_sections(row["body"])
    section = find_section(sections, args.title)
    if args.set is None and args.set_file is None:
        content = section_content(lines, section)
        if not emit_json(args, "\n".join(content)):
            for line in content:
                print(line)
        return False
    check_version(row, args.if_version)
    new_version(conn, args.id, {"body": replace_section(lines, section, read_text(args.set, args.set_file))})
    return True


def cmd_add_section(conn, args):
    row = get_item(conn, args.id)
    check_version(row, args.if_version)
    lines, sections = parse_sections(row["body"])
    heading = parse_heading(args.title.strip())
    level, title = heading if heading else (args.level, args.title.strip())
    if not title:
        raise TrackError("empty section title")
    if level <= SECTION_LEVEL:
        raise TrackError(f"only subsections ({'#' * (SECTION_LEVEL + 1)} or deeper) can be added: "
                         f"the sections of a {row['type']} are fixed")
    if any(section["title"].casefold() == title.casefold() for section in sections):
        raise TrackError(f"section '{title}' already exists")
    if args.after:
        at = find_section(sections, args.after)["end"]
    else:
        at = len(lines)
    body = insert_section(lines, at, level, title, read_text(args.body, args.body_file))
    new_version(conn, args.id, {"body": body})
    return True


# Replace one exact piece of an item's body (optionally only inside one section). It must appear
# exactly once there: zero or several matches change nothing, so a short text that happens to
# repeat elsewhere is never replaced by accident.
def cmd_replace(conn, args):
    row = get_item(conn, args.id)
    check_version(row, args.if_version)
    if reads_stdin(args.old, args.old_file) and reads_stdin(args.new, args.new_file):
        raise TrackError("only one of the texts can read stdin (old or new, inline or by file)")
    old = read_text(args.old, args.old_file)
    new = read_text(args.new, args.new_file)
    if not old:
        raise TrackError("empty text to replace")
    body = row["body"] or ""
    start, end, where = 0, len(body), ""
    if args.section:
        lines, sections = parse_sections(body)
        section = find_section(sections, args.section)
        # Character offsets of the section's content lines (heading excluded).
        end = len("\n".join(lines[:section["end"]]))
        start = min(len("\n".join(lines[:section["start"]])) + 1, end)
        where = f" in section '{section['title']}'"
    count = body[start:end].count(old)
    if count != 1:
        found = "not found" if count == 0 else f"found {count} times"
        raise TrackError(f"text {found}{where} in #{args.id}; it must appear exactly once (add context)")
    position = body.index(old, start, end)
    new_version(conn, args.id, {"body": body[:position] + new + body[position + len(old):]})
    print(f"#{args.id} v{row['version'] + 1}")
    return True


def cmd_note(conn, args):
    get_item(conn, args.id)
    add_note(conn, args.id, note_text(args))
    return True


def is_question(conn, note_id):
    return conn.execute("SELECT 1 FROM questions WHERE note_id = ?", (note_id,)).fetchone() is not None


# An existing note of an item, as `ask --note` and `answer --note` mark it; an error when the note
# does not exist or belongs to another item.
def existing_note(conn, note_id, item_id):
    note = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if note is None:
        raise TrackError(f"no note {note_id}")
    if note["item_id"] != item_id:
        raise TrackError(f"note {note_id} is not a note of #{item_id}")
    return note


# The note `ask` or `answer` marks: an existing one (`--note`) or a new one with the text given.
def marked_note(conn, args, item_id):
    if args.note is None:
        return add_note(conn, item_id, note_text(args))
    if args.text is not None or args.file is not None:
        raise TrackError("a text or --note, not both")
    return existing_note(conn, args.note, item_id)["id"]


# A question note, open until `answer`: a new note, or an existing one with --note (how the notes
# written before questions existed become questions); prints its note id.
def cmd_ask(conn, args):
    get_item(conn, args.id)
    if args.note is not None and is_question(conn, args.note):
        existing_note(conn, args.note, args.id)
        raise TrackError(f"note {args.note} is already a question")
    note_id = marked_note(conn, args, args.id)
    conn.execute("INSERT INTO questions (note_id) VALUES (?)", (note_id,))
    print(f"note {note_id}")
    return True


# The note that answers one or more open questions of an item, which closes them: a new note, or an
# existing one with --note, later than every question and not a question itself; prints its id.
def cmd_answer(conn, args):
    questions = []
    for note_id in args.notes:
        question = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if question is None:
            raise TrackError(f"no note {note_id}")
        if not is_question(conn, note_id):
            raise TrackError(f"note {note_id} is not a question")
        answer = conn.execute("SELECT note_id FROM answers WHERE question_id = ?", (note_id,)).fetchone()
        if answer is not None:
            raise TrackError(f"note {note_id} is already answered (note {answer['note_id']})")
        questions.append(question)
    if len({question["item_id"] for question in questions}) > 1:
        raise TrackError("questions of different items: an answer is a note of one item")
    item_id = questions[0]["item_id"]
    get_item(conn, item_id)
    note_id = marked_note(conn, args, item_id)
    # A new note is always the newest and never a question; an existing one is checked.
    for question in questions:
        if note_id < question["id"]:
            raise TrackError(f"note {note_id} is older than question {question['id']}")
    if is_question(conn, note_id):
        raise TrackError(f"note {note_id} is a question")
    conn.executemany("INSERT INTO answers (question_id, note_id) VALUES (?, ?)",
                     [(question["id"], note_id) for question in questions])
    print(f"note {note_id}")
    return True


# Every unanswered question of the live items: its note and item on one line, its text below.
def cmd_questions(conn, args):
    rows = open_questions(conn)
    if emit_json(args, rows):
        return False
    width = subject_width(rows)
    for row in rows:
        print(format_line(row, f"note {row['note_id']:<4} ", width))
        for line in row["text"].split("\n"):
            print(f"  {line}")
    return False


def cmd_set(conn, args):
    check_version(get_item(conn, args.id), args.if_version)
    changes, rank = {}, None
    for assignment in args.assignments:
        if "=" not in assignment:
            raise TrackError(f"expected field=value, got '{assignment}'")
        field, value = assignment.split("=", 1)
        if field not in FIELDS:
            raise TrackError(f"unknown field '{field}' (one of {', '.join(FIELDS)})")
        if field == "type":
            check_type(value)
        elif field == "status":
            check_status(value)
            # Closing sets the date, reopening clears it.
            changes["closed"] = today() if value in CLOSED else None
        elif field == "rank":
            rank = int(value)
            continue
        elif field == "body":
            # `body=@PATH` reads a file (`@-` stdin); `body=-` reads stdin as well.
            value = read_text(None, value[1:]) if value.startswith("@") else read_text(value, None)
        changes[field] = value
    # All the field changes make one version; the rank is a position, kept outside it.
    if changes:
        new_version(conn, args.id, changes)
    renumber(conn)
    if rank is not None:
        set_rank(conn, args.id, rank)
    return True


def cmd_close(conn, args):
    close_item(conn, args.id, "done", args.note)
    return True


def cmd_drop(conn, args):
    close_item(conn, args.id, "dropped", args.note)
    return True


# Delete an item, warning about the live bodies that still mention it: their reference now points
# at a deleted item (`refs --check` lists them).
def cmd_delete(conn, args):
    get_item(conn, args.id)
    new_version(conn, args.id, {"deleted": 1})
    renumber(conn)
    rows = conn.execute("SELECT item_id, body FROM latest WHERE deleted = 0 ORDER BY item_id").fetchall()
    mentioned_by = [f"#{row['item_id']}" for row in rows if args.id in mentioned_ids(row["body"])]
    if mentioned_by:
        warn(f"#{args.id} is still mentioned by {', '.join(mentioned_by)}")
    return True


def cmd_restore(conn, args):
    row = get_item(conn, args.id, include_deleted=True)
    if not row["deleted"]:
        raise TrackError(f"#{args.id} is not deleted")
    new_version(conn, args.id, {"deleted": 0})
    return True


def cmd_rank(conn, args):
    set_rank(conn, args.id, args.position)
    return True


def cmd_subjects(conn, args):
    rows = conn.execute(
        "SELECT subject, SUM(status NOT IN ('done', 'dropped')) AS open_count, COUNT(*) AS total "
        "FROM latest WHERE deleted = 0 GROUP BY subject ORDER BY subject").fetchall()
    if emit_json(args, rows):
        return False
    for row in rows:
        print(f"{row['subject'] or '(none)':<12} {row['open_count']} open / {row['total']} total")
    return False


# --- export: the latest, non-deleted items as markdown files --------------------------------

EXPORT_PREFIX = "tracker_export_"
EXPORT_FOLDERS = {"spec": "Specs", "feature": "Features", "bug": "Bugs", "debt": "Debt", "problem": "Problems"}


# A title as a file name: Windows-safe characters only, shortened.
def safe_name(title):
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", title).strip(" .")
    return re.sub(r"\s+", " ", cleaned)[:60] or "untitled"


# One line of an index file: the item's title as a link to its file, with its status and subject.
def export_line(row, rank=None):
    prefix = f"{rank}. " if rank else "- "
    subject = f" *{row['subject']}*" if row["subject"] else ""
    return f"{prefix}[#{row['item_id']} {row['title']}]({export_path(row)}) - {row['status']}{subject}"


def export_path(row):
    return f"{EXPORT_FOLDERS[row['type']]}/{row['item_id']:04d} {safe_name(row['title'])}.md"


# One item's file: a header with its fields, the body, the notes.
def export_item(row, notes):
    fields = [f"**{row['type']}** - {row['status']}", f"subject: {row['subject'] or '-'}",
              f"created: {row['created']}"]
    if row["rank"] is not None:
        fields.append(f"rank: {row['rank']}")
    if row["closed"]:
        fields.append(f"closed: {row['closed']}")
    fields.append(f"v{row['version']} {row['changed']}")
    text = f"# #{row['item_id']} {row['title']}\n\n" + "  \n".join(fields) + "\n"
    if row["body"]:
        text += "\n" + row["body"].rstrip("\n") + "\n"
    if notes:
        text += "\n## Notes\n\n" + "".join(f"- **{n['date']}**{note_label(n)} {n['text']}\n" for n in notes)
    return text


# Write every latest, non-deleted item under a new `tracker_export_<timestamp>` folder in `parent`:
# one file per item by type, plus the index files shaped like the spec lists (Next steps, Done,
# Potential problems, Debt, Drafts). Returns the folder.
def export_all(conn, parent):
    folder = os.path.join(parent, EXPORT_PREFIX + datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    rows = conn.execute("SELECT * FROM latest WHERE deleted = 0 ORDER BY item_id").fetchall()
    for name in EXPORT_FOLDERS.values():
        os.makedirs(os.path.join(folder, name), exist_ok=True)
    for row in rows:
        notes = item_notes(conn, row["item_id"])
        with open(os.path.join(folder, export_path(row)), "w", encoding="utf-8", newline="\n") as f:
            f.write(export_item(row, notes))
    ranked = sorted((r for r in rows if r["status"] in RANKABLE),
                    key=lambda r: (r["status"] != "doing", r["rank"] is None, r["rank"] or 0, r["item_id"]))
    indexes = {
        "Next steps.md": ("# Next steps", [export_line(r, r["rank"]) for r in ranked if r["rank"] is not None or r["status"] == "doing"]
                          + [""] + ["## Backlog"] + [export_line(r) for r in ranked if r["rank"] is None and r["status"] != "doing"]),
        "Drafts.md": ("# Drafts", [export_line(r) for r in rows if r["status"] == "draft"]),
        "Potential problems.md": ("# Potential problems", [export_line(r) for r in rows if r["type"] == "problem" and r["status"] not in CLOSED]),
        "Debt.md": ("# Debt", [export_line(r) for r in rows if r["type"] == "debt" and r["status"] not in CLOSED]),
        "Done.md": ("# Done", [export_line(r) + f" ({r['closed']})" for r in rows if r["status"] in CLOSED]),
    }
    for name, (title, lines) in indexes.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(title + "\n\n" + "\n".join(lines) + "\n")
    return folder


def cmd_export(conn, args):
    if not os.path.isdir(args.dir):
        raise TrackError(f"not a folder: {args.dir}")
    print(export_all(conn, args.dir))
    return False


def cmd_dump(conn, args):
    return True


def build_parser():
    parser = argparse.ArgumentParser(prog="track", description="Specs, features, bugs, debt and problems.")
    parser.add_argument("--dir", dest="tracker_dir", metavar="PATH",
                        help=f"the tracker folder: database, dump and sections file (default: ${DIR_VARIABLE})")
    parser.add_argument("--json", action="store_true", help="machine-readable output for the reading commands")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("guide", help="print the reference: how the tracker works and how to use it")
    p.set_defaults(func=cmd_guide)

    p = sub.add_parser("init", help="make a project's tracker folder (--dir), with the starting sections of its language")
    p.add_argument("--language", required=True, choices=LANGUAGES, help="the language of the project's content")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("next", help="the ranked list: doing first, then open by rank")
    p.add_argument("-n", type=int, default=10)
    p.add_argument("--section", metavar="TITLE", help="each item followed by that section's content")
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("list", help="items, one line each (closed ones only with --all/--status)")
    p.add_argument("--type")
    p.add_argument("--status")
    p.add_argument("--subject")
    p.add_argument("--all", action="store_true")
    p.add_argument("--deleted", action="store_true", help="the deleted items instead")
    p.add_argument("--search", metavar="TEXT", help="every word must appear in title, subject, body or notes")
    p.add_argument("--mentions", type=item_id, metavar="ID", help="only items whose body mentions #ID")
    p.add_argument("--section", metavar="TITLE", help="each item followed by that section's content")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("refs", help="what an item's body and notes mention, and which items mention it; --check: every broken reference")
    p.add_argument("id", type=item_id, nargs="?")
    p.add_argument("--check", action="store_true", help="every wrong reference in the bodies of the live items")
    p.add_argument("--type", help="only references of this type")
    p.set_defaults(func=cmd_refs)

    p = sub.add_parser("show", help="one item in full: header, body, notes")
    p.add_argument("id", type=item_id)
    p.add_argument("--version", type=int, help="an older version instead of the latest")
    p.add_argument("--deleted", action="store_true", help="allow a deleted item")
    p.add_argument("--expand", action="store_true", help="each reference followed by the title it names")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("history", help="every version of an item, one line each")
    p.add_argument("id", type=item_id)
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("add", help="new item; prints its id")
    p.add_argument("type")
    p.add_argument("title")
    p.add_argument("--subject")
    p.add_argument("--status", default="open")
    p.add_argument("--body")
    p.add_argument("--body-file", help="'-' reads stdin")
    p.add_argument("--rank", type=int)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("sections", help="the body's markdown headings, one per line; --check: the items off their type's sections")
    p.add_argument("id", type=item_id, nargs="?")
    p.add_argument("--check", action="store_true", help="every item whose body does not follow its type's sections")
    p.set_defaults(func=cmd_sections)

    p = sub.add_parser("section", help="one section's content; --set/--set-file replaces it")
    p.add_argument("id", type=item_id)
    p.add_argument("title", help="the heading, with or without its #s, case ignored")
    p.add_argument("--set", metavar="TEXT")
    p.add_argument("--set-file", metavar="PATH", help="'-' reads stdin")
    p.add_argument("--if-version", type=int, metavar="N", help="refuse unless the item is at version N")
    p.set_defaults(func=cmd_section)

    p = sub.add_parser("add-section", help="insert a subsection: at the end, or at the end of --after's section")
    p.add_argument("id", type=item_id)
    p.add_argument("title", help="the heading; its #s set the level, else --level")
    p.add_argument("--body", metavar="TEXT")
    p.add_argument("--body-file", metavar="PATH", help="'-' reads stdin")
    p.add_argument("--level", type=int, default=SECTION_LEVEL + 1, choices=range(1, 7))
    p.add_argument("--after", metavar="TITLE")
    p.add_argument("--if-version", type=int, metavar="N", help="refuse unless the item is at version N")
    p.set_defaults(func=cmd_add_section)

    p = sub.add_parser("replace", help="replace text that appears exactly once in the body")
    p.add_argument("id", type=item_id)
    p.add_argument("old", nargs="?", help="the exact text to replace")
    p.add_argument("new", nargs="?", default="", help="what to put instead (empty deletes it)")
    p.add_argument("--old-file", metavar="PATH", help="the old text from a file; '-' reads stdin")
    p.add_argument("--new-file", metavar="PATH", help="the new text from a file; '-' reads stdin")
    p.add_argument("--section", metavar="TITLE", help="look only inside this section")
    p.add_argument("--if-version", type=int, metavar="N", help="refuse unless the item is at version N")
    p.set_defaults(func=cmd_replace)

    p = sub.add_parser("note", help="append a dated note")
    p.add_argument("id", type=item_id)
    p.add_argument("text", nargs="?")
    p.add_argument("--file", help="'-' reads stdin")
    p.set_defaults(func=cmd_note)

    p = sub.add_parser("ask", help="append a question note (or mark one with --note), open until answered; prints its note id")
    p.add_argument("id", type=item_id)
    p.add_argument("text", nargs="?")
    p.add_argument("--file", help="'-' reads stdin")
    p.add_argument("--note", type=int, metavar="N", help="mark the item's existing note N as a question instead")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("answer", help="append the note that answers question notes (or mark one with --note); prints its note id")
    p.add_argument("notes", type=note_ids, help="the questions' note ids: 139 or 139,140")
    p.add_argument("text", nargs="?")
    p.add_argument("--file", help="'-' reads stdin")
    p.add_argument("--note", type=int, metavar="M", help="mark the existing note M as the answer instead")
    p.set_defaults(func=cmd_answer)

    p = sub.add_parser("questions", help="every unanswered question of the live items")
    p.set_defaults(func=cmd_questions)

    p = sub.add_parser("set", help="change fields: title type status subject rank body (body=@file, body=@- reads stdin)")
    p.add_argument("id", type=item_id)
    p.add_argument("assignments", nargs="+", metavar="field=value")
    p.add_argument("--if-version", type=int, metavar="N", help="refuse unless the item is at version N")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("close", help="status done, closed today, rank cleared")
    p.add_argument("id", type=item_id)
    p.add_argument("note", nargs="?")
    p.set_defaults(func=cmd_close)

    p = sub.add_parser("drop", help="status dropped, closed today, rank cleared")
    p.add_argument("id", type=item_id)
    p.add_argument("note", nargs="?")
    p.set_defaults(func=cmd_drop)

    p = sub.add_parser("delete", help="hide an item (logical delete; history kept)")
    p.add_argument("id", type=item_id)
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("restore", help="bring a deleted item back")
    p.add_argument("id", type=item_id)
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("rank", help="insert at position N of the ranked list (0 = backlog)")
    p.add_argument("id", type=item_id)
    p.add_argument("position", type=int)
    p.set_defaults(func=cmd_rank)

    p = sub.add_parser("subjects", help="distinct subjects with open counts")
    p.set_defaults(func=cmd_subjects)

    p = sub.add_parser("export", help="write the items as markdown files in a new tracker_export_<timestamp> folder")
    p.add_argument("dir", help="the folder to create it in")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("dump", help="rewrite the SQL dump")
    p.set_defaults(func=cmd_dump)
    return parser


# Write the dump after a committed change. If it cannot be written the change still stands (the
# database has it, and the next write rewrites the whole dump), so a write command only warns,
# never fails: failing would make a script repeat a write that was done. `track dump` itself fails.
def save_dump(conn, args):
    try:
        write_dump(conn, args.db)
    except OSError as error:
        if args.func is cmd_dump:
            raise TrackError(f"could not write the dump: {error}")
        warn(f"the change is saved in the database, but the dump could not be written ({error}); "
             f"run `track dump`")


# The tracker folder: --dir, else the TRACKER_DIR variable. It must exist (only `init` makes
# one): the tracker never guesses where a project keeps its files, and never creates the folder by
# accident.
def tracker_folder(args, must_exist=True):
    folder = args.tracker_dir or os.environ.get(DIR_VARIABLE)
    if not folder:
        raise TrackError(f"no tracker folder: pass --dir PATH or set {DIR_VARIABLE}")
    if must_exist and not os.path.isdir(folder):
        raise TrackError(f"not a folder: {folder}")
    return folder


# Make a project's tracker folder (created when missing): the template files, the starting
# sections of its language, its configuration, where the tracker is, and an empty database with its
# dump. Refused, with nothing written, when any of those files is already there.
def cmd_init(folder, args):
    db = os.path.join(folder, DB_NAME)
    made = [os.path.join(folder, name) for name in TEMPLATE_FILES + (CONFIG_NAME, TOOL_PATH_NAME)]
    made += [db, dump_path(db), sections_path(db)]
    existing = [os.path.basename(path) for path in made if os.path.exists(path)]
    if existing:
        raise TrackError(f"already a tracker folder: {folder} has {', '.join(existing)}")
    os.makedirs(folder, exist_ok=True)
    for name in TEMPLATE_FILES:
        shutil.copyfile(os.path.join(TEMPLATES, name), os.path.join(folder, name))
    shutil.copyfile(os.path.join(TEMPLATES, f"sections.{args.language}.json"), sections_path(db))
    with open(os.path.join(folder, CONFIG_NAME), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"language": args.language}, f, ensure_ascii=False)
        f.write("\n")
    with open(os.path.join(folder, TOOL_PATH_NAME), "w", encoding="utf-8") as f:
        f.write(TOOL_ROOT + "\n")
    conn = connect(db)
    try:
        write_dump(conn, db)
    finally:
        conn.close()
    print(f"created {folder}")


# Print the reference as it is, so an agent reads it through its project's launcher without
# knowing where the tracker repository is.
def cmd_guide():
    with open(GUIDE, encoding="utf-8") as f:
        print(f.read(), end="")


def main(argv=None):
    # Bodies and notes are markdown with any character; never let the console code page choke.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    if args.func is cmd_guide:
        cmd_guide()
        return 0
    try:
        folder = tracker_folder(args, must_exist=args.func is not cmd_init)
        if args.func is cmd_init:
            cmd_init(folder, args)
            return 0
        args.db = os.path.join(folder, DB_NAME)
    except TrackError as error:
        print(f"track: {error}", file=sys.stderr)
        return 1
    global SECTIONS_FILE
    SECTIONS_FILE = sections_path(args.db)
    conn = connect(args.db)
    try:
        changed = args.func(conn, args)
        if changed:
            conn.commit()
            save_dump(conn, args)
    except TrackError as error:
        conn.rollback()
        print(f"track: {error}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
