from __future__ import annotations

import unittest

from leqi_region_changer.serial_transport import (
    IncompleteWriteError,
    SerialTransportError,
    get_port_lock,
    write_transaction,
)


DATA_FRAME = bytes.fromhex("5A 01 97 01 01 FB 91")
COMMIT_FRAME = bytes.fromhex("5A 01 97 01 00 EB B0")


class FakeSerial:
    def __init__(self, actions=None, *, close_error: Exception | None = None) -> None:
        self.actions = list(actions or [])
        self.close_error = close_error
        self.writes: list[bytes] = []
        self.flush_count = 0
        self.close_count = 0

    def write(self, data: bytes) -> int:
        self.writes.append(bytes(data))
        action = self.actions.pop(0) if self.actions else len(data)
        if isinstance(action, Exception):
            raise action
        return int(action)

    def flush(self) -> None:
        self.flush_count += 1

    def close(self) -> None:
        self.close_count += 1
        if self.close_error is not None:
            raise self.close_error


class FakeFactory:
    def __init__(self, serial_port: FakeSerial | None = None, error: Exception | None = None) -> None:
        self.serial_port = serial_port
        self.error = error
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        assert self.serial_port is not None
        return self.serial_port


class SerialTransportTests(unittest.TestCase):
    def test_success_uses_8n1_exact_delays_and_complete_writes(self) -> None:
        fake_serial = FakeSerial()
        factory = FakeFactory(fake_serial)
        sleeps: list[float] = []
        events = []

        result = write_transaction(
            "COM7",
            baudrate=19200,
            data_frame=DATA_FRAME,
            commit_frame=COMMIT_FRAME,
            serial_factory=factory,
            sleep=sleeps.append,
            event_sink=events.append,
        )

        self.assertEqual(
            factory.calls,
            [
                {
                    "port": "COM7",
                    "baudrate": 19200,
                    "bytesize": 8,
                    "parity": "N",
                    "stopbits": 1,
                    "write_timeout": 2.0,
                }
            ],
        )
        self.assertEqual(fake_serial.writes, [DATA_FRAME, COMMIT_FRAME])
        self.assertEqual(fake_serial.flush_count, 2)
        self.assertEqual(fake_serial.close_count, 1)
        self.assertEqual(sleeps, [0.100, 0.100])
        self.assertEqual(result.data_bytes_written, len(DATA_FRAME))
        self.assertEqual(result.commit_bytes_written, len(COMMIT_FRAME))
        self.assertEqual(events[-1].kind, "closed")
        self.assertIn("completed", [event.kind for event in events])

    def test_queue_event_sink_is_supported(self) -> None:
        class Sink:
            def __init__(self) -> None:
                self.items = []

            def put(self, item) -> None:
                self.items.append(item)

        sink = Sink()
        write_transaction(
            "COM8",
            baudrate=115200,
            data_frame=DATA_FRAME,
            commit_frame=None,
            serial_factory=FakeFactory(FakeSerial()),
            sleep=lambda _seconds: None,
            event_sink=sink,
        )
        self.assertTrue(sink.items)
        self.assertEqual(sink.items[-1].kind, "closed")

    def test_partial_data_write_fails_without_retry_and_closes(self) -> None:
        fake_serial = FakeSerial(actions=[len(DATA_FRAME) - 1])
        factory = FakeFactory(fake_serial)
        sleeps: list[float] = []

        with self.assertRaises(IncompleteWriteError) as caught:
            write_transaction(
                "COM9",
                baudrate=19200,
                data_frame=DATA_FRAME,
                commit_frame=COMMIT_FRAME,
                serial_factory=factory,
                sleep=sleeps.append,
            )

        self.assertEqual(caught.exception.phase, "data")
        self.assertEqual(fake_serial.writes, [DATA_FRAME])
        self.assertEqual(fake_serial.flush_count, 0)
        self.assertEqual(fake_serial.close_count, 1)
        self.assertEqual(sleeps, [0.100])

    def test_port_open_error_has_no_retry(self) -> None:
        factory = FakeFactory(error=OSError("port busy"))
        sleeps: list[float] = []

        with self.assertRaises(SerialTransportError) as caught:
            write_transaction(
                "COM10",
                baudrate=19200,
                data_frame=DATA_FRAME,
                commit_frame=COMMIT_FRAME,
                serial_factory=factory,
                sleep=sleeps.append,
            )

        self.assertEqual(caught.exception.phase, "open")
        self.assertEqual(len(factory.calls), 1)
        self.assertEqual(sleeps, [])

    def test_process_local_busy_port_fails_without_opening_or_retrying(self) -> None:
        port = "COM24"
        factory = FakeFactory(FakeSerial())
        lock = get_port_lock(port)
        lock.acquire()
        try:
            with self.assertRaises(SerialTransportError) as caught:
                write_transaction(
                    port,
                    baudrate=19200,
                    data_frame=DATA_FRAME,
                    commit_frame=COMMIT_FRAME,
                    serial_factory=factory,
                    sleep=lambda _seconds: None,
                )
        finally:
            lock.release()

        self.assertEqual(caught.exception.phase, "lock")
        self.assertEqual(factory.calls, [])

    def test_commit_write_error_closes_and_does_not_retry(self) -> None:
        fake_serial = FakeSerial(actions=[len(DATA_FRAME), OSError("commit failed")])
        sleeps: list[float] = []

        with self.assertRaises(SerialTransportError) as caught:
            write_transaction(
                "COM11",
                baudrate=19200,
                data_frame=DATA_FRAME,
                commit_frame=COMMIT_FRAME,
                serial_factory=FakeFactory(fake_serial),
                sleep=sleeps.append,
            )

        self.assertEqual(caught.exception.phase, "commit")
        self.assertEqual(fake_serial.writes, [DATA_FRAME, COMMIT_FRAME])
        self.assertEqual(fake_serial.flush_count, 1)
        self.assertEqual(fake_serial.close_count, 1)
        self.assertEqual(sleeps, [0.100, 0.100])

    def test_close_error_is_reported_after_successful_writes(self) -> None:
        fake_serial = FakeSerial(close_error=OSError("close failed"))

        with self.assertRaises(SerialTransportError) as caught:
            write_transaction(
                "COM12",
                baudrate=19200,
                data_frame=DATA_FRAME,
                commit_frame=COMMIT_FRAME,
                serial_factory=FakeFactory(fake_serial),
                sleep=lambda _seconds: None,
            )

        self.assertEqual(caught.exception.phase, "close")
        self.assertEqual(fake_serial.close_count, 1)

    def test_original_write_error_wins_over_close_error(self) -> None:
        fake_serial = FakeSerial(
            actions=[OSError("write failed")],
            close_error=OSError("close failed"),
        )

        with self.assertRaises(SerialTransportError) as caught:
            write_transaction(
                "COM13",
                baudrate=19200,
                data_frame=DATA_FRAME,
                commit_frame=COMMIT_FRAME,
                serial_factory=FakeFactory(fake_serial),
                sleep=lambda _seconds: None,
            )

        self.assertEqual(caught.exception.phase, "data")
        self.assertEqual(fake_serial.close_count, 1)


if __name__ == "__main__":
    unittest.main()
