"""Scan likely dev roots for startable localhost servers.

Detects Node projects (package.json dev/start scripts), Python web servers
(Flask/FastAPI/uvicorn/Django/Streamlit/http.server), and .bat launchers,
and infers a best-guess port + start command for each. Pure logic, no UI.
"""
from __future__ import annotations

import json
import os
import re

# This app's own folder — never offer ourselves as a candidate.
APP_DIR = os.path.normcase(os.path.dirname(os.path.abspath(__file__)))

# Directory names never worth descending into.
SKIP = {
    'node_modules', '.git', '.venv', 'venv', 'env', '__pycache__', 'dist',
    'build', '.next', '.nuxt', '.svelte-kit', 'out', 'vendor', 'site-packages',
    '.obsidian', 'coverage', '.cache', '.turbo', '.parcel-cache', 'tmp',
    '.tmp.drivedownload', '.tmp.driveupload',
    # Test / example / utility dirs (noise, not deployable apps).
    'tests', 'test', '__tests__', 'e2e', 'examples', 'example', 'sample',
    'samples', 'fixtures', 'scripts', 'connectors', 'migrations',
    # Heavy / non-code content dirs worth skipping.
    'Vault', 'Design Assets', 'videos',
    # Local by Flywheel internals.
    'app', 'public', 'conf', 'logs',
}
MAX_DEPTH_DEFAULT = 4

# Python filenames that are servers-by-accident (auth callbacks, tests, …).
PY_NAME_SKIP = re.compile(
    r'auth|oauth|callback|setup|benchmark|conftest|bridge|example|sample'
    r'|migrat|fixture|wsgi|asgi|__init__|_test|test_', re.IGNORECASE)

FRAMEWORK_PORT = {
    'next': 3000, 'react-scripts': 3000, 'vite': 5173, 'astro': 4321,
    'nuxt': 3000, '@remix-run': 3000, 'gatsby': 8000, 'vue-cli-service': 8080,
    'ng': 4200, '@angular': 4200, 'svelte': 5173, 'http-server': 8080,
    'serve': 3000, 'electron': 5173, 'expo': 8081, 'docusaurus': 3000,
    'remotion': 3000,
}
SCRIPT_PREF = ['dev', 'start', 'serve', 'develop', 'preview', 'pwa:dev', 'web']
NON_SERVER = {'test', 'lint', 'build', 'check', 'typecheck', 'format', 'clean',
              'upgrade', 'postinstall', 'prepare', 'deploy', 'release'}
SERVER_RE = re.compile(
    r'vite(?!st)|next\b|astro\b|remotion studio|nuxt|ng serve|http-server'
    r'|\bserve\b|nodemon|node\s+.*server|uvicorn|flask|streamlit',
    re.IGNORECASE)


def default_roots() -> list[str]:
    """The dev-project locations to scan, filtered to those that exist."""
    home = os.path.expanduser('~')
    roots = [
        os.path.join(home, 'projects'),
        os.path.join(home, 'Local Sites'),
        os.path.join(home, 'source'),
        os.path.join(home, 'repos'),
        os.path.join(home, 'dev'),
        os.path.join(home, 'code'),
        os.path.join(home, 'Documents'),
    ]
    seen, out = set(), []
    for r in roots:
        key = os.path.normcase(os.path.normpath(r))
        if key not in seen and os.path.isdir(r):
            seen.add(key)
            out.append(r)
    return out


# ---------------------------------------------------------------------------
def scan(roots: list[str] | None = None,
         max_depth: int = MAX_DEPTH_DEFAULT) -> list[dict]:
    roots = roots or default_roots()
    found: list[dict] = []
    for root in roots:
        _walk(root, max_depth, found)
    # De-dupe by (cwd, command); never offer our own app folder.
    seen, uniq = set(), []
    for c in found:
        if os.path.normcase(os.path.normpath(c['cwd'])).startswith(APP_DIR):
            continue
        key = (os.path.normcase(c['cwd']), c['command'].lower())
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    uniq.sort(key=lambda c: (c['port_guessed'], c['name'].lower()))
    return uniq


def is_registered(candidate: dict, apps: list[dict]) -> bool:
    """True if an existing app already covers this candidate.

    Matches on the same project folder OR the same port, so re-scanning
    never offers a project (or port) that is already in the list.
    """
    cwd = os.path.normcase(os.path.normpath(candidate['cwd']))
    for a in apps:
        if os.path.normcase(os.path.normpath(a.get('cwd', ''))) == cwd:
            return True
        if a.get('port') == candidate['port']:
            return True
    return False


def new_candidates(apps: list[dict], roots: list[str] | None = None,
                   max_depth: int = MAX_DEPTH_DEFAULT) -> list[dict]:
    return [c for c in scan(roots, max_depth) if not is_registered(c, apps)]


# ---------------------------------------------------------------------------
def _read(path: str, limit: int = 20000) -> str:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
            return fh.read(limit)
    except OSError:
        return ''


