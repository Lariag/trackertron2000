# Known issues

The problems and limitations found while using the tracker, and what became of them. Each entry says
what happened, its impact and a possible solution; a fix is added under its entry, dated. Entries
are appended, never rewritten. Projects log their findings in their tracker folder's
`known-issues.md`; what matters is carried over here.

**Still open:** 6 (statuses and specs), 10 (no batch operations, an idea), 11 (no diff between
versions), 13 (unclosed files in the tests), 17 (deleted items listed like live ones).

## From Sembrados (2026-10-16 to 2026-10-19)

Translated from the project's own log, which was in Spanish. Item numbers (`#51`...) are that
project's.

### 2026-10-16: first load of the specification (30 specs, 45 features)

**1. There was no `spec` type.**
Only feature, bug, debt and problem existed. The `spec` type was added before loading anything.
*Fixed.*

**2. Part of a section cannot be edited.**
Sections are only the markdown headings (`##`). Inside `## Rules`, bold blocks are not sections, so
changing one line means rewriting the whole section (`section --set`) or the whole body
(`set body=@file`). Updates needed a local copy of each body, edited and uploaded whole again.
- **Impact:** if the user edits the same item in the GUI meanwhile, the full rewrite overwrites their
  change without warning.
- **Possible solution:** a command to replace one exact text in the body (`replace ID "old" "new"`)
  that fails unless the text appears exactly once; or checking the version before writing.
- *Fixed (2026-10-16):* `track replace ID "old" "new"` changes the text only when it appears exactly
  once (otherwise it fails, changes nothing and says how many times it was found), with `--section`
  to look in one section only. Also, `--if-version N` on `replace`, `set`, `section --set` and
  `add-section` refuses the write if the item changed since it was read.

**3. Long texts only go in through files.**
`--body` is for one line; multi-line bodies needed a temporary file and `--body-file`. Stdin could
not be read (`--body-file -`).
- **Impact:** every item needed a temporary file.
- **Possible solution:** accept `-` as "read stdin".
- *Fixed (2026-10-16):* every text option takes `-` for stdin (`--body-file -`, `--file -`,
  `--set-file -`, `body=@-`, `--old-file -`, `--new-file -`). Every text that comes in, whatever the
  way, has its line breaks normalized to `\n`.

**4. Relations between items are only text.**
A feature says which specs it implements by writing `#7` in its body, but the tracker does not know.
"Which features implement spec #7?" or "which items mention #12?" could not be asked without reading
every body, and nothing checked that an `#id` exists. During the load, the ids of cross references
had to be predicted before creating the items.
- **Possible solution:** a relations field or table (`implements`, `depends on`), or at least a
  command that lists the items mentioning an `#id`.
- *Fixed (2026-10-16):* references are read from the bodies: `track list --mentions ID` (for example
  `--type feature --mentions 7`), `track refs ID` both ways, and a warning when a body written
  mentions an id that does not exist or is deleted. There are no relation types: "implements" reads
  as "a feature mentions the spec".

**5. The CLI has no text search: search lives in the GUI.**
The GUI read every item once with `list --all --json` and filtered in memory with its own logic. The
CLI had nothing equivalent: to search from the terminal, `list --json` had to be filtered outside.
- **Impact:** against the rule that the GUI can do nothing the CLI cannot; the agent could not search
  the way the user did.
- **Possible solution:** `list --search "text"` in the CLI, with the same logic, used by the GUI.
- *Fixed (2026-10-16):* `track list --search "text"` with the same rule, and the GUI uses it (it asks
  the CLI for the matching ids 250 ms after typing stops).

**6. The statuses do not quite fit specs.**
A spec is not "finished": it is validated (`open`) or an idea (`draft`); `doing`, `done` and
`dropped` hardly mean anything for it. Also, `track subjects` adds specs and features into the same
"open" count, so "Parcel 6 open" mixes 3 specs with 3 features.
- **Possible solution:** `subjects` split the counts by type, or leave specs out of the open count.

**7. Columns misaligned with long subjects.**
`list` and `next` kept 12 characters for the subject; longer subjects ran into the title.
- **Possible solution:** size the column to the longest subject of the output.
- *Fixed (2026-10-16):* the column widens to the longest subject of each output and always leaves at
  least two spaces before the title. With short subjects, the output is unchanged.

**8. The `Spec/` folder has to exist.**
The CLI created the database, but not its folder; in a fresh clone without `Spec/` it failed.
- **Possible solution:** create the folder when missing.
- *Fixed (2026-10-20), by the tracker folder:* the folder is made by `track init` (with everything in
  it), and given by `--dir` or `TRACKER_DIR`; any other command refuses a path that is not a folder,
  saying so, instead of creating one by accident.

