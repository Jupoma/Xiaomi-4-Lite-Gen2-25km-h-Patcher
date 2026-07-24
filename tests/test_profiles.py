from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
import unittest

from leqi_region_changer.profiles import (
    BASELINE_PROFILES,
    ProfileValidationError,
    find_profile,
    load_profile_file,
    load_profiles,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class BaselineProfileTests(unittest.TestCase):
    def test_baseline_profiles_have_exact_order_and_values(self) -> None:
        self.assertEqual(
            [profile.id for profile in BASELINE_PROFILES],
            ["4litegen2_itde_with_turn_signal", "5_plus", "6_lite", "6", "elite"],
        )

        four_lite = find_profile("4litegen2_itde_with_turn_signal")
        self.assertEqual(four_lite.display_name, "4 Lite Gen2 DE/IT Version with turn Signals")
        self.assertEqual(four_lite.baudrate, 115200)
        self.assertEqual(dict(four_lite.regions), {"DE": "53777", "EU": "53937", "US": None})

        five_plus = find_profile("5_plus")
        self.assertEqual(five_plus.display_name, "5 Plus")
        self.assertEqual(five_plus.baudrate, 19200)
        self.assertEqual(five_plus.wire_separator, "/")
        self.assertEqual(
            dict(five_plus.regions),
            {"DE": "66232", "EU": "66230", "US": "66227"},
        )

        six_lite = find_profile("6_lite")
        self.assertEqual(six_lite.display_name, "6 Lite")
        self.assertEqual(six_lite.baudrate, 19200)
        self.assertEqual(six_lite.wire_separator, "")
        self.assertEqual(
            dict(six_lite.regions),
            {"DE": "72367", "EU": "72365", "US": "72364"},
        )

        six = find_profile("6")
        self.assertEqual(six.display_name, "6")
        self.assertEqual(six.baudrate, 19200)
        self.assertEqual(six.wire_separator, "/")
        self.assertEqual(
            dict(six.regions),
            {"DE": "72363", "EU": "72361", "US": "72359"},
        )

        elite = find_profile("elite")
        self.assertEqual(elite.display_name, "Elite")
        self.assertEqual(elite.baudrate, 19200)
        self.assertEqual(elite.wire_separator, "")
        self.assertEqual(
            dict(elite.regions),
            {"DE": "60543", "EU": "60545", "US": "60457"},
        )

        self.assertEqual(four_lite.wire_separator, "")

    def test_profiles_and_region_mappings_are_immutable(self) -> None:
        profile = find_profile("5_plus")
        with self.assertRaises(FrozenInstanceError):
            profile.baudrate = 115200  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            profile.regions.EU = "00000"  # type: ignore[misc]

    def test_shipped_json_files_match_embedded_baselines(self) -> None:
        result = load_profiles(PROJECT_ROOT / "profiles")
        self.assertEqual(result.profiles, BASELINE_PROFILES)
        self.assertEqual(result.warnings, ())


class ExternalOverrideTests(unittest.TestCase):
    def test_valid_external_profile_replaces_baseline_without_mutating_it(self) -> None:
        source = json.loads((PROJECT_ROOT / "profiles" / "5_plus.json").read_text(encoding="utf-8"))
        source["display_name"] = "5 Plus Lab"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "override.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            loaded = load_profiles(PROJECT_ROOT / "profiles", directory)

        overridden = find_profile("5_plus", loaded)
        self.assertEqual(overridden.display_name, "5 Plus Lab")
        self.assertEqual(find_profile("5_plus").display_name, "5 Plus")

    def test_invalid_external_profile_warns_and_keeps_baseline(self) -> None:
        source = json.loads((PROJECT_ROOT / "profiles" / "5_plus.json").read_text(encoding="utf-8"))
        source["baudrate"] = 9600
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "bad.json").write_text(json.dumps(source), encoding="utf-8")
            loaded = load_profiles(PROJECT_ROOT / "profiles", directory)

        self.assertEqual(find_profile("5_plus", loaded), find_profile("5_plus"))
        self.assertEqual(len(loaded.warnings), 1)
        self.assertIn("bad.json", loaded.warnings[0])

    def test_duplicate_external_ids_warn_and_first_file_wins(self) -> None:
        source = json.loads((PROJECT_ROOT / "profiles" / "5_plus.json").read_text(encoding="utf-8"))
        first = dict(source)
        first["display_name"] = "5 Plus Erstes Profil"
        second = dict(source)
        second["display_name"] = "5 Plus Zweites Profil"

        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "a.json").write_text(json.dumps(first), encoding="utf-8")
            Path(directory, "b.json").write_text(json.dumps(second), encoding="utf-8")
            loaded = load_profiles(PROJECT_ROOT / "profiles", directory)

        self.assertEqual(find_profile("5_plus", loaded).display_name, "5 Plus Erstes Profil")
        self.assertEqual(len(loaded.warnings), 1)
        self.assertIn("Duplicate profile ID", loaded.warnings[0])
        self.assertIn("b.json", loaded.warnings[0])

    def test_schema_rejects_bad_separator_protocol_and_region_prefix(self) -> None:
        source = json.loads((PROJECT_ROOT / "profiles" / "elite.json").read_text(encoding="utf-8"))
        invalid_values = (
            ("schema_version", 1.0),
            ("baudrate", True),
            ("wire_separator", "-"),
            ("protocol", "unknown"),
        )
        for field, value in invalid_values:
            with self.subTest(field=field):
                candidate = dict(source)
                candidate[field] = value
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "bad.json"
                    path.write_text(json.dumps(candidate), encoding="utf-8")
                    with self.assertRaises(ProfileValidationError):
                        load_profile_file(path)

        source["regions"]["EU"] = "1234/"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaises(ProfileValidationError):
                load_profile_file(path)


if __name__ == "__main__":
    unittest.main()
