"""界面配色、字体与 ttk 样式。"""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

PALETTE = {
    "bg": "#F4F6FB",
    "card": "#FFFFFF",
    "card_alt": "#F8FAFC",
    "border": "#E5E9F2",
    "border_strong": "#D3DAE6",
    "text": "#111827",
    "muted": "#667085",
    "faint": "#98A2B3",
    "accent": "#2563EB",
    "accent_dark": "#1D4ED8",
    "accent_soft": "#EFF5FF",
    "success": "#067647",
    "success_soft": "#ECFDF3",
    "warn": "#B54708",
    "warn_soft": "#FFFAEB",
    "danger": "#B42318",
    "danger_soft": "#FEF3F2",
    "sidebar": "#0C1426",
    "sidebar_active": "#16213A",
    "sidebar_text": "#9AA8C2",
    "sidebar_muted": "#5E6C84",
    "track": "#EDF1F7",
}

BG = PALETTE["bg"]
CARD = PALETTE["card"]
CARD_ALT = PALETTE["card_alt"]
BORDER = PALETTE["border"]
TEXT = PALETTE["text"]
MUTED = PALETTE["muted"]
FAINT = PALETTE["faint"]
ACCENT = PALETTE["accent"]
ACCENT_SOFT = PALETTE["accent_soft"]
SUCCESS = PALETTE["success"]
SUCCESS_SOFT = PALETTE["success_soft"]
WARN = PALETTE["warn"]
WARN_SOFT = PALETTE["warn_soft"]
DANGER = PALETTE["danger"]
DANGER_SOFT = PALETTE["danger_soft"]

FONT_FAMILY = "Microsoft YaHei UI"
MONO_FAMILY = "Consolas"
FONTS: dict[str, tuple] = {}


def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass


def _pick_family(root: tk.Misc) -> str:
    try:
        families = set(tkfont.families(root))
    except tk.TclError:
        return "Segoe UI"
    for candidate in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "Arial"):
        if candidate in families:
            return candidate
    return "Segoe UI"


