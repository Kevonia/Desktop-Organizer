# Changelog

All notable changes to Desktop Organizer are listed here.
Versions follow [Semantic Versioning](https://semver.org): MAJOR.MINOR.PATCH.

- **MAJOR**: big changes that may break saved settings or habits
- **MINOR**: new features
- **PATCH**: bug fixes

Add notes under **Unreleased** as you work; `python scripts/bump_version.py`
moves them under the new version number.

## [Unreleased]

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
