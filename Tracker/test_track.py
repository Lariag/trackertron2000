"""Tests for the tracker CLI (Tools/Tracker/track.py), run through Tools/Tracker/test.bat.
Every test runs the real CLI as a subprocess against a temporary tracker folder; no project's folder is
never touched.

Index:
- Empty database: next/list print nothing, unknown id fails
- add: id assigned, defaults, validation of type/status, body from file
- list: closed items hidden unless --all or --status, filters by type/subject
- show: header, body, notes in order
- rank: insert/shift/renumber, backlog with 0, closed items cannot be ranked
- next: doing first, then open by rank, unranked open hidden, -n limit
- set: fields, status=done closes, reopen clears closed, body=@file, bad field fails
- close/drop: status, closed date, rank cleared and renumbered, final note
- subjects: open counts
- versions: every change is a new version, older ones readable, rank changes make none
- delete/restore: logical delete hides the item everywhere, --deleted reaches it, restore brings it back
- sections: headings listed, content by title (#s and case normalized, subsections included)
- section --set: one section replaced, the rest untouched, missing section fails, one version
- add-section: a subsection at the end or after a section; level from the #s or --level; duplicate fails
- json: --json gives the reading commands' output as JSON with the same content
- json ids: an item's id is item_id alone (no version row id as `id`); the old view fixed on open; a read rewrites nothing
- export: a tracker_export_<timestamp> folder with one file per item by type and the index files; deleted items absent
- dump: rewritten after every change, database rebuilt from it when missing
- dump that cannot be written: change kept, warning, no half dump nor temporary file, `dump` fails
- spec type: accepted by add/set, filtered by list, exported to Specs/
- search: every word in title/subject/body/notes, case ignored, any order; combines with the other filters
- references: list --mentions, refs in both directions, missing/deleted ids, warnings on write
- references in notes and refs --check: refs reads the notes too; --check lists the bodies' broken references (missing, deleted, not a spec in Specs); warnings on notes and on delete
- stdin and line breaks: '-' reads stdin for every text option, \r\n and \r become \n
- inline '-': an inline text of exactly '-' reads stdin; empty stdin refused; one stdin per command
- replace: exactly-once rule, --section scope, texts from files/stdin, one version, --if-version
- ids with #: every id argument takes `#N` as well as `N`
- fixed sections: each type's sections, made by add, kept by every body write; old items still take other changes
- add-section, only subsections: a ## or # is refused
- sections --check: the items whose body does not follow their type's sections
- one section across items: next/list --section
- questions and answers: ask, answer, questions; show marks them; close warns; kept by the dump
- questions from existing notes: ask/answer --note mark a note already written; one answer for several questions
- sections file: the sections come from the file next to the database; read only when needed; missing or broken file refused
- show --expand: each reference followed by its title in «» (or deleted/missing), in body and notes; JSON keeps the raw texts
- tracker folder: --dir or TRACKER_DIR, --dir first; none, or not a folder, refused
- init: a project's tracker folder with its files, in its language; never over an existing one
- guide: prints the reference, with or without a tracker folder
- columns: the subject column widens so a long subject keeps two spaces before the title
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime

TRACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "track.py")


class TrackTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.dir.name, "tracker.db")
        self.dump = os.path.join(self.dir.name, "tracker.dump.sql")
        self.sections = os.path.join(self.dir.name, "tracker.sections.json")
        self.write_sections(self.SECTIONS)

    def tearDown(self):
        self.dir.cleanup()

    # Run the CLI on the test's tracker folder (`folder=None` passes no --dir), with `stdin` as its
    # standard input and `tracker_dir` as TRACKER_DIR (never the caller's own); returns (exit code,
    # stdout lines, stderr). The input goes in as raw bytes so `\r\n` and `\r` reach the CLI untranslated.
    def run_track(self, *args, stdin=None, folder="", tracker_dir=None):
        folder = self.dir.name if folder == "" else folder
        env = {key: value for key, value in os.environ.items() if key != "TRACKER_DIR"}
        if tracker_dir is not None:
            env["TRACKER_DIR"] = tracker_dir
        result = subprocess.run([sys.executable, TRACK, *(["--dir", folder] if folder else []), *args], env=env,
                                capture_output=True, input=None if stdin is None else stdin.encode("utf-8"))
        result.stdout = result.stdout.decode("utf-8")
        result.stderr = result.stderr.decode("utf-8")
        lines = result.stdout.splitlines()
        return result.returncode, lines, result.stderr.strip()

    def ok(self, *args, stdin=None):
        code, lines, err = self.run_track(*args, stdin=stdin)
        self.assertEqual(code, 0, err)
        return lines

    def fails(self, *args, stdin=None):
        code, lines, err = self.run_track(*args, stdin=stdin)
        self.assertEqual(code, 1, "\n".join(lines))
        self.assertTrue(err.startswith("track: "), err)
        return err

    def add(self, type_, title, *extra):
        return int(self.ok("add", type_, title, *extra)[0].lstrip("#"))

    # Each type's sections, as they were decided for the tracker: every body follows them.
    SECTIONS = {
        "spec": ["Qué es", "Reglas", "Configuración", "Más adelante"],
        "feature": ["Qué hay que hacer", "Specs", "Fuera de alcance"],
        "bug": ["Qué se ve", "Causa probable", "Qué hay que hacer", "Specs", "Fuera de alcance"],
        "debt": ["Qué hay que hacer", "Specs", "Fuera de alcance"],
        "problem": ["Qué es", "Posible solución", "Specs"],
    }

    # Write the sections file of the test database: each type's sections and the Specs section.
    def write_sections(self, sections, specs_section="Specs"):
        with open(self.sections, "w", encoding="utf-8") as f:
            json.dump({"specs_section": specs_section, "sections": sections}, f, ensure_ascii=False)

    # A body with every section of `type_`, in order, and `contents` ({title: text}) in some of them.
    def make_body(self, type_, contents=None):
        contents = contents or {}
        self.assertLessEqual(set(contents), set(self.SECTIONS[type_]))  # a typo in a title is a broken fixture
        return "\n\n".join("## " + title + ("\n\n" + contents[title] if contents.get(title) else "")
                           for title in self.SECTIONS[type_])

    # An item's body, as stored.
    def body(self, item_id):
        return json.loads("\n".join(self.ok("--json", "show", str(item_id))))["body"]

    # --- Empty database ---
    def test_empty(self):
        self.assertEqual(self.ok("next"), [])
        self.assertEqual(self.ok("list", "--all"), [])
        self.assertIn("no item #7", self.fails("show", "7"))
        self.assertTrue(os.path.exists(self.db))

    # --- add ---
    def test_add(self):
        self.assertEqual(self.add("feature", "First"), 1)
        self.assertEqual(self.add("bug", "Second", "--subject", "Physics", "--status", "draft"), 2)
        lines = self.ok("show", "1")
        self.assertEqual(lines[0], "#1 feature open  []  First")
        self.assertTrue(lines[1].startswith(f"created {datetime.now().strftime('%Y-%m-%d')}  v1 "), lines[1])
        self.assertEqual(self.ok("show", "2")[0], "#2 bug draft  [Physics]  Second")
        self.assertIn("unknown type", self.fails("add", "wish", "x"))
        self.assertIn("unknown status", self.fails("add", "bug", "x", "--status", "next"))
        self.assertIn("cannot be done", self.fails("add", "bug", "x", "--status", "done"))
        body = os.path.join(self.dir.name, "body.md")
        text = self.make_body("problem", {"Qué es": "- a\n- b"})
        with open(body, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        self.add("problem", "Third", "--body-file", body)
        self.assertEqual(self.ok("show", "3")[3:], text.split("\n"))

    # --- list ---
    def test_list(self):
        self.add("feature", "A", "--subject", "Physics")
        self.add("bug", "B", "--subject", "Multiplayer")
        self.add("debt", "C")
        self.ok("close", "2")
        titles = lambda lines: [line.split()[-1] for line in lines]
        self.assertEqual(titles(self.ok("list")), ["A", "C"])
        self.assertEqual(titles(self.ok("list", "--all")), ["A", "B", "C"])
        self.assertEqual(titles(self.ok("list", "--status", "done")), ["B"])
        self.assertEqual(titles(self.ok("list", "--type", "debt")), ["C"])
        self.assertEqual(titles(self.ok("list", "--subject", "physics")), ["A"])
        self.assertEqual(self.ok("list")[0], "#1    feature  open    Physics      A")
        self.assertIn("unknown type", self.fails("list", "--type", "wish"))

    # --- show ---
    def test_show(self):
        body = self.make_body("bug", {"Qué se ve": "Seen on dedicated."}).split("\n")
        notes = 3 + len(body) + 1  # header, blank, body, blank: then the notes
        self.add("bug", "Drift", "--body", "\n".join(body))
        self.ok("note", "1", "first note")
        self.ok("note", "1", "second note")
        lines = self.ok("show", "1")
        self.assertEqual(lines[3:notes - 1], body)
        self.assertEqual(lines[notes - 1], "")
        self.assertTrue(lines[notes].startswith("- ") and lines[notes].endswith(": first note"), lines[notes])
        self.assertTrue(lines[notes + 1].endswith(": second note"))
        note_file = os.path.join(self.dir.name, "note.md")
        with open(note_file, "w", encoding="utf-8") as f:
            f.write("from file\n")
        self.ok("note", "1", "--file", note_file)
        self.assertTrue(self.ok("show", "1")[notes + 2].endswith(": from file"))
        self.assertIn("empty note", self.fails("note", "1"))

    # --- rank ---
    def test_rank(self):
        for title in "ABCD":
            self.add("feature", title)
        ranked = lambda: [line.split()[-1] for line in self.ok("next")]
        self.assertEqual(ranked(), [])
        self.ok("rank", "1", "1")
        self.ok("rank", "2", "1")
        self.assertEqual(ranked(), ["B", "A"])
        self.ok("rank", "3", "2")
        self.assertEqual(ranked(), ["B", "C", "A"])
        self.ok("rank", "4", "99")  # past the end: last
        self.assertEqual(ranked(), ["B", "C", "A", "D"])
        self.ok("rank", "2", "0")  # to the backlog
        self.assertEqual(ranked(), ["C", "A", "D"])
        self.assertEqual([line[:3] for line in self.ok("next")], [" 1.", " 2.", " 3."])
        self.ok("close", "3")
        self.assertEqual(ranked(), ["A", "D"])
        self.assertEqual(self.ok("next")[1][:3], " 2.")
        self.assertIn("only open/doing", self.fails("rank", "3", "1"))
        self.assertIn("rank must be", self.fails("rank", "1", "-1"))
        self.add("bug", "E", "--rank", "1")
        self.assertEqual(ranked(), ["E", "A", "D"])

    # --- next ---
    def test_next(self):
        self.add("feature", "A", "--rank", "1")
        self.add("feature", "B", "--rank", "2")
        self.add("feature", "C")  # unranked open: hidden
        self.add("bug", "D", "--status", "draft")  # draft: hidden
        self.add("bug", "E")
        self.ok("set", "5", "status=doing")  # doing, unranked: first anyway
        lines = self.ok("next")
        self.assertEqual([line.split()[-1] for line in lines], ["E", "A", "B"])
        self.assertEqual(lines[0][:3], " -.")
        self.assertEqual(len(self.ok("next", "-n", "2")), 2)

    # --- set ---
    def test_set(self):
        self.add("feature", "A", "--rank", "1")
        self.ok("set", "1", "title=Renamed", "type=debt", "subject=Voxels")
        self.assertEqual(self.ok("show", "1")[0], "#1 debt open  rank 1  [Voxels]  Renamed")
        self.ok("set", "1", "status=done")
        lines = self.ok("show", "1")
        self.assertEqual(lines[0], "#1 debt done  [Voxels]  Renamed")
        self.assertIn("closed", lines[1])
        self.ok("set", "1", "status=open")
        self.assertNotIn("closed", self.ok("show", "1")[1])
        body = os.path.join(self.dir.name, "b.md")
        text = self.make_body("debt", {"Qué hay que hacer": "new body"})
        with open(body, "w", encoding="utf-8") as f:
            f.write(text)
        self.ok("set", "1", f"body=@{body}", "rank=1")
        self.assertEqual(self.body(1), text)
        self.assertEqual(self.ok("show", "1")[0], "#1 debt open  rank 1  [Voxels]  Renamed")
        self.assertIn("unknown field", self.fails("set", "1", "colour=red"))
        self.assertIn("expected field=value", self.fails("set", "1", "title"))
        self.assertIn("unknown status", self.fails("set", "1", "status=next"))
        self.assertIn("no item", self.fails("set", "9", "title=x"))

    # --- close/drop ---
    def test_close_drop(self):
        self.add("bug", "A", "--rank", "1")
        self.add("bug", "B", "--rank", "2")
        self.add("bug", "C", "--rank", "3")
        self.ok("close", "1", "fixed it")
        self.ok("drop", "2")
        lines = self.ok("show", "1")
        self.assertTrue(lines[0].startswith("#1 bug done  [") and "rank" not in lines[0])
        self.assertIn(f"closed {datetime.now().strftime('%Y-%m-%d')}  v2 ", lines[1])
        self.assertTrue(lines[-1].endswith(": fixed it"))
        self.assertTrue(self.ok("show", "2")[0].startswith("#2 bug dropped"))
        self.assertEqual(self.ok("next")[0][:3], " 1.")
        self.assertEqual(self.ok("list"), ["#3    bug      open                 C"])
        self.assertIn("no item", self.fails("close", "8"))

    # --- subjects ---
    def test_subjects(self):
        self.add("feature", "A", "--subject", "Physics")
        self.add("bug", "B", "--subject", "Physics")
        self.add("bug", "C")
        self.ok("close", "2")
        self.assertEqual(self.ok("subjects"), ["(none)       1 open / 1 total",
                                               "Physics      1 open / 2 total"])

    # --- versions ---
    def test_versions(self):
        first = self.make_body("feature", {"Qué hay que hacer": "first body"})
        second = self.make_body("feature", {"Qué hay que hacer": "second body"})
        self.add("feature", "A", "--body", first)
        self.ok("set", "1", "title=B", "body=" + second)
        self.ok("set", "1", "status=doing")
        self.ok("rank", "1", "1")  # a position, not a version
        self.ok("note", "1", "a note")  # notes are not versions either
        history = self.ok("history", "1")
        self.assertEqual(len(history), 3)
        self.assertTrue(history[0].startswith("v1 ") and history[0].endswith(" A"), history[0])
        self.assertTrue(history[1].startswith("v2 ") and history[1].endswith(" B"))
        self.assertIn(" doing ", history[2])
        latest = self.ok("show", "1")
        self.assertEqual(latest[0], "#1 feature doing  rank 1  []  B")
        self.assertIn("  v3 ", latest[1])
        self.assertEqual(self.body(1), second)
        old = self.ok("show", "1", "--version", "1")
        self.assertEqual(old[0], "#1 feature open  []  A")
        self.assertIn("  v1 ", old[1])
        self.assertEqual("\n".join(old[3:-2]), first)
        self.assertTrue(old[-1].endswith(": a note"))  # notes belong to the item, not the version
        self.assertIn("no version 9", self.fails("show", "1", "--version", "9"))
        self.assertEqual(self.ok("list", "--all"), ["#1    feature  doing                B"])

    # --- delete/restore ---
    def test_delete_restore(self):
        self.add("bug", "Gone", "--subject", "Physics", "--rank", "1")
        self.add("bug", "Kept", "--rank", "2")
        self.ok("delete", "1")
        self.assertIn("no item #1", self.fails("show", "1"))
        self.assertIn("no item #1", self.fails("set", "1", "title=x"))
        self.assertIn("no item #1", self.fails("note", "1", "x"))
        self.assertIn("no item #1", self.fails("rank", "1", "1"))
        self.assertIn("no item #1", self.fails("delete", "1"))
        self.assertEqual(self.ok("list", "--all"), ["#2    bug      open                 Kept"])
        self.assertEqual(self.ok("next"), [" 1. #2    bug      open                 Kept"])
        self.assertEqual(self.ok("subjects"), ["(none)       1 open / 1 total"])
        self.assertEqual(self.ok("list", "--deleted"), ["#1    bug      open    Physics      Gone"])
        shown = self.ok("show", "1", "--deleted")
        self.assertEqual(shown[0], "#1 bug open  [Physics]  Gone  DELETED")
        self.assertTrue(self.ok("history", "1")[1].endswith("Gone  DELETED"))
        self.assertIn("not deleted", self.fails("restore", "2"))
        self.ok("restore", "1")
        self.assertEqual(self.ok("show", "1")[0], "#1 bug open  [Physics]  Gone")
        self.assertEqual(self.ok("list", "--deleted"), [])
        self.assertEqual(len(self.ok("history", "1")), 3)
        self.assertEqual(self.ok("next"), [" 1. #2    bug      open                 Kept"])  # rank was lost

    BODY = ("## Qué hay que hacer\n\nHow it works.\n\n### Details\n\n- one\n- two\n\n"
            "## Specs\n\nNone yet.\n\n#not a heading\n\n## Fuera de alcance\n")
    HEADINGS = ["## Qué hay que hacer", "### Details", "## Specs", "## Fuera de alcance"]

    def body_of(self, item_id):
        return self.ok("show", str(item_id))[3:]

    # --- sections ---
    def test_sections(self):
        self.add("feature", "A", "--body", self.BODY)
        self.assertEqual(self.ok("sections", "1"), self.HEADINGS)
        self.assertEqual(self.ok("section", "1", "Qué hay que hacer"), ["How it works.", "", "### Details", "", "- one", "- two"])
        self.assertEqual(self.ok("section", "1", "### details"), ["- one", "- two"])
        self.assertEqual(self.ok("section", "1", "##   SPECS "), ["None yet.", "", "#not a heading"])
        self.assertIn("no section 'Missing'", self.fails("section", "1", "Missing"))
        self.add("feature", "B")
        self.assertEqual(self.ok("sections", "2"), ["## Qué hay que hacer", "## Specs", "## Fuera de alcance"])

    # --- section --set ---
    def test_section_set(self):
        self.add("feature", "A", "--body", self.BODY)
        self.ok("section", "1", "details", "--set", "- three")
        self.assertEqual(self.ok("section", "1", "Details"), ["- three"])
        self.assertEqual(self.ok("section", "1", "Qué hay que hacer"), ["How it works.", "", "### Details", "- three"])
        self.assertEqual(self.ok("section", "1", "Specs"), ["None yet.", "", "#not a heading"])
        self.assertEqual(self.ok("sections", "1"), self.HEADINGS)
        text = os.path.join(self.dir.name, "s.md")
        with open(text, "w", encoding="utf-8") as f:
            f.write("Answered.\n")
        self.ok("section", "1", "## Specs", "--set-file", text)
        self.assertEqual(self.ok("section", "1", "Specs"), ["Answered."])
        self.assertEqual(self.ok("section", "1", "Details"), ["- three"])  # the other sections are untouched
        self.assertEqual(self.ok("section", "1", "Fuera de alcance"), [])
        self.assertIn("no section 'Nope'", self.fails("section", "1", "Nope", "--set", "x"))
        self.assertEqual(len(self.ok("history", "1")), 3)  # one version per --set
        self.ok("section", "1", "Qué hay que hacer", "--set", "")  # emptied: heading kept, subsection gone
        self.assertEqual(self.ok("sections", "1"), ["## Qué hay que hacer", "## Specs", "## Fuera de alcance"])
        self.assertEqual(self.ok("section", "1", "Qué hay que hacer"), [])

    # --- add-section ---
    def test_add_section(self):
        self.add("feature", "A")
        self.ok("add-section", "1", "First", "--body", "one")  # a subsection, at the end
        self.assertEqual(self.body_of(1)[-4:], ["## Fuera de alcance", "", "### First", "one"])
        self.ok("add-section", "1", "Middle", "--after", "qué hay que hacer", "--level", "4", "--body", "a\nb")
        self.assertEqual(self.ok("sections", "1"), ["## Qué hay que hacer", "#### Middle", "## Specs", "## Fuera de alcance", "### First"])
        self.assertEqual(self.ok("section", "1", "Middle"), ["a", "b"])
        self.assertEqual(self.ok("section", "1", "Qué hay que hacer"), ["#### Middle", "a", "b"])
        # "after" a section is after its whole content, subsections included: at the very end here.
        self.ok("add-section", "1", "### Second", "--after", "Fuera de alcance")
        self.assertEqual(self.ok("sections", "1")[-2:], ["### First", "### Second"])
        self.assertIn("already exists", self.fails("add-section", "1", "first"))
        self.assertIn("no section 'Nope'", self.fails("add-section", "1", "X", "--after", "Nope"))
        self.assertIn("empty section title", self.fails("add-section", "1", "###"))
        self.assertEqual(len(self.ok("history", "1")), 4)

    # --- json ---
    def test_json(self):
        body = self.make_body("bug", {"Qué se ve": "text"})
        self.add("bug", "A", "--subject", "Physics", "--rank", "1", "--body", body)
        self.add("feature", "B")
        self.ok("note", "1", "n1")
        as_json = lambda *a: json.loads("\n".join(self.ok("--json", *a)))
        rows = as_json("list")
        self.assertEqual([r["title"] for r in rows], ["A", "B"])
        self.assertEqual((rows[0]["item_id"], rows[0]["rank"], rows[1]["rank"]), (1, 1, None))
        self.assertEqual((rows[0]["notes_text"], rows[1]["notes_text"]), ("n1", ""))
        self.assertEqual([r["item_id"] for r in as_json("next")], [1])
        item = as_json("show", "1")
        self.assertEqual((item["type"], item["subject"], item["body"], item["version"]), ("bug", "Physics", body, 1))
        self.assertEqual([n["text"] for n in item["notes"]], ["n1"])
        self.assertEqual([v["version"] for v in as_json("history", "1")], [1])
        self.assertEqual(as_json("sections", "1")[0], {"level": 2, "title": "Qué se ve"})
        self.assertEqual(as_json("section", "1", "Qué se ve"), "text")
        self.assertEqual(as_json("subjects")[1], {"subject": "Physics", "open_count": 1, "total": 1})
        self.assertIn("no item", self.fails("--json", "show", "9"))

    # --- json ids ---
    # An item's id in JSON is `item_id` alone: no row carries the versions table's own row id as `id`, which read
    # as an item's id names another item or none (Known issues, 2026-10-19). A database made with the old view is
    # fixed when opened, and a reading command leaves a current database's file as it was.
    def test_json_ids(self):
        self.add("feature", "A")
        self.add("feature", "B", "--rank", "1")
        self.ok("set", "1", "title=A2")
        self.ok("set", "1", "title=A3")  # item 1 at its third version: version rows 1, 3 and 4
        self.ok("ask", "2", "q?")
        as_json = lambda *a: json.loads("\n".join(self.ok("--json", *a)))
        for args, ids in [(("list",), [1, 2]), (("next",), [2]), (("questions",), [2]), (("history", "1"), [1, 1, 1])]:
            rows = as_json(*args)
            self.assertEqual([row["item_id"] for row in rows], ids, args)
            for row in rows:
                self.assertNotIn("id", row, args)
        for args in (("show", "1"), ("show", "1", "--version", "1")):
            item = as_json(*args)
            self.assertEqual(item["item_id"], 1, args)
            self.assertNotIn("id", item, args)
        conn = sqlite3.connect(self.db)
        conn.executescript(
            "DROP VIEW latest; CREATE VIEW latest AS SELECT v.*, i.created, r.rank FROM versions v "
            "JOIN items i ON i.id = v.item_id LEFT JOIN ranks r ON r.item_id = v.item_id "
            "WHERE v.version = (SELECT MAX(version) FROM versions WHERE item_id = v.item_id);")
        conn.close()
        self.assertNotIn("id", as_json("list")[0])  # the old view replaced on open
        with open(self.db, "rb") as f:
            before = f.read()
        as_json("list")
        with open(self.db, "rb") as f:
            self.assertEqual(f.read(), before)  # nothing rewritten by a read

    # --- export ---
    def test_export(self):
        self.add("bug", "Drift: on/dedicated?", "--subject", "Physics", "--rank", "1", "--body", self.make_body("bug", {"Qué se ve": "text"}))
        self.add("feature", "Doing thing", "--rank", "2")
        self.ok("set", "2", "status=doing")
        self.add("feature", "Backlog thing")
        self.add("feature", "A draft", "--status", "draft")
        self.add("problem", "May break")
        self.add("debt", "Slow")
        self.add("bug", "Fixed one")
        self.ok("close", "7", "fixed")
        self.add("bug", "Gone")
        self.ok("delete", "8")
        self.ok("note", "1", "a note")
        target = os.path.join(self.dir.name, "out")
        os.mkdir(target)
        dump_before = open(self.dump, encoding="utf-8").read()
        folder = self.ok("export", target)[0]
        name = os.path.basename(folder)
        self.assertTrue(name.startswith("tracker_export_") and len(name) == len("tracker_export_2026-09-20_141500"), name)
        self.assertEqual(sorted(os.listdir(folder)), ["Bugs", "Debt", "Debt.md", "Done.md", "Drafts.md", "Features", "Next steps.md", "Potential problems.md", "Problems", "Specs"])
        self.assertEqual(os.listdir(os.path.join(folder, "Bugs")), ["0001 Drift on dedicated.md", "0007 Fixed one.md"])  # no deleted #8
        text = open(os.path.join(folder, "Bugs", "0001 Drift on dedicated.md"), encoding="utf-8").read()
        self.assertTrue(text.startswith("# #1 Drift: on/dedicated?\n\n**bug** - open  \nsubject: Physics"), text)
        self.assertIn("rank: 1", text)
        self.assertIn("\n## Qué se ve\n\ntext\n", text)
        self.assertTrue(text.endswith("## Notes\n\n- **" + text.split("- **")[1]), text)
        self.assertTrue(text.rstrip().endswith("** a note"))
        steps = open(os.path.join(folder, "Next steps.md"), encoding="utf-8").read().splitlines()
        self.assertEqual(steps[2], "2. [#2 Doing thing](Features/0002 Doing thing.md) - doing")
        self.assertEqual(steps[3], "1. [#1 Drift: on/dedicated?](Bugs/0001 Drift on dedicated.md) - open *Physics*")
        self.assertEqual(steps[-3:], ["- [#3 Backlog thing](Features/0003 Backlog thing.md) - open",
                                      "- [#5 May break](Problems/0005 May break.md) - open",
                                      "- [#6 Slow](Debt/0006 Slow.md) - open"])  # the backlog: every unranked open item
        self.assertIn("#4 A draft", open(os.path.join(folder, "Drafts.md"), encoding="utf-8").read())
        self.assertIn("#5 May break", open(os.path.join(folder, "Potential problems.md"), encoding="utf-8").read())
        self.assertIn("#6 Slow", open(os.path.join(folder, "Debt.md"), encoding="utf-8").read())
        done = open(os.path.join(folder, "Done.md"), encoding="utf-8").read()
        self.assertIn("#7 Fixed one", done)
        self.assertIn(f"({datetime.now().strftime('%Y-%m-%d')})", done)
        self.assertNotIn("Gone", done)
        self.assertIn("not a folder", self.fails("export", os.path.join(target, "missing")))
        self.assertEqual(open(self.dump, encoding="utf-8").read(), dump_before)  # an export changes nothing

    # --- dump ---
    def test_dump_and_rebuild(self):
        self.ok("next")
        self.assertFalse(os.path.exists(self.dump))  # reads write no dump
        body = self.make_body("feature", {"Qué hay que hacer": "ünïcödé body"})
        self.add("feature", "Kept", "--body", body)
        self.assertTrue(os.path.exists(self.dump))
        with open(self.dump, encoding="utf-8") as f:
            self.assertIn("Kept", f.read())
        self.ok("note", "1", "a note")
        os.remove(self.db)
        self.assertEqual(self.body(1), body)
        self.assertTrue(self.ok("show", "1")[-1].endswith(": a note"))
        self.ok("dump")
        with open(self.dump, encoding="utf-8") as f:
            self.assertIn("a note", f.read())
        self.assertEqual(sorted(os.listdir(self.dir.name)), ["tracker.db", "tracker.dump.sql", "tracker.sections.json"])  # no temporary file left

    # A dump that cannot be replaced (here a folder in its place; in real life a file locked by
    # another program) never leaves half a dump: the change is kept, a warning names `track dump`,
    # and `track dump` itself fails until it can write (Known issues #20).
    def test_dump_cannot_be_written(self):
        self.add("feature", "Kept")
        os.remove(self.dump)
        os.mkdir(self.dump)
        code, _, err = self.run_track("note", "1", "saved anyway")
        self.assertEqual(code, 0, err)
        self.assertIn("track: warning:", err)
        self.assertIn("the change is saved", err)
        self.assertIn("track dump", err)
        self.assertTrue(self.ok("show", "1")[-1].endswith(": saved anyway"))
        self.assertIn("could not write the dump", self.fails("dump"))
        self.assertEqual(os.listdir(self.dump), [])
        self.assertEqual(sorted(os.listdir(self.dir.name)), ["tracker.db", "tracker.dump.sql", "tracker.sections.json"])  # temporary files cleaned up
        os.rmdir(self.dump)
        self.ok("dump")
        with open(self.dump, encoding="utf-8") as f:
            self.assertIn("saved anyway", f.read())

    # --- spec type ---
    def test_spec_type(self):
        self.add("spec", "Parcel", "--body", self.make_body("spec", {"Reglas": "text"}))
        self.add("feature", "Build it")
        self.ok("set", "2", "type=spec", "body=" + self.make_body("spec"))
        self.add("bug", "Other")
        self.assertEqual([line.split()[:2] for line in self.ok("list", "--type", "spec")], [["#1", "spec"], ["#2", "spec"]])
        self.assertEqual(self.ok("section", "1", "Reglas"), ["text"])
        target = os.path.join(self.dir.name, "out")
        os.mkdir(target)
        folder = self.ok("export", target)[0]
        self.assertEqual(sorted(os.listdir(os.path.join(folder, "Specs"))), ["0001 Parcel.md", "0002 Build it.md"])

    # --- search ---
    def test_search(self):
        ids = lambda *args: [int(line.split()[0].lstrip("#")) for line in self.ok("list", *args)]
        self.add("spec", "Plantas", "--subject", "Cultivo", "--body", self.make_body("spec", {"Qué es": "La salud baja con los BICHOS."}))
        self.add("feature", "Riego manual", "--subject", "Parcela", "--body", self.make_body("feature", {"Qué hay que hacer": "Pasar el dedo."}))
        self.add("bug", "Cosecha rota")
        self.ok("note", "3", "Falla con la salud a cero")
        self.add("feature", "Cerrada con salud")
        self.ok("close", "4")
        self.assertEqual(ids("--search", "salud"), [1, 3])  # body and notes; closed #4 hidden
        self.assertEqual(ids("--search", "bichos SALUD"), [1])  # every word, any order, case ignored
        self.assertEqual(ids("--search", "riego"), [2])  # title
        self.assertEqual(ids("--search", "cultivo"), [1])  # subject
        self.assertEqual(ids("--search", "salud", "--all"), [1, 3, 4])
        self.assertEqual(ids("--search", "salud", "--type", "bug"), [3])
        self.assertEqual(ids("--search", "salud dedo"), [])
        self.assertEqual(ids("--search", "   "), [1, 2, 3])  # an empty query filters nothing
        found = json.loads("\n".join(self.ok("--json", "list", "--search", "dedo")))
        self.assertEqual([row["item_id"] for row in found], [2])

    # --- references ---
    def test_references(self):
        ids = lambda lines: [int(line.split()[0].lstrip("#")) for line in lines]
        self.add("spec", "Parcela")
        self.add("spec", "Plantas", "--body", self.make_body("spec", {"Qué es": "Ver #1. Otra vez #1."}))
        code, _, err = self.run_track("add", "feature", "Suelo", "--body", self.make_body("feature", {"Specs": "#1, #2 y #9"}))
        self.assertEqual(code, 0)
        self.assertIn("mentions #9, which does not exist", err)  # warned, still added
        self.add("feature", "Sin refs", "--body", self.make_body("feature", {"Specs": "Nada. C#1 y ## 2 no cuentan."}))
        self.assertEqual(ids(self.ok("list", "--mentions", "1")), [2, 3])
        self.assertEqual(ids(self.ok("list", "--mentions", "1", "--type", "feature")), [3])
        lines = self.ok("refs", "3")
        self.assertEqual(lines[0], "#3 mentions:")
        self.assertEqual(ids(lines[1:3]), [1, 2])
        self.assertEqual(lines[3].split(), ["#9", "(missing)"])
        self.assertEqual(lines[4:], ["#3 is mentioned by:"])
        refs = json.loads("\n".join(self.ok("--json", "refs", "1")))
        self.assertEqual(([r["item_id"] for r in refs["mentions"]], [r["item_id"] for r in refs["mentioned_by"]]), ([], [2, 3]))
        self.assertEqual([r["item_id"] for r in json.loads("\n".join(self.ok("--json", "refs", "1", "--type", "spec")))["mentioned_by"]], [2])
        self.ok("delete", "2")
        refs = json.loads("\n".join(self.ok("--json", "refs", "3")))
        self.assertEqual(refs["missing"], [{"item_id": 2, "state": "deleted", "in": ["body"]}, {"item_id": 9, "state": "missing", "in": ["body"]}])
        self.assertEqual(ids(self.ok("list", "--mentions", "1")), [3])  # a deleted item mentions nothing
        code, _, err = self.run_track("section", "4", "Specs", "--set", "#2")
        self.assertEqual(code, 0)
        self.assertIn("mentions #2, which is deleted", err)  # body writes warn too

    # --- references in notes, refs --check ---
    def test_references_notes_and_check(self):
        refs = lambda item_id: json.loads("\n".join(self.ok("--json", "refs", item_id)))
        self.add("spec", "Parcela")
        self.add("feature", "Suelo", "--body", self.make_body("feature", {"Specs": "#1"}))
        code, _, err = self.run_track("add", "feature", "Riego", "--body", self.make_body("feature", {"Specs": "#1, #2"}))
        self.assertEqual(code, 0)
        self.assertIn("mentions #2 in Specs, which is a feature, not a spec", err)  # warned, still added
        code, _, err = self.run_track("add", "feature", "Libre", "--body", self.make_body("feature", {"Qué hay que hacer": "Como #2."}))
        self.assertEqual(err, "")  # outside Specs, any type may be mentioned
        self.ok("note", "1", "Pregunta abierta: ¿como en #3?")
        code, _, err = self.run_track("note", "1", "Ver #99.")
        self.assertEqual(code, 0)
        self.assertIn("the note mentions #99, which does not exist", err)  # notes warn too
        # refs reads the notes as well, in both directions, and says where a reference is.
        lines = self.ok("refs", "1")
        self.assertEqual(lines[0], "#1 mentions:")
        self.assertTrue(lines[1].startswith("  #3 ") and lines[1].endswith("  (in notes)"), lines[1])
        self.assertEqual(lines[2].split(), ["#99", "(missing,", "in", "notes)"])
        self.assertEqual(lines[3], "#1 is mentioned by:")
        self.assertEqual([line.split()[0] for line in lines[4:]], ["#2", "#3"])
        self.assertEqual([(r["item_id"], r["in"]) for r in refs("1")["mentions"]], [(3, ["notes"])])
        self.assertEqual(refs("1")["missing"], [{"item_id": 99, "state": "missing", "in": ["notes"]}])
        self.assertEqual([(r["item_id"], r["in"]) for r in refs("3")["mentioned_by"]], [(1, ["notes"])])
        self.assertEqual([(r["item_id"], r["in"]) for r in refs("2")["mentioned_by"]], [(3, ["body"]), (4, ["body"])])
        self.assertEqual(self.ok("list", "--mentions", "3"), [])  # --mentions reads the bodies only
        # refs --check: every broken reference of the bodies; the notes are history, never errors.
        lines = self.ok("refs", "--check")
        self.assertEqual(lines[0].split()[:2], ["#3", "feature"])
        self.assertEqual(lines[1:], ["  Specs: #2 is a feature, not a spec"])
        code, _, err = self.run_track("delete", "1")
        self.assertEqual(code, 0)
        self.assertIn("#1 is still mentioned by #2, #3", err)  # warned, still deleted
        lines = self.ok("refs", "--check")
        self.assertEqual([line.split()[0] for line in lines if not line.startswith(" ")], ["#2", "#3"])
        self.assertEqual(lines[1], "  Specs: #1 is deleted")
        self.assertEqual(lines[3:], ["  Specs: #1 is deleted", "  Specs: #2 is a feature, not a spec"])
        rows = json.loads("\n".join(self.ok("--json", "refs", "--check")))
        self.assertEqual(rows[0], {"item_id": 2, "section": "Specs", "ref": 1, "problem": "is deleted"})
        self.assertEqual(len(rows), 3)
        self.assertIn("an id or --check", self.fails("refs"))

    # --- stdin and line breaks ---
    # A spec body with `rules` in its Reglas section; `crlf` writes every line break as \r\n.
    def spec_body(self, rules, crlf=False):
        body = self.make_body("spec", {"Reglas": rules})
        return body.replace("\n", "\r\n") if crlf else body

    def test_stdin_and_newlines(self):
        self.ok("add", "spec", "A", "--body-file", "-", stdin=self.spec_body("uno\r\ndos\rtres") + "\n\n")
        self.assertEqual(self.body(1), self.spec_body("uno\ndos\ntres"))  # normalized, trailing breaks dropped
        self.ok("set", "1", "body=@-", stdin=self.spec_body("viejo", crlf=True) + "\r\n")
        self.assertEqual(self.body(1), self.spec_body("viejo"))
        self.ok("section", "1", "Reglas", "--set-file", "-", stdin="nuevo\r\nlínea")
        self.assertIn("## Reglas\nnuevo\nlínea\n\n## Configuración", self.body(1))
        self.ok("add-section", "1", "T", "--body-file", "-", stdin="t1\rt2")
        self.assertTrue(self.body(1).endswith("### T\nt1\nt2"), self.body(1))
        self.ok("note", "1", "--file", "-", stdin="nota\r\nde dos")
        self.assertEqual(json.loads("\n".join(self.ok("--json", "show", "1")))["notes"][0]["text"], "nota\nde dos")
        self.ok("add", "spec", "B", "--body", self.spec_body("a\r\nb"))  # text given inline is normalized too
        self.assertEqual(self.body(2), self.spec_body("a\nb"))
        path = os.path.join(self.dir.name, "crlf.md")
        with open(path, "wb") as f:
            f.write((self.spec_body("x\ny", crlf=True) + "\r\n").encode("utf-8"))
        self.ok("set", "2", f"body=@{path}")
        self.assertEqual(self.body(2), self.spec_body("x\ny"))  # files keep their \r until normalized

    # An inline text of exactly '-' reads stdin too, never stores a literal '-' (Known issues #19).
    def test_inline_dash_reads_stdin(self):
        self.ok("add", "spec", "A", "--body", "-", stdin=self.spec_body("viejas", crlf=True) + "\n")
        self.assertEqual(self.body(1), self.spec_body("viejas"))
        self.ok("section", "1", "Reglas", "--set", "-", stdin="nuevas\r\nreglas\n")
        self.assertIn("## Reglas\nnuevas\nreglas\n\n## Configuración", self.body(1))
        self.ok("add-section", "1", "Más", "--body", "-", stdin="más")
        self.assertTrue(self.body(1).endswith("### Más\nmás"), self.body(1))
        self.ok("set", "1", "body=-", stdin=self.spec_body("otras"))
        self.assertEqual(self.body(1), self.spec_body("otras"))
        self.ok("replace", "1", "otras", "-", stdin="las de stdin")
        self.assertEqual(self.body(1), self.spec_body("las de stdin"))
        self.ok("replace", "1", "-", "las de siempre", stdin="las de stdin")
        self.assertEqual(self.body(1), self.spec_body("las de siempre"))
        self.ok("note", "1", "-", stdin="nota\r\nlarga")
        self.assertEqual(json.loads("\n".join(self.ok("--json", "show", "1")))["notes"][0]["text"], "nota\nlarga")
        self.assertIn("only one of the texts can read stdin", self.fails("replace", "1", "-", "-", stdin="x"))
        self.assertIn("only one of the texts can read stdin", self.fails("replace", "1", "-", "--new-file", "-", stdin="x"))
        # Empty stdin is a failed pipe, not an empty text: refused, nothing written.
        self.assertIn("empty stdin", self.fails("section", "1", "Reglas", "--set", "-", stdin=""))
        self.assertIn("empty stdin", self.fails("section", "1", "Reglas", "--set-file", "-", stdin="\n\n"))
        self.assertIn("empty stdin", self.fails("add", "spec", "B", "--body", "-", stdin=""))
        self.assertEqual(self.body(1), self.spec_body("las de siempre"))
        self.assertEqual(len(self.ok("history", "1")), 6)

    # --- replace ---
    BODY_R = ("## Qué es\n\n## Reglas\n\nEl agua cuesta dinero.\nEl precio es fijo.\n\n"
              "## Configuración\n\nEl precio es fijo.\n\n## Más adelante")

    def test_replace(self):
        self.add("spec", "A", "--body", self.BODY_R)
        self.assertEqual(self.ok("replace", "1", "cuesta dinero", "es gratis"), ["#1 v2"])
        self.assertIn("El agua es gratis.", self.body(1))
        self.assertIn("not found in #1", self.fails("replace", "1", "no existe", "x"))
        self.assertIn("found 2 times", self.fails("replace", "1", "El precio es fijo.", "x"))
        self.assertEqual(self.body(1).count("El precio es fijo."), 2)  # a refused replace changes nothing
        self.ok("replace", "1", "El precio es fijo.", "El precio varía.", "--section", "configuración")
        self.assertIn("## Configuración\n\nEl precio varía.\n\n## Más adelante", self.body(1))
        self.assertIn("El agua es gratis.\nEl precio es fijo.", self.body(1))  # the other copy untouched
        self.assertIn("not found in section 'Reglas'", self.fails("replace", "1", "varía", "x", "--section", "Reglas"))
        self.assertIn("section 'Configuración'", self.fails("replace", "1", "agua", "x", "--section", "Configuración"))  # errors in UTF-8
        self.ok("replace", "1", "--old-file", "-", "--new-file", os.devnull, stdin="gratis.\r\nEl precio")
        self.assertIn("El agua es  es fijo.", self.body(1))  # multi-line old text from stdin, new one empty
        self.assertIn("only one of", self.fails("replace", "1", "--old-file", "-", "--new-file", "-", stdin="x"))
        self.assertIn("empty text", self.fails("replace", "1", "", "x"))
        self.assertEqual(len(self.ok("history", "1")), 4)  # one version per replace, none for refusals
        self.assertIn("is at v4, not v3", self.fails("replace", "1", "agua", "riego", "--if-version", "3"))
        self.ok("replace", "1", "agua", "riego", "--if-version", "4")
        self.assertIn("not v1", self.fails("set", "1", "title=B", "--if-version", "1"))
        self.assertIn("not v1", self.fails("section", "1", "Reglas", "--set", "x", "--if-version", "1"))
        self.assertIn("not v1", self.fails("add-section", "1", "Nueva", "--if-version", "1"))
        self.ok("set", "1", "title=B", "--if-version", "5")
        self.assertEqual(self.ok("section", "1", "Reglas", "--if-version", "1"), self.ok("section", "1", "Reglas"))  # reads ignore it

    # --- ids with # ---
    # Every id argument takes the id as `add` prints it and as a reference writes it, `#N`, or bare
    # (Known issues #18, #21).
    def test_hash_ids(self):
        new_id = self.ok("add", "spec", "A")[0]
        self.assertEqual(new_id, "#1")
        self.add("feature", "B", "--body", self.make_body("feature", {"Specs": "#1"}))
        self.ok("note", new_id, "with #")
        self.ok("rank", "#2", "1")
        self.ok("set", "#2", "subject=Parcela")
        self.assertTrue(self.ok("show", new_id)[-1].endswith(": with #"))
        self.assertEqual(self.ok("next")[0].split()[1], "#2")
        self.assertEqual(self.ok("list", "--mentions", "#1")[0].split()[0], "#2")
        self.assertEqual(self.ok("refs", "#1")[-1].split()[0], "#2")
        self.assertEqual(self.ok("section", "#2", "Specs"), ["#1"])
        for bad in ("##1", "#", "#x", "1#"):
            code, _, err = self.run_track("show", bad)
            self.assertNotEqual(code, 0, bad)
            self.assertIn("invalid item id", err)

    # --- fixed sections ---
    # Write an off-template body straight into the latest version, past the CLI, as the items made
    # before the sections were fixed have one.
    def force_body(self, item_id, body):
        con = sqlite3.connect(self.db)
        with con:
            con.execute("UPDATE versions SET body = ? WHERE item_id = ? AND version = "
                        "(SELECT MAX(version) FROM versions WHERE item_id = ?)", (body, item_id, item_id))
        con.close()

    def test_templates(self):
        for item_id, (type_, titles) in enumerate(self.SECTIONS.items(), start=1):
            self.add(type_, type_)  # no body: the type's sections, empty
            headings = ["## " + title for title in titles]
            self.assertEqual(self.ok("sections", str(item_id)), headings, type_)
            self.assertEqual(self.body(item_id), "\n\n".join(headings))
        good = "## Qué hay que hacer\n\nAlgo.\n\n### Detalle\n\nMás.\n\n## Specs\n\n#1\n\n## Fuera de alcance"
        self.add("feature", "Bien", "--body", good)  # subsections are free
        refused = {
            "missing": "## Qué hay que hacer\n\n## Specs",
            "extra": good + "\n\n## Otra",
            "level 1": "# Qué hay que hacer\n\n## Specs\n\n## Fuera de alcance",
            "order": "## Specs\n\n## Qué hay que hacer\n\n## Fuera de alcance",
            "renamed": "## qué hay que hacer\n\n## Specs\n\n## Fuera de alcance",
            "text before": "Intro.\n\n## Qué hay que hacer\n\n## Specs\n\n## Fuera de alcance",
            "free text": "Sin secciones.",
        }
        for case, body in refused.items():
            self.assertIn("does not follow the feature sections", self.fails("add", "feature", case, "--body", body), case)
        self.assertEqual(len(self.ok("list")), 6)  # nothing refused was added
        # Every body write is checked; a refused one changes nothing.
        self.assertIn("does not follow", self.fails("replace", "6", "## Specs\n\n", ""))
        self.assertIn("does not follow", self.fails("section", "6", "Specs", "--set", "#1\n\n## Nueva"))
        self.assertIn("does not follow", self.fails("set", "6", "body=Nada"))
        self.assertIn("does not follow the bug sections", self.fails("set", "6", "type=bug"))
        self.assertEqual(self.body(6), good)
        self.assertEqual(len(self.ok("history", "6")), 1)
        self.ok("set", "6", "type=debt")  # the same sections: allowed
        self.ok("set", "6", "type=bug", "body=" + self.make_body("bug", {"Qué se ve": "Falla."}))
        self.assertEqual(self.ok("section", "6", "Qué se ve"), ["Falla."])
        # An old off-template item still takes changes that leave its body alone.
        self.force_body(2, "## Qué es\n\nViejo.")
        self.ok("set", "2", "status=doing", "subject=Viejo")
        self.ok("note", "2", "nota")
        self.ok("close", "2")
        self.assertIn("does not follow", self.fails("replace", "2", "Viejo", "Nuevo"))

    def test_add_section_only_subsections(self):
        self.add("feature", "A")
        self.assertIn("only subsections", self.fails("add-section", "1", "## Nueva"))
        self.assertIn("only subsections", self.fails("add-section", "1", "Nueva", "--level", "2"))
        self.assertIn("only subsections", self.fails("add-section", "1", "# Nueva"))
        self.ok("add-section", "1", "Detalle", "--after", "Specs", "--body", "uno")
        self.assertEqual(self.ok("section", "1", "Specs"), ["### Detalle", "uno"])
        self.assertEqual(len(self.ok("history", "1")), 2)

    def test_sections_check(self):
        self.add("spec", "Bien")
        self.add("debt", "Vieja")
        self.add("problem", "Borrado")
        self.assertEqual(self.ok("sections", "--check"), [])
        self.force_body(2, "## Qué es\n\nAlgo.\n\n## Qué hay que hacer\n\nArreglarlo.")
        self.force_body(3, "Texto suelto.")
        self.ok("delete", "3")  # deleted items are not checked
        lines = self.ok("sections", "--check")
        self.assertEqual(lines[0].split()[:2], ["#2", "debt"])
        self.assertEqual(lines[1], "  expected: ## Qué hay que hacer, ## Specs, ## Fuera de alcance; "
                                   "found: ## Qué es, ## Qué hay que hacer")
        self.assertEqual(len(lines), 2)
        rows = json.loads("\n".join(self.ok("--json", "sections", "--check")))
        self.assertEqual([(r["item_id"], r["type"]) for r in rows], [(2, "debt")])
        self.assertIn("expected:", rows[0]["problem"])
        self.assertIn("an id or --check", self.fails("sections"))

    def test_section_across_items(self):
        self.add("feature", "Uno", "--rank", "1", "--body", self.make_body("feature", {"Qué hay que hacer": "Hacer uno.\n\n### Paso\n\nA."}))
        self.add("spec", "Dos", "--rank", "2")
        self.add("bug", "Tres", "--rank", "3", "--body", self.make_body("bug", {"Qué hay que hacer": "Hacer tres."}))
        self.add("debt", "Cuatro", "--subject", "Otro")
        lines = self.ok("next", "--section", "qué hay que hacer")
        self.assertEqual([line.split()[1] for line in (lines[0], lines[7], lines[10])], ["#1", "#2", "#3"])
        self.assertEqual(lines[1:6], ["Hacer uno.", "", "### Paso", "", "A."])
        self.assertEqual((lines[6], lines[9]), ("", ""))  # a blank line between items
        self.assertEqual(lines[8], "(a spec has no section 'Qué hay que hacer')")
        self.assertEqual(lines[11], "Hacer tres.")
        self.assertEqual(len(lines), 12)
        lines = self.ok("list", "--subject", "Otro", "--section", "Specs")
        self.assertEqual((lines[0].split()[0], lines[1:]), ("#4", []))  # empty section: nothing under the line
        rows = json.loads("\n".join(self.ok("--json", "next", "--section", "Qué hay que hacer")))
        self.assertEqual([r["section"] for r in rows], ["Hacer uno.\n\n### Paso\n\nA.", None, "Hacer tres."])
        self.force_body(3, "Viejo.")
        self.assertEqual(self.ok("next", "--section", "Qué hay que hacer")[-1], "(no section 'Qué hay que hacer')")
        self.assertIn("no type has a section 'Nada'", self.fails("next", "--section", "Nada"))

    # --- questions and answers ---
    def test_questions(self):
        self.add("feature", "Stock", "--subject", "Tienda")
        self.add("spec", "Semillas")
        self.ok("note", "1", "Una nota normal.")
        self.assertEqual(self.ok("ask", "1", "¿Dónde se separan? Propuesta: dos apartados."), ["note 2"])
        self.assertEqual(self.ok("ask", "#2", "-", stdin="¿Cuántas?\r\nPropuesta: 10."), ["note 3"])
        lines = self.ok("show", "1")
        self.assertTrue(lines[-2].endswith(": Una nota normal."), lines[-2])
        self.assertIn(" [question 2, open]: ¿Dónde se separan?", lines[-1])
        lines = self.ok("questions")
        self.assertEqual(lines[0].split()[:4], ["note", "2", "#1", "feature"])
        self.assertEqual(lines[1], "  ¿Dónde se separan? Propuesta: dos apartados.")
        self.assertEqual(lines[2].split()[:3], ["note", "3", "#2"])
        self.assertEqual(lines[3:], ["  ¿Cuántas?", "  Propuesta: 10."])
        # An answer is a note of the same item, joined to its question, which is then closed.
        self.assertEqual(self.ok("answer", "2", "Dos apartados, como se propuso."), ["note 4"])
        lines = self.ok("show", "1")
        self.assertIn(" [question 2, answered in 4]: ", lines[-2])
        self.assertIn(" [answer 4 to 2]: Dos apartados, como se propuso.", lines[-1])
        self.assertEqual(self.ok("questions")[0].split()[:3], ["note", "3", "#2"])
        notes = json.loads("\n".join(self.ok("--json", "show", "1")))["notes"]
        self.assertEqual([(n["id"], n["question"], n["answered_by"], n["answers"]) for n in notes],
                         [(1, 0, None, []), (2, 1, 4, []), (4, 0, None, [2])])
        rows = json.loads("\n".join(self.ok("--json", "questions")))
        self.assertEqual([(r["note_id"], r["item_id"], r["text"]) for r in rows], [(3, 2, "¿Cuántas?\nPropuesta: 10.")])
        self.assertIn("note 2 is already answered (note 4)", self.fails("answer", "2", "Otra"))
        self.assertIn("note 1 is not a question", self.fails("answer", "1", "x"))
        self.assertIn("no note 99", self.fails("answer", "99", "x"))
        self.assertIn("empty note", self.fails("ask", "1", ""))
        # Closing an item with an open question warns, and still closes it.
        code, _, err = self.run_track("close", "2")
        self.assertEqual(code, 0)
        self.assertIn("#2 is closed with an open question: note 3", err)
        self.assertEqual(self.ok("questions")[0].split()[:3], ["note", "3", "#2"])  # still open
        self.ok("delete", "2")
        self.assertEqual(self.ok("questions"), [])  # deleted items have none
        # Questions survive a rebuild from the dump.
        os.remove(self.db)
        self.assertIn(" [answer 4 to 2]: ", self.ok("show", "1")[-1])

    # An existing note can be marked as a question or as an answer, and one answer can close several
    # questions: how the notes written before ask/answer existed become questions and answers.
    def test_questions_from_existing_notes(self):
        self.add("feature", "A")
        self.add("feature", "B")
        self.ok("note", "1", "Pregunta abierta: ¿uno?")  # note 1
        self.ok("note", "1", "Pregunta abierta: ¿dos?")  # note 2
        self.ok("note", "2", "Otra cosa.")  # note 3
        self.ok("note", "1", "Respuesta: uno y dos.")  # note 4
        self.ok("note", "2", "Pregunta abierta: ¿tres?")  # note 5
        self.assertEqual(self.ok("ask", "1", "--note", "1"), ["note 1"])
        self.ok("ask", "#1", "--note", "2")
        self.ok("ask", "2", "--note", "5")
        self.assertIn("note 3 is not a note of #1", self.fails("ask", "1", "--note", "3"))
        self.assertIn("note 1 is already a question", self.fails("ask", "1", "--note", "1"))
        self.assertIn("a text or --note, not both", self.fails("ask", "1", "x", "--note", "4"))
        self.assertIn("no note 99", self.fails("ask", "1", "--note", "99"))
        self.assertEqual([line.split()[1] for line in self.ok("questions") if line.startswith("note")], ["1", "2", "5"])
        # The refused answers change nothing.
        self.assertIn("note 3 is not a note of #1", self.fails("answer", "1", "--note", "3"))
        self.assertIn("note 2 is a question", self.fails("answer", "1", "--note", "2"))
        self.assertIn("note 1 is older than question 2", self.fails("answer", "2", "--note", "1"))
        self.assertIn("questions of different items", self.fails("answer", "1,5", "Las dos."))
        self.assertIn("a text or --note, not both", self.fails("answer", "1", "x", "--note", "4"))
        code, _, err = self.run_track("answer", "1,x", "x")
        self.assertNotEqual(code, 0)
        self.assertIn("invalid note ids", err)
        self.assertEqual(len(self.ok("questions")), 6)
        # One note answers both questions of #1.
        self.assertEqual(self.ok("answer", "1,2", "--note", "4"), ["note 4"])
        lines = self.ok("show", "1")
        self.assertIn(" [question 1, answered in 4]: Pregunta abierta: ¿uno?", lines[-3])
        self.assertIn(" [question 2, answered in 4]: ", lines[-2])
        self.assertIn(" [answer 4 to 1, 2]: Respuesta: uno y dos.", lines[-1])
        notes = json.loads("\n".join(self.ok("--json", "show", "1")))["notes"]
        self.assertEqual([(n["id"], n["answered_by"], n["answers"]) for n in notes], [(1, 4, []), (2, 4, []), (4, None, [1, 2])])
        self.assertIn("note 1 is already answered (note 4)", self.fails("answer", "1", "--note", "4"))
        self.assertEqual([line.split()[1] for line in self.ok("questions") if line.startswith("note")], ["5"])
        self.assertEqual(self.ok("answer", "5", "Tres."), ["note 6"])  # a new answer note, as before
        self.assertEqual(self.ok("questions"), [])

    # --- show --expand ---
    def test_show_expand(self):
        self.add("spec", "Parcela")
        self.add("spec", "Borrada")
        body = self.make_body("feature", {"Specs": "#1, #2 y #9. C#1 no cuenta."})
        self.add("feature", "Suelo", "--body", body)
        self.ok("note", "3", "Como dice #1.")
        self.ok("delete", "2")
        expanded = self.make_body("feature", {"Specs": "#1 «Parcela», #2 (deleted) y #9 (missing). C#1 no cuenta."})
        lines = self.ok("show", "3", "--expand")
        self.assertEqual("\n".join(lines[3:-2]), expanded)
        self.assertTrue(lines[-1].endswith(": Como dice #1 «Parcela»."), lines[-1])
        self.assertEqual("\n".join(self.ok("show", "3")[3:-2]), body)  # without --expand, as stored
        item = json.loads("\n".join(self.ok("--json", "show", "3", "--expand")))
        self.assertEqual((item["body"], item["expanded_body"]), (body, expanded))  # the raw text stays
        self.assertEqual([(n["text"], n["expanded_text"]) for n in item["notes"]], [("Como dice #1.", "Como dice #1 «Parcela».")])
        self.assertNotIn("expanded_body", json.loads("\n".join(self.ok("--json", "show", "3"))))

    # --- sections file ---
    # The sections belong to the project (their titles are in its language): they are read from the
    # sections file next to the database, never from the code.
    def test_sections_file(self):
        english = {"spec": ["What", "Rules"], "feature": ["To do", "Specs"], "bug": ["Seen", "To do"],
                   "debt": ["To do"], "problem": ["What"]}
        self.write_sections(english)
        self.add("spec", "Physics")
        self.assertEqual(self.ok("sections", "1"), ["## What", "## Rules"])
        code, _, err = self.run_track("add", "feature", "Step", "--body", "## To do\n\nIt.\n\n## Specs\n\n#1")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("does not follow the feature sections", self.fails("add", "feature", "x", "--body", self.make_body("feature")))
        self.assertEqual(self.ok("next", "--section", "to do"), [])
        self.assertIn("no type has a section 'Reglas'", self.fails("list", "--section", "Reglas"))
        code, _, err = self.run_track("add", "feature", "Other", "--body", "## To do\n\n## Specs\n\n#2")
        self.assertIn("mentions #2 in Specs, which is a feature, not a spec", err)
        # A project that names no Specs section has no such check.
        self.write_sections(english, specs_section=None)
        code, _, err = self.run_track("add", "feature", "Third", "--body", "## To do\n\n## Specs\n\n#2")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.ok("refs", "--check"), [])
        # Only what needs the sections reads the file: without it the rest works, and a body write
        # or a section lookup fails saying so.
        os.remove(self.sections)
        self.assertEqual(len(self.ok("list")), 4)
        self.ok("note", "1", "Como #2.")
        self.ok("set", "1", "status=doing")
        self.assertIn("no sections file", self.fails("add", "spec", "y"))
        self.assertIn("no sections file", self.fails("sections", "--check"))
        # A broken file is refused, saying why, and nothing is written.
        for broken in ("{", '{"sections": {"spec": ["What"]}, "specs_section": null}',
                       '{"sections": {"spec": [], "feature": ["a"], "bug": ["a"], "debt": ["a"], "problem": ["a"]}, "specs_section": null}'):
            with open(self.sections, "w", encoding="utf-8") as f:
                f.write(broken)
            self.assertIn("bad sections file", self.fails("add", "spec", "y"))
        self.assertEqual(len(self.ok("list")), 4)

    # --- tracker folder ---
    # Every file the tracker uses is in one folder, given by --dir or TRACKER_DIR (--dir first);
    # without either, or with a path that is not a folder, nothing runs.
    def test_tracker_folder(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        with open(os.path.join(other.name, "tracker.sections.json"), "w", encoding="utf-8") as f:
            json.dump({"specs_section": "Specs", "sections": self.SECTIONS}, f, ensure_ascii=False)
        self.add("spec", "Here")
        code, lines, err = self.run_track("add", "spec", "There", folder=None, tracker_dir=other.name)
        self.assertEqual((code, lines), (0, ["#1"]), err)
        self.assertEqual(sorted(os.listdir(other.name)), ["tracker.db", "tracker.dump.sql", "tracker.sections.json"])
        code, lines, err = self.run_track("list", tracker_dir=other.name)  # --dir wins over TRACKER_DIR
        self.assertEqual([line.split()[-1] for line in lines], ["Here"])
        code, _, err = self.run_track("list", folder=None)
        self.assertEqual(code, 1)
        self.assertIn("no tracker folder: pass --dir PATH or set TRACKER_DIR", err)
        missing = os.path.join(self.dir.name, "missing")
        code, _, err = self.run_track("list", folder=missing)
        self.assertEqual(code, 1)
        self.assertIn(f"not a folder: {missing}", err)
        self.assertFalse(os.path.exists(missing))  # nothing created

    # --- init ---
    # `init` makes a project's tracker folder: the launchers, the configuration, the starting
    # sections in the project's language, an empty database with its dump and where the tracker is.
    # It creates the folder when missing and never overwrites anything.
    def test_init(self):
        tool = os.path.dirname(os.path.dirname(TRACK))
        target = os.path.join(self.dir.name, "Project", "Tracker")  # not there yet
        code, lines, err = self.run_track("init", "--language", "es", folder=target)
        self.assertEqual((code, lines), (0, [f"created {target}"]), err)
        self.assertEqual(sorted(os.listdir(target)), [
            ".gitignore", "find-tracker.bat", "known-issues.md", "tool-path.txt", "track.bat", "track.init.bat",
            "tracker.db", "tracker.dump.sql", "tracker.json", "tracker.sections.json", "tracker_gui.bat"])
        with open(os.path.join(target, "tool-path.txt"), encoding="utf-8") as f:
            self.assertEqual(os.path.normcase(f.read().strip()), os.path.normcase(tool))
        with open(os.path.join(target, "tracker.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"language": "es"})
        for name in (".gitignore", "track.bat", "track.init.bat", "tracker_gui.bat", "find-tracker.bat", "known-issues.md"):
            with open(os.path.join(tool, "Templates", name), "rb") as template, open(os.path.join(target, name), "rb") as copy:
                self.assertEqual(copy.read(), template.read(), name)  # copied as it is
        # The folder works at once, with the starting sections of its language.
        self.assertEqual(self.run_track("add", "spec", "Una", folder=target)[0], 0)
        self.assertEqual(self.run_track("sections", "1", folder=target)[1], ["## Qué es", "## Reglas", "## Más adelante"])
        english = os.path.join(self.dir.name, "Other")
        self.assertEqual(self.run_track("init", "--language", "en", folder=english)[0], 0)
        self.assertEqual(self.run_track("add", "feature", "One", folder=english)[0], 0)
        self.assertEqual(self.run_track("sections", "1", folder=english)[1], ["## What to do", "## Specs", "## Out of scope"])
        # Never over a tracker folder: refused, and nothing changed.
        with open(os.path.join(target, "tracker.db"), "rb") as f:
            before = f.read()
        code, _, err = self.run_track("init", "--language", "en", folder=target)
        self.assertEqual(code, 1)
        self.assertIn(f"already a tracker folder: {target}", err)
        with open(os.path.join(target, "tracker.db"), "rb") as f:
            self.assertEqual(f.read(), before)
        with open(os.path.join(target, "tracker.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"language": "es"})
        self.assertNotEqual(self.run_track("init", "--language", "fr", folder=os.path.join(self.dir.name, "x"))[0], 0)
        self.assertIn("no tracker folder", self.run_track("init", "--language", "en", folder=None)[2])

    # --- guide ---
    # `guide` prints the reference (tracker.md, at the root of the tracker repository) as it is, so
    # an agent reads it through its project's launcher without knowing where the tracker is. It
    # needs no tracker folder.
    def test_guide(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(TRACK)), "tracker.md"), encoding="utf-8") as f:
            reference = f.read()
        code, lines, err = self.run_track("guide")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual("\n".join(lines), reference.rstrip("\n"))
        self.assertTrue(lines[0].startswith("# "))
        self.assertEqual(self.run_track("guide", folder=None)[1], lines)

    # --- columns ---
    def test_columns(self):
        self.add("feature", "Título uno", "--subject", "Visión general larga")
        self.add("feature", "Título dos", "--subject", "Corto")
        lines = self.ok("list")
        self.assertIn("Visión general larga  Título uno", lines[0])
        self.assertEqual(lines[0].index("Título"), lines[1].index("Título"))  # titles aligned
        self.assertEqual(self.ok("list", "--subject", "Corto"), ["#2    feature  open    Corto        Título dos"])  # short: as before


if __name__ == "__main__":
    unittest.main(verbosity=1)
