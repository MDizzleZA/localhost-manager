"""Design system: colour palette, fonts, ttk theme, and the app icon.

Central place for the visual language so the tray icon, the dashboard and
the generated .ico all stay consistent.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

# --- palette (light) -------------------------------------------------------
APP_BG = '#EAEEF3'
SURFACE = '#FFFFFF'
SURFACE_ALT = '#F4F7FA'
BORDER = '#D7DDE5'
TEXT = '#1B2430'
MUTED = '#6C7684'
FAINT = '#9AA3AF'
ACCENT = '#2F6FEB'
ACCENT_DK = '#2560CF'
ACCENT_SOFT = '#E7EFFD'
RUNNING = '#12A150'
RUNNING_BG = '#E6F6ED'
STOPPED = '#98A1AD'
DANGER = '#DC5B4B'
DANGER_DK = '#C6493B'
SEL_BG = '#E4EDFC'
GROUP_BG = '#EBEFF5'

# --- fonts (family + sizes; concrete Font objects made after Tk root) ------
FAMILY = 'Segoe UI'
SEMI = 'Segoe UI Semibold'
F_TITLE = (SEMI, 15)
F_SUBTITLE = (FAMILY, 9)
F_BODY = (FAMILY, 10)
F_ROW = (FAMILY, 10)
F_GROUP = (SEMI, 10)
F_SMALL = (FAMILY, 8)
F_CHIP = (SEMI, 9)
F_BTN = (FAMILY, 9)

# --- icon colours ----------------------------------------------------------
_SLATE_TOP = (43, 52, 66)
_SLATE_BOT = (28, 34, 44)
_PANEL = (86, 96, 112)
_PANEL_HI = (108, 119, 137)
_ACCENT = (0x2F, 0x6F, 0xEB)
_GREEN = (0x16, 0xB0, 0x59)
_GREY = (0x8A, 0x93, 0xA0)

HERE = os.path.dirname(os.path.abspath(__file__))
ICO_PATH = os.path.join(HERE, 'assets', 'localhost_manager.ico')


def make_icon_image(size: int = 64, running: bool = True) -> Image.Image:
    """Render the app mark at `size` px (drawn at 4x, downsampled)."""
    s = 256
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded slate tile with a soft vertical gradient.
    tile = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    grad = Image.new('RGB', (1, s))
    for y in range(s):
        t = y / (s - 1)
        grad.putpixel((0, y), tuple(
            int(_SLATE_TOP[i] + (_SLATE_BOT[i] - _SLATE_TOP[i]) * t)
            for i in range(3)))
    grad = grad.resize((s, s))
    mask = Image.new('L', (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((14, 14, s - 14, s - 14),
                                           radius=58, fill=255)
    tile.paste(grad, (0, 0), mask)
    img = Image.alpha_composite(img, tile)
    d = ImageDraw.Draw(img)

    # Accent header strip on a "server/monitor" panel.
    d.rounded_rectangle((52, 62, 204, 92), radius=10, fill=_ACCENT)
    # Two server rows.
    for y in (112, 158):
        d.rounded_rectangle((52, y, 204, y + 34), radius=10, fill=_PANEL)
        d.ellipse((64, y + 9, 80, y + 25), fill=_PANEL_HI)
        d.rounded_rectangle((92, y + 12, 176, y + 22), radius=5,
                            fill=(58, 66, 80))

    # Status dot, bottom-right, ringed so it reads at 16px.
    c = _GREEN if running else _GREY
    d.ellipse((150, 150, 214, 214), fill=_SLATE_BOT)
    d.ellipse((158, 158, 206, 206), fill=c)

    if size != s:
        img = img.resize((size, size), Image.LANCZOS)
    return img


def write_ico(path: str = ICO_PATH, running: bool = True) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    base = make_icon_image(256, running)
    base.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                           (64, 64), (128, 128), (256, 256)])
    return path


def ensure_ico() -> str | None:
    """Make sure the .ico exists on disk; return its path (or None)."""
    try:
        if not os.path.exists(ICO_PATH):
            write_ico(ICO_PATH, running=True)
        return ICO_PATH
    except Exception:
        return None


def apply_theme(root) -> None:
    """Configure a clam-based ttk theme with the palette above."""
    from tkinter import ttk
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except Exception:
        pass
    root.configure(background=APP_BG)

    style.configure('.', background=APP_BG, foreground=TEXT,
                    font=F_BODY, borderwidth=0, focuscolor=APP_BG)
    style.configure('TFrame', background=APP_BG)
    style.configure('Surface.TFrame', background=SURFACE)
    style.configure('Header.TFrame', background=SURFACE)
    style.configure('TLabel', background=APP_BG, foreground=TEXT)
    style.configure('Surface.TLabel', background=SURFACE, foreground=TEXT)
    style.configure('Title.TLabel', background=SURFACE, foreground=TEXT,
                    font=F_TITLE)
    style.configure('Subtitle.TLabel', background=SURFACE, foreground=MUTED,
                    font=F_SUBTITLE)
    style.configure('Muted.TLabel', background=APP_BG, foreground=MUTED,
                    font=F_SMALL)
    style.configure('Chip.TLabel', background=RUNNING_BG, foreground=RUNNING,
                    font=F_CHIP, padding=(10, 4))
    style.configure('ChipIdle.TLabel', background=GROUP_BG, foreground=MUTED,
                    font=F_CHIP, padding=(10, 4))
    style.configure('Status.TLabel', background=SURFACE, foreground=MUTED,
                    font=F_SMALL, padding=(10, 5))

    # Treeview.
    style.configure('Treeview', background=SURFACE, fieldbackground=SURFACE,
                    foreground=TEXT, rowheight=32, font=F_ROW,
                    borderwidth=0)
    style.map('Treeview', background=[('selected', SEL_BG)],
              foreground=[('selected', TEXT)])
    style.configure('Treeview.Heading', background=SURFACE_ALT,
                    foreground=FAINT, font=(FAMILY, 8), relief='flat',
                    padding=(8, 6))
    style.map('Treeview.Heading', background=[('active', SURFACE_ALT)])

    # Buttons — ghost (default) and primary.
    style.configure('TButton', background=SURFACE, foreground=TEXT,
                    font=F_BTN, padding=(10, 6), relief='flat',
                    bordercolor=BORDER, borderwidth=1)
    style.map('TButton',
              background=[('active', SURFACE_ALT), ('disabled', APP_BG)],
              foreground=[('disabled', FAINT)],
              bordercolor=[('active', ACCENT)])
    style.configure('Primary.TButton', background=ACCENT, foreground='#FFFFFF',
                    font=(SEMI, 9), padding=(14, 6), borderwidth=0)
    style.map('Primary.TButton',
              background=[('active', ACCENT_DK), ('disabled', '#BFCEF3')],
              foreground=[('disabled', '#EAF0FC')])
    style.configure('Danger.TButton', background=SURFACE, foreground=DANGER,
                    font=F_BTN, padding=(12, 6), borderwidth=1,
                    bordercolor=BORDER)
    style.map('Danger.TButton',
              background=[('active', '#FBEDEB'), ('disabled', APP_BG)],
              foreground=[('disabled', FAINT)],
              bordercolor=[('active', DANGER)])
    style.configure('Vertical.TScrollbar', background=SURFACE_ALT,
                    troughcolor=SURFACE, borderwidth=0, arrowcolor=MUTED)
