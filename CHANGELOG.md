# Changelog

All notable changes to Desktop Organizer are listed here.
Versions follow [Semantic Versioning](https://semver.org): MAJOR.MINOR.PATCH.

- **MAJOR**: big changes that may break saved settings or habits
- **MINOR**: new features
- **PATCH**: bug fixes

Add notes under **Unreleased** as you work; `python scripts/bump_version.py`
moves them under the new version number.

## [Unreleased]

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
