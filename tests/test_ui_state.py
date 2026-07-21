from __future__ import annotations

import unittest

from leqi_region_changer.profiles import ScooterProfile, RegionPrefixes
from leqi_region_changer.ui_state import UiState, build_profile_label_map


class UiStateTests(unittest.TestCase):
    def test_write_requires_every_precondition(self) -> None:
        state = UiState(
            profile_selected=True,
            port_selected=True,
            serial_valid=True,
            target_region_selected=True,
            acknowledged=True,
        )
        self.assertTrue(state.can_write)

        for field in (
            "profile_selected",
            "port_selected",
            "serial_valid",
            "target_region_selected",
            "acknowledged",
        ):
            self.assertFalse(state.updated(**{field: False}).can_write, field)

    def test_worker_and_diagnostics_are_mutually_exclusive(self) -> None:
        ready = UiState(True, True, True, True, True)
        self.assertFalse(ready.updated(busy=True).can_write)
        self.assertFalse(ready.updated(diagnostics_active=True).can_write)

    def test_block_reason_has_safety_order(self) -> None:
        self.assertEqual(UiState(busy=True).block_reason(), "Eine Übertragung läuft.")
        self.assertEqual(
            UiState(diagnostics_active=True).block_reason(),
            "Beende zuerst die Diagnoseverbindung.",
        )

    def test_duplicate_display_names_are_disambiguated_by_profile_id(self) -> None:
        first = ScooterProfile(
            1,
            "elite_a",
            "Elite",
            19200,
            "leqi_serial_write_v1",
            "",
            RegionPrefixes("11111", "11112", None),
        )
        second = ScooterProfile(
            1,
            "elite_b",
            "Elite",
            115200,
            "leqi_serial_write_v1",
            "",
            RegionPrefixes("22221", "22222", None),
        )

        labels = build_profile_label_map((first, second))

        self.assertEqual(list(labels), ["Elite · elite_a", "Elite · elite_b"])
        self.assertIs(labels["Elite · elite_a"], first)
        self.assertIs(labels["Elite · elite_b"], second)


if __name__ == "__main__":
    unittest.main()
