"""Tkinter application for safe, profile-aware LEQI region writes."""

from __future__ import annotations

import ctypes
import os
import queue
import re
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from PIL import Image, ImageTk

from .diagnostic_window import DiagnosticWindow
from .profiles import ProfileLoadResult, ScooterProfile, load_profiles
from .protocol import (
    SerialNumberError,
    SerialTransaction,
    SerialTransactionError,
    normalize_serial_number,
    prepare_region_change,
)
from .resources import asset_path, bundled_profiles_path, external_profiles_path
from .serial_transport import SerialEvent, SerialTransactionResult, write_transaction
from .theme import (
    AMBER,
    BRICK,
    BRICK_LIGHT,
    GRAVEL,
    INK,
    LINEN,
    MOSS,
    PAPER,
    RULE,
    SOIL,
    TOAST,
    WHITE,
    configure_theme,
)
from .ui_state import UiState, build_profile_label_map
from .version import APP_NAME, __version__
from .widgets import BorderPanel, GridHeader, ReadOnlyText, SectionTitle, labeled_value


REGIONS = ("DE", "EU", "US")
_COM_NUMBER = re.compile(r"^COM(\d+)$", re.IGNORECASE)


def enable_windows_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def display_serial(canonical: str) -> str:
    if len(canonical) != 19:
        return canonical or "—"
    return f"{canonical[:5]}/{canonical[5:]}"


def hex_line(data: bytes) -> str:
    return data.hex(" ").upper()


def _port_sort_key(device: str) -> tuple[int, int | str]:
    match = _COM_NUMBER.fullmatch(device)
    if match:
        return (0, int(match.group(1)))
    return (1, device.casefold())


def run_self_test() -> None:
    """Validate frozen imports and embedded resources without opening Tk."""

    import serial  # noqa: F401 - verifies the frozen runtime dependency
    from serial.tools import list_ports  # noqa: F401

    expected_ids = {
        "4litegen2_itde_with_turn_signal",
        "5_plus",
        "elite",
    }
    profile_result = load_profiles(bundled_profiles_path(), None)
    loaded_ids = {profile.id for profile in profile_result.profiles}
    if profile_result.warnings or not expected_ids.issubset(loaded_ids):
        raise RuntimeError(
            "Eingebettete Profile konnten im Selbsttest nicht vollständig geladen werden"
        )

    for image_name in ("jupoma-logo.png", "jupoma.ico"):
        with Image.open(asset_path(image_name)) as image:
            image.verify()
    for font_name in (
        "SpaceGrotesk-Medium.ttf",
        "SpaceGrotesk-SemiBold.ttf",
        "SpaceGrotesk-Bold.ttf",
        "InterTight-Regular.ttf",
        "InterTight-SemiBold.ttf",
        "InterTight-Bold.ttf",
        "JetBrainsMono-Regular.ttf",
        "JetBrainsMono-Bold.ttf",
    ):
        if not asset_path("fonts", font_name).is_file():
            raise RuntimeError(f"Eingebettete Schrift fehlt: {font_name}")


def run_ui_smoke_test() -> None:
    """Construct the complete Tk UI once without showing an interactive window."""

    enable_windows_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    try:
        RegionChangerApp(root)
        root.update_idletasks()
    finally:
        root.destroy()


