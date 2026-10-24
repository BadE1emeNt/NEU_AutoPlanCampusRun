"""可复用的界面组件：卡片、状态标签、进度环、滚动容器、侧边导航。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .theme import ACCENT, BG, BORDER, CARD, FAINT, FONTS, MUTED, PALETTE, TEXT, font

TONE_STYLES = {
    "success": (PALETTE["success"], PALETTE["success_soft"]),
    "warn": (PALETTE["warn"], PALETTE["warn_soft"]),
    "danger": (PALETTE["danger"], PALETTE["danger_soft"]),
    "accent": (PALETTE["accent"], PALETTE["accent_soft"]),
    "ok": (PALETTE["success"], PALETTE["success_soft"]),
    "muted": (MUTED, "#F2F4F7"),
}


class Card(tk.Frame):
    def __init__(self, master: tk.Misc, padding: int = 18, bg: str = CARD):
        super().__init__(master, bg=bg, bd=0, highlightthickness=1, highlightbackground=BORDER)
        self.body = tk.Frame(self, bg=bg)
        self.body.pack(fill="both", expand=True, padx=padding, pady=padding)


class StatCard(Card):
    def __init__(
        self,
        master: tk.Misc,
        label: str,
        value: str = "—",
        hint: str = "",
        accent: str = ACCENT,
    ):
        super().__init__(master, padding=14)
        self._accent = accent
        bar = tk.Frame(self.body, bg=accent, height=3, width=26)
        bar.pack(anchor="w", pady=(0, 12))
        self.value_label = tk.Label(
            self.body,
            text=value,
            bg=CARD,
            fg=TEXT,
            font=font("stat"),
            anchor="w",
        )
        self.value_label.pack(anchor="w")
        self.label_label = tk.Label(
            self.body,
            text=label,
            bg=CARD,
            fg=MUTED,
            font=font("small"),
            anchor="w",
        )
        self.label_label.pack(anchor="w", pady=(2, 4))
        self.hint_label = tk.Label(
            self.body,
            text=hint,
            bg=CARD,
            fg=FAINT,
            font=font("tiny"),
            anchor="w",
            justify="left",
            wraplength=170,
        )
        self.hint_label.pack(anchor="w")

    def set(self, value: str, hint: str | None = None, tone: str | None = None) -> None:
        self.value_label.configure(text=value)
        if hint is not None:
            self.hint_label.configure(text=hint)
        if tone is not None:
            self.value_label.configure(fg=TONE_STYLES.get(tone, (TEXT, CARD))[0])


class Pill(tk.Label):
    def __init__(self, master: tk.Misc, text: str = "", tone: str = "muted", bg: str | None = None):
        fg, soft = TONE_STYLES.get(tone, TONE_STYLES["muted"])
        super().__init__(
            master,
            text=text,
            bg=soft,
            fg=fg,
            font=font("tiny"),
            padx=9,
            pady=3,
        )
        self._bg_override = bg

    def set(self, text: str, tone: str = "muted") -> None:
        fg, soft = TONE_STYLES.get(tone, TONE_STYLES["muted"])
        self.configure(text=text, bg=soft, fg=fg)


class ProgressRing(tk.Canvas):
    def __init__(self, master: tk.Misc, size: int = 190, bg: str = CARD):
        super().__init__(master, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
        self.size = size
        self.bg = bg
        self._ratio = 0.0
        self._title = "0%"
        self._sub = "完成度"
        self._color = ACCENT
        self.bind("<Configure>", lambda _event: self._draw())
        self._draw()

    def set(self, ratio: float, title: str | None = None, sub: str | None = None, color: str | None = None) -> None:
        self._ratio = max(0.0, min(1.0, ratio))
        if title is not None:
            self._title = title
        if sub is not None:
            self._sub = sub
        if color is not None:
            self._color = color
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        size = min(self.size, max(60, min(self.winfo_width(), self.winfo_height()))) if self.winfo_width() > 1 else self.size
        pad = max(12, int(size * 0.09))
        box = (pad, pad, size - pad, size - pad)
        width = max(10, int(size * 0.075))
        self.create_arc(
            *box,
            start=90,
            extent=-359.9,
            style="arc",
            width=width,
            outline=PALETTE["track"],
        )
        if self._ratio > 0:
            self.create_arc(
                *box,
                start=90,
                extent=-359.9 * self._ratio,
                style="arc",
                width=width,
                outline=self._color,
            )
        center = size / 2
        self.create_text(
            center,
            center - 8,
            text=self._title,
            fill=TEXT,
            font=(FONTS["body"][0], 22, "bold"),
        )
        self.create_text(center, center + 24, text=self._sub, fill=MUTED, font=font("small"))


class ScrollFrame(tk.Frame):
    """带竖向滚动条的容器；内容放在 ``.inner``。"""

    def __init__(self, master: tk.Misc, bg: str = BG):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_inner_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0)


class NavItem(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        key: str,
        text: str,
        command: Callable[[str], None],
        badge: str = "",
    ):
        super().__init__(master, bg=PALETTE["sidebar"], cursor="hand2")
        self.key = key
        self._active = False
        self.indicator = tk.Frame(self, bg=PALETTE["sidebar"], width=3)
        self.indicator.pack(side="left", fill="y")
        self.label = tk.Label(
            self,
            text=text,
            bg=PALETTE["sidebar"],
            fg=PALETTE["sidebar_text"],
            font=font("nav"),
            anchor="w",
            padx=15,
            pady=9,
        )
        self.label.pack(side="left", fill="both", expand=True)
        self.badge = tk.Label(
            self,
            text=badge,
            bg=PALETTE["sidebar"],
            fg=PALETTE["sidebar_muted"],
            font=font("tiny"),
        )
        if badge:
            self.badge.pack(side="right", padx=(0, 14))
        for widget in (self, self.label, self.badge):
            widget.bind("<Button-1>", lambda _event: command(key))
        for widget in (self, self.label):
            widget.bind("<Enter>", self._hover)
            widget.bind("<Leave>", self._unhover)

    def _paint(self, bg: str, fg: str) -> None:
        self.configure(bg=bg)
        self.label.configure(bg=bg, fg=fg)
        self.badge.configure(bg=bg)
        self.indicator.configure(bg=ACCENT if self._active else bg)

    def _hover(self, _event: tk.Event) -> None:
        if not self._active:
            self._paint(PALETTE["sidebar_active"], "#DCE4F2")

    def _unhover(self, _event: tk.Event) -> None:
        if not self._active:
            self._paint(PALETTE["sidebar"], PALETTE["sidebar_text"])

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            self._paint(PALETTE["sidebar_active"], "#FFFFFF")
        else:
            self._paint(PALETTE["sidebar"], PALETTE["sidebar_text"])


class PageHeader(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        title: str,
        subtitle: str = "",
        action: tk.Widget | None = None,
        bg: str = BG,
    ):
        super().__init__(master, bg=bg)
        left = tk.Frame(self, bg=bg)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=title, bg=bg, fg=TEXT, font=font("h1"), anchor="w").pack(anchor="w")
        self.subtitle = tk.Label(
            left,
            text=subtitle,
            bg=bg,
            fg=MUTED,
            font=font("small"),
            anchor="w",
        )
        self.subtitle.pack(anchor="w", pady=(4, 0))
        if action is not None:
            action.pack(side="right", anchor="e")

    def set_subtitle(self, text: str) -> None:
        self.subtitle.configure(text=text)


class LinkLabel(tk.Label):
    def __init__(self, master: tk.Misc, text: str, command: Callable[[], None], bg: str = CARD):
        super().__init__(master, text=text, bg=bg, fg=ACCENT, font=font("small"), cursor="hand2")
        self._command = command
        self.bind("<Button-1>", lambda _event: self._command())
        self.bind("<Enter>", lambda _event: self.configure(font=(FONTS["body"][0], 9, "underline")))
        self.bind("<Leave>", lambda _event: self.configure(font=font("small")))


def section_title(parent: tk.Misc, title: str, subtitle: str = "", bg: str = CARD) -> tk.Frame:
    frame = tk.Frame(parent, bg=bg)
    tk.Label(frame, text=title, bg=bg, fg=TEXT, font=font("h2"), anchor="w").pack(anchor="w")
    if subtitle:
        tk.Label(
            frame,
            text=subtitle,
            bg=bg,
            fg=MUTED,
            font=font("small"),
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(anchor="w", pady=(3, 0))
    return frame


def hline(parent: tk.Misc, bg: str = BORDER) -> tk.Frame:
    line = tk.Frame(parent, bg=bg, height=1)
    line.pack(fill="x")
    return line


def small_label(parent: tk.Misc, text: str, bg: str = CARD, fg: str | None = None, wrap: int = 0) -> tk.Label:
    return tk.Label(
        parent,
        text=text,
        bg=bg,
        fg=fg or MUTED,
        font=font("small"),
        anchor="w",
        justify="left",
        wraplength=wrap or 0,
    )
