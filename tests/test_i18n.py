from __future__ import annotations

from pathlib import Path
from string import Formatter
import tempfile
import unittest

from leqi_region_changer.i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGE_LABELS,
    SUPPORTED_LANGUAGES,
    TRANSLATIONS,
    get_language,
    language_from_label,
    set_language,
    translate,
)
from leqi_region_changer.settings import (
    default_settings_path,
    load_language,
    save_language,
)


def _format_fields(template: str) -> tuple[str, ...]:
    return tuple(
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name is not None
    )


class TranslationTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_language(DEFAULT_LANGUAGE)

    def test_default_and_native_language_labels(self) -> None:
        self.assertEqual(DEFAULT_LANGUAGE, "en")
        self.assertEqual(SUPPORTED_LANGUAGES, ("en", "de", "it"))
        self.assertEqual(
            LANGUAGE_LABELS,
            {"en": "English", "de": "Deutsch", "it": "Italiano"},
        )
        self.assertEqual(language_from_label("English"), "en")
        self.assertEqual(language_from_label("Deutsch"), "de")
        self.assertEqual(language_from_label("Italiano"), "it")

    def test_languages_have_identical_keys_and_format_parameters(self) -> None:
        english = TRANSLATIONS["en"]
        for language in SUPPORTED_LANGUAGES:
            with self.subTest(language=language):
                translated = TRANSLATIONS[language]
                self.assertEqual(set(translated), set(english))
                for key, template in english.items():
                    self.assertEqual(
                        _format_fields(translated[key]),
                        _format_fields(template),
                        f"placeholder mismatch for {language}.{key}",
                    )

    def test_required_safety_copy_is_byte_exact(self) -> None:
        expected = {
            "en": "Check the adapter pinout. Changing the region may affect road approval and warranty.",
            "de": "Prüfe die Pinbelegung vom Adapter. Eine Regionsänderung kann die Zulassung und Garantie betreffen.",
            "it": "Controlla la piedinatura dell’adattatore. La modifica della regione può influire sull’omologazione e sulla garanzia.",
        }
        for language, copy in expected.items():
            with self.subTest(language=language):
                set_language(language)
                self.assertEqual(translate("safety_text"), copy)

    def test_switching_language_changes_runtime_messages(self) -> None:
        set_language("de")
        self.assertEqual(get_language(), "de")
        self.assertEqual(translate("current_region"), "AKTUELL")
        set_language("it")
        self.assertEqual(translate("current_region"), "ATTUALE")
        self.assertEqual(set_language("unsupported"), "en")
        self.assertEqual(translate("current_region"), "CURRENT")


class SettingsTests(unittest.TestCase):
    def test_settings_path_uses_local_app_data(self) -> None:
        self.assertEqual(
            default_settings_path({"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}),
            Path(r"C:\Users\Test\AppData\Local")
            / "Jupoma"
            / "LEQI Region Changer"
            / "settings.json",
        )
        self.assertIsNone(default_settings_path({}))

    def test_missing_corrupt_invalid_and_unreadable_settings_fall_back_to_english(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing.json"
            self.assertEqual(load_language(missing), "en")

            corrupt = root / "corrupt.json"
            corrupt.write_text("{not json", encoding="utf-8")
            self.assertEqual(load_language(corrupt), "en")

            invalid = root / "invalid.json"
            invalid.write_text('{"language": "fr"}', encoding="utf-8")
            self.assertEqual(load_language(invalid), "en")

            unreadable = root / "directory.json"
            unreadable.mkdir()
            self.assertEqual(load_language(unreadable), "en")

    def test_language_round_trip_is_atomic_and_rejects_unknown_codes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "settings.json"
            for language in ("de", "it", "en"):
                with self.subTest(language=language):
                    self.assertTrue(save_language(language, path))
                    self.assertEqual(load_language(path), language)
                    self.assertFalse(path.with_suffix(".tmp").exists())

            before = path.read_bytes()
            self.assertFalse(save_language("fr", path))
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
