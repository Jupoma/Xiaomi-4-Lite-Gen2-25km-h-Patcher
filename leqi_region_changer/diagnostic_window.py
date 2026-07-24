"""Tk presentation for the read-only serial diagnostics worker."""

from __future__ import annotations

from datetime import datetime
import queue
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from .diagnostics import DiagnosticFrame, PassiveMonitor
from .i18n import translate as tr
from .serial_transport import SerialEvent
from .theme import AMBER, BRICK, GRAVEL, INK, LINEN, MOSS, PAPER, RULE, SOIL, WHITE
from .widgets import SectionTitle, set_text_widget_colors


class DiagnosticWindow:
    """Read-only monitor. All worker events enter through the application queue."""

    def __init__(
        self,
        parent: tk.Tk,
        *,
        port: str,
        baudrate: int,
        profile_name: str,
        app_queue: "queue.Queue[tuple]",
        on_active_changed: Callable[[bool], None],
    ) -> None:
        self.parent = parent
        self.port = port
        self.baudrate = baudrate
        self.profile_name = profile_name
        self.app_queue = app_queue
        self.on_active_changed = on_active_changed
        self.monitor: PassiveMonitor | None = None
        self._active = False
        self._closing = False
        self._terminal_error = ""
        self._port_release_uncertain = False

        self.window = tk.Toplevel(parent)
        self.window.title(f"{tr('diag_title')} · {port} · LEQI Region Changer")
        self.window.geometry("920x590")
        self.window.minsize(760, 460)
        self.window.configure(background=PAPER)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.status_var = tk.StringVar(value=tr("diag_disconnected"))
        self.counter_var = tk.StringVar(value=tr("diag_counter", frames=0, errors=0))
        self._status_translation: tuple[str, dict[str, object]] = ("diag_disconnected", {})
        self._frames = 0
        self._crc_errors = 0
        self._build()

    @property
    def exists(self) -> bool:
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    @property
    def active(self) -> bool:
        return self._active

    def _build(self) -> None:
        header = tk.Frame(self.window, background=INK, padx=24, pady=18)
        header.pack(fill=tk.X)
        self.diag_label = tk.Label(
            header,
            text=tr("diag_label"),
            background=INK,
            foreground=AMBER,
            font=("JetBrains Mono", 8, "bold"),
        )
        self.diag_label.grid(row=0, column=0, sticky="w")
        self.monitor_label = tk.Label(
            header,
            text=tr("diag_monitor"),
            background=INK,
            foreground=PAPER,
            font=("Space Grotesk", 18, "bold"),
        )
        self.monitor_label.grid(row=1, column=0, sticky="w", pady=(4, 0))
        tk.Label(
            header,
            text=f"{self.profile_name} · {self.port} · {self.baudrate} Baud · 8N1",
            background=INK,
            foreground=LINEN,
            font=("JetBrains Mono", 9),
        ).grid(row=2, column=0, sticky="w", pady=(5, 0))
        header.columnconfigure(0, weight=1)

        controls = tk.Frame(self.window, background=PAPER, padx=24, pady=16)
        controls.pack(fill=tk.X)
        self.start_button = ttk.Button(controls, text=tr("diag_start"), command=self.toggle)
        self.start_button.pack(side=tk.LEFT)
        self.clear_button = ttk.Button(controls, text=tr("diag_clear"), command=self.clear)
        self.clear_button.pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(
            controls,
            textvariable=self.counter_var,
            background=PAPER,
            foreground=GRAVEL,
            font=("JetBrains Mono", 8),
        ).pack(side=tk.RIGHT)

        body = tk.Frame(self.window, background=PAPER, padx=24)
        body.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        self.frames_title = SectionTitle(body, "01", tr("diag_section_frames"))
        self.frames_title.pack(fill=tk.X, pady=(0, 10))
        log_border = tk.Frame(body, background=RULE, padx=1, pady=1)
        log_border.pack(fill=tk.BOTH, expand=True)
        self.log = tk.Text(log_border, wrap=tk.NONE, font=("JetBrains Mono", 9), padx=12, pady=12)
        set_text_widget_colors(self.log)
        self.log.configure(highlightthickness=0, state=tk.DISABLED)
        scroll_y = ttk.Scrollbar(log_border, orient=tk.VERTICAL, command=self.log.yview)
        scroll_x = ttk.Scrollbar(log_border, orient=tk.HORIZONTAL, command=self.log.xview)
        self.log.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        log_border.columnconfigure(0, weight=1)
        log_border.rowconfigure(0, weight=1)
        self.log.tag_configure("ok", foreground=MOSS)
        self.log.tag_configure("error", foreground=BRICK)
        self.log.tag_configure("meta", foreground=GRAVEL)
        self.log.tag_configure("frame", foreground=SOIL)

        status = tk.Frame(self.window, background=LINEN, padx=24, pady=12)
        status.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_dot = tk.Canvas(status, width=12, height=12, background=LINEN, highlightthickness=0)
        self._dot = self.status_dot.create_oval(2, 2, 10, 10, fill=GRAVEL, outline="")
        self.status_dot.pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(
            status,
            textvariable=self.status_var,
            background=LINEN,
            foreground=INK,
            font=("Inter Tight", 9),
        ).pack(side=tk.LEFT)

    def set_language(self) -> None:
        self.window.title(f"{tr('diag_title')} · {self.port} · LEQI Region Changer")
        self.diag_label.configure(text=tr("diag_label"))
        self.monitor_label.configure(text=tr("diag_monitor"))
        self.clear_button.configure(text=tr("diag_clear"))
        self.frames_title.set_title(tr("diag_section_frames"))
        self.start_button.configure(text=tr("diag_stop" if self._active else "diag_start"))
        key, values = self._status_translation
        self.status_var.set(tr(key, **values))
        self._update_counter()

    def _set_status_key(self, key: str, **values: object) -> None:
        self._status_translation = (key, dict(values))
        self.status_var.set(tr(key, **values))

    def _set_active(self, active: bool, status_key: str, **values: object) -> None:
        self._active = active
        self._set_status_key(status_key, **values)
        self.status_dot.itemconfigure(self._dot, fill=MOSS if active else GRAVEL)
        self.start_button.configure(text=tr("diag_stop" if active else "diag_start"))
        self.on_active_changed(active)

    def toggle(self) -> None:
        if self._active:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        if self._active:
            return
        try:
            self._terminal_error = ""
            self._port_release_uncertain = False
            self.monitor = PassiveMonitor(
                self.port,
                baudrate=self.baudrate,
                event_sink=lambda event: self.app_queue.put(("diagnostic", self, event)),
            )
            self.monitor.start()
            self._set_active(True, "diag_opening")
            self._append(tr("diag_requested"), "meta")
        except Exception as exc:
            self.monitor = None
            self._set_active(False, "diag_start_failed")
            messagebox.showerror(tr("diag_not_started"), str(exc), parent=self.window)

    def stop(self) -> None:
        monitor = self.monitor
        if monitor is not None:
            monitor.stop()
        self._set_status_key("diag_stopping")
        self.start_button.configure(state=tk.DISABLED)

    def handle_event(self, event: SerialEvent) -> None:
        if not self.exists:
            return
        if event.kind == "monitor_started":
            self._set_active(True, "diag_receiving", port=self.port, baudrate=self.baudrate)
            self._append(tr("diag_port_open"), "ok")
        elif event.kind == "monitor_waiting":
            self._set_status_key("diag_waiting")
        elif event.kind == "frame_received":
            frame = event.details.get("frame")
            if isinstance(frame, DiagnosticFrame):
                self._append_frame(frame)
        elif event.kind == "noise_discarded":
            count = event.details.get("bytes", 0)
            self._append(tr("diag_noise", count=count), "meta")
        elif event.kind == "monitor_error":
            self._terminal_error = event.message or tr("diag_unknown_error")
            self._append(event.message or tr("diag_unknown_error"), "error")
            self._set_status_key("diag_error")
        elif event.kind == "monitor_stopped":
            self.monitor = None
            self.start_button.configure(state=tk.NORMAL)
            close_ok = bool(event.details.get("close_ok", True))
            if close_ok:
                if self._terminal_error:
                    self._set_active(False, "diag_closed_after_error")
                    self._append(tr("diag_port_closed_after_error"), "meta")
                else:
                    self._set_active(False, "diag_disconnected")
                    self._append(tr("diag_port_closed"), "meta")
                if self._closing and self.exists:
                    self.window.destroy()
            else:
                self._port_release_uncertain = True
                self._active = True
                self.on_active_changed(True)
                self._set_status_key("diag_release_uncertain")
                self.start_button.configure(state=tk.DISABLED)
                self._append(tr("diag_release_uncertain_log"), "error")

    def _append_frame(self, frame: DiagnosticFrame) -> None:
        self._frames += 1
        if not frame.crc_ok:
            self._crc_errors += 1
        self._update_counter()
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        verdict = (
            tr("diag_crc_ok")
            if frame.crc_ok
            else tr(
                "diag_crc_error",
                received=frame.crc_received,
                computed=frame.crc_computed,
            )
        )
        tag = "ok" if frame.crc_ok else "error"
        self._append(
            tr(
                "diag_frame_meta",
                timestamp=timestamp,
                verdict=verdict,
                command=frame.command,
                subcommand=frame.subcommand,
                length=frame.payload_length,
            ),
            tag,
        )
        self._append("  " + frame.data.hex(" ").upper(), "frame")

    def _append(self, text: str, tag: str = "frame") -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n", tag)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def clear(self) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)
        self._frames = 0
        self._crc_errors = 0
        self._update_counter()

    def _update_counter(self) -> None:
        self.counter_var.set(
            tr("diag_counter", frames=self._frames, errors=self._crc_errors)
        )

    def close(self) -> None:
        if self._port_release_uncertain:
            if self.exists:
                self.window.destroy()
            return
        monitor = self.monitor
        if monitor is not None and monitor.is_running:
            self._closing = True
            monitor.stop()
            self._set_status_key("diag_stopping_safe")
            self.start_button.configure(state=tk.DISABLED)
            return
        self.monitor = None
        self._set_active(False, "diag_disconnected")
        if self.exists:
            self.window.destroy()
