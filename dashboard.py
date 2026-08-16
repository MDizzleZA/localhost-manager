"""The Tk dashboard window: a live table of registered + discovered apps
with Start / Stop / Open / Add controls.

Runs on the Tk main thread. Potentially slow actions (stopping a process
tree) are executed on short-lived worker threads and reported back via
``root.after`` so the UI never blocks.
"""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import manager
import ports
import registry
import scanner
import theme
from state import AppState

# Kept as names for the dialogs; sourced from the design system.
RUN_GREEN = theme.RUNNING
STOP_GREY = theme.MUTED
GROUP_FG = theme.TEXT


class Dashboard:
    def __init__(self, root: tk.Tk, state: AppState) -> None:
        self.root = root
        self.state = state
        self._row_meta: dict[str, tuple] = {}
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self.root.title('Localhost Manager')
        self.root.geometry('790x540')
        self.root.minsize(700, 440)
        theme.apply_theme(self.root)
        self._set_window_icon()

        # ---- header card ----------------------------------------------
        header = ttk.Frame(self.root, style='Header.TFrame', padding=(16, 13))
        header.pack(fill='x')
        header.columnconfigure(1, weight=1)
        self._logo = None
        try:
            from PIL import ImageTk
            self._logo = ImageTk.PhotoImage(theme.make_icon_image(36, True))
            ttk.Label(header, image=self._logo, style='Surface.TLabel').grid(
                row=0, column=0, rowspan=2, padx=(0, 13))
        except Exception:
            pass
        ttk.Label(header, text='Localhost Manager',
                  style='Title.TLabel').grid(row=0, column=1, sticky='w')
        ttk.Label(header, text='Your local dev servers at a glance',
                  style='Subtitle.TLabel').grid(row=1, column=1, sticky='w')
        self.chip = ttk.Label(header, text='', style='ChipIdle.TLabel')
        self.chip.grid(row=0, column=2, sticky='e')
        self.disc_lbl = ttk.Label(header, text='', style='Subtitle.TLabel')
        self.disc_lbl.grid(row=1, column=2, sticky='e', pady=(4, 0))
        tk.Frame(self.root, background=theme.BORDER, height=1).pack(fill='x')

        # ---- body: bordered surface card holding the tree -------------
        body = ttk.Frame(self.root, padding=(14, 12, 14, 8))
        body.pack(fill='both', expand=True)
        card = tk.Frame(body, background=theme.BORDER)
        card.pack(fill='both', expand=True)
        inner = tk.Frame(card, background=theme.SURFACE)
        inner.pack(fill='both', expand=True, padx=1, pady=1)

        cols = ('port', 'status', 'proc')
        self.tree = ttk.Treeview(inner, columns=cols, show='tree headings',
                                 selectmode='browse')
        self.tree.heading('#0', text='   APP')
        self.tree.heading('port', text='PORT')
        self.tree.heading('status', text='STATUS')
        self.tree.heading('proc', text='PROCESS')
        self.tree.column('#0', width=300, anchor='w')
        self.tree.column('port', width=66, anchor='center')
        self.tree.column('status', width=132, anchor='w')
        self.tree.column('proc', width=150, anchor='w')

        vsb = ttk.Scrollbar(inner, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        self.tree.pack(side='left', fill='both', expand=True)

        self.tree.tag_configure('running', foreground=theme.RUNNING,
                                background=theme.RUNNING_BG)
        self.tree.tag_configure('stopped', foreground=theme.MUTED,
                                background=theme.SURFACE)
        self.tree.tag_configure('group', foreground=theme.TEXT,
                                background=theme.GROUP_BG, font=theme.F_GROUP)
        self.tree.tag_configure('empty', foreground=theme.FAINT,
                                background=theme.SURFACE)
        self.tree.bind('<Double-1>', self._on_double)
        self.tree.bind('<<TreeviewSelect>>', lambda _e: self._sync_buttons())

        # ---- toolbar --------------------------------------------------
        bar = ttk.Frame(self.root, padding=(14, 0, 14, 10))
        bar.pack(fill='x')
        self.b_start = ttk.Button(bar, text='Start', style='Primary.TButton',
                                  command=self._start)
        self.b_stop = ttk.Button(bar, text='Stop', style='Danger.TButton',
                                 command=self._stop)
        self.b_open = ttk.Button(bar, text='Open', command=self._open)
        self.b_start.pack(side='left')
        self.b_stop.pack(side='left', padx=(6, 0))
        self.b_open.pack(side='left', padx=(6, 0))
        ttk.Separator(bar, orient='vertical').pack(
            side='left', fill='y', padx=11, pady=3)
        self.b_add = ttk.Button(bar, text='Add / Edit', command=self._add_edit)
        self.b_scan = ttk.Button(bar, text='Scan PC…', command=self._scan_pc)
        self.b_add.pack(side='left')
        self.b_scan.pack(side='left', padx=(6, 0))
        ttk.Button(bar, text='Edit apps.json',
                   command=self._edit_json).pack(side='right')
        ttk.Button(bar, text='Refresh',
                   command=self._force_refresh).pack(side='right', padx=(0, 6))

        # ---- footer status bar ---------------------------------------
        tk.Frame(self.root, background=theme.BORDER, height=1).pack(fill='x')
        self.status = ttk.Label(self.root, text='Ready', style='Status.TLabel',
                                anchor='w')
        self.status.pack(fill='x', side='bottom')

        self.root.bind('<FocusIn>', self._on_focus)

    def _set_window_icon(self) -> None:
        try:
            ico = theme.ensure_ico()
            if ico:
                self.root.iconbitmap(ico)
        except Exception:
            pass

    # -------------------------------------------------------------- render
    def refresh(self) -> None:
        """Re-render the tree from the current cached view (cheap)."""
        view = self.state.build_view()
        selected = self.tree.selection()
        sel_key = self._row_meta.get(selected[0]) if selected else None

        self.tree.delete(*self.tree.get_children())
        self._row_meta.clear()

        apps_node = self.tree.insert(
            '', 'end', text='  Your apps', open=True, tags=('group',))
        if not view.apps:
            self.tree.insert(apps_node, 'end',
                             text='  (none registered — use Add / Edit)',
                             tags=('empty',))
        for i, row in enumerate(view.apps):
            dot = '\u25cf  running' if row.running else '\u25cb  not running'
            tag = 'running' if row.running else 'stopped'
            item = self.tree.insert(
                apps_node, 'end', text='   ' + row.app['name'],
                values=(row.app['port'], dot, row.proc or ''), tags=(tag,))
            self._row_meta[item] = ('app', i)

        disc_node = self.tree.insert(
            '', 'end', text='  Discovered on localhost', open=True,
            tags=('group',))
        if not view.discovered:
            self.tree.insert(disc_node, 'end',
                             text='  (nothing else listening in range)',
                             tags=('empty',))
        for row in view.discovered:
            item = self.tree.insert(
                disc_node, 'end', text='   port ' + str(row.port),
                values=(row.port, '\u25cf  running', row.proc or ''),
                tags=('running',))
            self._row_meta[item] = ('disc', row.port)

        # Restore selection by key where possible; otherwise keep the top
        # ("Your apps") group in view rather than drifting down the list.
        restored = False
        if sel_key:
            for item, key in self._row_meta.items():
                if key == sel_key:
                    self.tree.selection_set(item)
                    restored = True
                    break
        if not restored:
            self.tree.yview_moveto(0.0)

        run = view.running_count
        self.chip.configure(text=f'{run} running',
                            style='Chip.TLabel' if run else 'ChipIdle.TLabel')
        self.disc_lbl.configure(text=f'{len(view.discovered)} discovered')
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        kind, row = self._selected()
        is_app = kind == 'app'
        is_disc = kind == 'disc'
        running = False
        if is_app:
            running = row.running
        elif is_disc:
            running = True
        self.b_start.state(['!disabled'] if (is_app and not running)
                           else ['disabled'])
        self.b_stop.state(['!disabled'] if running else ['disabled'])
        self.b_open.state(['!disabled'] if (is_app or is_disc) else ['disabled'])

    # -------------------------------------------------------------- helpers
    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            return None, None
        meta = self._row_meta.get(sel[0])
        if not meta:
            return None, None
        view = self.state.build_view()
        if meta[0] == 'app':
            idx = meta[1]
            if idx < len(view.apps):
                return 'app', view.apps[idx]
        elif meta[0] == 'disc':
            for d in view.discovered:
                if d.port == meta[1]:
                    return 'disc', d
        return None, None

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def _run_async(self, fn, *args) -> None:
        def worker():
            ok, msg = fn(*args)
            self.root.after(0, self._after_action, ok, msg)
        threading.Thread(target=worker, daemon=True).start()

    def _after_action(self, ok: bool, msg: str) -> None:
        self._set_status(msg)
        # Force a fresh scan so status flips promptly after start/stop.
        threading.Thread(
            target=lambda: (self.state.refresh_listeners(),
                            self.root.after(0, self.refresh)),
            daemon=True).start()

    # -------------------------------------------------------------- actions
    def _start(self) -> None:
        kind, row = self._selected()
        if kind != 'app':
            return
        self._set_status(f"Starting '{row.app['name']}'…")
        self._run_async(manager.start_app, row.app)

    def _stop(self) -> None:
        kind, row = self._selected()
        if kind == 'app':
            self._set_status(f"Stopping '{row.app['name']}'…")
            self._run_async(manager.stop_port, row.app['port'],
                            f"'{row.app['name']}'")
        elif kind == 'disc':
            label = f'{row.proc} on port {row.port}'
            if not messagebox.askyesno(
                    'Stop discovered process',
                    f'Stop {label}?\n\nThis is not one of your registered '
                    'apps. Its whole process tree (PID '
                    f'{row.pid}) will be terminated.',
                    parent=self.root):
                return
            self._set_status(f'Stopping {label}…')
            self._run_async(manager.stop_port, row.port, label)

    def _open(self) -> None:
        kind, row = self._selected()
        if kind == 'app':
            manager.open_app(row.app)
            self._set_status(f"Opened {row.app['url']}")
        elif kind == 'disc':
            url = f'http://localhost:{row.port}'
            manager.open_app(url)
            self._set_status(f'Opened {url}')

    def _on_double(self, _event) -> None:
        kind, row = self._selected()
        if kind == 'app' and not row.running:
            self._start()
        elif kind in ('app', 'disc'):
            self._open()

    def _add_edit(self) -> None:
        kind, row = self._selected()
        if kind == 'app':
            self._open_dialog(existing=row.app)
        elif kind == 'disc':
            prefill = {
                'name': row.proc.replace('.exe', '') or f'Port {row.port}',
                'port': row.port,
                'cwd': ports.process_cwd(row.pid),
                'command': '',
                'url': f'http://localhost:{row.port}',
                'console': False,
            }
            self._open_dialog(prefill=prefill)
        else:
            self._open_dialog()

    def _open_dialog(self, existing: dict | None = None,
                     prefill: dict | None = None) -> None:
        AppDialog(self.root, self.state, self._on_saved,
                  existing=existing, prefill=prefill)

    def _on_saved(self, msg: str) -> None:
        self.state.reload_config()
        self._set_status(msg)
        self.refresh()

    # ------------------------------------------------------------- scan PC
    def _scan_pc(self) -> None:
        self.b_scan.state(['disabled'])
        self._set_status('Scanning your dev folders for local servers…')
        cfg = self.state.config
        scan_cfg = cfg.get('scan', {})
        roots = scan_cfg.get('roots') or scanner.default_roots()
        depth = scan_cfg.get('max_depth', 4)
        apps = list(cfg['apps'])

        def worker():
            try:
                cands, err = scanner.new_candidates(apps, roots, depth), None
            except Exception as exc:
                cands, err = [], str(exc)
            self.root.after(0, lambda: self._show_scan_results(cands, roots, err))
        threading.Thread(target=worker, daemon=True).start()

    def _show_scan_results(self, candidates, roots, err=None) -> None:
        self.b_scan.state(['!disabled'])
        if err:
            self._set_status(f'Scan failed: {err}')
            return
        if not candidates:
            self._set_status(
                f'Scan complete — no new servers found across '
                f'{len(roots)} location(s).')
            return
        self._set_status(f'Scan found {len(candidates)} new server(s).')
        ScanResultsDialog(self.root, self.state, self._on_saved,
                          candidates, roots)

    def _edit_json(self) -> None:
        try:
            os.startfile(registry.CONFIG_PATH)  # type: ignore[attr-defined]
            self._set_status('Opened apps.json — save it, then click Refresh.')
        except Exception as exc:
            self._set_status(f'Could not open apps.json: {exc}')

    def _force_refresh(self) -> None:
        self._set_status('Refreshing…')
        threading.Thread(
            target=lambda: (self.state.refresh_listeners(),
                            self.root.after(0, self._done_refresh)),
            daemon=True).start()

    def _done_refresh(self) -> None:
        self.refresh()
        self._set_status('Ready')

    def _on_focus(self, event) -> None:
        # Returning from the external editor: pick up any manual edits.
        if event.widget is self.root:
            self.state.reload_config()
            self.refresh()


class AppDialog(tk.Toplevel):
    """Modal add/edit form for a single registry entry."""

    def __init__(self, parent, state: AppState, on_saved,
                 existing: dict | None = None, prefill: dict | None = None):
        super().__init__(parent)
        self.state = state
        self.on_saved = on_saved
        self.existing = existing
        data = existing or prefill or {}
        self.title('Edit app' if existing else 'Add app')
        self.resizable(False, False)
        self.configure(background=theme.APP_BG)
        self.transient(parent)
        self.grab_set()

        frm = ttk.Frame(self, padding=14)
        frm.pack(fill='both', expand=True)

        self.vars = {
            'name': tk.StringVar(value=data.get('name', '')),
            'port': tk.StringVar(value=str(data.get('port', '') or '')),
            'cwd': tk.StringVar(value=data.get('cwd', '')),
            'command': tk.StringVar(value=data.get('command', '')),
            'url': tk.StringVar(value=data.get('url', '')),
        }
        self.console = tk.BooleanVar(value=bool(data.get('console', False)))

        rows = [
            ('Name', 'name', 'Friendly label, e.g. "Pulse dev server"'),
            ('Port', 'port', 'The localhost port it listens on'),
            ('Working folder', 'cwd', 'Folder to run the command in'),
            ('Start command', 'command', 'e.g. npm run dev  /  python app.py'),
            ('URL (optional)', 'url', 'Defaults to http://localhost:<port>'),
        ]
        for r, (label, key, hint) in enumerate(rows):
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky='w',
                                            pady=4, padx=(0, 8))
            entry = ttk.Entry(frm, textvariable=self.vars[key], width=44)
            entry.grid(row=r, column=1, sticky='we', pady=4)
            if key == 'cwd':
                ttk.Button(frm, text='…', width=3,
                           command=self._browse).grid(row=r, column=2,
                                                       padx=(6, 0))
            ttk.Label(frm, text=hint, foreground=STOP_GREY,
                      font=('Segoe UI', 8)).grid(row=r, column=1, sticky='w',
                                                 pady=(24, 0))

        ttk.Checkbutton(frm, text='Show console window when running '
                        '(watch logs)', variable=self.console).grid(
            row=len(rows), column=1, sticky='w', pady=(14, 4))

        actions = ttk.Frame(frm)
        actions.grid(row=len(rows) + 1, column=0, columnspan=3,
                     sticky='e', pady=(14, 0))
        if existing:
            ttk.Button(actions, text='Remove', command=self._remove).pack(
                side='left', padx=(0, 20))
        ttk.Button(actions, text='Cancel', command=self.destroy).pack(
            side='left', padx=(0, 6))
        ttk.Button(actions, text='Save', command=self._save).pack(side='left')

        frm.columnconfigure(1, weight=1)
        self.bind('<Return>', lambda _e: self._save())
        self.bind('<Escape>', lambda _e: self.destroy())

    def _browse(self) -> None:
        initial = self.vars['cwd'].get() or 'C:\\'
        chosen = filedialog.askdirectory(parent=self, initialdir=initial)
        if chosen:
            self.vars['cwd'].set(os.path.normpath(chosen))

    def _collect(self) -> dict:
        return {k: v.get() for k, v in self.vars.items()} | {
            'console': self.console.get()}

    def _save(self) -> None:
        app = registry.normalise_app(self._collect())
        if app is None:
            messagebox.showwarning(
                'Missing details',
                'A name and a numeric port are required.', parent=self)
            return
        apps = list(self.state.config['apps'])
        if self.existing:
            for i, a in enumerate(apps):
                if a is self.existing or a.get('port') == self.existing.get(
                        'port'):
                    apps[i] = app
                    break
            else:
                apps.append(app)
            msg = f"Updated '{app['name']}'."
        else:
            apps.append(app)
            msg = f"Added '{app['name']}'."
        registry.replace_apps(self.state.config, apps)
        self.on_saved(msg)
        self.destroy()

    def _remove(self) -> None:
        if not messagebox.askyesno(
                'Remove app',
                f"Remove '{self.existing['name']}' from the list?\n"
                '(This does not stop it if running.)', parent=self):
            return
        apps = [a for a in self.state.config['apps']
                if a.get('port') != self.existing.get('port')]
        registry.replace_apps(self.state.config, apps)
        self.on_saved(f"Removed '{self.existing['name']}'.")
        self.destroy()


