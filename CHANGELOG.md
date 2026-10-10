# Changelog

All notable changes to Desktop Organizer are listed here.
Versions follow [Semantic Versioning](https://semver.org): MAJOR.MINOR.PATCH.

- **MAJOR**: big changes that may break saved settings or habits
- **MINOR**: new features
- **PATCH**: bug fixes

Add notes under **Unreleased** as you work; `python scripts/bump_version.py`
moves them under the new version number.

## [Unreleased]

### Added

- **Ready-made setups** for a Student, Freelancer, Photographer and Music
  collector (Tools › Ready-made setups). New installs are offered them once on
  first launch. A setup merges with existing rules and folders.
- **Placeholders from inside files**: `{photo_date}`, `{photo_year}` and
  `{photo_month}` (when a photo was taken), `{camera}`, `{artist}` and
  `{album}` (music tags in MP3, FLAC, M4A and Ogg), and `{source}` (the website
  a download came from). Also `{date}` (e.g. 2025-01-05). A file's contents
  are only read when a layout uses one of these.
- **Text inside a file** as a rule condition: PDF (first 5 pages), Word, Excel,
  PowerPoint, OpenDocument, RTF and text files.
- **Rename as you organize**, per folder (*File names* button) or per rule
  (*Rename to*), with `{name}` for the original name. Shown in the preview and
  undone with the run.
- **Put files in another folder**, such as a USB drive or a network folder
  (*Put files in* button). The roots of USB drives and network shares can now
  be organized. Unplugged drives show *(not connected)*; nothing moves and
  auto-organize waits until the drive is back.
- **Export the preview** (Actions › Export preview, Ctrl+E) or **a past run**
  (History › Export run) as CSV or HTML.
- **Storage stats** (sidebar, or Ctrl+I): space by category, the largest
  files, and files not used in a chosen number of months.
- **Export and import settings** (File menu) as a `.json` file: rules,
  categories, folders and layouts, and files never to move.
- **File Explorer menu** (Settings › File Explorer): *Organize with Desktop
  Organizer* on folders opens the preview, and *Where did this file come
  from?* on files shows its earlier locations and download page. The
  uninstaller removes these entries.
- Command line: `setups`, `report`, `stats`, `settings export|import`,
  `where`, `shell`, and `folders add --rename / --dest`.

### Changed

- New dependency: `pypdf` (BSD licence) to read text in PDFs.
- A second launch now passes its request (e.g. from the File Explorer menu) to
  the copy that's already running.

### Fixed

- The sidebar button showed "Find _recover" instead of "Find & recover".

## [1.3.0] - 2026-10-05

### Added

- **Find & recover** window (sidebar button, or Ctrl+F) with three tabs:
  - **Find a file**: type part of a name to see where the organizer moved
    it, from where and when, plus matches in your saved folders. Open the
    file or show it in File Explorer.
  - **File versions**: protect folders and the app keeps the last 4 saved
    versions of every file in them (1–20, adjustable), checked about once a
    minute. Restore any version (the current file is saved first, so it can
    be switched back), save a copy, or bring back a protected file that was
    deleted. Versions follow files the organizer moves.
  - **Recycle Bin**: list what's in the Recycle Bin with original location
    and deletion date, filter, and put items back where they came from.
    Never overwrites: a clash is restored as `name (recovered 1)`.

## [1.2.0] - 2026-10-05

### Added

- **One copy at a time**: opening the app while it is already running (for
  example hidden in the tray) brings the existing window forward instead of
  starting a second copy.
- **Check for updates** in the Help menu, using GitHub Releases. An optional
  weekly check can be turned on in Settings; it is off by default, so the
  app never goes online unless asked.
- **Log file and error dialog**: runs, undos and problems are written to a
  small rotating log (`%APPDATA%\DesktopOrganizer\logs`). Unexpected errors
  show a dialog with *Copy details* and *Open log folder* instead of closing
  the app. Help › Open log folder opens it any time.
- **Licence notices** for Qt for Python (LGPL v3) and Python in the About box.
- Ctrl+Q quits the app.

## [1.1.0] - 2026-10-05

### Added

- **Rules**: e.g. "name contains *invoice* and type is pdf → `Finance/Invoices/{year}`",
  or "leave these files alone". Conditions: name contains / starts with /
  matches a pattern, type, size, age. Rules can apply to all folders or one,
  are checked in order, and show which files they match as you edit them.
  The preview shows which rule moved each file.
- **Auto-organize** per folder: when new files arrive, every hour or every
  day. Files are only moved once they've finished downloading or saving.
  Every automatic run can be undone like a manual one.
- **System tray**: closing the window keeps the app running so auto-organize
  keeps working. Tray menu to open, run now, pause or quit. Notifications
  after automatic runs.
- **Start with Windows** (minimized to the tray), in Settings.
- **Find duplicates**: finds identical files (optionally in subfolders),
  keeps the oldest copy ticked off, and moves the extra copies to the
  Recycle Bin so they can be restored.
- History shows how many files have been organized in total.

### Changed

- Files still downloading (`.crdownload`, `.part`, `.tmp`...) are never moved.

## [1.0.0] - 2026-10-05

First release as a desktop app. All features are free while licensing is
being built.

### Added

- App window: saved folders sidebar, live preview of every move with
  checkboxes and filter, organize in the background with progress.
- Organize any folder: Desktop, Documents, Downloads, Pictures, Music, Videos
  or one you choose. Each folder can use its own structure.
- Five ready-made structures plus a builder for your own, using placeholders
  such as `{year}`, `{month_name}`, `{quarter}`, `{type}`, `{category}`,
  `{size}` and `{first_letter}`.
- Your own categories (e.g. *Invoices = pdf*).
- Undo for any run, from the app or History. Never overwrites files.
- Safety checks: refuses drive roots, the whole user folder and system
  folders; warns before organizing code/Docker projects.
- Light, dark and match-system themes.
- Command line with `preview`, `organize`, `undo`, `history`, `folders`,
  `structure` and `categories` commands.
- Windows installer and portable zip.

### Fixed

- Files on macOS/Linux were filed under the wrong month (used the metadata
  change time instead of the creation/modification date).
- Shortcuts, hidden/system files and Office lock files are no longer moved.
- Finds the Desktop when Windows redirects it into OneDrive.

## [0.1.0]

- Original command-line script: sorted Desktop files into Year/Month/FileType.
