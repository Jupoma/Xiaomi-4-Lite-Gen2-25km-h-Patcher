from __future__ import annotations

import unittest

from leqi_region_changer.profiles import find_profile
from leqi_region_changer.protocol import (
    COMMIT_FRAME,
    SerialNumberError,
    SerialTransactionError,
    build_serial_write_frame,
    crc16_xmodem,
    normalize_serial_number,
    prepare_region_change,
    prepare_serial_transaction,
)


class CrcAndFrameGoldenTests(unittest.TestCase):
    def test_crc16_xmodem_reference_vector(self) -> None:
        self.assertEqual(crc16_xmodem(b"123456789"), 0x31C3)
        self.assertEqual(crc16_xmodem(COMMIT_FRAME[:-2]), 0xEBB0)

    def test_4lite_eu_golden_crc_5715(self) -> None:
        frame = build_serial_write_frame("5393700000000JUPOMA")
        self.assertEqual(frame[0:5], bytes.fromhex("5A 01 97 14 01"))
        self.assertEqual(frame[-2:], bytes.fromhex("57 15"))

    def test_5plus_eu_slash_len15_golden_crc_dd95(self) -> None:
        frame = build_serial_write_frame("66230/DXAN2F5V101557")
        self.assertEqual(frame[0:5], bytes.fromhex("5A 01 97 15 01"))
        self.assertEqual(frame[-2:], bytes.fromhex("DD 95"))

    def test_elite_eu_golden_crc_d5a5(self) -> None:
        frame = build_serial_write_frame("60545DXAN2F5QD02305")
        self.assertEqual(frame[0:5], bytes.fromhex("5A 01 97 14 01"))
        self.assertEqual(frame[-2:], bytes.fromhex("D5 A5"))

    def test_commit_frame_is_exact(self) -> None:
        self.assertEqual(COMMIT_FRAME, bytes.fromhex("5A 01 97 01 00 EB B0"))

    def test_all_golden_transactions_are_byte_exact(self) -> None:
        cases = (
            (
                "4litegen2_itde_with_turn_signal",
                "53777/00000000JUPOMA",
                "5393700000000JUPOMA",
                "5A 01 97 14 01 35 33 39 33 37 30 30 30 30 30 30 30 30 4A 55 50 4F 4D 41 57 15",
            ),
            (
                "5_plus",
                "66232/DXAN2F5V101557",
                "66230/DXAN2F5V101557",
                "5A 01 97 15 01 36 36 32 33 30 2F 44 58 41 4E 32 46 35 56 31 30 31 35 35 37 DD 95",
            ),
            (
                "elite",
                "60543DXAN2F5QD02305",
                "60545DXAN2F5QD02305",
                "5A 01 97 14 01 36 30 35 34 35 44 58 41 4E 32 46 35 51 44 30 32 33 30 35 D5 A5",
            ),
        )

        for profile_id, current_serial, expected_wire, expected_hex in cases:
            with self.subTest(profile=profile_id):
                transaction = prepare_region_change(
                    find_profile(profile_id),
                    current_serial,
                    "EU",
                )
                self.assertEqual(transaction.wire_serial, expected_wire)
                self.assertEqual(transaction.data_frame, bytes.fromhex(expected_hex))
                self.assertEqual(transaction.commit_frame, COMMIT_FRAME)


class SerialNormalizationTests(unittest.TestCase):
    def test_optional_separator_normalizes_to_same_canonical_serial(self) -> None:
        expected = "66230DXAN2F5V101557"
        self.assertEqual(normalize_serial_number(expected), expected)
        self.assertEqual(normalize_serial_number("66230/DXAN2F5V101557"), expected)

    def test_rejects_non_strict_serials(self) -> None:
        invalid = (
            "66230//DXAN2F5V101557",
            "6623/DXAN2F5V101557",
            "66230-DXAN2F5V101557",
            "66230/dxan2f5v101557",
            " 66230DXAN2F5V101557",
            "66230DXAN2F5V101557 ",
            "66230DXAN2F5V10155",
        )
        for serial in invalid:
            with self.subTest(serial=serial), self.assertRaises(SerialNumberError):
                normalize_serial_number(serial)


class PrepareTransactionTests(unittest.TestCase):
    def test_preserves_tail_and_uses_profile_separator_and_baudrate(self) -> None:
        profile = find_profile("5_plus")
        transaction = prepare_region_change(
            profile,
            "66232ABCDEF12345678",
            "EU",
        )
        self.assertEqual(transaction.current_serial, "66232ABCDEF12345678")
        self.assertEqual(transaction.target_serial, "66230ABCDEF12345678")
        self.assertEqual(transaction.wire_serial, "66230/ABCDEF12345678")
        self.assertEqual(transaction.target_region, "EU")
        self.assertEqual(transaction.baudrate, 19200)
        self.assertEqual(transaction.data_frame, build_serial_write_frame(transaction.wire_serial))
        self.assertEqual(transaction.write_frame, transaction.data_frame)
        self.assertEqual(transaction.commit_frame, COMMIT_FRAME)

    def test_blocks_current_prefix_from_other_profile(self) -> None:
        with self.assertRaisesRegex(SerialTransactionError, "passt nicht zum Profil"):
            prepare_serial_transaction(
                find_profile("elite"),
                "66232DXAN2F5V101557",
                "EU",
            )

    def test_blocks_unavailable_target_region(self) -> None:
        with self.assertRaisesRegex(SerialTransactionError, "nicht verfügbar"):
            prepare_serial_transaction(
                find_profile("4litegen2_itde_with_turn_signal"),
                "5377700000000JUPOMA",
                "US",
            )

    def test_blocks_noop_target_region(self) -> None:
        with self.assertRaisesRegex(SerialTransactionError, "entspricht bereits"):
            prepare_serial_transaction(
                find_profile("elite"),
                "60545DXAN2F5QD02305",
                "EU",
            )

    def test_blocks_unknown_region_code(self) -> None:
        with self.assertRaisesRegex(SerialTransactionError, "Zielregion"):
            prepare_serial_transaction(
                find_profile("elite"),
                "60543DXAN2F5QD02305",
                "GLOBAL",
            )


if __name__ == "__main__":
    unittest.main()
