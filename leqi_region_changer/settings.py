"""Non-fatal persistence for the user's language preference."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

from .i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES


def default_settings_path(environ: Mapping[str, str] | None = None) -> Path | None:
    values = os.environ if environ is None else environ
    local_app_data = values.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        return None
    return Path(local_app_data) / "Jupoma" / "LEQI Region Changer" / "settings.json"


def load_language(path: str | Path | None = None) -> str:
    settings_path = Path(path) if path is not None else default_settings_path()
    if settings_path is None:
        return DEFAULT_LANGUAGE
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return DEFAULT_LANGUAGE
    if not isinstance(payload, dict):
        return DEFAULT_LANGUAGE
    language = payload.get("language")
    return language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def save_language(language: str, path: str | Path | None = None) -> bool:
    if language not in SUPPORTED_LANGUAGES:
        return False
    settings_path = Path(path) if path is not None else default_settings_path()
    if settings_path is None:
        return False
    temporary_path = settings_path.with_suffix(".tmp")
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps({"language": language}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, settings_path)
    except (OSError, UnicodeError):
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    return True