class RegionChangerApp:
    POLL_INTERVAL_MS = 60

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.fonts = configure_theme(root)
        self.root.title(f"{APP_NAME} · {__version__}")
        self.root.geometry("1000x900")
        self.root.minsize(880, 720)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.app_queue: "queue.Queue[tuple[Any, ...]]" = queue.Queue()
        self.ui_state = UiState()
        self.transaction: SerialTransaction | None = None
        self.profile_result = self._load_profiles()
        self.profiles = self.profile_result.profiles
        self.profile_by_label = build_profile_label_map(self.profiles)
        self.port_by_label: dict[str, str] = {}
        self.region_buttons: dict[str, ttk.Button] = {}
        self.diagnostics: DiagnosticWindow | None = None
        self._write_thread: threading.Thread | None = None

        self.profile_var = tk.StringVar()
        self.port_var = tk.StringVar()
        self.serial_var = tk.StringVar()
        self.ack_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Bereit. Wähle Profil, Port und Seriennummer.")
        self.serial_hint_var = tk.StringVar(value="5 Ziffern + 14 Zeichen. Ein Slash nach Stelle 5 ist erlaubt.")
        self.preview_profile_var = tk.StringVar(value="—")
        self.preview_baud_var = tk.StringVar(value="—")
        self.preview_current_var = tk.StringVar(value="—")
        self.preview_target_var = tk.StringVar(value="—")
        self.preview_wire_var = tk.StringVar(value="—")

        self._load_logo()
        self._build_ui()
        self._bind_state()
        self.refresh_ports(initial=True)
        if self.profiles:
            self.profile_var.set(next(iter(self.profile_by_label), ""))
        self._recalculate()
        self.root.after(self.POLL_INTERVAL_MS, self._poll_queue)
        self.root.after(250, self._show_profile_warnings)

    def _load_profiles(self) -> ProfileLoadResult:
        bundled = bundled_profiles_path()
        external = external_profiles_path()
        try:
            same_directory = bundled.resolve() == external.resolve()
        except OSError:
            same_directory = False
        return load_profiles(bundled, None if same_directory else external)

    def _load_logo(self) -> None:
        path = asset_path("jupoma-logo.png")
        with Image.open(path) as source:
            image = source.convert("RGBA")
            image.thumbnail((108, 108), Image.Resampling.LANCZOS)
        self.logo_photo = ImageTk.PhotoImage(image)
        try:
            self.root.iconbitmap(default=str(asset_path("jupoma.ico")))
        except tk.TclError:
            self.root.iconphoto(True, self.logo_photo)

    def _build_ui(self) -> None:
        self._build_header()

        outer = tk.Frame(self.root, background=PAPER, padx=32, pady=24)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=3, uniform="main")
        outer.columnconfigure(1, weight=2, uniform="main")
        outer.rowconfigure(0, weight=1)

        left = tk.Frame(outer, background=PAPER)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        right = tk.Frame(outer, background=PAPER)
        right.grid(row=0, column=1, sticky="nsew", padx=(16, 0))

        self._build_configuration(left)
        self._build_preview(right)

        warning = BorderPanel(outer, background=BRICK_LIGHT)
        warning.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(22, 0))
        warning.body.configure(padx=16, pady=12)
        tk.Label(
            warning.body,
            text="SICHERHEIT",
            background=BRICK_LIGHT,
            foreground=BRICK,
            font=self.fonts["meta"],
        ).grid(row=0, column=0, sticky="nw", padx=(0, 16))
        tk.Label(
            warning.body,
            text=(
                "Das Dashboard arbeitet mit bis zu 21 V. Prüfe Modell, Pinbelegung und Adapter. "
                "Eine Regionsänderung kann Zulassung und Garantie betreffen."
            ),
            background=BRICK_LIGHT,
            foreground=SOIL,
            font=self.fonts["small"],
            justify=tk.LEFT,
            wraplength=760,
        ).grid(row=0, column=1, sticky="ew")
        warning.body.columnconfigure(1, weight=1)

        actions = tk.Frame(outer, background=PAPER)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        self.ack_check = ttk.Checkbutton(
            actions,
            text="Ich habe Modell, Verkabelung und Seriennummer geprüft.",
            variable=self.ack_var,
            command=self._on_ack_changed,
        )
        self.ack_check.pack(side=tk.LEFT)
        self.send_button = ttk.Button(
            actions,
            text="REGION SCHREIBEN",
            style="Primary.TButton",
            command=self._begin_write,
        )
        self.send_button.pack(side=tk.RIGHT)

        ttk.Separator(self.root).pack(fill=tk.X)
        status = tk.Frame(self.root, background=PAPER, padx=32, pady=12)
        status.pack(fill=tk.X)
        self.status_canvas = tk.Canvas(status, width=12, height=12, background=PAPER, highlightthickness=0)
        self.status_dot = self.status_canvas.create_oval(2, 2, 10, 10, fill=GRAVEL, outline="")
        self.status_canvas.pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(
            status,
            textvariable=self.status_var,
            background=PAPER,
            foreground=SOIL,
            font=self.fonts["small"],
        ).pack(side=tk.LEFT)
        tk.Label(
            status,
            text=f"VERSION {__version__}",
            background=PAPER,
            foreground=GRAVEL,
            font=self.fonts["meta"],
        ).pack(side=tk.RIGHT)

    def _build_header(self) -> None:
        header = GridHeader(self.root, height=146)
        header.pack(fill=tk.X)
        content = header.content
        content.columnconfigure(1, weight=1)
        tk.Label(content, image=self.logo_photo, background=LINEN).grid(row=0, column=0, rowspan=3, sticky="w")
        tk.Label(
            content,
            text="LEQI REGION CHANGER",
            background=LINEN,
            foreground=INK,
            font=self.fonts["display"],
        ).grid(row=0, column=1, sticky="sw", padx=(22, 0), pady=(8, 0))
        tk.Label(
            content,
            text="Dein Scooter. Dein Setup.",
            background=LINEN,
            foreground=SOIL,
            font=self.fonts["body_bold"],
        ).grid(row=1, column=1, sticky="nw", padx=(22, 0), pady=(3, 0))
        tk.Label(
            content,
            text="REGION · SERIENNUMMER · UART",
            background=LINEN,
            foreground=TOAST,
            font=self.fonts["meta"],
        ).grid(row=2, column=1, sticky="nw", padx=(22, 0), pady=(10, 0))

    def _build_configuration(self, parent: tk.Misc) -> None:
        SectionTitle(parent, "01", "Scooter und Verbindung").pack(fill=tk.X, pady=(0, 10))
        panel = BorderPanel(parent, background=PAPER)
        panel.pack(fill=tk.X)
        panel.body.configure(padx=16, pady=14)

        tk.Label(panel.body, text="SCOOTERPROFIL", background=PAPER, foreground=GRAVEL, font=self.fonts["meta"]).grid(row=0, column=0, sticky="w")
        self.profile_combo = ttk.Combobox(
            panel.body,
            textvariable=self.profile_var,
            values=list(self.profile_by_label),
            state="readonly",
        )
        self.profile_combo.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(5, 13))

        tk.Label(panel.body, text="COM-PORT", background=PAPER, foreground=GRAVEL, font=self.fonts["meta"]).grid(row=2, column=0, sticky="w")
        self.port_combo = ttk.Combobox(panel.body, textvariable=self.port_var, state="readonly")
        self.port_combo.grid(row=3, column=0, sticky="ew", pady=(5, 0))
        self.refresh_button = ttk.Button(panel.body, text="AKTUALISIEREN", command=self.refresh_ports)
        self.refresh_button.grid(row=3, column=1, padx=(8, 0), sticky="ew", pady=(5, 0))
        self.diagnostic_button = ttk.Button(panel.body, text="DIAGNOSE", command=self._open_diagnostics)
        self.diagnostic_button.grid(row=3, column=2, padx=(8, 0), sticky="ew", pady=(5, 0))
        panel.body.columnconfigure(0, weight=1)

        SectionTitle(parent, "02", "Vorhandene Seriennummer").pack(fill=tk.X, pady=(22, 10))
        serial_panel = BorderPanel(parent, background=PAPER)
        serial_panel.pack(fill=tk.X)
        serial_panel.body.configure(padx=16, pady=14)
        self.serial_entry = ttk.Entry(serial_panel.body, textvariable=self.serial_var)
        self.serial_entry.pack(fill=tk.X)
        tk.Label(
            serial_panel.body,
            textvariable=self.serial_hint_var,
            background=PAPER,
            foreground=GRAVEL,
            font=self.fonts["small"],
            justify=tk.LEFT,
            anchor="w",
        ).pack(fill=tk.X, pady=(7, 0))

        SectionTitle(parent, "03", "Zielregion").pack(fill=tk.X, pady=(22, 10))
        regions = tk.Frame(parent, background=RULE, padx=1, pady=1)
        regions.pack(fill=tk.X)
        inner = tk.Frame(regions, background=RULE)
        inner.pack(fill=tk.X)
        for column, region in enumerate(REGIONS):
            button = ttk.Button(
                inner,
                text=region,
                style="Region.TButton",
                command=lambda value=region: self._select_region(value),
            )
            button.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 1, 0))
            inner.columnconfigure(column, weight=1, uniform="regions")
            self.region_buttons[region] = button

    def _build_preview(self, parent: tk.Misc) -> None:
        SectionTitle(parent, "04", "Schreibvorgang").pack(fill=tk.X, pady=(0, 10))
        panel = BorderPanel(parent, background=LINEN)
        panel.pack(fill=tk.BOTH, expand=True)
        panel.body.configure(padx=18, pady=16)
        panel.body.columnconfigure(1, weight=1)

        labeled_value(panel.body, "Profil", self.preview_profile_var, row=0)
        labeled_value(panel.body, "Baudrate", self.preview_baud_var, row=1)
        labeled_value(panel.body, "Aktuell", self.preview_current_var, row=2)
        labeled_value(panel.body, "Ziel", self.preview_target_var, row=3)
        labeled_value(panel.body, "UART-SN", self.preview_wire_var, row=4)

        tk.Frame(panel.body, background=RULE, height=1).grid(row=5, column=0, columnspan=2, sticky="ew", pady=14)
        tk.Label(
            panel.body,
            text="DATENFRAME",
            background=LINEN,
            foreground=GRAVEL,
            font=self.fonts["meta"],
        ).grid(row=6, column=0, columnspan=2, sticky="w")
        self.data_frame_text = ReadOnlyText(panel.body, lines=5, background=LINEN)
        self.data_frame_text.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=(6, 12))
        tk.Label(
            panel.body,
            text="COMMIT / ENDBEFEHL",
            background=LINEN,
            foreground=GRAVEL,
            font=self.fonts["meta"],
        ).grid(row=8, column=0, columnspan=2, sticky="w")
        self.commit_frame_text = ReadOnlyText(panel.body, lines=2, background=LINEN)
        self.commit_frame_text.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(6, 12))
        tk.Label(
            panel.body,
            text=(
                "Die App prüft Übertragung und Byteanzahl. Der Scooter sendet kein "
                "belastbares Schreib-ACK. Prüfe die Region nach einem Neustart."
            ),
            background=LINEN,
            foreground=SOIL,
            font=self.fonts["small"],
            justify=tk.LEFT,
            wraplength=340,
        ).grid(row=10, column=0, columnspan=2, sticky="sw", pady=(8, 0))
        panel.body.rowconfigure(7, weight=1)

    def _bind_state(self) -> None:
        self.profile_var.trace_add("write", lambda *_: self._on_profile_changed())
        self.port_var.trace_add("write", lambda *_: self._on_port_changed())
        self.serial_var.trace_add("write", lambda *_: self._on_serial_changed())

    def current_profile(self) -> ScooterProfile | None:
        return self.profile_by_label.get(self.profile_var.get())

    def current_port(self) -> str:
        return self.port_by_label.get(self.port_var.get(), "")

    def refresh_ports(self, initial: bool = False) -> None:
        previous_port = self.current_port()
        try:
            from serial.tools import list_ports

            ports = sorted(list_ports.comports(), key=lambda item: _port_sort_key(item.device))
        except Exception as exc:
            ports = []
            if not initial:
                messagebox.showerror("COM-Ports nicht verfügbar", str(exc), parent=self.root)

        labels: list[str] = []
        mapping: dict[str, str] = {}
        for port in ports:
            description = str(getattr(port, "description", "") or "Serieller Port")
            label = f"{port.device} · {description}"
            labels.append(label)
            mapping[label] = port.device
        self.port_by_label = mapping
        self.port_combo.configure(values=labels)

        selected = next((label for label, device in mapping.items() if device == previous_port), "")
        if not selected and len(labels) == 1:
            selected = labels[0]
        self.port_var.set(selected)
        if not initial:
            self._set_status(
                f"{len(labels)} COM-Port{'s' if len(labels) != 1 else ''} gefunden.",
                "idle",
            )

    def _on_profile_changed(self) -> None:
        if self.diagnostics is not None and self.diagnostics.exists and not self.diagnostics.active:
            self.diagnostics.close()
            self.diagnostics = None
        self._reset_confirmation()
        self._recalculate()

    def _on_port_changed(self) -> None:
        self._reset_confirmation()
        self._recalculate()

    def _on_serial_changed(self) -> None:
        self._reset_confirmation()
        self._recalculate()

    def _on_ack_changed(self) -> None:
        self._refresh_ready_state()

    def _reset_confirmation(self) -> None:
        if self.ack_var.get():
            self.ack_var.set(False)

    def _select_region(self, region: str) -> None:
        profile = self.current_profile()
        if profile is None or profile.prefix_for(region) is None:
            return
        self.target_region = region
        self._reset_confirmation()
        self._recalculate()

    @property
    def target_region(self) -> str:
        return getattr(self, "_target_region", "")

    @target_region.setter
    def target_region(self, value: str) -> None:
        self._target_region = value

    def _recalculate(self) -> None:
        profile = self.current_profile()
        port = self.current_port()
        canonical = ""
        current_region = ""
        serial_valid = False

        if profile is None:
            self.preview_profile_var.set("—")
            self.preview_baud_var.set("—")
        else:
            self.preview_profile_var.set(profile.display_name)
            self.preview_baud_var.set(f"{profile.baudrate} · 8N1")

        raw_serial = self.serial_var.get()
        if profile is not None and raw_serial:
            try:
                canonical = normalize_serial_number(raw_serial)
                prefix = canonical[:5]
                current_region = next(
                    (region for region in REGIONS if profile.prefix_for(region) == prefix),
                    "",
                )
                if not current_region:
                    raise SerialTransactionError(
                        f"Präfix {prefix} gehört nicht zum gewählten Profil."
                    )
                serial_valid = True
                self.serial_hint_var.set(
                    f"Erkannt: Region {current_region}. Der 14-stellige Rest bleibt unverändert."
                )
            except (SerialNumberError, SerialTransactionError, ValueError) as exc:
                self.serial_hint_var.set(str(exc))
        elif not raw_serial:
            self.serial_hint_var.set("5 Ziffern + 14 Zeichen. Ein Slash nach Stelle 5 ist erlaubt.")

        self.preview_current_var.set(display_serial(canonical))
        if self.target_region and (
            profile is None
            or profile.prefix_for(self.target_region) is None
            or self.target_region == current_region
        ):
            self.target_region = ""

        self.transaction = None
        if profile is not None and serial_valid and self.target_region:
            try:
                self.transaction = prepare_region_change(profile, canonical, self.target_region)
            except (SerialNumberError, SerialTransactionError, ValueError) as exc:
                self.serial_hint_var.set(str(exc))

        self._update_regions(profile, current_region)
        if self.transaction is None:
            self.preview_target_var.set("—")
            self.preview_wire_var.set("—")
            self.data_frame_text.set_text("Zielregion wählen.")
            self.commit_frame_text.set_text("5A 01 97 01 00 EB B0")
        else:
            self.preview_target_var.set(display_serial(self.transaction.target_serial))
            self.preview_wire_var.set(self.transaction.wire_serial)
            self.data_frame_text.set_text(hex_line(self.transaction.data_frame))
            self.commit_frame_text.set_text(hex_line(self.transaction.commit_frame))

        self.ui_state = self.ui_state.updated(
            profile_selected=profile is not None,
            port_selected=bool(port),
            serial_valid=serial_valid,
            target_region_selected=self.transaction is not None,
            acknowledged=self.ack_var.get(),
        )
        self._refresh_ready_state()

    def _update_regions(self, profile: ScooterProfile | None, current_region: str) -> None:
        for region, button in self.region_buttons.items():
            button.state(["!selected", "!disabled"])
            if profile is None:
                button.configure(text=region)
                button.state(["disabled"])
                continue
            prefix = profile.prefix_for(region)
            if prefix is None:
                button.configure(text=f"{region}\nNICHT VERFÜGBAR")
                button.state(["disabled"])
            elif region == current_region:
                button.configure(text=f"{region} · AKTUELL\n{prefix}")
                button.state(["disabled"])
            else:
                button.configure(text=f"{region}\n{prefix}")
                if region == self.target_region:
                    button.state(["selected"])

    def _refresh_ready_state(self) -> None:
        diagnostics_active = bool(self.diagnostics and self.diagnostics.active)
        self.ui_state = self.ui_state.updated(
            acknowledged=self.ack_var.get(),
            diagnostics_active=diagnostics_active,
        )
        if self.ui_state.can_write:
            self.send_button.state(["!disabled"])
        else:
            self.send_button.state(["disabled"])

        locked = self.ui_state.busy or diagnostics_active
        self.profile_combo.configure(state="disabled" if locked else "readonly")
        self.port_combo.configure(state="disabled" if locked else "readonly")
        self.serial_entry.configure(state="disabled" if locked else "normal")
        self.refresh_button.state(["disabled"] if locked else ["!disabled"])
        self.diagnostic_button.state(["disabled"] if self.ui_state.busy else ["!disabled"])
        self.ack_check.state(["disabled"] if locked else ["!disabled"])

    def _begin_write(self) -> None:
        profile = self.current_profile()
        port = self.current_port()
        transaction = self.transaction
        if not self.ui_state.can_write or profile is None or not port or transaction is None:
            messagebox.showwarning("Noch nicht bereit", self.ui_state.block_reason(), parent=self.root)
            return

        confirmed = messagebox.askokcancel(
            "Region schreiben",
            (
                f"Profil: {profile.display_name}\n"
                f"Port: {port} · {profile.baudrate} Baud\n"
                f"Vorhanden: {display_serial(transaction.current_serial)}\n"
                f"Ziel: {display_serial(transaction.target_serial)} ({transaction.target_region})\n\n"
                "Die App sendet Datenframe und Commit genau einmal. Es gibt kein "
                "belastbares Schreib-ACK. Scooter danach vollständig neu starten."
            ),
            icon="warning",
            parent=self.root,
        )
        if not confirmed:
            return

        self.ui_state = self.ui_state.updated(busy=True)
        self._refresh_ready_state()
        self._set_status("COM-Port wird geöffnet …", "working")
        self._write_thread = threading.Thread(
            target=self._write_worker,
            args=(port, transaction),
            name="LEQI-region-write",
            daemon=True,
        )
        self._write_thread.start()

    def _write_worker(self, port: str, transaction: SerialTransaction) -> None:
        try:
            result = write_transaction(
                port,
                baudrate=transaction.baudrate,
                data_frame=transaction.data_frame,
                commit_frame=transaction.commit_frame,
                event_sink=lambda event: self.app_queue.put(("write_event", event)),
            )
        except BaseException as exc:
            self.app_queue.put(("write_error", exc))
        else:
            self.app_queue.put(("write_success", result, transaction))

    def _handle_write_event(self, event: SerialEvent) -> None:
        messages = {
            "opening": "COM-Port wird geöffnet …",
            "opened": "Port offen. Verbindung stabilisiert sich …",
            "completed": "Daten- und Commitframe übertragen.",
            "closed": "COM-Port geschlossen.",
        }
        if event.kind == "frame_written":
            label = "Datenframe" if event.phase == "data" else "Commitframe"
            self._set_status(f"{label} vollständig gesendet.", "working")
        elif event.kind in messages:
            self._set_status(messages[event.kind], "working")

    def _handle_write_success(self, result: SerialTransactionResult, transaction: SerialTransaction) -> None:
        self.ui_state = self.ui_state.updated(busy=False)
        self.ack_var.set(False)
        self._refresh_ready_state()
        self._set_status(
            "Übertragung abgeschlossen – Scooter neu starten und Region prüfen.",
            "ok",
        )
        messagebox.showinfo(
            "Übertragung abgeschlossen",
            (
                f"{result.data_bytes_written} Byte Datenframe und "
                f"{result.commit_bytes_written} Byte Commit wurden übertragen.\n\n"
                f"Zielregion: {transaction.target_region}\n"
                "Scooter vollständig ausschalten, neu starten und Region prüfen. "
                "Der Scooter bestätigt den Schreibvorgang nicht zuverlässig."
            ),
            parent=self.root,
        )

    def _handle_write_error(self, error: BaseException) -> None:
        self.ui_state = self.ui_state.updated(busy=False)
        self.ack_var.set(False)
        self._refresh_ready_state()
        self._set_status("Übertragung abgebrochen. Es wurde nicht automatisch wiederholt.", "error")
        messagebox.showerror(
            "Übertragung fehlgeschlagen",
            f"{error}\n\nEs wurde kein automatischer Wiederholungsversuch ausgeführt.",
            parent=self.root,
        )

    def _open_diagnostics(self) -> None:
        profile = self.current_profile()
        port = self.current_port()
        if self.ui_state.busy:
            messagebox.showwarning("Port belegt", "Eine Übertragung läuft.", parent=self.root)
            return
        if profile is None or not port:
            messagebox.showwarning(
                "Diagnose nicht bereit",
                "Wähle zuerst ein Scooterprofil und einen COM-Port.",
                parent=self.root,
            )
            return
        if self.diagnostics is not None:
            if self.diagnostics.exists:
                self.diagnostics.window.lift()
                return
            if self.diagnostics.active:
                messagebox.showerror(
                    "Portfreigabe unbestätigt",
                    "Schreiben bleibt aus Sicherheitsgründen gesperrt. Starte die App neu.",
                    parent=self.root,
                )
                return
        self.diagnostics = DiagnosticWindow(
            self.root,
            port=port,
            baudrate=profile.baudrate,
            profile_name=profile.display_name,
            app_queue=self.app_queue,
            on_active_changed=self._on_diagnostics_active,
        )

    def _on_diagnostics_active(self, active: bool) -> None:
        self.ui_state = self.ui_state.updated(diagnostics_active=active)
        self._refresh_ready_state()
        if active:
            self._set_status("Diagnose belegt den COM-Port exklusiv.", "working")
        elif not self.ui_state.busy:
            self._set_status("Diagnose beendet. Port ist wieder frei.", "idle")

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self.app_queue.get_nowait()
                kind = item[0]
                if kind == "write_event":
                    self._handle_write_event(item[1])
                elif kind == "write_success":
                    self._handle_write_success(item[1], item[2])
                elif kind == "write_error":
                    self._handle_write_error(item[1])
                elif kind == "diagnostic":
                    window, event = item[1], item[2]
                    if isinstance(window, DiagnosticWindow):
                        window.handle_event(event)
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(self.POLL_INTERVAL_MS, self._poll_queue)

    def _set_status(self, message: str, state: str) -> None:
        color = {"working": AMBER, "ok": MOSS, "error": BRICK}.get(state, GRAVEL)
        self.status_var.set(message)
        self.status_canvas.itemconfigure(self.status_dot, fill=color)

    def _show_profile_warnings(self) -> None:
        if self.profile_result.warnings:
            messagebox.showwarning(
                "Profilhinweise",
                "Einige externe Profildateien wurden nicht geladen:\n\n"
                + "\n".join(self.profile_result.warnings),
                parent=self.root,
            )

    def _on_close(self) -> None:
        if self.ui_state.busy:
            messagebox.showwarning(
                "Übertragung läuft",
                "Warte, bis der COM-Port geschlossen wurde.",
                parent=self.root,
            )
            return
        if self.diagnostics is not None and self.diagnostics.exists:
            self.diagnostics.close()
        self.root.destroy()


def main() -> None:
    if "--self-test" in sys.argv:
        run_self_test()
        return
    if "--ui-smoke-test" in sys.argv:
        run_ui_smoke_test()
        return
    enable_windows_dpi_awareness()
    root = tk.Tk()
    try:
        RegionChangerApp(root)
    except Exception as exc:
        root.withdraw()
        messagebox.showerror(
            "LEQI Region Changer konnte nicht starten",
            str(exc),
            parent=root,
        )
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
