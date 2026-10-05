# 🗂️ Desktop Organizer

**Version 1.3.0** · [Changelog](CHANGELOG.md)

A Windows desktop app that keeps your Desktop, Downloads, Documents (or any
folder) tidy by sorting files into folders, in a structure **you** choose.
Every run can be undone.

> All features are currently free. Free/Premium tiers will come with licensing
> in a later release.

## 📥 Install

Download one of these from a release (or build them yourself, see below):

| File | Use it when |
| --- | --- |
| `DesktopOrganizer-1.3.0-Setup.exe` | Normal install. No admin rights needed; adds a Start menu entry and an uninstaller. |
| `DesktopOrganizer-1.3.0-portable.zip` | No install. Unzip anywhere and run `DesktopOrganizer.exe`. |

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
- **Rules** that run before the structure, e.g. "name contains *invoice* and
  type is pdf → `Finance/Invoices/{year}`", or "leave these files alone".
  Conditions: name contains / starts with / matches (`IMG_*.jpg`), type,
  larger/smaller than N MB, older/newer than N days. Match all or any; limit a
  rule to one folder. The preview's **Rule** column shows which rule applied.
- **Auto-organize** each folder: *when new files arrive*, *every hour* or
  *every day*. Files are only moved after they've stopped changing for a few
  seconds, and in-progress downloads (`.crdownload`, `.part`...) are never
  moved. Automatic runs show up in History and can be undone.
- **System tray**: closing the window keeps the app running for auto-organize
  (Open · Run now · Pause · Quit). Optional notifications and *Start with
  Windows*.
- **Find duplicates**: compares file contents (size, then a quick hash, then a
  full hash), keeps the oldest copy, and moves extras to the **Recycle Bin**.
- **Undo** any run from History. Folders a run created are removed again and
  files are never overwritten.
- **Safety**: refuses drive roots, your whole user folder and system folders,
  and warns before touching code/Docker projects (folders containing `.git`,
  `Dockerfile`, `package.json`...). Shortcuts, hidden/system files and Office
  lock files are left alone.
- Finds the real Desktop/Documents/Downloads even when Windows moves them into OneDrive.
- **Find & recover** (Ctrl+F):
  - *Find a file* — search by name to see where the organizer moved a file,
    from where and when; open it or show it in File Explorer.
  - *File versions* — protect folders and keep the last 4 saved versions of
    every file in them (1–20); restore any version or bring back deleted files.
  - *Recycle Bin* — list deleted items with their original location and put
    them back, never overwriting.
- **One copy at a time**: opening the app again brings the running copy forward.
- **Updates**: *Help › Check for updates...* looks for a newer release on
  GitHub. A weekly check can be turned on in Settings (off by default — the
  app never goes online unless asked).
- **Error log**: runs and problems are logged to `%APPDATA%\DesktopOrganizer\logs`;
  unexpected errors show a dialog with details to copy instead of closing the app.

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
    user_rules.py     rule conditions and actions
    auto.py           auto-organize (watch / hourly / daily)
    duplicates.py     duplicate finder
    trash.py          send to Recycle Bin / Trash
    startup.py        start with Windows (registry Run key)
    updates.py        check GitHub Releases for a newer version
    search.py         find files by name (organizer moves + saved folders)
    versions.py       version history for protected folders
    recycle_bin.py    read and restore Windows Recycle Bin items
    logs.py           rotating log file
    version.py        parse/compare/bump versions
  ui/                 PySide6 app
    app.py            entry point
    main_window.py    folders sidebar, preview, organize/undo, tray, auto-organize
    dialogs.py        structure builder, categories, history, settings
    tools.py          rules editor, duplicate finder
    recover.py        Find & recover window (find, versions, Recycle Bin)
    theme.py          light/dark theme tokens
    worker.py         background thread for moves
    single_instance.py  one running copy; a second launch shows the first
    errors.py         crash dialog and error logging
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

## 📚 Documents

- [User guide](docs/user-guide.html) (also `docs/user-guide.docx`)
- [Project briefing](docs/briefing.html) with SWOT, PESTEL, competitors and
  roadmap (also `docs/briefing.docx`)

## 🚀 Publishing a release

Update checks read the latest release at
`https://github.com/Kevonia/Desktop-Organizer/releases`. To publish one:

1. Bump the version, commit and tag (see Versioning above), then build.
2. `git push origin master --tags`
3. On GitHub, create a release from the tag (e.g. `v1.2.0`), paste the
   changelog notes, and attach `DesktopOrganizer-<version>-Setup.exe` and the
   portable zip. The app links straight to the file ending in `-Setup.exe`.

## 🧪 Tests

```bash
python -m pytest
```

Tests never touch your real folders: the Desktop, Downloads etc. are redirected
to temporary folders.

## 🗺️ Roadmap

- [x] 1.0: desktop app, any folder, custom structures, undo, Windows installer
- [x] 1.1: rules, auto-organize (watch / hourly / daily), tray, start with
      Windows, duplicate finder
- [x] 1.2: one copy at a time, update checker, error log and crash dialog,
      licence notices
- [x] 1.3: Find & recover — file search, version history, Recycle Bin restore
- [ ] 1.4: licensing (Free / Premium) and in-app upgrade
- [ ] 1.5: code signing, first public GitHub release, website
- [ ] 2.x: macOS build, Microsoft Store listing

## 🛠️ License

MIT
