"""System-tray icon + right-click menu (pystray).

The tray lives on its own thread. Menu callbacks do no real work — they push
an action tuple onto the shared queue, which the Tk main thread drains. This
keeps the menu responsive and keeps all Tk/subprocess work on one thread.
"""
from __future__ import annotations

import pystray

import autostart
import theme
from state import AppState, View

MAX_MENU_APPS = 12
MAX_MENU_DISCOVERED = 12


def make_image(any_running: bool):
    """The tray glyph, tinted green when at least one app is running."""
    return theme.make_icon_image(64, running=any_running)


class Tray:
    def __init__(self, state: AppState) -> None:
        self.state = state
        self._last_running = False
        self._view = View()
        self.icon = pystray.Icon(
            'localhost_manager',
            icon=make_image(False),
            title='Localhost Manager',
            menu=self._build_menu(),
        )

    def run(self) -> None:
        self.icon.run_detached()

    def stop(self) -> None:
        try:
            self.icon.stop()
        except Exception:
            pass

    def update(self, view: View) -> None:
        """Refresh menu + icon to reflect a new view (called from main thread)."""
        self._view = view
        running = view.any_running
        if running != self._last_running:
            self.icon.icon = make_image(running)
            self._last_running = running
        self.icon.menu = self._build_menu()
        try:
            self.icon.update_menu()
        except Exception:
            pass

    # ---------------------------------------------------------------- menu
    def _build_menu(self) -> pystray.Menu:
        M, I, S = pystray.Menu, pystray.MenuItem, pystray.Menu.SEPARATOR
        items = [I('Open dashboard', self._act('open_dashboard'), default=True),
                 S]

        for row in self._view.apps[:MAX_MENU_APPS]:
            app = row.app
            dot = '● ' if row.running else '○ '
            sub = M(
                I('Start', self._act('start', app),
                  enabled=not row.running),
                I('Stop', self._act('stop', app['port'], f"'{app['name']}'"),
                  enabled=row.running),
                I('Open', self._act('open', app)),
            )
            items.append(I(dot + app['name'], sub))

        if self._view.discovered:
            disc_items = []
            for d in self._view.discovered[:MAX_MENU_DISCOVERED]:
                label = f'port {d.port} — {d.proc}'
                sub = M(
                    I('Stop', self._act('stop', d.port,
                                        f'{d.proc} on port {d.port}')),
                    I('Open', self._act('open', f'http://localhost:{d.port}')),
                )
                disc_items.append(I(label, sub))
            items.append(I(f'Discovered ({len(self._view.discovered)})',
                           M(*disc_items)))

        items += [
            S,
            I('Start at login', self._act('toggle_autostart'),
              checked=lambda _i: autostart.is_enabled()),
            I('Create desktop shortcut', self._act('desktop_shortcut')),
            I('Edit apps.json', self._act('edit_json')),
            I('Refresh', self._act('refresh')),
            S,
            I('Quit', self._act('quit')),
        ]
        return pystray.Menu(*items)

    def _act(self, *action):
        """Return a menu callback that just enqueues an action."""
        def handler(_icon=None, _item=None):
            self.state.enqueue(*action)
        return handler
