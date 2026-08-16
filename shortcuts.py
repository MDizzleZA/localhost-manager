"""Create the Desktop launcher shortcut (with the app icon)."""
from __future__ import annotations

import os
import subprocess
import sys

import autostart
import theme

_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0
SHORTCUT_NAME = 'Localhost Manager.lnk'


def desktop_dir() -> str:
    """The user's Desktop, accounting for OneDrive redirection."""
    candidates = [
        os.path.join(os.environ.get('USERPROFILE', ''), 'OneDrive', 'Desktop'),
        os.path.join(os.path.expanduser('~'), 'Desktop'),
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return os.path.join(os.path.expanduser('~'), 'Desktop')


def desktop_shortcut_path() -> str:
    return os.path.join(desktop_dir(), SHORTCUT_NAME)


def desktop_exists() -> bool:
    return os.path.exists(desktop_shortcut_path())


def create_desktop_shortcut() -> tuple[bool, str]:
    link = desktop_shortcut_path()
    ok, err = _create(link)
    if ok and os.path.exists(link):
        return True, f'Desktop shortcut created:\n{link}'
    return False, err or 'Could not create the desktop shortcut.'


def remove_desktop_shortcut() -> tuple[bool, str]:
    link = desktop_shortcut_path()
    try:
        if os.path.exists(link):
            os.remove(link)
        return True, 'Removed desktop shortcut.'
    except OSError as exc:
        return False, str(exc)


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _create(link: str) -> tuple[bool, str]:
    if sys.platform != 'win32':
        return False, 'Desktop shortcuts are only supported on Windows.'
    icon = theme.ensure_ico() or autostart.pythonw()
    script = (
        '$s = (New-Object -ComObject WScript.Shell).CreateShortcut('
        f'{_ps_quote(link)}); '
        f'$s.TargetPath = {_ps_quote(autostart.pythonw())}; '
        f'$s.Arguments = {_ps_quote(chr(34) + autostart.APP_ENTRY + chr(34))}; '
        f'$s.WorkingDirectory = {_ps_quote(autostart.HERE)}; '
        f'$s.IconLocation = {_ps_quote(icon)}; '
        '$s.WindowStyle = 7; '
        f'$s.Description = {_ps_quote("Localhost Manager")}; '
        '$s.Save()'
    )
    return _run_ps(script)


def _run_ps(script: str) -> tuple[bool, str]:
    try:
        res = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
            capture_output=True, text=True, creationflags=_NO_WINDOW)
        if res.returncode == 0:
            return True, ''
        return False, (res.stderr or res.stdout or '').strip()
    except Exception as exc:
        return False, str(exc)
