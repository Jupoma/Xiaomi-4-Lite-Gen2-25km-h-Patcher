"""Small Tk widgets that express the Jupoma visual system."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from .theme import AMBER, GRAVEL, INK, LINEN, MOSS, PAPER, RULE, SOIL, WHITE


class GridHeader(tk.Canvas):
    """Header canvas with the restrained 32 px Jupoma paper grid."""

    def __init__(self, master: tk.Misc, *, height: int = 144, **kwargs: Any) -> None:
        super().__init__(
            master,
            height=height,
            background=LINEN,
            highlightthickness=0,
            borderwidth=0,
            **kwargs,
        )
        self._height = height
        self._content = ttk.Frame(self, style="Linen.TFrame")
        self._window = self.create_window(32, 20, anchor="nw", window=self._content)
        self.bind("<Configure>", self._redraw, add=True)

    @property
    def content(self) -> ttk.Frame:
        return self._content

    def _redraw(self, event: tk.Event) -> None:
        self.delete("grid-line")
        width = max(int(event.width), 64)
        height = max(int(event.height), self._height)
        for x in range(0, width + 1, 32):
            self.create_line(x, 0, x, height, fill=RULE, width=1, tags="grid-line")
        for y in range(0, height + 1, 32):
            self.create_line(0, y, width, y, fill=RULE, width=1, tags="grid-line")
        self.tag_lower("grid-line")
        self.itemconfigure(self._window, width=max(width - 64, 1))
        self.create_line(0, height - 1, width, height - 1, fill=INK, width=1, tags="grid-line")


class BorderPanel(tk.Frame):
    """Flat one-pixel panel; content is available through ``body``."""

    def __init__(self, master: tk.Misc, *, background: str = PAPER, **kwargs: Any) -> None:
        super().__init__(master, background=RULE, padx=1, pady=1, borderwidth=0, **kwargs)
        self.body = tk.Frame(self, background=background, borderwidth=0)
        self.body.pack(fill=tk.BOTH, expand=True)


class SectionTitle(tk.Frame):
    def __init__(self, master: tk.Misc, number: str, title: str, *, background: str = PAPER) -> None:
        super().__init__(master, background=background)
        tk.Frame(self, width=20, height=1, background=AMBER).pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(
            self,
            text=f"§{number}  {title.upper()}",
            background=background,
            foreground=GRAVEL,
            font=("JetBrains Mono", 8, "bold"),
        ).pack(side=tk.LEFT)


class StatusDot(tk.Canvas):
    COLORS = {"idle": GRAVEL, "working": AMBER, "ok": MOSS, "error": "#9a2e1e"}

    def __init__(self, master: tk.Misc, **kwargs: Any) -> None:
        super().__init__(master, width=12, height=12, background=PAPER, highlightthickness=0, **kwargs)
        self._dot = self.create_oval(2, 2, 10, 10, fill=GRAVEL, outline="")

    def set_state(self, state: str) -> None:
        self.itemconfigure(self._dot, fill=self.COLORS.get(state, GRAVEL))


class ReadOnlyText(tk.Text):
    def __init__(self, master: tk.Misc, *, lines: int = 4, background: str = LINEN, **kwargs: Any) -> None:
        super().__init__(
            master,
            height=lines,
            wrap=tk.WORD,
            background=background,
            foreground=INK,
            insertbackground=AMBER,
            selectbackground="#d8cfba",
            selectforeground=INK,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            font=("JetBrains Mono", 9),
            cursor="arrow",
            **kwargs,
        )
        self.configure(state=tk.DISABLED)

    def set_text(self, value: str) -> None:
        self.configure(state=tk.NORMAL)
        self.delete("1.0", tk.END)
        self.insert("1.0", value)
        self.configure(state=tk.DISABLED)


def labeled_value(master: tk.Misc, label: str, variable: tk.StringVar, *, row: int) -> None:
    tk.Label(
        master,
        text=label.upper(),
        background=LINEN,
        foreground=GRAVEL,
        font=("JetBrains Mono", 8, "bold"),
    ).grid(row=row, column=0, sticky="nw", padx=(0, 16), pady=5)
    tk.Label(
        master,
        textvariable=variable,
        background=LINEN,
        foreground=SOIL,
        font=("JetBrains Mono", 9),
        justify=tk.LEFT,
        anchor="w",
        wraplength=235,
    ).grid(row=row, column=1, sticky="ew", pady=5)


def set_text_widget_colors(widget: tk.Text) -> None:
    widget.configure(
        background=WHITE,
        foreground=SOIL,
        insertbackground=AMBER,
        selectbackground="#d8cfba",
        selectforeground=INK,
        highlightthickness=1,
        highlightbackground=RULE,
        highlightcolor=AMBER,
        relief=tk.FLAT,
    )
