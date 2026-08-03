"""Passive serial diagnostics with incremental LEQI frame parsing."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any

from .i18n import translate as tr
from .serial_transport import (
    EventSink,
    SerialEvent,
    SerialFactory,
    SleepFunction,
    emit_event,
    get_port_lock,
    resolve_serial_factory,
)


FRAME_START = 0x5A


def crc16_xmodem(data: bytes | bytearray | memoryview) -> int:
    """Return CRC-16/XMODEM (poly 0x1021, init 0x0000)."""

    crc = 0x0000
    for value in data:
        crc ^= int(value) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


@dataclass(frozen=True)
class DiagnosticFrame:
    """One complete ``5A CMD SUB LEN PAYLOAD CRC`` frame."""

    data: bytes
    payload_length: int
    crc_received: int
    crc_computed: int
    crc_ok: bool

    @property
    def command(self) -> int:
        return self.data[1]

    @property
    def subcommand(self) -> int:
        return self.data[2]

    @property
    def payload(self) -> bytes:
        return self.data[4:-2]


class FrameParser:
    """Incrementally split arbitrary byte chunks into LEQI frames.

    Leading noise is discarded.  A bad-CRC candidate is returned for
    diagnostics, then the parser advances by one byte so it can resynchronise
    on a valid nested/later ``0x5A`` frame instead of losing the whole stream.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.discarded_noise = 0

    @property
    def buffered_bytes(self) -> bytes:
        return bytes(self._buffer)

    def reset(self) -> None:
        self._buffer.clear()
        self.discarded_noise = 0

    @staticmethod
    def _decode(candidate: bytes) -> DiagnosticFrame:
        payload_length = candidate[3]
        crc_received = (candidate[-2] << 8) | candidate[-1]
        crc_computed = crc16_xmodem(candidate[:-2])
        return DiagnosticFrame(
            data=candidate,
            payload_length=payload_length,
            crc_received=crc_received,
            crc_computed=crc_computed,
            crc_ok=crc_received == crc_computed,
        )

    def _later_complete_valid_start(self) -> int | None:
        """Find a complete valid frame behind an incomplete false start."""

        search_from = 1
        while True:
            index = self._buffer.find(FRAME_START, search_from)
            if index < 0:
                return None
            if len(self._buffer) - index < 4:
                return None
            frame_length = 4 + self._buffer[index + 3] + 2
            if len(self._buffer) - index >= frame_length:
                candidate = bytes(self._buffer[index : index + frame_length])
                if self._decode(candidate).crc_ok:
                    return index
            search_from = index + 1

    def feed(self, chunk: bytes | bytearray | memoryview) -> list[DiagnosticFrame]:
        """Consume one chunk and return every newly completed frame."""

        if chunk:
            self._buffer.extend(chunk)
        frames: list[DiagnosticFrame] = []

        while self._buffer:
            start = self._buffer.find(FRAME_START)
            if start < 0:
                self.discarded_noise += len(self._buffer)
                self._buffer.clear()
                break
            if start > 0:
                self.discarded_noise += start
                del self._buffer[:start]

            if len(self._buffer) < 4:
                break

            frame_length = 4 + self._buffer[3] + 2
            if len(self._buffer) < frame_length:
                later_start = self._later_complete_valid_start()
                if later_start is None:
                    break
                self.discarded_noise += later_start
                del self._buffer[:later_start]
                continue

            candidate = bytes(self._buffer[:frame_length])
            frame = self._decode(candidate)
            frames.append(frame)
            if frame.crc_ok:
                del self._buffer[:frame_length]
            else:
                # Drop only the false start, then rescan for the next frame.
                del self._buffer[0]

        return frames


class PassiveMonitor:
    """Read-only background monitor for one profile-specific baudrate.

    The monitor owns the same per-port lock as ``write_transaction`` for its
    complete open/read/close lifetime.  It intentionally exposes no transmit
    method.
    """

    def __init__(
        self,
        port: str,
        *,
        baudrate: int,
        event_sink: EventSink = None,
        serial_factory: SerialFactory | None = None,
        sleep: SleepFunction = time.sleep,
        parser: FrameParser | None = None,
        read_size: int = 256,
        read_timeout: float = 0.1,
        idle_sleep: float = 0.01,
    ) -> None:
        port_name = str(port).strip()
        if not port_name:
            raise ValueError(tr("port_empty"))
        if isinstance(baudrate, bool) or not isinstance(baudrate, int) or baudrate <= 0:
            raise ValueError(tr("baud_positive"))
        if read_size <= 0:
            raise ValueError(tr("read_size_positive"))
        if read_timeout < 0 or idle_sleep < 0:
            raise ValueError(tr("timeouts_nonnegative"))

        self.port = port_name
        self.baudrate = baudrate
        self.event_sink = event_sink
        self.serial_factory = serial_factory
        self.sleep = sleep
        self.parser = parser if parser is not None else FrameParser()
        self.read_size = read_size
        self.read_timeout = read_timeout
        self.idle_sleep = idle_sleep
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._state_lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> None:
        """Start the passive worker; duplicate starts are rejected."""

        with self._state_lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError(tr("monitor_running"))
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name=f"LEQI-monitor-{self.port}",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Request a stop.  ``join`` can be used when synchronous shutdown is needed."""

        self._stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _event(
        self,
        kind: str,
        phase: str,
        *,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        emit_event(
            self.event_sink,
            SerialEvent(
                kind=kind,
                port=self.port,
                phase=phase,
                message=message,
                details={} if details is None else details,
            ),
        )

    def _acquire_interruptibly(self, lock: threading.Lock) -> bool:
        while not self._stop_event.is_set():
            if lock.acquire(timeout=0.05):
                return True
        return False

    def _run(self) -> None:
        port_lock = get_port_lock(self.port)
        serial_port: Any | None = None
        acquired = False
        close_ok = True
        previous_noise = self.parser.discarded_noise
        try:
            self._event("monitor_waiting", "lock")
            acquired = self._acquire_interruptibly(port_lock)
            if not acquired:
                return
            if self._stop_event.is_set():
                return

            factory = resolve_serial_factory(self.serial_factory)
            serial_port = factory(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=self.read_timeout,
            )
            self._event(
                "monitor_started",
                "monitor",
                details={"baudrate": self.baudrate},
            )

            while not self._stop_event.is_set():
                chunk = serial_port.read(self.read_size)
                if not chunk:
                    if self.idle_sleep:
                        self.sleep(self.idle_sleep)
                    continue

                frames = self.parser.feed(chunk)
                if self.parser.discarded_noise != previous_noise:
                    delta = self.parser.discarded_noise - previous_noise
                    previous_noise = self.parser.discarded_noise
                    self._event(
                        "noise_discarded",
                        "parse",
                        details={"bytes": delta},
                    )
                for frame in frames:
                    self._event(
                        "frame_received",
                        "parse",
                        details={"frame": frame},
                    )
        except BaseException as exc:
            self._event(
                "monitor_error",
                getattr(exc, "phase", "monitor"),
                message=str(exc),
            )
        finally:
            if serial_port is not None:
                try:
                    serial_port.close()
                except Exception as exc:
                    close_ok = False
                    self._event("monitor_error", "close", message=str(exc))
            if acquired:
                port_lock.release()
            self._event(
                "monitor_stopped",
                "monitor",
                details={"close_ok": close_ok},
            )


__all__ = [
    "DiagnosticFrame",
    "FRAME_START",
    "FrameParser",
    "PassiveMonitor",
    "crc16_xmodem",
]
