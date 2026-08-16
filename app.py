"""Localhost Manager — a system-tray control panel for local dev servers.

Entry point. Wires together:
  * a background poller thread that scans listening ports,
  * the pystray tray icon (its own thread),
  * the Tk dashboard window (main thread),
  * an action queue drained on the main thread so every UI/subprocess action
    runs single-threaded and Tk-safe.

Launch silently (tray only) with pythonw:  pythonw app.py
Launch with the dashboard shown:           python  app.py --show
"""
from __future__ import annotations

import os
import sys
import threading
import time
import tkinter as tk

import autostart
import manager
import registry
import shortcuts
from dashboard import Dashboard
from state import AppState
from tray import Tray

POLL_SECONDS = 2.5
TICK_MS = 1000


class LocalhostManagerApp:
    def __init__(self, show: bool = False) -> None:
        self.state = AppState()
        self.root = tk.Tk()
        self.dashboard = Dashboard(self.root, self.state)
        self.root.protocol('WM_DELETE_WINDOW', self._hide)
        self.root.withdraw()  # start hidden — the tray icon is the home base
        self.tray = Tray(self.state)
        self._sig = None
        self._want_show = show
        self._quitting = False

    # ------------------------------------------------------------- lifecycle
    def run(self) -> None:
        threading.Thread(target=self._poll_loop, daemon=True).start()
        self.tray.run()
        self.dashboard.refresh()
        if self._want_show:
            self._show()
        else:
            self._notify('Localhost Manager is running in the system tray.')
        self.root.after(300, self._tick)
        self.root.mainloop()

    def _poll_loop(self) -> None:
        while not self._quitting:
            try:
                self.state.refresh_listeners()
            except Exception:
                pass
            time.sleep(POLL_SECONDS)

    def _tick(self) -> None:
        if self._quitting:
            return
        try:
            self._drain_actions()
            view = self.state.build_view()
            sig = _signature(view)
            if sig != self._sig:
                self._sig = sig
                self.tray.update(view)
                if self.root.state() == 'normal':
                    self.dashboard.refresh()
        except Exception as exc:  # keep the loop alive no matter what
            sys.stderr.write(f'[tick] {exc}\n')
        finally:
            self.root.after(TICK_MS, self._tick)

    # --------------------------------------------------------------- actions
    def _drain_actions(self) -> None:
        q = self.state.action_queue
        while not q.empty():
            action = q.get_nowait()
            self._handle(action)

    def _handle(self, action: tuple) -> None:
        name = action[0]
        if name == 'open_dashboard':
            self._show()
        elif name == 'start':
            self._async(manager.start_app, action[1])
        elif name == 'stop':
            self._async(manager.stop_port, action[1],
                        action[2] if len(action) > 2 else '')
        elif name == 'open':
            manager.open_app(action[1])
        elif name == 'toggle_autostart':
            self._toggle_autostart()
        elif name == 'desktop_shortcut':
            ok, msg = shortcuts.create_desktop_shortcut()
            self._notify(msg if ok else f'Shortcut: {msg}')
        elif name == 'edit_json':
            self._edit_json()
        elif name == 'refresh':
            self._async(self.state.refresh_listeners)
        elif name == 'quit':
            self._quit()

    def _async(self, fn, *args) -> None:
        def worker():
            try:
                fn(*args)
            except Exception as exc:
                sys.stderr.write(f'[action] {exc}\n')
            # Force a prompt rescan so status flips right after the action.
            try:
                self.state.refresh_listeners()
            except Exception:
                pass
            self.root.after(0, self._force_ui)
        threading.Thread(target=worker, daemon=True).start()

    def _force_ui(self) -> None:
        view = self.state.build_view()
        self._sig = _signature(view)
        self.tray.update(view)
        if self.root.state() == 'normal':
            self.dashboard.refresh()

    def _toggle_autostart(self) -> None:
        ok, msg = (autostart.disable() if autostart.is_enabled()
                   else autostart.enable())
        self._notify(msg if ok else f'Autostart: {msg}')
        self._force_ui()

    def _edit_json(self) -> None:
        try:
            os.startfile(registry.CONFIG_PATH)  # type: ignore[attr-defined]
        except Exception as exc:
            self._notify(f'Could not open apps.json: {exc}')

    # ----------------------------------------------------------------- window
    def _show(self) -> None:
        self.dashboard.refresh()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _hide(self) -> None:
        self.root.withdraw()

    def _notify(self, message: str) -> None:
        try:
            self.tray.icon.notify(message, 'Localhost Manager')
        except Exception:
            pass

    def _quit(self) -> None:
        self._quitting = True
        self.tray.stop()
        try:
            self.root.destroy()
        except Exception:
            pass


def _signature(view) -> tuple:
    return (
        tuple((r.app['name'], r.app['port'], r.running) for r in view.apps),
        tuple((d.port, d.proc) for d in view.discovered),
    )


def main() -> None:
    show = '--show' in sys.argv
    LocalhostManagerApp(show=show).run()


if __name__ == '__main__':
    main()