def configure_styles(root: tk.Tk) -> dict[str, tuple]:
    global FONT_FAMILY

    FONT_FAMILY = _pick_family(root)
    try:
        scaling = root.winfo_fpixels("1i") / 72.0
        root.tk.call("tk", "scaling", scaling)
    except tk.TclError:
        pass

    FONTS.update(
        {
            "body": (FONT_FAMILY, 10),
            "small": (FONT_FAMILY, 9),
            "tiny": (FONT_FAMILY, 8),
            "button": (FONT_FAMILY, 10),
            "nav": (FONT_FAMILY, 10),
            "h1": (FONT_FAMILY, 18, "bold"),
            "h2": (FONT_FAMILY, 12, "bold"),
            "h3": (FONT_FAMILY, 10, "bold"),
            "stat": (FONT_FAMILY, 20, "bold"),
            "stat_small": (FONT_FAMILY, 17, "bold"),
            "mono": (MONO_FAMILY, 9),
            "mono_small": (MONO_FAMILY, 8),
        }
    )

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=BG)
    root.option_add("*tearOff", False)

    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD)
    style.configure("TLabel", background=BG, foreground=TEXT, font=FONTS["body"])
    style.configure("TSeparator", background=BORDER)

    style.configure(
        "TButton",
        font=FONTS["button"],
        padding=(13, 7),
        background=PALETTE["card_alt"],
        foreground=TEXT,
        bordercolor="#D8E0EC",
        lightcolor="#D8E0EC",
        darkcolor="#D8E0EC",
        relief="flat",
        focusthickness=0,
    )
    style.map(
        "TButton",
        background=[("disabled", "#F2F4F7"), ("pressed", "#E3EAF4"), ("active", "#EEF3FA")],
        foreground=[("disabled", FAINT)],
        bordercolor=[("focus", ACCENT)],
    )
    style.configure(
        "Accent.TButton",
        font=(FONT_FAMILY, 10, "bold"),
        background=ACCENT,
        foreground="#FFFFFF",
        bordercolor=ACCENT,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
    )
    style.map(
        "Accent.TButton",
        background=[("disabled", "#9DBEF5"), ("pressed", PALETTE["accent_dark"]), ("active", PALETTE["accent_dark"])],
        foreground=[("disabled", "#F5F8FF")],
        bordercolor=[("active", PALETTE["accent_dark"])],
    )
    style.configure(
        "Ghost.TButton",
        background=BG,
        bordercolor=BG,
        lightcolor=BG,
        darkcolor=BG,
        foreground=MUTED,
    )
    style.map(
        "Ghost.TButton",
        background=[("active", "#E9EEF7"), ("pressed", "#DFE6F1")],
        foreground=[("active", TEXT)],
    )
    style.configure("Danger.TButton", foreground=PALETTE["danger"], background=CARD, bordercolor=BORDER)
    style.map("Danger.TButton", background=[("active", PALETTE["danger_soft"])])

    style.configure(
        "TEntry",
        fieldbackground=PALETTE["card_alt"],
        foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        insertcolor=TEXT,
        padding=(8, 6),
        relief="flat",
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", ACCENT)],
        lightcolor=[("focus", ACCENT)],
        darkcolor=[("focus", ACCENT)],
        fieldbackground=[("disabled", "#F2F4F7")],
    )
    style.configure(
        "TSpinbox",
        fieldbackground=PALETTE["card_alt"],
        foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        arrowcolor=MUTED,
        padding=(8, 5),
        relief="flat",
    )
    style.map("TSpinbox", bordercolor=[("focus", ACCENT)], arrowcolor=[("active", TEXT)])

    style.configure(
        "TCheckbutton",
        background=CARD,
        foreground=TEXT,
        font=FONTS["small"],
        padding=(2, 3),
        focuscolor=CARD,
    )
    style.map(
        "TCheckbutton",
        background=[("active", CARD)],
        foreground=[("disabled", FAINT)],
        indicatorcolor=[("selected", ACCENT), ("!selected", "#FFFFFF")],
    )
    style.configure(
        "Rest.TCheckbutton",
        background=CARD,
        foreground=TEXT,
        font=FONTS["tiny"],
        padding=(0, 2),
        focuscolor=CARD,
    )
    style.map(
        "Rest.TCheckbutton",
        background=[("active", CARD)],
        indicatorcolor=[("selected", ACCENT), ("!selected", "#FFFFFF")],
    )

    style.configure(
        "TCombobox",
        fieldbackground=PALETTE["card_alt"],
        background=CARD,
        foreground=TEXT,
        bordercolor=BORDER,
        arrowcolor=MUTED,
        padding=(6, 5),
    )
    style.map("TCombobox", fieldbackground=[("readonly", PALETTE["card_alt"])], bordercolor=[("focus", ACCENT)])

    style.configure(
        "Treeview",
        background=CARD,
        fieldbackground=CARD,
        foreground=TEXT,
        font=FONTS["body"],
        rowheight=34,
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Treeview",
        background=[("selected", PALETTE["accent_soft"])],
        foreground=[("selected", TEXT)],
    )
    style.configure(
        "Treeview.Heading",
        background=PALETTE["card_alt"],
        foreground=MUTED,
        font=FONTS["small"],
        relief="flat",
        padding=(8, 7),
        borderwidth=0,
    )
    style.map("Treeview.Heading", background=[("active", "#F1F5F9")])
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    style.configure(
        "Vertical.TScrollbar",
        background="#CBD5E1",
        troughcolor=CARD,
        bordercolor=CARD,
        arrowcolor=MUTED,
        arrowsize=10,
        relief="flat",
        width=10,
    )
    style.map("Vertical.TScrollbar", background=[("active", "#94A3B8")])

    return FONTS


def font(kind: str) -> tuple:
    return FONTS.get(kind, FONTS.get("body", (FONT_FAMILY, 10)))
