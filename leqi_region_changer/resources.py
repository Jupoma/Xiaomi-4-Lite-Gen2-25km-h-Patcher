"""Resolve packaged resources and register bundled fonts on Windows."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Iterable


def bundle_root() -> Path:
    """Return the read-only bundle root for source and PyInstaller builds."""

    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parent.parent


def executable_root() -> Path:
    """Return the directory beside the running script or executable."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def asset_path(*parts: str) -> Path:
    return bundle_root().joinpath("assets", *parts)


def bundled_profiles_path() -> Path:
    return bundle_root() / "profiles"


def external_profiles_path() -> Path:
    return executable_root() / "profiles"


def register_private_fonts(paths: Iterable[Path]) -> list[Path]:
    """Register local fonts for this Windows process only.

    Tk resolves the family names after registration. Missing files and platforms
    are harmless; the UI then uses its documented system fallbacks.
    """

    if os.name != "nt":
        return []

    try:
        add_font = ctypes.windll.gdi32.AddFontResourceExW
    except (AttributeError, OSError):
        return []

    registered: list[Path] = []
    for path in paths:
        if path.is_file() and add_font(str(path), 0x10, 0):  # FR_PRIVATE
            registered.append(path)
    return registered


def register_bundled_fonts() -> list[Path]:
    font_dir = asset_path("fonts")
    return register_private_fonts(sorted(font_dir.glob("*.ttf")))

