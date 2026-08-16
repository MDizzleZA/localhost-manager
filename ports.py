"""Listening-port detection and process control.

Primary path uses psutil; if that raises (e.g. permissions or an
environment where psutil misbehaves) we fall back to parsing the output
of `netstat -ano` + `tasklist`, which needs no third-party packages.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass

try:
    import psutil
except Exception:  # pragma: no cover - psutil is a declared dependency
    psutil = None

# Loopback / any-interface addresses we treat as "localhost".
LOCAL_IPS = {'127.0.0.1', '0.0.0.0', '::1', '::', ''}

# Hide the console window that CreateProcess would otherwise flash for the
# helper commands we shell out to on Windows.
_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0


@dataclass(frozen=True)
class Listener:
    """A single process listening on a local TCP port."""
    port: int
    pid: int | None
    name: str
    ip: str


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------
def scan_listeners() -> dict[int, Listener]:
    """Return {port: Listener} for every local TCP LISTEN socket."""
    if psutil is not None:
        try:
            return _scan_psutil()
        except Exception:
            pass
    return _scan_netstat()


def _scan_psutil() -> dict[int, Listener]:
    result: dict[int, Listener] = {}
    name_cache: dict[int, str] = {}
    for conn in psutil.net_connections(kind='tcp'):
        if conn.status != psutil.CONN_LISTEN or not conn.laddr:
            continue
        ip = conn.laddr.ip
        if ip not in LOCAL_IPS:
            continue
        port = conn.laddr.port
        pid = conn.pid
        # Prefer a loopback binding over an already-recorded one, but never
        # let a duplicate hide the first process we found for a port.
        if port in result and result[port].pid is not None:
            continue
        name = _proc_name(pid, name_cache)
        result[port] = Listener(port=port, pid=pid, name=name, ip=ip)
    return result


def _proc_name(pid: int | None, cache: dict[int, str]) -> str:
    if pid is None:
        return 'unknown'
    if pid in cache:
        return cache[pid]
    name = 'unknown'
    if psutil is not None:
        try:
            name = psutil.Process(pid).name()
        except Exception:
            name = 'unknown'
    cache[pid] = name
    return name


_NETSTAT_RE = re.compile(
    r'^\s*TCP\s+(\S+):(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$', re.IGNORECASE)


def _scan_netstat() -> dict[int, Listener]:
    result: dict[int, Listener] = {}
    try:
        out = subprocess.run(
            ['netstat', '-ano', '-p', 'tcp'],
            capture_output=True, text=True, creationflags=_NO_WINDOW,
        ).stdout
    except Exception:
        return result
    names = _tasklist_names()
    for line in out.splitlines():
        m = _NETSTAT_RE.match(line)
        if not m:
            continue
        ip, port_s, pid_s = m.group(1), m.group(2), m.group(3)
        ip = ip.strip('[]')
        if ip not in LOCAL_IPS:
            continue
        port = int(port_s)
        pid = int(pid_s)
        if port in result and result[port].pid:
            continue
        result[port] = Listener(
            port=port, pid=pid, name=names.get(pid, 'unknown'), ip=ip)
    return result


def _tasklist_names() -> dict[int, str]:
    names: dict[int, str] = {}
    try:
        out = subprocess.run(
            ['tasklist', '/fo', 'csv', '/nh'],
            capture_output=True, text=True, creationflags=_NO_WINDOW,
        ).stdout
    except Exception:
        return names
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2:
            image = parts[0].strip('"')
            try:
                names[int(parts[1])] = image
            except ValueError:
                continue
    return names


# ---------------------------------------------------------------------------
# Process control
# ---------------------------------------------------------------------------
def pid_for_port(port: int) -> int | None:
    listener = scan_listeners().get(port)
    return listener.pid if listener else None


def process_label(pid: int | None) -> str:
    """Human label for a pid, e.g. 'node.exe (12764)'."""
    if pid is None:
        return 'unknown'
    return f'{_proc_name(pid, {})} ({pid})'


def kill_tree(pid: int | None, timeout: float = 6.0) -> tuple[bool, str]:
    """Terminate a process and all of its descendants.

    Children are signalled before the parent so orphaned dev-server workers
    (npm -> node, cmd -> python, ...) do not survive.
    """
    if pid is None:
        return False, 'No owning process found for that port.'
    if psutil is None:
        return _taskkill(pid)
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return True, 'Process already gone.'
    except Exception as exc:  # pragma: no cover
        return False, f'Cannot access process {pid}: {exc}'

    try:
        procs = parent.children(recursive=True)
    except Exception:
        procs = []
    procs.append(parent)

    for proc in procs:
        try:
            proc.terminate()
        except Exception:
            pass
    gone, alive = psutil.wait_procs(procs, timeout=timeout)
    for proc in alive:
        try:
            proc.kill()
        except Exception:
            pass
    if alive:
        psutil.wait_procs(alive, timeout=2.0)

    still = _is_running(pid)
    if still:
        return _taskkill(pid)
    return True, f'Stopped {len(procs)} process(es).'


def _is_running(pid: int) -> bool:
    if psutil is None:
        return True
    try:
        return psutil.pid_exists(pid) and \
            psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except Exception:
        return False


def _taskkill(pid: int) -> tuple[bool, str]:
    """Last-resort forced kill of a tree via the Windows taskkill command."""
    try:
        res = subprocess.run(
            ['taskkill', '/PID', str(pid), '/T', '/F'],
            capture_output=True, text=True, creationflags=_NO_WINDOW,
        )
        if res.returncode == 0:
            return True, 'Stopped via taskkill.'
        return False, (res.stderr or res.stdout or 'taskkill failed').strip()
    except Exception as exc:
        return False, f'taskkill failed: {exc}'


def process_cwd(pid: int | None) -> str:
    """Best-effort working directory of a process (for 'Add to my apps')."""
    if pid is None or psutil is None:
        return ''
    try:
        return psutil.Process(pid).cwd()
    except Exception:
        return ''
