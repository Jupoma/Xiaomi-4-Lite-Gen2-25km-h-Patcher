"""Thread-safe, UI-agnostic serial write transactions.

The transport deliberately knows nothing about scooter profiles or Tk.  Callers
pass already-built protocol frames and receive progress through an event sink.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import os
import threading
import time
from typing import Any, Callable, Mapping, Protocol

from .i18n import translate as tr

try:  # pyserial is an optional runtime dependency.
    import serial as _pyserial  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depends on the host installation
    _pyserial = None


OPEN_SETTLE_SECONDS = 0.100
INTER_FRAME_SECONDS = 0.100
PORT_LOCK_TIMEOUT_SECONDS = 0.250
SERIAL_WRITE_TIMEOUT_SECONDS = 2.000


class EventQueue(Protocol):
    """Small structural type accepted as an alternative to a callback."""

    def put(self, item: object) -> object: ...


@dataclass(frozen=True)
class SerialEvent:
    """A transport event suitable for callbacks or ``queue.Queue`` objects."""

    kind: str
    port: str
    phase: str
    message: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)


EventSink = Callable[[SerialEvent], object] | EventQueue | None
SerialFactory = Callable[..., Any]
SleepFunction = Callable[[float], object]


class SerialTransportError(RuntimeError):
    """Base error for a failed serial transaction."""

    def __init__(self, message: str, *, port: str, phase: str) -> None:
        super().__init__(message)
        self.port = port
        self.phase = phase


class SerialDependencyError(SerialTransportError):
    """Raised when the default transport is used without pyserial."""


class IncompleteWriteError(SerialTransportError):
    """Raised when ``Serial.write`` accepts fewer bytes than requested."""

    def __init__(
        self,
        *,
        port: str,
        phase: str,
        expected: int,
        written: int,
    ) -> None:
        super().__init__(
            tr("incomplete_write", phase=phase, written=written, expected=expected),
            port=port,
            phase=phase,
        )
        self.expected = expected
        self.written = written


@dataclass(frozen=True)
class SerialTransactionResult:
    """Successful write counts for one data/commit transaction."""

    port: str
    baudrate: int
    data_bytes_written: int
    commit_bytes_written: int


_lock_registry_guard = threading.Lock()
_port_locks: dict[str, threading.Lock] = {}


def _normalise_port_key(port: str) -> str:
    value = str(port).strip()
    if not value:
        raise ValueError(tr("port_empty"))
    return os.path.normcase(value)


def get_port_lock(port: str) -> threading.Lock:
    """Return the process-wide exclusive lock for ``port``.

    Diagnostics and write transactions intentionally share this registry so a
    monitor can never consume bytes while a write transaction owns the port.
    """

    key = _normalise_port_key(port)
    with _lock_registry_guard:
        lock = _port_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _port_locks[key] = lock
        return lock


@contextmanager
def _acquire_port_lock(lock: threading.Lock, port: str):
    acquired = lock.acquire(timeout=PORT_LOCK_TIMEOUT_SECONDS)
    if not acquired:
        raise SerialTransportError(
            tr("port_locked"),
            port=port,
            phase="lock",
        )
    try:
        yield
    finally:
        lock.release()


def emit_event(sink: EventSink, event: SerialEvent) -> None:
    """Deliver an event without importing or calling any GUI framework."""

    if sink is None:
        return
    if callable(sink):
        sink(event)
        return
    put = getattr(sink, "put", None)
    if callable(put):
        put(event)
        return
    raise TypeError(tr("event_sink_invalid"))


def resolve_serial_factory(serial_factory: SerialFactory | None) -> SerialFactory:
    """Resolve an injected factory, importing pyserial only when required."""

    if serial_factory is not None:
        return serial_factory
    if _pyserial is None:
        raise SerialDependencyError(
            tr("pyserial_missing"),
            port="",
            phase="dependency",
        )
    return _pyserial.Serial


def _write_and_flush(
    serial_port: Any,
    frame: bytes,
    *,
    port: str,
    phase: str,
) -> int:
    try:
        written_raw = serial_port.write(frame)
    except Exception as exc:
        raise SerialTransportError(
            tr("serial_write_failed", phase=phase, error=exc),
            port=port,
            phase=phase,
        ) from exc

    written = written_raw if isinstance(written_raw, int) else 0
    if written != len(frame):
        raise IncompleteWriteError(
            port=port,
            phase=phase,
            expected=len(frame),
            written=written,
        )

    try:
        serial_port.flush()
    except Exception as exc:
        raise SerialTransportError(
            tr("serial_flush_failed", phase=phase, error=exc),
            port=port,
            phase=f"{phase}_flush",
        ) from exc
    return written


def write_transaction(
    port: str,
    *,
    baudrate: int,
    data_frame: bytes | bytearray | memoryview,
    commit_frame: bytes | bytearray | memoryview | None,
    serial_factory: SerialFactory | None = None,
    sleep: SleepFunction = time.sleep,
    event_sink: EventSink = None,
) -> SerialTransactionResult:
    """Write exactly one data frame and, if supplied, one commit frame.

    The port is configured as 8N1.  It settles for exactly 100 ms after opening;
    data and commit writes are separated by exactly another 100 ms.  Writes are
    attempted once only, checked for their complete byte count, flushed, and the
    port is closed on every success or failure path.
    """

    port_name = str(port).strip()
    _normalise_port_key(port_name)
    if isinstance(baudrate, bool) or not isinstance(baudrate, int) or baudrate <= 0:
        raise ValueError(tr("baud_positive"))

    data = bytes(data_frame)
    commit = None if commit_frame is None else bytes(commit_frame)
    if not data:
        raise ValueError(tr("data_frame_empty"))
    if commit_frame is not None and not commit:
        raise ValueError(tr("commit_frame_empty"))

    factory = resolve_serial_factory(serial_factory)
    lock = get_port_lock(port_name)
    serial_port: Any | None = None
    pending_error: BaseException | None = None
    result: SerialTransactionResult | None = None

    with _acquire_port_lock(lock, port_name):
        try:
            emit_event(
                event_sink,
                SerialEvent("opening", port_name, "open", details={"baudrate": baudrate}),
            )
            try:
                serial_port = factory(
                    port=port_name,
                    baudrate=baudrate,
                    bytesize=8,
                    parity="N",
                    stopbits=1,
                    write_timeout=SERIAL_WRITE_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                raise SerialTransportError(
                    tr("port_open_failed", error=exc),
                    port=port_name,
                    phase="open",
                ) from exc

            emit_event(event_sink, SerialEvent("opened", port_name, "open"))
            sleep(OPEN_SETTLE_SECONDS)

            data_written = _write_and_flush(
                serial_port,
                data,
                port=port_name,
                phase="data",
            )
            emit_event(
                event_sink,
                SerialEvent(
                    "frame_written",
                    port_name,
                    "data",
                    details={"bytes": data_written},
                ),
            )

            commit_written = 0
            if commit is not None:
                sleep(INTER_FRAME_SECONDS)
                commit_written = _write_and_flush(
                    serial_port,
                    commit,
                    port=port_name,
                    phase="commit",
                )
                emit_event(
                    event_sink,
                    SerialEvent(
                        "frame_written",
                        port_name,
                        "commit",
                        details={"bytes": commit_written},
                    ),
                )

            result = SerialTransactionResult(
                port=port_name,
                baudrate=baudrate,
                data_bytes_written=data_written,
                commit_bytes_written=commit_written,
            )
            emit_event(event_sink, SerialEvent("completed", port_name, "transaction"))
        except BaseException as exc:  # close must also run for cancellation paths
            pending_error = exc
            emit_event(
                event_sink,
                SerialEvent(
                    "error",
                    port_name,
                    getattr(exc, "phase", "transaction"),
                    message=str(exc),
                ),
            )
        finally:
            if serial_port is not None:
                try:
                    serial_port.close()
                except Exception as exc:
                    close_error = SerialTransportError(
                        tr("port_close_failed", error=exc),
                        port=port_name,
                        phase="close",
                    )
                    emit_event(
                        event_sink,
                        SerialEvent("error", port_name, "close", message=str(close_error)),
                    )
                    if pending_error is None:
                        pending_error = close_error
                else:
                    emit_event(event_sink, SerialEvent("closed", port_name, "close"))

    if pending_error is not None:
        raise pending_error
    assert result is not None
    return result


__all__ = [
    "EventSink",
    "IncompleteWriteError",
    "INTER_FRAME_SECONDS",
    "OPEN_SETTLE_SECONDS",
    "PORT_LOCK_TIMEOUT_SECONDS",
    "SERIAL_WRITE_TIMEOUT_SECONDS",
    "SerialDependencyError",
    "SerialEvent",
    "SerialTransactionResult",
    "SerialTransportError",
    "emit_event",
    "get_port_lock",
    "resolve_serial_factory",
    "write_transaction",
]