**9. `track.bat` depends on conda.**
`env.bat` needs conda to create and activate the environment. As the CLI only uses the standard
library, the load ran `python track.py` directly.
- **Possible solution:** fall back to the system's Python when there is no conda.
- *Dropped (2026-10-19):* the tracker uses conda on purpose, by the user's decision. What did hurt was
  already fixed on 2026-10-16: `env.bat` only activates the environment (no check, creation or
  install), and creating and installing belongs to `env_install.bat`. Measured on 2026-10-19: about
  0.5 s per call through `track.bat`, against 0.13 s calling Python directly.

**10. There are no batch operations.**
Each command is one independent write that rewrites the whole dump. The load needed 75 `add` and 15
`set` commands. Fast today, but it grows with the database.
- *An idea for later, if the need comes:* a file of operations applied in one transaction (all or
  none). Set aside for now: there will be no more initial loads, and it is complex (for example, an
  operation that refers to an item created in the same batch).

**11. History shows no differences.**
`history` lists the versions and `show --version N` shows one whole, but there is no way to see what
changed between two versions without comparing them by hand.
- **Possible solution:** `track diff ID [N [M]]`.

### 2026-10-16: search and references

**12. There is no global reference check.**
`refs ID` and the warning on write look at one item at a time. Finding out whether any body
mentioned a missing or deleted id took one `refs` per item (79 calls).
- **Possible solution:** `track refs --check`, listing every broken reference at once.
- *Fixed (2026-10-19):* `track refs --check` lists at once the wrong references of the live items'
  bodies: an id that does not exist, a deleted one, or one that is not a spec in the Specs section.
  Also, `refs ID` reads the notes too (without counting for `--check`), a note with a wrong reference
  warns when written, and `delete` warns about the bodies that still mention the deleted item.

**13. The tests leave unclosed-file warnings.**
`test_export` opens files with `open(...).read()` without closing them, and Python warns about it
(`ResourceWarning`) when the suite runs. It does not change the result, but clutters the output.
- **Possible solution:** read with `with open(...)` or a reading helper in the tests.

**14. Error messages came out garbled on Windows.**
The CLI switched stdout to UTF-8 but not stderr, so an error with accents showed as `'M�s adelante'`.
- *Fixed (2026-10-16):* stderr is UTF-8 too, with a test that checks it.

### 2026-10-16: first look at the next steps

**15. `env.bat` writes to stdout when installing.**
The first `track.bat` call on that machine wrote `Installing ...\requirements.txt...` to stdout, mixed
with the output of `track next`. It happened whenever the `.installed` stamp was missing (it is
git-ignored, so on every clone or new machine) or the requirements changed.
- **Impact:** with `--json`, that line would break the JSON of the first call; the GUI, which reads
  JSON, would fail on that first start.
- **Possible solution:** `env.bat` write its messages to stderr, or nothing when all is well.
- *Fixed (2026-10-16, noted on 2026-10-19):* `env.bat` no longer installs nor writes anything to
  stdout; its only message, when it cannot activate the environment, goes to stderr. Installing is
  in `env_install.bat`.

**16. One section of several items cannot be read in one call.**
Summing up the next 10 steps meant reading each one's "What to do": 10 `track section` calls in a
loop. `next` only gives the title and `--json next` would give whole bodies.
- **Impact:** small: it works and the output is just what is needed, but it costs one call (and one
  conda activation) per item.
- **Possible solution:** several ids for `section`, or a `next --section TITLE` option.
- *Fixed (2026-10-19):* `next --section TITLE` and `list ... --section TITLE` print each item
  followed by that section's content. So that a section means the same in every item, each type's
  sections are now fixed: every body write is checked against them, only subsections (`###` or
  deeper) can be added, and `sections --check` lists the items that do not follow them. The 6 items
  that did not were adapted. The sections later moved from the code to a file per project
  (`tracker.sections.json`), so that projects in other languages use the same code.

**17. A deleted item is listed like a live one.**
`list --deleted` prints its lines in the same format as `list`: the status it had (`open`) and
nothing that says it is deleted. Run right after a `list` with no output, the lines of two deleted
items were read as open items, and the user was told they were still open. `history` does mark the
version with `DELETED`.
- **Impact:** easy to mistake deleted items for live ones when reading outputs together.
- **Possible solution:** mark the lines of deleted items (`DELETED` at the end, as in `history`).
- *Still open (reviewed on 2026-10-19):* `show` and `history` mark deleted items with `DELETED`, but
  `list --deleted`, the case of this entry, does not. `test_delete_restore` asserts the
  `list --deleted` line without the mark, so fixing it changes what that test asserts: waiting for
  the user's decision.

### 2026-10-17: adding an item during a feature

