from __future__ import annotations

import unittest

from leqi_region_changer.profiles import BASELINE_PROFILES, find_profile
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

    def test_6lite_eu_len14_golden_crc_59a7(self) -> None:
        frame = build_serial_write_frame("72365DXAN2L5ZH00502")
        self.assertEqual(frame[0:5], bytes.fromhex("5A 01 97 14 01"))
        self.assertEqual(frame[-2:], bytes.fromhex("59 A7"))

    def test_6_eu_slash_len15_golden_crc_19f5(self) -> None:
        frame = build_serial_write_frame("72361/DXAN2L5ZN00191")
        self.assertEqual(frame[0:5], bytes.fromhex("5A 01 97 15 01"))
        self.assertEqual(frame[-2:], bytes.fromhex("19 F5"))

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
                "6_lite",
                "72364DXAN2L5ZH00502",
                "72365DXAN2L5ZH00502",
                "5A 01 97 14 01 37 32 33 36 35 44 58 41 4E 32 4C 35 5A 48 30 30 35 30 32 59 A7",
            ),
            (
                "6",
                "72359/DXAN2L5ZN00191",
                "72361/DXAN2L5ZN00191",
                "5A 01 97 15 01 37 32 33 36 31 2F 44 58 41 4E 32 4C 35 5A 4E 30 30 31 39 31 19 F5",
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

    def test_accepts_unknown_current_prefix_and_preserves_tail(self) -> None:
        transaction = prepare_serial_transaction(
            find_profile("elite"),
            "99999DXAN2F5V101557",
            "EU",
        )

        self.assertEqual(transaction.current_serial, "99999DXAN2F5V101557")
        self.assertEqual(transaction.target_serial, "60545DXAN2F5V101557")
        self.assertEqual(transaction.wire_serial, "60545DXAN2F5V101557")
        self.assertEqual(transaction.current_serial[5:], transaction.target_serial[5:])
        self.assertEqual(transaction.baudrate, 19200)
        self.assertEqual(transaction.data_frame, build_serial_write_frame(transaction.wire_serial))

    def test_unknown_prefix_can_be_replaced_by_every_configured_target(self) -> None:
        for profile in BASELINE_PROFILES:
            for target_region, target_prefix in profile.regions.items():
                if target_prefix is None:
                    continue
                with self.subTest(profile=profile.id, region=target_region):
                    transaction = prepare_region_change(
                        profile,
                        "99999DXAN2F5V101557",
                        target_region,
                    )
                    self.assertEqual(transaction.target_serial[:5], target_prefix)
                    self.assertEqual(transaction.target_serial[5:], "DXAN2F5V101557")
                    self.assertEqual(
                        transaction.wire_serial,
                        f"{target_prefix}{profile.wire_separator}DXAN2F5V101557",
                    )

    def test_blocks_unavailable_target_region(self) -> None:
        with self.assertRaisesRegex(SerialTransactionError, "not available"):
            prepare_serial_transaction(
                find_profile("4litegen2_itde_with_turn_signal"),
                "5377700000000JUPOMA",
                "US",
            )

    def test_allows_rewriting_the_current_region(self) -> None:
        transaction = prepare_serial_transaction(
            find_profile("elite"),
            "60545DXAN2F5QD02305",
            "EU",
        )

        self.assertEqual(transaction.current_serial, transaction.target_serial)
        self.assertEqual(transaction.wire_serial, "60545DXAN2F5QD02305")
        self.assertEqual(transaction.data_frame, build_serial_write_frame(transaction.wire_serial))

    def test_blocks_unknown_region_code(self) -> None:
        with self.assertRaisesRegex(SerialTransactionError, "target region"):
            prepare_serial_transaction(
                find_profile("elite"),
                "60543DXAN2F5QD02305",
                "GLOBAL",
            )


if __name__ == "__main__":
    unittest.main()
