# 🗂️ Desktop Organizer

A desktop app that keeps your Desktop, Downloads, Documents (or any folder)
tidy by sorting files into folders, in a structure **you** choose. Every run
can be undone.

## 🚀 Features

- **App window** with a live preview of every move. Untick files to leave them,
  filter the list, then organize. Light and dark themes.
- **Any folder**: Desktop, Documents, Downloads, Pictures, Music, Videos or one
  you pick. Each folder can have its own structure.
- **Ready-made structures**: File type · Category · Year / Month ·
  Year / Month / File type · Year / Month / Category.
- **Build your own structure** from placeholders, e.g. `Work/{category}/{year}`:

  | Placeholder      | Example      | Placeholder     | Example     |
  |------------------|--------------|-----------------|-------------|
  | `{year}`         | 2025         | `{quarter}`     | Q1          |
  | `{month}`        | 01-January   | `{type}`        | pdf         |
  | `{month_num}`    | 01           | `{category}`    | Documents   |
  | `{month_name}`   | January      | `{size}`        | Small       |
  | `{month_short}`  | Jan          | `{first_letter}`| R           |
  | `{day}`          | 05           |                 |             |

- **Your own categories**, e.g. *Invoices = pdf*, used by `{category}`.
- **Undo** any run from History. Folders a run created are removed again and
  files are never overwritten.
- **Safety**: refuses drive roots, your whole user folder and system folders,
  and warns before touching code/Docker projects (folders containing `.git`,
  `Dockerfile`, `package.json`...). Shortcuts, hidden/system files and Office
  lock files are left alone.
- Finds the real Desktop/Documents/Downloads even when Windows moves them into OneDrive.

## ▶️ Run it

Requires Python 3.10+.

```bash
pip install -e .[dev]
python main.py            # opens the app window
```

### Command line

```bash
python main.py preview downloads
python main.py organize --all                      # every saved folder
python main.py organize docs --pattern "{category}/{year}"
python main.py undo
python main.py history
python main.py folders add downloads --mode category
python main.py structure set --pattern "Work/{category}/{year}"
python main.py structure tokens
python main.py categories add Invoices pdf
python -m desktop_organizer                        # text menu
```

Settings (`settings.json`) and the undo log (`history.db`) live in
`%APPDATA%\DesktopOrganizer` on Windows,
`~/Library/Application Support/DesktopOrganizer` on macOS and
`~/.local/share/DesktopOrganizer` on Linux.

## 🧱 Project layout

```text
desktop_organizer/
  cli.py              command line + text menu
  core/               engine with no UI code (shared by CLI and app)
    paths.py          Desktop/Downloads/... and app-data locations
    config.py         settings, saved folders, preset structures
    structure.py      custom structure patterns and placeholders
    categories.py     extension -> category map
    safety.py         forbidden folders and project warnings
    dates.py          which date a file belongs to
    scanner.py        which files are eligible
    rules.py          plans where each file goes
    mover.py          performs moves and logs them
    history.py        SQLite undo log
    organizer.py      facade used by the UIs
  ui/                 PySide6 app
    app.py            entry point
    main_window.py    folders sidebar, preview table, organize/undo
    dialogs.py        structure builder, categories, history, settings
    theme.py          light/dark theme tokens
    worker.py         background thread for moves
  resources/icon.svg
tests/                pytest; GUI tests run headless
```

## 🧪 Tests

```bash
python -m pytest
```

Tests never touch your real folders: the Desktop, Downloads etc. are redirected
to temporary folders.

## 🛠️ License

MIT
