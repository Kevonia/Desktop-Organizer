"""Start the app (minimized to the tray) when the user signs in to Windows."""

from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "DesktopOrganizer"
MINIMIZED_FLAG = "--minimized"


def is_supported() -> bool:
    return sys.platform == "win32"


def app_command(*args: str) -> str:
    """The command line that opens the app window, followed by ``args``."""
    if getattr(sys, "frozen", False):  # the installed DesktopOrganizer.exe
        base = f'"{sys.executable}"'
    else:
        # Running from source: use pythonw so no console window appears.
        python = Path(sys.executable)
        pythonw = python.with_name("pythonw.exe")
        main_py = Path(__file__).resolve().parents[2] / "main.py"
        base = f'"{pythonw if pythonw.exists() else python}" "{main_py}"'
    return " ".join([base, *args])


def app_icon() -> str:
    """What Windows should show next to the app's menu entries."""
    return f'"{sys.executable}",0' if getattr(sys, "frozen", False) else ""


def launch_command() -> str:
    return app_command(MINIMIZED_FLAG)


def is_enabled() -> bool:
    if not is_supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    if not is_supported():
        return
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