def _find_port(text: str) -> int | None:
    for pat in (r'--port[= ]+(\d{2,5})', r'\bport\s*[=:]\s*(\d{2,5})',
                r'PORT\s*[=:]\s*(\d{2,5})', r'runserver[^\d]*(\d{2,5})',
                r'localhost:(\d{2,5})', r'0\.0\.0\.0:(\d{2,5})',
                r'127\.0\.0\.1:(\d{2,5})', r'listen\(\s*(\d{2,5})'):
        m = re.search(pat, text)
        if m:
            p = int(m.group(1))
            if 80 <= p <= 65535:
                return p
    return None


def _node_candidate(pdir: str) -> dict | None:
    try:
        pkg = json.loads(_read(os.path.join(pdir, 'package.json')))
    except Exception:
        return None
    scripts = pkg.get('scripts', {}) or {}
    if not scripts:
        return None
    script = next((s for s in SCRIPT_PREF if s in scripts), None)
    if script is None:
        for k, v in scripts.items():
            if k in NON_SERVER:
                continue
            if SERVER_RE.search(str(v)):
                script = k
                break
    if script is None:
        return None
    deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
    blob = ' '.join(deps) + ' ' + ' '.join(scripts.values())
    fw = next((f for f in FRAMEWORK_PORT if f in blob), None)
    port = _find_port(scripts.get(script, ''))
    if port is None:
        for cfg in ('vite.config.ts', 'vite.config.js', 'vite.config.mjs',
                    'next.config.js', 'next.config.mjs', 'astro.config.mjs',
                    'vue.config.js'):
            fp = os.path.join(pdir, cfg)
            if os.path.exists(fp):
                port = _find_port(_read(fp))
                if port:
                    break
    guessed = port is None
    if port is None:
        port = FRAMEWORK_PORT.get(fw, 3000)
    return {'name': pkg.get('name') or os.path.basename(pdir), 'port': port,
            'cwd': pdir, 'command': f'npm run {script}',
            'kind': f'node/{fw or "?"}', 'port_guessed': guessed}


def _python_candidates(pdir: str, files: list[str]) -> list[dict]:
    """Detect real Python web servers only — precise over exhaustive.

    Requires a genuine framework signature (not a passing mention of the
    word), and for a plain http.server it must actually serve and have a
    __main__ entrypoint. Auth/test/setup helper scripts are skipped by name.
    """
    out = []
    lower = {f.lower() for f in files}
    if 'manage.py' in lower:
        return [_pc(pdir, 'Django', 'python manage.py runserver', 8000,
                    guessed=True)]
    for f in files:
        if not f.endswith('.py') or PY_NAME_SKIP.search(f):
            continue
        txt = _read(os.path.join(pdir, f))
        low = txt.lower()
        port = _find_port(txt)
        sig, cmd = None, f'python {f}'
        if re.search(r'^\s*(import|from)\s+streamlit', txt, re.MULTILINE):
            sig, cmd, port = 'Streamlit', f'streamlit run {f}', port or 8501
        elif 'uvicorn.run(' in low or re.search(r'=\s*FastAPI\(', txt):
            sig, port = 'FastAPI/uvicorn', port or 8000
        elif re.search(r'Flask\(__name__', txt) and 'app.run(' in low:
            sig, port = 'Flask', port or 5000
        elif re.search(r'aiohttp\.web|bottle\s*\(|\.run_server\(', txt):
            sig, port = 'python server', port or 8000
        elif (('serve_forever' in low
               or re.search(r'(?:Threading)?(?:HTTP|TCP)Server\(', txt))
              and '__main__' in low):
            sig, port = 'http server', port or 8000
        if sig:
            out.append(_pc(pdir, sig, cmd, port,
                           guessed=_find_port(txt) is None, entry=f))
    return out


def _bat_candidates(pdir: str, files: list[str]) -> list[dict]:
    out = []
    for f in files:
        if not f.lower().endswith(('.bat', '.cmd')):
            continue
        if not re.search(r'run|start|serve|dev', f, re.I):
            continue
        txt = _read(os.path.join(pdir, f))
        if not re.search(r'python|node|npm|uvicorn|flask|streamlit|http\.server',
                         txt, re.I):
            continue
        port = _find_port(txt)
        if port:
            out.append(_pc(pdir, 'bat launcher', f, port, guessed=False,
                           entry=f))
    return out


def _pc(pdir, kind, cmd, port, guessed=False, entry=''):
    return {'name': os.path.basename(pdir) + (f' ({entry})' if entry else ''),
            'port': port, 'cwd': pdir, 'command': cmd, 'kind': kind,
            'port_guessed': guessed}


def _walk(root: str, max_depth: int, out: list[dict]) -> None:
    if not os.path.isdir(root):
        return
    base = root.rstrip('\\').count('\\')
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath.count('\\') - base >= max_depth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP and not d.startswith('.')]
        try:
            if 'package.json' in filenames:
                c = _node_candidate(dirpath)
                if c:
                    out.append(c)
            if any(f.endswith('.py') for f in filenames):
                out.extend(_python_candidates(dirpath, filenames))
            out.extend(_bat_candidates(dirpath, filenames))
        except Exception:
            continue
