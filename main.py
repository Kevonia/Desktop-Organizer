"""`python main.py` opens the app window; `python main.py <command>` uses the command line."""

import sys

if __name__ == "__main__":
    # The app window's own flags: start in the tray, or a request from the File Explorer menu.
    if len(sys.argv) > 1 and sys.argv[1] not in ("--minimized", "--organize", "--where"):
        from desktop_organizer.cli import main
    else:
        from desktop_organizer.ui.app import main
    raise SystemExit(main())
