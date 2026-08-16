# Localhost Manager

A small Windows **system-tray** app that shows every local app on `localhost`
— **registered**, **running**, or **not running** — plus anything else it
finds listening, with one-click **Start / Stop / Open**.

## Run it

Silent (tray icon only — this is the normal way):

```bash
run.bat
```

With the dashboard shown on launch (handy the first time):

```bash
python app.py --show
```

First run creates `apps.json` with one example entry.

### Desktop shortcut

There's a **Localhost Manager** shortcut on your Desktop (custom icon) that
launches it silently with `pythonw`. To recreate it, use the tray menu →
**Create desktop shortcut**.

## How it decides "running"

Each registered app has a **port**. If something is `LISTENING` on that port,
the app is *running*; otherwise it's *not running*. Discovery lists any other
process listening on a localhost dev port (default `3000–9999`, plus a few
common ones like `5432`) so you can Stop / Open / add it to your list.

## The dashboard

- **Your apps** — registered entries with live status. Select one, then
  **Start**, **Stop**, or **Open**. Double-click starts a stopped app (or
  opens a running one).
- **Discovered on localhost** — everything else listening. **Stop** asks for
  confirmation first (so you don't kill Postgres by accident). **Add / Edit**
  turns a discovered port into a registered app.
- **Edit apps.json** opens the config in your default editor; **Refresh**
  re-scans immediately.

## The tray menu (right-click)

Quick Start/Stop/Open per app, a **Discovered** submenu, **Start at login**
(toggle), **Create desktop shortcut**, **Edit apps.json**, **Refresh**, and
**Quit**. Left-click opens the dashboard. The icon's dot turns green when at
least one registered app is up.

## Finding apps to add

Click **Scan PC…** on the dashboard. It scans your dev folders (see
`scan.roots` / defaults in `scanner.py`), detects startable Node and Python
servers, skips ones already registered, and lists the rest as a checklist to
add in one click. Ports it can't read exactly are marked *(guessed)*.

## apps.json

```json
{
  "discovery": {
    "enabled": true,
    "port_min": 3000,
    "port_max": 9999,
    "extra_ports": [80, 5000, 5173, 5432, 8000, 8080, 27017]
  },
  "apps": [
    {
      "name": "Example — Vite dev server",
      "port": 5173,
      "cwd": "C:\\path\\to\\your\\project",
      "command": "npm run dev",
      "url": "http://localhost:5173",
      "console": false
    }
  ]
}
```

- `command` runs via the shell in `cwd`. Set `console: true` to open a visible
  console window for that app (to watch its logs).
- `url` is optional; it defaults to `http://localhost:<port>`.
- **Stop** works even for apps you didn't start from here — it finds the
  process that owns the port and terminates that process tree.

## Start at login

The **Start at login** toggle creates/removes a shortcut in your Startup
folder that launches the tray app with `pythonw` (no console). Toggle it off
to stop it auto-starting.

## Requirements

Python 3 with `pystray`, `psutil`, `Pillow`:

```bash
pip install -r requirements.txt
```
