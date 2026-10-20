# trackertron2000

A tracker for a project's specification and its to-do list, made to be used by an AI agent and its
user: specs, features, bugs, debt and potential problems in a small SQLite database, behind a CLI
that answers each question in a few lines, and a GUI for the user. `tracker.md` is the full reference.

One copy of this repository serves any number of projects. **Using the tracker never changes this
repository**: everything a project's tracker needs and writes lives in a folder of that project (its
*tracker folder*, usually `Tracker/` at the project's root).

## Requirements

- Windows: the launchers are batch files.
- conda (Miniconda or Anaconda), usable from `cmd` (`conda activate` must work there; if it does not,
  run `conda init cmd.exe` once). The tracker's environment, `pw-tracker` (Python 3.12, plus PySide6
  for the GUI), is created and filled by the setup scripts.

## This repository

| path | what it is |
|---|---|
| `tracker.md` | the reference: data model, commands, rules of use (printed by `track.bat guide`) |
| `KNOWN_ISSUES.md` | the problems found while using the tracker, and what became of them |
| `Tracker/track.py` | the CLI; the only thing that touches a database |
| `Tracker/test_track.py`, `Tracker/test.bat` | the CLI's tests (against temporary folders) |
| `Tracker/init.bat` | the initial configuration of a project: installs the environment, makes its tracker folder |
| `Tracker/install.bat`, `env_install.bat`, `env.bat` | the conda environment: install, install one requirements file, activate |
| `TrackerGui/` | the GUI (PySide6), a window over the CLI |
| `Templates/` | what `init` copies into a tracker folder: the launchers, its `.gitignore`, `known-issues.md`, and the starting sections in each language (`sections.en.json`, `sections.es.json`) |

## Initial configuration

These steps set the tracker up for a project. They are written for an AI agent working in that
project, with its user; a person can follow them just as well.

1. **Ask the user two things, and wait for the answers:**
   - the language of the project's content, `en` or `es` (it sets the starting sections and which
     instructions block below to use);
   - where the tracker folder goes; propose `Tracker/` at the project's root.
2. **Make the tracker folder.** From anywhere, run this repository's
   `Tracker\init.bat <tracker folder> <language>`, for example
   `C:\tools\trackertron2000\Tracker\init.bat C:\work\myproject\Tracker en`. It creates the conda
   environment if missing, installs what the CLI and the GUI need, and makes the folder with all its
   files (see "The tracker folder" in `tracker.md`). It refuses to write over an existing tracker
   folder.
3. **Check it works:** `<tracker folder>\track.bat next` prints nothing and exits 0;
   `<tracker folder>\track.bat guide` prints the reference.
4. **Add the instructions block** below, in the project's language, to the file where the project's
   agent reads its standing instructions (whatever file the agent system uses), adapting the
   launcher's path if the folder is not `Tracker/`. Keep any instructions the project already has;
   if some of them point to an older way of keeping specs or to-dos, ask the user what to do with
   them.
5. **Tell the user about the sections, and do not change them on your own.** The folder starts with a
   generic set of sections per type (`tracker.sections.json`). Tell the user they are a starting
   point, and that they can either ask for a study of the project, to propose sections that fit it,
   or write the sections themselves. Do not study the project or change the sections unless the user
   asks. Settle them before writing items: once items exist, every body must follow its type's
   sections.
6. **Tell the user what to commit:** the whole tracker folder. Its `.gitignore` already leaves out
   `tool-path.txt` (where this repository is on this machine) and the temporary files.

Never change this repository while setting up or using the tracker. A problem found with the tracker
goes into the project's `<tracker folder>/known-issues.md`; the user carries what matters over to
this repository's `KNOWN_ISSUES.md`.

### On another machine, or a fresh clone

The tracker folder is in the project's git, but `tool-path.txt` is not. Clone this repository
anywhere, then run `<tracker folder>\track.init.bat <path to this repository>` once: it records the
path and installs the environment. Instead of `tool-path.txt`, the `TRACKER_HOME` environment variable
can name this repository; it wins when set.

### Updating the tracker

Pull this repository. Every project that uses it gets the new version at once; a database made by an
older version is brought up to date the first time a command opens it.

## Instructions block for the project's agent

Paste the block in the project's language into the agent's instructions file, adapting what does not
apply.

### English

