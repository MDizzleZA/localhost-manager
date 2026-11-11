"""Load / save / validate the app registry (apps.json)."""
from __future__ import annotations

import os
import sys
import json

if getattr(sys, 'frozen', False):
    # Version compilée en EXE
    CONFIG_DIR = os.path.dirname(sys.executable)
else:
    # Version Python classique
    CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(CONFIG_DIR, "apps.json")

DEFAULT_CONFIG = {
    'discovery': {
        'enabled': True,
        'port_min': 3000,
        'port_max': 9999,
        # Common dev/service ports outside the range above worth surfacing.
        'extra_ports': [80, 5000, 5173, 5432, 8000, 8080, 27017],
    },
    'apps': [
        {
            'name': 'Example — Vite dev server',
            'port': 5173,
            'cwd': 'C:\\path\\to\\your\\project',
            'command': 'npm run dev',
            'url': 'http://localhost:5173',
            'console': False,
        }
    ],
    # Empty roots => the "Scan PC" button uses scanner.default_roots().
    'scan': {'roots': [], 'max_depth': 4},
}

# Every app entry is normalised to these keys.
_APP_KEYS = ('name', 'port', 'cwd', 'command', 'url', 'console')


def load(path: str = CONFIG_PATH) -> dict:
    """Return the config, creating a default file the first time."""
    if not os.path.exists(path):
        save(DEFAULT_CONFIG, path)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(DEFAULT_CONFIG))
    return _normalise(data)


def save(config: dict, path: str = CONFIG_PATH) -> None:
    tmp = f'{path}.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(config, fh, indent=2)
    os.replace(tmp, path)


def _normalise(data: dict) -> dict:
    disc = data.get('discovery') or {}
    default_disc = DEFAULT_CONFIG['discovery']
    discovery = {
        'enabled': bool(disc.get('enabled', default_disc['enabled'])),
        'port_min': _as_int(disc.get('port_min'), default_disc['port_min']),
        'port_max': _as_int(disc.get('port_max'), default_disc['port_max']),
        'extra_ports': [
            p for p in (
                _as_int(x, 0) for x in disc.get('extra_ports', default_disc['extra_ports'])
            ) if p
        ],
    }
    apps = []
    for raw in data.get('apps', []):
        app = normalise_app(raw)
        if app is not None:
            apps.append(app)

    scan = data.get('scan') or {}
    scan_cfg = {
        'roots': [str(r) for r in scan.get('roots', []) if str(r).strip()],
        'max_depth': _as_int(scan.get('max_depth'), 4),
    }
    return {'discovery': discovery, 'apps': apps, 'scan': scan_cfg}


def normalise_app(raw: dict) -> dict | None:
    """Coerce one raw entry into a valid app dict, or None if unusable."""
    if not isinstance(raw, dict):
        return None
    port = _as_int(raw.get('port'), 0)
    name = str(raw.get('name') or '').strip()
    if not port or not name:
        return None
    url = str(raw.get('url') or '').strip() or f'http://localhost:{port}'
    return {
        'name': name,
        'port': port,
        'cwd': str(raw.get('cwd') or '').strip(),
        'command': str(raw.get('command') or '').strip(),
        'url': url,
        'console': bool(raw.get('console', False)),
    }


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def add_app(config: dict, app: dict, path: str = CONFIG_PATH) -> None:
    config['apps'].append(app)
    save(config, path)


def replace_apps(config: dict, apps: list[dict], path: str = CONFIG_PATH) -> None:
    config['apps'] = apps
    save(config, path)
