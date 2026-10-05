# 🗂️ Desktop Organizer

**Version 1.0.0** · [Changelog](CHANGELOG.md)

A Windows desktop app that keeps your Desktop, Downloads, Documents (or any
folder) tidy by sorting files into folders, in a structure **you** choose.
Every run can be undone.

> All features are currently free. Free/Premium tiers will come with licensing
> in a later release.

## 📥 Install

Download one of these from a release (or build them yourself, see below):

| File | Use it when |
| --- | --- |
| `DesktopOrganizer-1.0.0-Setup.exe` | Normal install. No admin rights needed; adds a Start menu entry and an uninstaller. |
| `DesktopOrganizer-1.0.0-portable.zip` | No install. Unzip anywhere and run `DesktopOrganizer.exe`. |

Uninstalling keeps your settings and undo history in
`%APPDATA%\DesktopOrganizer`, so reinstalling picks up where you left off.

## 🚀 Features

- **App window** with a live preview of every move. Untick files to leave them,
  filter the list, then organize. Light, dark or match-system theme.
- **Any folder**: Desktop, Documents, Downloads, Pictures, Music, Videos or one
  you pick. Each folder can have its own structure.
- **Ready-made structures**: File type · Category · Year / Month ·
  Year / Month / File type · Year / Month / Category.
- **Build your own structure** from placeholders, e.g. `Work/{category}/{year}`:

  | Placeholder      | Example      | Placeholder      | Example     |
  |------------------|--------------|------------------|-------------|
  | `{year}`         | 2025         | `{quarter}`      | Q1          |
  | `{month}`        | 01-January   | `{type}`         | pdf         |
  | `{month_num}`    | 01           | `{category}`     | Documents   |
  | `{month_name}`   | January      | `{size}`         | Small       |
  | `{month_short}`  | Jan          | `{first_letter}` | R           |
  | `{day}`          | 05           |                  |             |

- **Your own categories**, e.g. *Invoices = pdf*, used by `{category}`.
- **Undo** any run from History. Folders a run created are removed again and
  files are never overwritten.
- **Safety**: refuses drive roots, your whole user folder and system folders,
  and warns before touching code/Docker projects (folders containing `.git`,
  `Dockerfile`, `package.json`...). Shortcuts, hidden/system files and Office
  lock files are left alone.
- Finds the real Desktop/Documents/Downloads even when Windows moves them into OneDrive.

## 🧑‍💻 Run from source

Requires Python 3.10+.

```bash
pip install -e .[dev]
python main.py              # opens the app window
python main.py --version
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

## 🔢 Versioning

The app uses [Semantic Versioning](https://semver.org), starting at **1.0.0**:

- **PATCH** (1.0.0 → 1.0.1): bug fixes
- **MINOR** (1.0.0 → 1.1.0): new features
- **MAJOR** (1.0.0 → 2.0.0): big changes that may break settings or habits

The version lives in one place, `desktop_organizer/__init__.py`. The CLI,
About box, `pyproject.toml`, the `.exe` file properties and the installer
all read it from there.

To release a new version:

1. While working, add notes under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md).
2. Bump the version (this also moves the Unreleased notes under the new number):

   ```bash
   python scripts/bump_version.py patch     # or minor / major / 1.2.0
   python scripts/bump_version.py --show    # current version
   ```

3. Commit, tag and build:

   ```bash
   git commit -am "Release 1.0.1"
   git tag v1.0.1
   python packaging/build.py
   ```

## 📦 Build the Windows app

```bash
pip install -e .[build]                 # PyInstaller
winget install JRSoftware.InnoSetup     # for the installer (optional)
python packaging/build.py               # add --no-installer to skip Inno Setup
```

Output in `dist/`:

```text
dist/DesktopOrganizer/DesktopOrganizer.exe       the app folder
dist/DesktopOrganizer-<version>-portable.zip
dist/DesktopOrganizer-<version>-Setup.exe
```

The installer's `AppId` in `packaging/installer.iss` must never change:
Windows uses it to treat new versions as upgrades of the same app.

## 🧱 Project layout

```text
desktop_organizer/
  __init__.py         app name and version (single source)
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
    version.py        parse/compare/bump versions
  ui/                 PySide6 app
    app.py            entry point
    main_window.py    folders sidebar, preview table, organize/undo
    dialogs.py        structure builder, categories, history, settings
    theme.py          light/dark theme tokens
    worker.py         background thread for moves
  resources/icon.svg
packaging/
  build.py            icon, PyInstaller, zip and installer in one step
  installer.iss       Inno Setup script
  launcher.py         entry point frozen into the .exe
scripts/
  bump_version.py     bump version + roll the changelog
tests/                pytest; GUI tests run headless
CHANGELOG.md
```

## 🧪 Tests

```bash
python -m pytest
```

Tests never touch your real folders: the Desktop, Downloads etc. are redirected
to temporary folders.

## 🗺️ Roadmap

- [x] 1.0: desktop app, any folder, custom structures, undo, Windows installer
- [ ] Premium features: auto-organize (folder watching), scheduled runs, rule
      builder, duplicate finder, run from the tray
- [ ] Licensing (Free / Premium) and in-app upgrade
- [ ] Auto-update, code signing, macOS build

## 🛠️ License

MIT
