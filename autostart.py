"""Run-at-login support via a Startup-folder shortcut.

The shortcut launches the tray app with ``pythonw.exe`` (no console) so it
appears silently in the notification area after the user logs in. The
shortcut is created/removed with a short PowerShell WScript.Shell snippet,
which avoids taking a dependency on pywin32.
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ENTRY = os.path.join(HERE, 'app.py')
SHORTCUT_NAME = 'Localhost Manager.lnk'
_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0


def _startup_dir() -> str:
    return os.path.join(
        os.environ.get('APPDATA', ''),
        'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup',
    )


def shortcut_path() -> str:
    return os.path.join(_startup_dir(), SHORTCUT_NAME)


def pythonw() -> str:
    """Path to pythonw.exe alongside the current interpreter."""
    exe = sys.executable
    candidate = os.path.join(os.path.dirname(exe), 'pythonw.exe')
    return candidate if os.path.exists(candidate) else exe


def is_enabled() -> bool:
    return os.path.exists(shortcut_path())


def _ps_quote(value: str) -> str:
    """Quote a value as a PowerShell single-quoted literal."""
    return "'" + value.replace("'", "''") + "'"


def enable() -> tuple[bool, str]:
    if sys.platform != 'win32':
        return False, 'Autostart is only supported on Windows.'
    link = shortcut_path()
    try:
        import theme
        icon = theme.ensure_ico() or pythonw()
    except Exception:
        icon = pythonw()
    script = (
        '$s = (New-Object -ComObject WScript.Shell).CreateShortcut('
        f'{_ps_quote(link)}); '
        f'$s.TargetPath = {_ps_quote(pythonw())}; '
        f'$s.Arguments = {_ps_quote(chr(34) + APP_ENTRY + chr(34))}; '
        f'$s.WorkingDirectory = {_ps_quote(HERE)}; '
        f'$s.IconLocation = {_ps_quote(icon)}; '
        f'$s.WindowStyle = 7; '
        f'$s.Description = {_ps_quote("Localhost Manager tray app")}; '
        '$s.Save()'
    )
    ok, err = _run_ps(script)
    if ok and is_enabled():
        return True, 'Localhost Manager will start at login.'
    return False, err or 'Could not create the startup shortcut.'


def disable() -> tuple[bool, str]:
    link = shortcut_path()
    try:
        if os.path.exists(link):
            os.remove(link)
        return True, 'Removed from login startup.'
    except OSError as exc:
        return False, f'Could not remove startup shortcut: {exc}'


def _run_ps(script: str) -> tuple[bool, str]:
    try:
        res = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
            capture_output=True, text=True, creationflags=_NO_WINDOW,
        )
        if res.returncode == 0:
            return True, ''
        return False, (res.stderr or res.stdout or '').strip()
    except Exception as exc:
        return False, str(exc)