class ScanResultsDialog(tk.Toplevel):
    """Shows scan candidates as a checklist; adds the selected ones."""

    def __init__(self, parent, state: AppState, on_saved, candidates, roots):
        super().__init__(parent)
        self.state = state
        self.on_saved = on_saved
        self.candidates = candidates
        self.title('Scan results')
        self.geometry('620x480')
        self.minsize(520, 360)
        self.configure(background=theme.APP_BG)
        self.transient(parent)
        self.grab_set()

        top = ttk.Frame(self, padding=(14, 12, 14, 6))
        top.pack(fill='x')
        ttk.Label(top, text=f'Found {len(candidates)} startable server(s) '
                  'not yet in your list',
                  font=('Segoe UI Semibold', 11)).pack(side='left')

        hint = ttk.Frame(self, padding=(14, 0, 14, 6))
        hint.pack(fill='x')
        ttk.Label(hint, text=f'Scanned {len(roots)} location(s). '
                  'Tick the ones to add, then Add selected. '
                  '(guessed) = port is a best guess — verify after adding.',
                  foreground=STOP_GREY, wraplength=560,
                  font=('Segoe UI', 8)).pack(side='left')

        # Scrollable checklist.
        mid = ttk.Frame(self, padding=(10, 0, 10, 0))
        mid.pack(fill='both', expand=True)
        canvas = tk.Canvas(mid, highlightthickness=0, background=theme.APP_BG)
        sb = ttk.Scrollbar(mid, orient='vertical', command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind('<Configure>',
                   lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        canvas.bind_all('<MouseWheel>',
                        lambda e: canvas.yview_scroll(int(-e.delta / 120),
                                                      'units'))

        self.vars = []
        for c in candidates:
            var = tk.BooleanVar(value=True)
            self.vars.append((var, c))
            row = ttk.Frame(inner, padding=(2, 4))
            row.pack(fill='x', anchor='w')
            g = ' (guessed)' if c.get('port_guessed') else ''
            ttk.Checkbutton(
                row, variable=var,
                text=f"{c['name']}   ·   port {c['port']}{g}   ·   {c['kind']}"
            ).pack(anchor='w')
            ttk.Label(row, text=f"{c['command']}    —    {c['cwd']}",
                      foreground=STOP_GREY, font=('Segoe UI', 8)).pack(
                anchor='w', padx=(22, 0))

        foot = ttk.Frame(self, padding=(14, 6, 14, 12))
        foot.pack(fill='x')
        ttk.Button(foot, text='Select all',
                   command=lambda: self._set_all(True)).pack(side='left')
        ttk.Button(foot, text='Select none',
                   command=lambda: self._set_all(False)).pack(
            side='left', padx=(6, 0))
        ttk.Button(foot, text='Add selected',
                   command=self._add).pack(side='right')
        ttk.Button(foot, text='Cancel', command=self.destroy).pack(
            side='right', padx=(0, 6))
        self.bind('<Escape>', lambda _e: self.destroy())

    def _set_all(self, value: bool) -> None:
        for var, _c in self.vars:
            var.set(value)

    def _add(self) -> None:
        chosen = [c for var, c in self.vars if var.get()]
        if not chosen:
            self.destroy()
            return
        apps = list(self.state.config['apps'])
        added = 0
        for c in chosen:
            app = registry.normalise_app({
                'name': c['name'], 'port': c['port'], 'cwd': c['cwd'],
                'command': c['command'], 'console': False,
            })
            if app is not None and not scanner.is_registered(app, apps):
                apps.append(app)
                added += 1
        registry.replace_apps(self.state.config, apps)
        self.on_saved(f'Added {added} app(s) from scan.')
        self.destroy()