**18. `add` prints the id with a hash and the other commands do not take it.**
`track add` prints the new id as `#95`; chaining that value into `track note $id ...` and
`track show $id` failed with `argument id: invalid int value: '#95'`.
- **Impact:** the output of `add` could not be used directly by the next commands.
- **Possible solution:** `add` print only the number, or id arguments accept `#N` too.
- *Fixed (2026-10-19):* see 21, the same problem.

### 2026-10-17: rewriting the parcel's specs

**19. `section --set -` stores a literal "-" and wipes the section silently.**
On 2026-10-16, writing the decisions of #51, `section 5 "Rules" --set -` was run with the text on
stdin. `--set` takes the text inline, so it stored a "-" as the rules of spec #5; only `--set-file -`
read stdin. Nobody noticed until 2026-10-17, when the spec was seen without rules. Reproduced on a
temporary database.
- **Impact:** a whole section of a validated spec silently lost; it was recovered from the previous
  version and the notes of #51.
- **Possible solution:** `--set -` read stdin like `--set-file -`, or be refused; and warn when a
  section's new content is one line and the old one had several.
- *Fixed (2026-10-19):* an inline text that is exactly `-` reads stdin in every command (`--body -`,
  `section --set -`, `set body=-`, `note ID -`, `replace ID - NEW`), because the fix is in the one
  function that reads texts. Empty stdin (or only blank lines) is refused with nothing written, since
  it is nearly always a failed pipe. Only one text per command can read stdin. The warning for
  shrinking sections was not added: with these two rules, the cause cannot happen again.

**20. Several writes in a row sometimes fail to rewrite the dump (`OSError: [Errno 22] Invalid
argument` on the dump).**
On 2026-10-18, three writes in a row (two notes and a close) were run from a script. All three
reached the database, but two ended with that error while rewriting the dump, and the dump stayed
behind the database until `track dump` was run by hand.
- **Impact:** the dump kept in git can fall behind without anyone noticing, but for the error's
  trace; the database is fine.
- **Possible solution:** write the dump to a temporary file and rename it, with a short retry when
  the file is locked (likely an antivirus, the Windows indexer or the GUI reading it); and say in the
  error that the write was done and `track dump` is enough.
- *Seen on 2026-10-19:* it was worse than it looked. The dump was opened in write mode, which empties
  it before writing, so an error halfway could leave it cut short, not just behind. And the database
  is rebuilt from the dump when the `.db` is missing.
- *Fixed (2026-10-19):* the dump is written whole to a temporary file next to it and swapped in at
  once, so it is never half written. If that fails, it is retried 5 times, 0.2 s apart. If it still
  fails, the write command keeps its change, warns on stderr (`the change is saved in the database
  ... run track dump`) and exits 0, so that a script does not repeat a write that was done.
  `track dump` itself does fail in that case. The next write rewrites the whole dump.

**21. `track add` prints the new id as `#119`, but `note`, `rank` and the other commands only take
`119`.**
On 2026-10-18, creating items from a script, the output of `add` was used as the id of the next
commands. `track note "#119" ...` and `track rank "#119" 7` failed with `invalid int value: '#119'`.
The item was created, but without its note and rank until they were repeated by hand.
- **Impact:** a script that chains `add` with other commands fails halfway and leaves the item
  incomplete.
- **Possible solution:** the commands accept the id with or without `#` (as references write it), or
  `add` print only the number.
- *Fixed (2026-10-19), together with 18, the same problem:* every id argument (and `--mentions`)
  takes `42` and `#42`. `add` still prints `#42`, the way a reference is written.

## From PruebaPhysicsworld1 (2026-10-19 to 2026-10-20)

**22. `--json list` rows have an `id` that is not the item's id.** (2026-10-19)
Scripting over `track --json list --all`, the field `id` was taken as the item number; it was the
version row's id, and the item's is `item_id`. A batch of `track set` calls went to ids that do not
exist (all refused with "no item", nothing changed).
- **Impact:** any script or GUI code reading `id` from list rows addresses the wrong item: harmlessly
  when that id does not exist, silently wrong when it does. The JSON rows' fields were not
  documented.
- **Possible solution:** drop the version's `id` from the JSON rows (or rename it `version_id`), or
  document the rows' fields, `item_id` first.
- *Fixed (2026-10-20):* the `latest` view and the version queries (`history`, `show --version`) name
  their columns, the versions table's own `id` left out, so an item row's only id is `item_id`; a
  database made with the old view gets it replaced the first time a command opens it, and a current
  one is left untouched. `tracker.md` lists every JSON output's fields, a note's `id` (the note's
  own number) included. Tested by `test_json_ids` (red before the fix: item #1's row carried
  `"id": 4`).
