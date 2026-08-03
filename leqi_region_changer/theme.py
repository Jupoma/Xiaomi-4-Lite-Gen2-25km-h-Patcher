"""Jupoma CI tokens and Tk styling."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from .resources import register_bundled_fonts

PAPER = "#f4efe4"
LINEN = "#ece6d8"
SAND = "#d8cfba"
GRAVEL = "#8c8070"
SOIL = "#3a3228"
INK = "#1a160f"
AMBER = "#d97706"
TOAST = "#b45e00"
BUTTER = "#fce8b8"
MOSS = "#3a6349"
MOSS_LIGHT = "#d4edd9"
BRICK = "#9a2e1e"
BRICK_LIGHT = "#f5d4cf"
RULE = "#cfc5b2"
WHITE = "#fffdf8"


def _available_family(root: tk.Misc, preferred: str, fallback: str) -> str:
    families = set(tkfont.families(root))
    return preferred if preferred in families else fallback


def configure_theme(root: tk.Tk) -> dict[str, tuple[str, int, str]]:
    register_bundled_fonts()

    display = _available_family(root, "Space Grotesk", "Segoe UI")
    body = _available_family(root, "Inter Tight", "Segoe UI")
    mono = _available_family(root, "JetBrains Mono", "Consolas")

    fonts = {
        "display": (display, 26, "bold"),
        "heading": (display, 15, "bold"),
        "subheading": (display, 11, "bold"),
        "body": (body, 10, "normal"),
        "body_bold": (body, 10, "bold"),
        "small": (body, 9, "normal"),
        "mono": (mono, 9, "normal"),
        "mono_bold": (mono, 9, "bold"),
        "meta": (mono, 8, "bold"),
    }

    root.configure(background=PAPER)
    root.option_add("*Font", fonts["body"])
    root.option_add("*selectBackground", SAND)
    root.option_add("*selectForeground", INK)
    root.option_add("*insertBackground", AMBER)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", background=PAPER, foreground=INK, font=fonts["body"], borderwidth=1)
    style.configure("TFrame", background=PAPER)
    style.configure("Linen.TFrame", background=LINEN)
    style.configure("TLabel", background=PAPER, foreground=SOIL, font=fonts["body"])
    style.configure("Linen.TLabel", background=LINEN, foreground=SOIL, font=fonts["body"])
    style.configure("Heading.TLabel", background=PAPER, foreground=INK, font=fonts["heading"])
    style.configure("Display.TLabel", background=PAPER, foreground=INK, font=fonts["display"])
    style.configure("Meta.TLabel", background=PAPER, foreground=TOAST, font=fonts["meta"])
    style.configure("Caption.TLabel", background=PAPER, foreground=GRAVEL, font=fonts["small"])
    style.configure("Mono.TLabel", background=PAPER, foreground=INK, font=fonts["mono"])
    style.configure("LinenMono.TLabel", background=LINEN, foreground=INK, font=fonts["mono"])
    style.configure("Status.TLabel", background=PAPER, foreground=SOIL, font=fonts["small"])
    style.configure("Ok.TLabel", background=PAPER, foreground=MOSS, font=fonts["body_bold"])
    style.configure("Warn.TLabel", background=PAPER, foreground=BRICK, font=fonts["body_bold"])

    style.configure(
        "TEntry", fieldbackground=WHITE, foreground=INK, bordercolor=RULE,
        lightcolor=RULE, darkcolor=RULE, insertcolor=AMBER, padding=(10, 8),
        font=fonts["mono"], relief="flat",
    )
    style.map("TEntry", bordercolor=[("focus", AMBER)], lightcolor=[("focus", AMBER)])
    style.configure(
        "TCombobox", fieldbackground=WHITE, background=WHITE, foreground=INK,
        arrowcolor=INK, bordercolor=RULE, lightcolor=RULE, darkcolor=RULE,
        padding=(10, 8), font=fonts["body"], relief="flat",
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", WHITE), ("disabled", LINEN)],
        selectbackground=[("readonly", WHITE)],
        selectforeground=[("readonly", INK)],
        bordercolor=[("focus", AMBER)],
    )
    style.configure(
        "TButton", background=LINEN, foreground=INK, bordercolor=RULE,
        lightcolor=LINEN, darkcolor=LINEN, padding=(14, 9),
        font=fonts["mono_bold"], relief="flat", anchor="center",
    )
    style.map(
        "TButton",
        background=[("active", WHITE), ("pressed", SAND), ("disabled", LINEN)],
        foreground=[("disabled", GRAVEL)],
        bordercolor=[("focus", AMBER), ("active", INK)],
    )
    style.configure(
        "Primary.TButton", background=INK, foreground=PAPER, bordercolor=INK,
        lightcolor=INK, darkcolor=INK, padding=(18, 12), font=fonts["mono_bold"],
    )
    style.map(
        "Primary.TButton",
        background=[("active", TOAST), ("pressed", AMBER), ("disabled", SAND)],
        foreground=[("active", PAPER), ("pressed", INK), ("disabled", GRAVEL)],
        bordercolor=[("active", TOAST), ("pressed", AMBER)],
    )
    style.configure(
        "Region.TButton", background=WHITE, foreground=INK, bordercolor=RULE,
        lightcolor=WHITE, darkcolor=WHITE, padding=(12, 12), font=fonts["mono_bold"],
    )
    style.map(
        "Region.TButton",
        background=[("active", LINEN), ("selected", INK), ("disabled", LINEN)],
        foreground=[("selected", PAPER), ("disabled", GRAVEL)],
        bordercolor=[("selected", INK), ("focus", AMBER)],
    )
    style.configure(
        "TCheckbutton", background=PAPER, foreground=SOIL, font=fonts["small"],
        indicatorbackground=WHITE, indicatorforeground=INK, bordercolor=RULE,
        padding=(0, 4),
    )
    style.map("TCheckbutton", indicatorbackground=[("selected", AMBER)], bordercolor=[("focus", AMBER)])
    style.configure("TSeparator", background=RULE)
    style.configure("Vertical.TScrollbar", background=LINEN, troughcolor=PAPER, bordercolor=RULE)

    return fonts

