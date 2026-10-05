"""`python main.py` opens the app window; `python main.py <command>` uses the command line."""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from desktop_organizer.cli import main
    else:
        from desktop_organizer.ui.app import main
    raise SystemExit(main())
