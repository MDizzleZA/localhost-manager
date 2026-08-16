"""Start / stop / open orchestration for registered and discovered apps."""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser

import ports

# Windows process creation flags.
CREATE_NEW_CONSOLE = 0x00000010
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200

# Popen handles for things we launched, keyed by port (best-effort bookkeeping;
# stop-by-port is authoritative and works even for processes we did not start).
_LAUNCHED: dict[int, subprocess.Popen] = {}


def start_app(app: dict) -> tuple[bool, str]:
    """Launch an app's command in its working directory."""
    command = (app.get('command') or '').strip()
    if not command:
        return False, f"No start command set for '{app['name']}'. Edit apps.json."

    cwd = (app.get('cwd') or '').strip() or None
    if cwd and not os.path.isdir(cwd):
        return False, f"Working folder does not exist: {cwd}"

    if ports.scan_listeners().get(app['port']):
        return True, f"'{app['name']}' is already running on port {app['port']}."

    if sys.platform == 'win32':
        flags = CREATE_NEW_PROCESS_GROUP
        flags |= CREATE_NEW_CONSOLE if app.get('console') else CREATE_NO_WINDOW
        creationflags = flags
    else:  # pragma: no cover - target platform is Windows
        creationflags = 0

    try:
        proc = subprocess.Popen(
            command, cwd=cwd, shell=True, creationflags=creationflags,
        )
    except Exception as exc:
        return False, f"Failed to start '{app['name']}': {exc}"

    _LAUNCHED[app['port']] = proc
    return True, f"Starting '{app['name']}' (port {app['port']})…"


def stop_port(port: int, label: str = '') -> tuple[bool, str]:
    """Stop whatever process owns a port, killing its whole tree."""
    who = label or f'port {port}'
    pid = ports.pid_for_port(port)
    if pid is None:
        _LAUNCHED.pop(port, None)
        return True, f"{who} is not running."
    ok, msg = ports.kill_tree(pid)
    if ok:
        _LAUNCHED.pop(port, None)
        return True, f"Stopped {who}. {msg}"
    return False, f"Could not stop {who}: {msg}"


def open_app(app_or_url) -> tuple[bool, str]:
    if isinstance(app_or_url, dict):
        url = app_or_url.get('url') or f"http://localhost:{app_or_url['port']}"
    else:
        url = str(app_or_url)
    try:
        webbrowser.open(url)
        return True, f'Opened {url}'
    except Exception as exc:
        return False, f'Could not open {url}: {exc}'
