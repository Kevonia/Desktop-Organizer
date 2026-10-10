"""File Explorer right-click menu entries: "Organize with Desktop Organizer" on folders and
"Where did this file come from?" on files. Per user (HKCU), so no admin rights are needed.

On Windows 11 they appear under "Show more options", as for most apps.
"""

from __future__ import annotations

from desktop_organizer import APP_NAME
from desktop_organizer.core.startup import app_command, app_icon, is_supported

ORGANIZE_FLAG = "--organize"
WHERE_FLAG = "--where"
GUI_FLAGS = (ORGANIZE_FLAG, WHERE_FLAG)

CLASSES = r"Software\Classes"
ORGANIZE_LABEL = f"Organize with {APP_NAME}"
WHERE_LABEL = "Where did this file come from?"

# registry key under CLASSES -> (menu text, flag, placeholder Explorer fills in)
ENTRIES = {
    r"Directory\shell\DesktopOrganizer.Organize": (ORGANIZE_LABEL, ORGANIZE_FLAG, "%1"),
    r"Directory\Background\shell\DesktopOrganizer.Organize": (ORGANIZE_LABEL, ORGANIZE_FLAG, "%V"),
    r"Drive\shell\DesktopOrganizer.Organize": (ORGANIZE_LABEL, ORGANIZE_FLAG, "%1"),
    r"*\shell\DesktopOrganizer.WhereFrom": (WHERE_LABEL, WHERE_FLAG, "%1"),
}


def is_enabled() -> bool:
    if not is_supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{CLASSES}\{next(iter(ENTRIES))}\command"):
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    if not is_supported():
        return
    import winreg

    for key_path, (text, flag, placeholder) in ENTRIES.items():
        full = rf"{CLASSES}\{key_path}"
        if not enabled:
            for sub in (rf"{full}\command", full):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
                except FileNotFoundError:
                    pass
            continue
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, full) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, text)
            icon = app_icon()
            if icon:
                winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, icon)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{full}\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, app_command(flag, f'"{placeholder}"'))


def refresh() -> None:
    """Re-point the entries at this copy of the app, e.g. after it was installed somewhere new."""
    if is_enabled():
        set_enabled(True)


def parse_args(argv: list[str]) -> tuple[str, str] | None:
    """('organize' | 'where', path) from the app's command line, if Explorer started it."""
    for flag in GUI_FLAGS:
        if flag in argv:
            index = argv.index(flag)
            if index + 1 < len(argv) and argv[index + 1].strip():
                return flag.lstrip("-"), argv[index + 1].strip().strip('"')
    return None