```markdown
## Specification and to-do list: the tracker

- The specification and everything pending (features, bugs, debt, potential problems) live in the tracker. Its folder is `Tracker/`; run every command as `Tracker\track.bat <command>`.
- **Before using it for the first time in a session, run `Tracker\track.bat guide`** and read it: the commands, the data model and how to work with it.
- Use it only through the CLI. Never open or search `Tracker/tracker.db` or its dump as text: ask the CLI.
- The GUI (`Tracker\tracker_gui.bat`) is for the user, not for the agent.
- Everything in the tracker (titles, bodies, notes, subjects) is in English.
- Each type's sections are fixed in `Tracker/tracker.sections.json`, and the CLI enforces them on every write; only `###` subsections can be added. Read the spec, or just the section you need, before working on a topic.
- Specs: `open` = validated, `draft` = an idea not yet final. Features: those for the current version are `open` and ranked (`track next`); those planned for later are `draft`.
- Finding your way: `track subjects` for the subjects; `track list --type spec --subject X` for a subject's specs; `track next` for the build order; `track list --search "words"` to search text; `track list --type feature --mentions ID` for the features that implement a spec; `track refs ID` for references both ways; `track next --section "TITLE"` to read one section of the next items.
- Open questions: ask with `track ask ID "..."`, including the recommended proposal. The user's answer goes in with `track answer NOTE "..."` (NOTE is the number `ask` printed), and what is decided goes into the item's body or its spec. `track questions` lists the questions still open.
- Nothing agreed is left hanging: whatever the user asks for or accepts and is not built in the same piece of work goes into the tracker (`track add`), and the report to the user gives the `#id` and where it sits (status, rank).
- Problems with the tracker itself are never logged in the tracker: they go to `Tracker/known-issues.md` (date, what happened, its impact, a possible solution), appended at the end without rewriting what is there, and mentioned in the report to the user.
- Never change the tracker's own repository: everything the tracker writes is in `Tracker/`.
```

### Español

```markdown
## Especificación y TODO: el tracker

- La especificación y todo lo pendiente (features, bugs, deuda, problemas potenciales) viven en el tracker. Su carpeta es `Tracker/`; todos los comandos se ejecutan como `Tracker\track.bat <comando>`.
- **Antes de usarlo por primera vez en una sesión, ejecuta `Tracker\track.bat guide`** y léelo: sus comandos, su modelo de datos y cómo se trabaja con él.
- Se usa solo a través del CLI. Nunca abras ni busques en `Tracker/tracker.db` ni en su dump como texto: pregunta al CLI.
- La GUI (`Tracker\tracker_gui.bat`) es para el usuario, no para el agente.
- Todo el contenido del tracker (títulos, cuerpos, notas, temas) está en español.
- Las secciones de cada tipo están fijadas en `Tracker/tracker.sections.json`, y el CLI las comprueba en cada escritura; solo se añaden subsecciones (`###`). Lee la spec, o solo la sección que necesites, antes de trabajar en un tema.
- Specs: `open` = validada; `draft` = idea no definitiva. Features: las de la versión actual están en `open` y ordenadas por rank (`track next`); las previstas para más adelante, en `draft`.
- Orientarse: `track subjects` da los temas; `track list --type spec --subject X`, las specs de un tema; `track next`, el orden de ejecución; `track list --search "palabras"` busca por texto; `track list --type feature --mentions ID` da las features que implementan una spec; `track refs ID`, las referencias en ambos sentidos; `track next --section "TÍTULO"` lee una sección de los siguientes items.
- Preguntas abiertas: se apuntan con `track ask ID "…"`, con la propuesta recomendada; la respuesta del usuario, con `track answer NOTA "…"` (NOTA es el número que imprimió `ask`), y lo decidido pasa al cuerpo del item o a su spec. `track questions` lista las preguntas que siguen abiertas.
- Nada de lo acordado se queda en el aire: todo lo que el usuario pida o acepte y no se construya en el mismo desarrollo se registra en el tracker (`track add`), y el informe al usuario dice el `#id` y dónde queda (estado, rank).
- Los problemas del propio tracker nunca se registran en el tracker: se apuntan en `Tracker/known-issues.md` (fecha, qué pasó, su impacto y una posible solución), al final y sin reescribir lo anterior, y se dicen en el informe al usuario.
- Nunca cambies el repositorio del propio tracker: todo lo que escribe el tracker está en `Tracker/`.
```

## Tests

`Tracker\test.bat` runs the CLI's tests, each against its own temporary tracker folder; they never
touch a project's folder. The GUI has no tests.
