"""Tk presentation for the read-only serial diagnostics worker."""

from __future__ import annotations

from datetime import datetime
import queue
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from .diagnostics import DiagnosticFrame, PassiveMonitor
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
        self.window.title(f"Diagnose · {port} · LEQI Region Changer")
        self.window.geometry("920x590")
        self.window.minsize(760, 460)
        self.window.configure(background=PAPER)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.status_var = tk.StringVar(value="Nicht verbunden")
        self.counter_var = tk.StringVar(value="0 Frames · 0 CRC-Fehler")
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
        tk.Label(
            header,
            text="DIAGNOSE",
            background=INK,
            foreground=AMBER,
            font=("JetBrains Mono", 8, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="UART-Monitor",
            background=INK,
            foreground=PAPER,
            font=("Space Grotesk", 18, "bold"),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
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
        self.start_button = ttk.Button(controls, text="MONITOR STARTEN", command=self.toggle)
        self.start_button.pack(side=tk.LEFT)
        ttk.Button(controls, text="PROTOKOLL LEEREN", command=self.clear).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(
            controls,
            textvariable=self.counter_var,
            background=PAPER,
            foreground=GRAVEL,
            font=("JetBrains Mono", 8),
        ).pack(side=tk.RIGHT)

        body = tk.Frame(self.window, background=PAPER, padx=24, pady=(0, 20))
        body.pack(fill=tk.BOTH, expand=True)
        SectionTitle(body, "01", "Empfangene Frames").pack(fill=tk.X, pady=(0, 10))
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

    def _set_active(self, active: bool, text: str) -> None:
        self._active = active
        self.status_var.set(text)
        self.status_dot.itemconfigure(self._dot, fill=MOSS if active else GRAVEL)
        self.start_button.configure(text="MONITOR STOPPEN" if active else "MONITOR STARTEN")
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
            self._set_active(True, "Verbindung wird geöffnet …")
            self._append("Monitor angefordert. Der Port ist währenddessen exklusiv belegt.", "meta")
        except Exception as exc:
            self.monitor = None
            self._set_active(False, "Start fehlgeschlagen")
            messagebox.showerror("Diagnose nicht gestartet", str(exc), parent=self.window)

    def stop(self) -> None:
        monitor = self.monitor
        if monitor is not None:
            monitor.stop()
        self.status_var.set("Verbindung wird beendet …")
        self.start_button.configure(state=tk.DISABLED)

    def handle_event(self, event: SerialEvent) -> None:
        if not self.exists:
            return
        if event.kind == "monitor_started":
            self._set_active(True, f"Empfang aktiv · {self.port} · {self.baudrate} Baud")
            self._append("Port geöffnet. Empfang läuft.", "ok")
        elif event.kind == "monitor_waiting":
            self.status_var.set("Warte auf exklusiven Portzugriff …")
        elif event.kind == "frame_received":
            frame = event.details.get("frame")
            if isinstance(frame, DiagnosticFrame):
                self._append_frame(frame)
        elif event.kind == "noise_discarded":
            count = event.details.get("bytes", 0)
            self._append(f"{count} Byte außerhalb eines 5A-Frames verworfen.", "meta")
        elif event.kind == "monitor_error":
            self._terminal_error = event.message or "Unbekannter Diagnosefehler."
            self._append(event.message or "Unbekannter Diagnosefehler.", "error")
            self.status_var.set("Diagnosefehler")
        elif event.kind == "monitor_stopped":
            self.monitor = None
            self.start_button.configure(state=tk.NORMAL)
            close_ok = bool(event.details.get("close_ok", True))
            if close_ok:
                if self._terminal_error:
                    self._set_active(False, "Diagnose beendet – Port geschlossen")
                    self._append("Port trotz Diagnosefehler geschlossen.", "meta")
                else:
                    self._set_active(False, "Nicht verbunden")
                    self._append("Port geschlossen.", "meta")
                if self._closing and self.exists:
                    self.window.destroy()
            else:
                self._port_release_uncertain = True
                self._active = True
                self.on_active_changed(True)
                self.status_var.set("Portfreigabe unbestätigt – App neu starten")
                self.start_button.configure(state=tk.DISABLED)
                self._append(
                    "Portfreigabe konnte nicht bestätigt werden. Schreiben bleibt bis zum App-Neustart gesperrt.",
                    "error",
                )

    def _append_frame(self, frame: DiagnosticFrame) -> None:
        self._frames += 1
        if not frame.crc_ok:
            self._crc_errors += 1
        self.counter_var.set(f"{self._frames} Frames · {self._crc_errors} CRC-Fehler")
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        verdict = "CRC OK" if frame.crc_ok else f"CRC FEHLER {frame.crc_received:04X}/{frame.crc_computed:04X}"
        tag = "ok" if frame.crc_ok else "error"
        self._append(
            f"{timestamp}  {verdict}  CMD {frame.command:02X}  SUB {frame.subcommand:02X}  LEN {frame.payload_length}",
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
        self.counter_var.set("0 Frames · 0 CRC-Fehler")

    def close(self) -> None:
        if self._port_release_uncertain:
            if self.exists:
                self.window.destroy()
            return
        monitor = self.monitor
        if monitor is not None and monitor.is_running:
            self._closing = True
            monitor.stop()
            self.status_var.set("Verbindung wird sicher beendet …")
            self.start_button.configure(state=tk.DISABLED)
            return
        self.monitor = None
        self._set_active(False, "Nicht verbunden")
        if self.exists:
            self.window.destroy()
