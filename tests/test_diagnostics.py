from __future__ import annotations

import threading
import unittest

from leqi_region_changer.diagnostics import (
    FrameParser,
    PassiveMonitor,
    crc16_xmodem,
)
from leqi_region_changer.serial_transport import get_port_lock


def make_frame(command: int, subcommand: int, payload: bytes) -> bytes:
    header = bytes([0x5A, command, subcommand, len(payload)]) + payload
    crc = crc16_xmodem(header)
    return header + bytes([crc >> 8, crc & 0xFF])


class MonitorSerial:
    def __init__(self, chunks: list[bytes], *, close_error: Exception | None = None) -> None:
        self.chunks = list(chunks)
        self.close_error = close_error
        self.close_count = 0
        self.read_sizes: list[int] = []

    def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        if self.chunks:
            return self.chunks.pop(0)
        return b""

    def close(self) -> None:
        self.close_count += 1
        if self.close_error is not None:
            raise self.close_error


class MonitorFactory:
    def __init__(self, serial_port: MonitorSerial | None = None, error: Exception | None = None) -> None:
        self.serial_port = serial_port
        self.error = error
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        assert self.serial_port is not None
        return self.serial_port


class FrameParserTests(unittest.TestCase):
    def test_crc16_xmodem_reference_vector(self) -> None:
        self.assertEqual(crc16_xmodem(b"123456789"), 0x31C3)

    def test_fragmented_frame_is_emitted_only_when_complete(self) -> None:
        frame = make_frame(0x12, 0x20, bytes.fromhex("01 02 03 04"))
        parser = FrameParser()

        self.assertEqual(parser.feed(frame[:2]), [])
        self.assertEqual(parser.feed(frame[2:7]), [])
        parsed = parser.feed(frame[7:])

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].data, frame)
        self.assertEqual(parsed[0].payload, bytes.fromhex("01 02 03 04"))
        self.assertTrue(parsed[0].crc_ok)
        self.assertEqual(parser.buffered_bytes, b"")

    def test_combined_frames_and_leading_noise(self) -> None:
        first = make_frame(0x12, 0x20, b"\x01")
        second = make_frame(0x21, 0x20, b"\x02\x03")
        parser = FrameParser()

        parsed = parser.feed(b"\x00\x7Fnoise" + first + second)

        self.assertEqual([item.data for item in parsed], [first, second])
        self.assertEqual(parser.discarded_noise, 7)

    def test_bad_crc_is_reported_and_parser_resynchronises(self) -> None:
        damaged = bytearray(make_frame(0x12, 0x21, b"abc"))
        damaged[-1] ^= 0x01
        valid = make_frame(0x21, 0x20, b"ok")
        parser = FrameParser()

        parsed = parser.feed(bytes(damaged) + valid)

        self.assertEqual(len(parsed), 2)
        self.assertFalse(parsed[0].crc_ok)
        self.assertEqual(parsed[0].data, bytes(damaged))
        self.assertTrue(parsed[1].crc_ok)
        self.assertEqual(parsed[1].data, valid)

    def test_false_incomplete_start_does_not_hide_later_valid_frame(self) -> None:
        valid = make_frame(0x12, 0x20, b"ok")
        parser = FrameParser()

        parsed = parser.feed(bytes([0x5A, 0x99, 0x99, 0xFF, 0x01]) + valid)

        self.assertEqual([item.data for item in parsed], [valid])
        self.assertEqual(parser.discarded_noise, 5)


class PassiveMonitorTests(unittest.TestCase):
    def test_monitor_uses_profile_baud_8n1_parses_and_closes(self) -> None:
        first = make_frame(0x12, 0x20, b"\x01")
        second = make_frame(0x21, 0x20, b"\x02")
        serial_port = MonitorSerial([b"noise" + first + second])
        factory = MonitorFactory(serial_port)
        events = []
        monitor_holder = {}

        def on_event(event) -> None:
            events.append(event)
            if event.kind == "frame_received" and event.details["frame"].data == second:
                monitor_holder["monitor"].stop()

        monitor = PassiveMonitor(
            "COM20",
            baudrate=19200,
            serial_factory=factory,
            event_sink=on_event,
            sleep=lambda _seconds: None,
            read_size=64,
        )
        monitor_holder["monitor"] = monitor

        monitor.start()
        monitor.join(1.0)

        self.assertFalse(monitor.is_running)
        self.assertEqual(
            factory.calls,
            [
                {
                    "port": "COM20",
                    "baudrate": 19200,
                    "bytesize": 8,
                    "parity": "N",
                    "stopbits": 1,
                    "timeout": 0.1,
                }
            ],
        )
        received = [event.details["frame"] for event in events if event.kind == "frame_received"]
        self.assertEqual([frame.data for frame in received], [first, second])
        self.assertIn("noise_discarded", [event.kind for event in events])
        self.assertEqual(serial_port.close_count, 1)
        self.assertEqual(events[-1].kind, "monitor_stopped")
        self.assertFalse(hasattr(monitor, "write"))
        self.assertFalse(hasattr(monitor, "send_raw"))

    def test_monitor_reports_open_error_without_retry(self) -> None:
        factory = MonitorFactory(error=OSError("missing port"))
        events = []
        monitor = PassiveMonitor(
            "COM21",
            baudrate=115200,
            serial_factory=factory,
            event_sink=events.append,
        )

        monitor.start()
        monitor.join(1.0)

        self.assertEqual(len(factory.calls), 1)
        self.assertIn("monitor_error", [event.kind for event in events])
        self.assertEqual(events[-1].kind, "monitor_stopped")

    def test_monitor_reports_close_failure_in_terminal_event(self) -> None:
        serial_port = MonitorSerial([], close_error=OSError("close failed"))
        events = []
        monitor_holder = {}

        def on_event(event) -> None:
            events.append(event)
            if event.kind == "monitor_started":
                monitor_holder["monitor"].stop()

        monitor = PassiveMonitor(
            "COM23",
            baudrate=19200,
            serial_factory=MonitorFactory(serial_port),
            event_sink=on_event,
        )
        monitor_holder["monitor"] = monitor

        monitor.start()
        monitor.join(1.0)

        self.assertIn("monitor_error", [event.kind for event in events])
        self.assertFalse(events[-1].details["close_ok"])

    def test_stop_while_waiting_for_shared_port_lock_never_opens_port(self) -> None:
        port = "COM22"
        port_lock = get_port_lock(port)
        factory = MonitorFactory(MonitorSerial([]))
        waiting = threading.Event()
        events = []

        def on_event(event) -> None:
            events.append(event)
            if event.kind == "monitor_waiting":
                waiting.set()

        port_lock.acquire()
        try:
            monitor = PassiveMonitor(
                port,
                baudrate=19200,
                serial_factory=factory,
                event_sink=on_event,
            )
            monitor.start()
            self.assertTrue(waiting.wait(1.0))
            monitor.stop()
        finally:
            port_lock.release()

        monitor.join(1.0)
        self.assertFalse(monitor.is_running)
        self.assertEqual(factory.calls, [])
        self.assertEqual(events[-1].kind, "monitor_stopped")


if __name__ == "__main__":
    unittest.main()
