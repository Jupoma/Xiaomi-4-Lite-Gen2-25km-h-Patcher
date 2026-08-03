"""LEQI serial-number write protocol and transaction preparation."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final

from .i18n import translate as tr
from .profiles import REGION_CODES, SUPPORTED_PROTOCOL, ScooterProfile


SERIAL_WRITE_PREFIX: Final = bytes((0x5A, 0x01, 0x97))
COMMIT_FRAME: Final = bytes.fromhex("5A 01 97 01 00 EB B0")
_SERIAL_RE = re.compile(
    r"^(?P<prefix>[0-9]{5})(?P<separator>/)?(?P<tail>[A-Z0-9]{14})$",
    re.ASCII,
)


class SerialNumberError(ValueError):
    """Raised when a serial number violates the strict LEQI format."""


class SerialTransactionError(ValueError):
    """Raised when a safe region-change transaction cannot be prepared."""


@dataclass(frozen=True, slots=True)
class SerialTransaction:
    """Complete immutable write transaction consumed by the serial transport."""

    profile_id: str
    baudrate: int
    current_serial: str
    target_region: str
    target_serial: str
    wire_serial: str
    data_frame: bytes
    commit_frame: bytes

    @property
    def write_frame(self) -> bytes:
        """Compatibility alias for transports using the older field name."""

        return self.data_frame


def crc16_xmodem(data: bytes) -> int:
    """Return CRC-16/XMODEM (poly 0x1021, init/xorout 0x0000)."""

    crc = 0x0000
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _match_serial(serial: str) -> re.Match[str]:
    if not isinstance(serial, str):
        raise SerialNumberError(tr("serial_type_error"))
    match = _SERIAL_RE.fullmatch(serial)
    if match is None:
        raise SerialNumberError(tr("serial_format_error"))
    return match


def normalize_serial_number(serial: str) -> str:
    """Validate ``serial`` and return its canonical 19-character no-slash form."""

    match = _match_serial(serial)
    return f"{match.group('prefix')}{match.group('tail')}"


def build_serial_write_frame(wire_serial: str) -> bytes:
    """Build ``5A 01 97 LEN 01 ASCII CRC`` for a strict wire serial."""

    _match_serial(wire_serial)
    serial_bytes = wire_serial.encode("ascii")
    payload_length = len(serial_bytes) + 1
    body = SERIAL_WRITE_PREFIX + bytes((payload_length, 0x01)) + serial_bytes
    crc = crc16_xmodem(body)
    return body + crc.to_bytes(2, "big")


def prepare_region_change(
    profile: ScooterProfile,
    current_serial: str,
    target_region: str,
) -> SerialTransaction:
    """Prepare a safe profile-aware serial-number region change.

    The current serial's 14-character tail is retained. Any syntactically
    valid current prefix is accepted. Only unavailable target regions are
    deliberately blocked.
    """

    if profile.protocol != SUPPORTED_PROTOCOL:
        raise SerialTransactionError(tr("unsupported_protocol", protocol=profile.protocol))
    canonical_current = normalize_serial_number(current_serial)
    serial_tail = canonical_current[5:]

    if target_region not in REGION_CODES:
        raise SerialTransactionError(tr("target_region_invalid", regions=", ".join(REGION_CODES)))

    target_prefix = profile.prefix_for(target_region)
    if target_prefix is None:
        raise SerialTransactionError(
            tr("target_region_unavailable", region=target_region, profile=profile.id)
        )

    target_serial = f"{target_prefix}{serial_tail}"
    wire_serial = f"{target_prefix}{profile.wire_separator}{serial_tail}"
    return SerialTransaction(
        profile_id=profile.id,
        baudrate=profile.baudrate,
        current_serial=canonical_current,
        target_region=target_region,
        target_serial=target_serial,
        wire_serial=wire_serial,
        data_frame=build_serial_write_frame(wire_serial),
        commit_frame=COMMIT_FRAME,
    )


def prepare_serial_transaction(
    profile: ScooterProfile,
    current_serial: str,
    target_region: str,
) -> SerialTransaction:
    """Compatibility alias for :func:`prepare_region_change`."""

    return prepare_region_change(profile, current_serial, target_region)
