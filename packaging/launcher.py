"""Entry point PyInstaller freezes into DesktopOrganizer.exe (the app window only)."""

from desktop_organizer.ui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
