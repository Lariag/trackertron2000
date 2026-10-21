# Tracker

The store of a project's specification and of everything to do, being done and done: specs,
features, bugs, debt and potential problems, kept in a small SQLite database and used only through a
command-line tool that prints a few lines per question. "What is next?" or "what is open about X?"
costs a line of output, not a long file.

This is the reference: how the tracker works and how to use it. `README.md` explains how a project
sets it up. In a project, run every command through its tracker folder's launcher,
`<tracker folder>\track.bat <command>` (`Tracker\track.bat` when the folder is `Tracker/` at the
project's root, as usual); `track.bat guide` prints this file.

## Rules of use

- **Use the CLI, never the files.** Never open the tracker folder's `tracker.db` or
  `tracker.dump.sql` as text, nor grep them: ask the CLI.
- **Ask, don't read.** `track next` is what is next; `track list --subject X` is what is open
  there; `track show ID` is one item in full, read only when working on it.
- **Change the smallest piece you can**: one exact text with `track replace`, or one section
  (`sections`, `section`, `section --set`, `add-section`). Never rewrite a whole body to change a
  line.
- **Pass the version you read** (`--if-version N`) on writes that rewrite a body, so an edit made
  meanwhile in the GUI is never overwritten unseen.
- **Multi-line text goes through stdin** (`-`), not temporary files, and never inline: cmd, which runs
  the launchers, keeps only the first line of an argument.
- **Search and follow references with the CLI**: `track list --search "words"` finds items by
  text; `track refs ID` shows what an item mentions and what mentions it;
  `track list --type feature --mentions 7` is "which features implement spec #7".
- **Write as things happen.** `track add` when something is agreed, `track note` when evidence
  lands, `track set ID status=doing` before starting work on an item, `track close ID "what
  landed"` when it is done. The report to the user names the `#id`.
- **Open questions are questions**: `track ask ID "..."` with the recommended proposal, the user's
  answer with `track answer NOTE "..."`, and what is decided goes into the item's body or its spec.
  `track questions` lists those still open.
- **The GUI is the user's**, not the agent's. The agent uses the CLI.
- **Never change the tracker repository** while using the tracker: everything a project's tracker
  writes is in its tracker folder.

## Data model

One database, `tracker.db` in the tracker folder. **Nothing is overwritten or physically deleted**:
an item is a chain of versions, each change appends one, a delete is a version flagged `deleted`,
notes are append-only. Only the rank order lives outside the versions (a position, not part of the
document).

**items**: `id` (integer, assigned once, never reused; the `#42` everything refers to), `created`.

**versions**: one row per change of an item; the row with the highest `version` *is* the item.

| column | meaning |
|---|---|
| `item_id`, `version` | which item, `1..n` |
| `changed` | `YYYY-MM-DD HH:MM` of this version |
| `deleted` | `1` on a logically deleted item (hidden from every command unless asked; `restore` appends a version with `0`) |
| `type` | `spec` (a piece of the specification: what the project or one of its systems is and how it works; the body is the spec text), `feature` (something to build), `bug` (wrong behaviour, seen), `debt` (does not change behaviour: performance, code quality, tooling), `problem` (not wrong yet, but may make things misbehave later) |
| `status` | `draft` (wanted, still being defined), `open` (defined, waiting), `doing` (in progress), `done`, `dropped` |
| `subject` | free text, by convention a subject of the spec, or empty |
| `title` | one line |
| `body` | markdown, any length, in the type's fixed sections (see below) |
| `closed` | `YYYY-MM-DD`, set when the status becomes `done` or `dropped`, cleared when reopened |

**ranks**: `item_id`, `rank` - position in the "next" order, integers `1..k` over the `open`/`doing`
items that have one; absent = backlog. Closing, dropping or deleting removes the rank and renumbers
the rest. Rank changes make no version.

**notes**: `id`, `item_id`, `date` (`YYYY-MM-DD HH:MM`), `text` (markdown). A running log per item:
what was tried, what was measured, what was decided. A bug investigation is its notes.

**questions**: `note_id` - the notes that are questions. **answers**: `question_id`, `note_id` - the
note that answers each question: a question has one answer, and one note (of the same item, later
than its questions) can answer several. A question is open until it has an answer. Like notes, they
are never changed or removed. The decision an answer brings still goes into the item's body or its
spec by hand: the notes keep how it was decided, the body what is decided.

Rules the schema encodes:
- **Type is what the thing is and never changes by itself**; status is the phase it is in. "A
  feature still being defined" is `feature` + `draft`.
- **`next` is a position, not a status.** Statuses have a lifecycle order
  (`draft → open → doing → done|dropped`); the priority order is `rank`, and only `open`/`doing`
  items have one.
- **`debt` and `problem` are different things**: debt never makes anything misbehave (it costs
  performance, clarity or time); a problem is something that may make behaviour go wrong.

## Commands

One item is one line: id, type, status, subject, title; in `next` the line starts with the rank,
or `-` for a `doing` item without one. Two examples, from two projects in two languages:

```
#42  bug      doing   Economía     Embargo not applied on sale
#42  bug      doing   Multiplayer  A root change desyncs a client on a dedicated server
```

Every `ID` argument (and `--mentions ID`) takes the id bare or with its `#` (`42` or `#42`), so what
`add` prints can be passed straight to the next command.

| command | does |
|---|---|
| `track guide` | print this reference |
| `track init --language en\|es` | make a tracker folder (see "The tracker folder"); normally run through the repository's `Tracker\init.bat` |
| `track next [-n N] [--section TITLE]` | the ranked list: `doing` items first, then `open` by rank; `N` lines (default 10). Unranked open items are not shown (`track list --status open` shows them). `--section`: see below |
| `track list [--type T] [--status S] [--subject X] [--all] [--deleted] [--search TEXT] [--mentions ID]` | one line per matching item. Without `--status`, closed items are excluded unless `--all`; `--deleted` lists the deleted items instead. `--search`: every word of `TEXT` must appear, in any order and ignoring case, in the title, subject, body or notes (the same rule the GUI uses, by asking the CLI). `--mentions ID`: only items whose body mentions `#ID`. `--section TITLE`: each line followed by that section's content (see below) |
| `track refs ID [--type T]` | both directions of an item's references: the items its body and notes mention (a missing or deleted id is listed as such) and the items whose body or notes mention it; a reference only in notes says `(in notes)`. `--type` keeps only references of that type |
| `track refs --check` | every wrong reference in the bodies of the live items, by item: `Specs: #12 is deleted`. Notes are never checked |
| `track show ID [--version N] [--deleted] [--expand]` | the header, the body (raw markdown) and the notes, oldest first; a question is marked `[question N, open]` or `[question N, answered in M]`, an answer `[answer M to N, N2]`. `--version N` shows an older version, `--deleted` allows a deleted item. `--expand` follows each reference of the body and the notes with what it names: `#12 «Title»`, `#12 (deleted)` or `#12 (missing)` |
| `track history ID` | one line per version: `vN date type status subject title [DELETED]` |
| `track add TYPE "title" [--subject X] [--status draft\|open] [--body TEXT \| --body-file PATH] [--rank N]` | new item; default status `open`, unranked. Without a body, the body is the type's sections, empty; a body given must follow them. Prints the new id |
| `track sections ID` | the body's markdown headings, one per line |
| `track sections --check` | every live item whose body does not follow its type's sections, each followed by what was expected and what was found; nothing when all do |
| `track section ID TITLE` | one section's content (heading line excluded) |
| `track section ID TITLE --set TEXT` / `--set-file PATH` | replace that section's content, heading kept, the rest of the body untouched; fails if there is no such section |
| `track add-section ID TITLE [--body TEXT \| --body-file PATH] [--level N] [--after TITLE]` | insert a subsection: at the end of the body (default), or at the end of a section's content, after its own subsections. The `#`s in `TITLE` set the level, else `--level` (default 3). Only subsections (`###` or deeper): fails for a `##` or `#`, if the title exists or if `--after`'s does not |
| `track replace ID OLD [NEW] [--old-file PATH] [--new-file PATH] [--section TITLE] [--if-version N]` | replace `OLD` with `NEW` (empty `NEW` deletes it) in the body. `OLD` must appear exactly once (in that section with `--section`): zero or several matches fail and change nothing, saying how many were found; add context until it is unique. Prints `#ID vN` |
| `track note ID "text"` (or `--file PATH`) | append a dated note |
| `track ask ID "text"` (or `--file PATH`, or `--note N`) | append a question note (with the recommended proposal in its text); prints `note N`. `--note N` marks the item's existing note `N` as a question instead (how notes written before `ask` existed become questions) |
| `track answer N[,N2...] "text"` (or `--file PATH`, or `--note M`) | append, to the questions' item, the note that answers question notes `N` (one or several, all of one item), which closes them; prints `note M`. `--note M` marks the existing note `M` as the answer instead: it must be of the same item, later than every question, and not a question. Fails if a note is not a question or is already answered |
| `track questions` | every unanswered question of the live items, oldest first: `note N` and the item's line, then the question's text indented |
| `track set ID field=value ...` | change `title`, `type`, `status`, `subject`, `rank`, `body` (`body=@PATH` reads a file). `status=done/dropped` behaves like `close`/`drop` |
| `track close ID ["note"]` / `track drop ID ["note"]` | status `done`/`dropped`, `closed` = today, rank cleared, optional final note. Warns when the item still has open questions |
| `track rank ID N` | insert the item at position `N` of the ranked list (shifting the rest); `N = 0` sends it to the backlog. Only `open`/`doing` items can be ranked |
| `track delete ID` / `track restore ID` | logical delete (the item disappears from every command, its rank is removed) and its undo. `delete` warns when live bodies still mention the item |
| `track subjects` | the distinct subjects with their open counts |
| `track export DIR` | write the latest, non-deleted items as markdown files into a new `DIR/tracker_export_<YYYY-MM-DD_HHMMSS>/`; prints the folder. Reads only |
| `track dump` | rewrite the SQL dump (done automatically after every change) |

**Text input:** every text option takes a file path or `-` for stdin: `add --body-file`,
`set body=@PATH`, `section --set-file`, `add-section --body-file`, `note --file`,
`replace --old-file/--new-file`. An inline text that is exactly `-` reads stdin too (`--body -`,
`section --set -`, `set body=-`, `note ID -`, `replace ID - NEW`): a lone `-` is never stored as
text. Only one text per command can read stdin, and empty stdin (nothing, or only blank lines) is
refused with nothing written, since it means the pipe failed. Whatever the source (inline, file,
stdin), line breaks are normalized to `\n`; text from a file or stdin also loses its trailing line
breaks.

**`--if-version N`** on `set`, `section --set`, `add-section` and `replace` refuses the write
unless the item is still at version `N` (`show` prints it as `vN`).

**Line format:** the subject column widens to the longest subject of each output and always leaves
at least two spaces before the title; with short subjects it is 12 characters as always.

**Sections** are the body's markdown headings (`#` to `######` followed by a space), outside fenced
code blocks (between ```` ``` ```` or `~~~` fences), so a code example may have a `#` comment at column 0;
a fence never closed makes the rest of the body code. A title given
to a command is normalized before matching: leading `#`s and surrounding spaces are dropped and case
is ignored. A section runs to the next heading of the same or a higher level, so its subsections are
part of it.

**Fixed sections.** Every type's body has the same sections (`##`), in the same order. They belong
to the project, not to the tracker (their titles are in the project's language), so they live in
the tracker folder's **sections file**, `tracker.sections.json`:

```json
{
  "specs_section": "Specs",
  "sections": {"spec": ["What it is", "..."], "feature": ["..."], "bug": ["..."], "debt": ["..."], "problem": ["..."]}
}
```

`sections` lists every type's titles, in order; `specs_section` names the section whose references
must be specs, or is `null` for none. The file is read only by what needs it (a body write,
`--section`, `sections --check`, the Specs check of `refs --check` and of the warnings); a missing or
broken file makes those fail, saying why. `init` writes a generic starting set in the project's
language; each project then makes it its own. Two examples:

| type | a game written in Spanish | a physics sandbox written in English |
|---|---|---|
| `spec` | Qué es, Reglas, Configuración, Más adelante | What it is, Rules, How it works, Files, Tests, Known gaps |
| `feature` | Qué hay que hacer, Specs, Fuera de alcance | What to do, Why, Plan, Specs, Out of scope |
| `bug` | Qué se ve, Causa probable, Qué hay que hacer, Specs, Fuera de alcance | What is seen, Cause, What to do, Specs, Out of scope |
| `debt` | Qué hay que hacer, Specs, Fuera de alcance | What to do, Why, Plan, Specs, Out of scope |
| `problem` | Qué es, Posible solución, Specs | What it is, When it would bite, Possible fix, Specs |

A body has exactly its type's sections, spelled exactly so, and nothing before the first one;
subsections (`###` and deeper) are free inside them. Every write that changes a body or a type
(`add`, `set body=`, `set type=`, `section --set`, `add-section`, `replace`) is checked, and refused
with nothing written when the result does not follow the sections, saying what was expected and
what was found. An old item that does not follow them (written before the sections changed) still
takes every change that leaves its body alone (status, rank, notes...); `sections --check` lists
those items. So the sections are best settled before the first items are written.

**One section across items:** `next --section TITLE` and `list ... --section TITLE` print each item's
line followed by the content of that section (nothing when it is empty), with a blank line between
items. `TITLE` is matched like any section title, and must be a section of some type. An item whose
type has no such section says `(a spec has no section '...')`; an old item whose body lacks it, `(no
section '...')`. With `--json`, each row carries `section`: the text, or `null`.

**References** are read from the texts, not stored apart: a reference is `#<digits>` not glued to a
word or to another `#` (so `## Heading` and `C#1` are not references); it is the only way to refer to
an item. They are always as current as the texts. A reference is wrong when the id does not exist
or is deleted, or when it sits in the section the sections file names as `specs_section` (usually
**Specs**) and is not a spec (that section lists what the item implements or is about). A write with
a wrong reference (any body write, or `note`) still succeeds, with a `track: warning:` line on
stderr.

Bodies and notes are read differently:
- `refs ID` reads both, and says where a reference is.
- `list --mentions ID` reads the bodies only: it answers "which features implement spec #7", and a
  note that names a spec does not implement it.
- `refs --check` reads the bodies only: notes are history that is never edited, and a note that
  names an item deleted afterwards is not wrong.

**Export** writes `Specs/`, `Features/`, `Bugs/`, `Debt/`, `Problems/` with one `NNNN Title.md` per item, plus
the index files `Next steps.md`, `Drafts.md`, `Potential problems.md`, `Debt.md` and `Done.md`. The
`tracker_export_*/` folders are git-ignored when they are made inside the tracker folder.

**JSON.** `--json` before the command makes the reading commands print JSON (it is what the GUI reads).
**An item's id is always `item_id`, in every JSON output, and nothing else names an item**:
- **An item row** (`list`, `next`, `show`, and each entry of `refs` and `questions`): `item_id`, `version`,
  `changed`, `type`, `status`, `subject`, `title`, `body`, `closed`, `deleted`, `created`, `rank`. `list` adds
  `notes_text` (every note of the item, joined); `list`/`next --section` add `section`; `show` adds `notes` (and,
  with `--expand`, `expanded_body`); `questions` adds `note_id` (the question's note number), `asked` (its date)
  and `text`; a `refs` entry adds `in`.
- **A version row** (`history`, `show --version N`): the same columns as an item row's first ten, `item_id` to
  `deleted`; `show --version` adds `created` and a null `rank`.
- **A note** (each entry of `show`'s `notes`): `id` is **the note's own number** (what `note`, `ask` and
  `answer` print, and what `answer`/`ask --note` take), never an item; `item_id` is its item's. It also carries
  `date`, `text`, `question`, `answered_by` and `answers` (the list of questions it answers; and, with
  `--expand`, `expanded_text`).
- No row carries the database's internal row ids: the versions table's own `id` is left out on purpose (it once
  came through as `id` and read as an item's id named another item, or none). A database made before that is
  brought up to date the first time any command opens it.
- `refs` gives `{"mentions", "missing", "mentioned_by"}`, each entry with `in`: `["body"]`, `["notes"]` or
  both; `refs --check` gives one `{"item_id", "section", "ref", "problem"}` per wrong reference; `subjects` gives
  `{"subject", "open_count", "total"}`; `sections` gives `{"level", "title"}`; `section` the text alone.

**Every write says what it wrote**, one line each: `#ID vN` for a new version (`set`,
`section --set`, `add-section`, `replace`, `close`, `drop`, `delete`, `restore`), `note N on #ID` for a
note (`note`, and the final note of `close`/`drop`), `#ID rank N` or `#ID backlog` for a rank (`rank`,
`set rank=`). `add` prints the new id, and `ask`/`answer` the note number (`note N`). A write that writes
nothing prints nothing on stdout (its warning is on stderr).

Errors exit with code 1 and one line on stderr. Every write that changes an item appends exactly one
version; `note` and `rank` append none, and neither does a write that changes nothing:
- **A text that would leave the body as it is** (`replace`, `section --set`, `set body=` with
  nothing else changing) is refused with nothing written: writing a text means wanting a change.
  When the text was given in the command, the error names the likeliest cause, cmd keeping only its
  first line. `section --set` compares the content as `section` reads it, blank lines around it aside.
- **A field given the value it already has** (`set status=open` on an open item, `close` on a done
  one...) is no error: nothing is written, a `track: warning:` line says so, and the command exits 0.
  A `close` or `drop` with a note on an item already so still adds the note.

## The tracker folder

Everything a project's tracker needs is in one folder of the project, usually `Tracker/` at its root,
and the tracker writes nowhere else. The CLI is told which folder with `--dir PATH`, or the
`TRACKER_DIR` environment variable when `--dir` is not given; without either, or when the path is not
a folder, nothing runs. The folder's launchers always pass `--dir` with their own folder.

| file | what it is | in git |
|---|---|---|
| `tracker.db` | the database | yes |
| `tracker.dump.sql` | the database as SQL, rewritten after every write | yes |
| `tracker.sections.json` | each type's sections | yes |
| `tracker.json` | the project's configuration: `{"language": "en"}` or `"es"`, the language of its content | yes |
| `known-issues.md` | the project's log of problems with the tracker itself (never logged in the tracker) | yes |
| `track.bat` | the CLI on this folder: `track.bat <command>` | yes |
| `tracker_gui.bat` | the GUI on this folder | yes |
| `track.init.bat` | sets the tracker up on a machine: `track.init.bat [PATH_TO_THE_TRACKER]` | yes |
| `find-tracker.bat` | finds the tracker repository for the other launchers | yes |
| `.gitignore` | ignores `tool-path.txt` and the temporary files | yes |
| `tool-path.txt` | where the tracker repository is on this machine | no (local) |

The launchers find the tracker repository through the `TRACKER_HOME` environment variable when it
is set, else through `tool-path.txt`, which `init` writes and `track.init.bat PATH` rewrites (on a new
machine or a fresh clone).

## Storage and git

- `tracker.db` and `tracker.dump.sql` are both tracked in git. The CLI rewrites the dump after every
  write, so git history shows every change as text, and a lost database is rebuilt from it the first
  time the CLI runs.
- The dump is written whole into a temporary file next to it and then swapped in, so it is never
  left half written. A dump locked by another program is retried a few times; if it still cannot
  be written, the write command keeps its change (it is in the database), warns on stderr and exits
  0, and `track dump` (which does fail in that case) or the next write brings the dump up to date.

## Environment

Python 3, standard library only for the CLI; the GUI needs PySide6. Both run in the conda environment
`pw-tracker`, set up by the scripts of the repository's `Tracker/` folder:
- `env.bat` only activates it: no check, no creation, no installs and nothing on stdout, so the CLI
  starts fast and its JSON stays clean. Every launcher calls it. If the environment does not exist it
  fails, saying so on stderr.
- `env_install.bat` creates the environment if it is missing, activates it and installs a
  requirements file when it changed since the last install (`<file>.installed` stamp, git-ignored).
- `install.bat` runs `env_install.bat` for the CLI's and the GUI's requirements; `init.bat` and each
  project's `track.init.bat` call it.

## Tests

`Tracker/test_track.py` (`Tracker\test.bat` in the repository) runs the real CLI as a subprocess
against a temporary tracker folder per test and checks every command. It never touches a project's
folder.

## The GUI

A project's `tracker_gui.bat` opens a PySide6 window on its folder for the user. Everything it does
is a `track.py` call, so it can never do something the CLI cannot. Its rendered views (the body, the
notes, the history) show the texts from `show --expand`, so every reference carries its title. An
item is shown in one of two modes, switched with the Edit button or Ctrl+E: view mode (the default)
only reads, with the body and notes rendered and every field and writing action locked in place;
edit mode has the plain editor instead of the rendered body, the note input and the actions. In the
notes, a question is marked ❓ (open) or ✅ (answered) and an answer 💬, with the note numbers; the
❓ Questions button of the list keeps only the items with an open question (`track questions`),
closed ones included. Its search box asks `list --search` a moment after typing stops; the chips and
the subject filter work on the loaded rows.
