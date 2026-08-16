"""Shared application state: the registry, the latest port scan, and the
derived view consumed by both the dashboard and the tray menu.

A single lock guards the mutable fields. The status poller (a background
thread) writes ``listeners``; the Tk main thread reads snapshots. UI actions
raised from the tray thread are funnelled through ``action_queue`` and drained
on the main thread.
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field

import ports
import registry


@dataclass
class AppRow:
    app: dict
    running: bool
    pid: int | None
    proc: str


@dataclass
class DiscoveredRow:
    port: int
    pid: int | None
    proc: str
    ip: str


@dataclass
class View:
    apps: list[AppRow] = field(default_factory=list)
    discovered: list[DiscoveredRow] = field(default_factory=list)

    @property
    def any_running(self) -> bool:
        return any(r.running for r in self.apps)

    @property
    def running_count(self) -> int:
        return sum(1 for r in self.apps if r.running)


class AppState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.config = registry.load()
        self.listeners: dict[int, ports.Listener] = {}
        self.action_queue: "queue.Queue[tuple]" = queue.Queue()

    # -- polling -----------------------------------------------------------
    def refresh_listeners(self) -> None:
        found = ports.scan_listeners()
        with self.lock:
            self.listeners = found

    def reload_config(self) -> None:
        cfg = registry.load()
        with self.lock:
            self.config = cfg

    # -- derived view ------------------------------------------------------
    def build_view(self) -> View:
        with self.lock:
            config = self.config
            listeners = dict(self.listeners)

        view = View()
        registered_ports = set()
        for app in config['apps']:
            registered_ports.add(app['port'])
            listener = listeners.get(app['port'])
            view.apps.append(AppRow(
                app=app,
                running=listener is not None,
                pid=listener.pid if listener else None,
                proc=listener.name if listener else '',
            ))

        disc = config['discovery']
        if disc.get('enabled', True):
            lo, hi = disc['port_min'], disc['port_max']
            extra = set(disc.get('extra_ports', []))
            for port, listener in sorted(listeners.items()):
                if port in registered_ports:
                    continue
                if not (lo <= port <= hi or port in extra):
                    continue
                view.discovered.append(DiscoveredRow(
                    port=port, pid=listener.pid,
                    proc=listener.name, ip=listener.ip,
                ))
        return view

    # -- actions -----------------------------------------------------------
    def enqueue(self, *action) -> None:
        self.action_queue.put(action)
