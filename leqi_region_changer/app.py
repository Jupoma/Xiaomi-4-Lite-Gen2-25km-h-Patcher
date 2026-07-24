"""Tkinter application for safe, profile-aware LEQI region writes."""

from __future__ import annotations

import ctypes
import os
import queue
import re
import sys
import threading
import tkinter as tk
import traceback
from tkinter import messagebox, ttk
from typing import Any, Callable

from PIL import Image, ImageTk

from .diagnostic_window import DiagnosticWindow
from .i18n import (
    LANGUAGE_LABELS,
    SUPPORTED_LANGUAGES,
    language_from_label,
    set_language,
    translate as tr,
)
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
from .settings import load_language, save_language
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
        "6_lite",
        "6",
        "elite",
    }
    profile_result = load_profiles(bundled_profiles_path(), None)
    loaded_ids = {profile.id for profile in profile_result.profiles}
    if profile_result.warnings or not expected_ids.issubset(loaded_ids):
        raise RuntimeError(tr("self_test_profiles"))

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
            raise RuntimeError(tr("self_test_font", font=font_name))


def run_ui_smoke_test() -> None:
    """Construct and relocalize the complete Tk UI without showing it."""

    enable_windows_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    diagnostics: DiagnosticWindow | None = None
    try:
        app = RegionChangerApp(root)
        original_language = app.language
        diagnostics = DiagnosticWindow(
            root,
            port="COM-SMOKE",
            baudrate=115200,
            profile_name="UI Smoke Profile",
            app_queue=app.app_queue,
            on_active_changed=lambda _active: None,
        )
        app.diagnostics = diagnostics
        diagnostics.window.withdraw()
        language_order = tuple(
            language for language in SUPPORTED_LANGUAGES if language != original_language
        ) + (original_language,)
        for language in language_order:
            app.ack_var.set(True)
            app._change_language(language, persist=False)
            root.update_idletasks()
            if app.ack_var.get():
                raise RuntimeError("Language change did not reset the safety confirmation")
            if app.safety_text_label.cget("text") != tr("safety_text"):
                raise RuntimeError("Safety copy did not update during UI smoke test")
            if diagnostics.monitor_label.cget("text") != tr("diag_monitor"):
                raise RuntimeError("Diagnostics did not update during UI smoke test")

        profile = app.current_profile()
        if profile is None:
            raise RuntimeError("No profile available during UI smoke test")
        current_region = next(
            region for region in REGIONS if profile.prefix_for(region) is not None
        )
        current_prefix = profile.prefix_for(current_region)
        if current_prefix is None:
            raise RuntimeError("Current region has no prefix during UI smoke test")
        app.serial_var.set(f"{current_prefix}00000000JUPOMA")
        app.target_region = current_region
        app._recalculate()
        current_button = app.region_buttons[current_region]
        if current_button.instate(["disabled"]) or not current_button.instate(["selected"]):
            raise RuntimeError("Current region is not selectable during UI smoke test")
        for region, button in app.region_buttons.items():
            expected_disabled = profile.prefix_for(region) is None
            if button.instate(["disabled"]) != expected_disabled:
                raise RuntimeError(f"Unexpected availability for region {region}")
    finally:
        if diagnostics is not None and diagnostics.exists:
            diagnostics.window.destroy()
        root.destroy()


def run_command_line_test(test: Callable[[], None]) -> None:
    """Run a hidden executable check with an explicit process exit code."""

    try:
        test()
    except Exception:
        if sys.stderr is not None:
            traceback.print_exc()
        raise SystemExit(1)
    raise SystemExit(0)


class RegionChangerApp:
    POLL_INTERVAL_MS = 60

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.language = set_language(load_language())
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
        self.language_var = tk.StringVar(value=LANGUAGE_LABELS[self.language])
        self.ack_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value=tr("startup_status"))
        self._status_translation: tuple[str, dict[str, object]] = ("startup_status", {})
        self._status_state = "idle"
        self.serial_hint_var = tk.StringVar(value=tr("serial_hint_empty"))
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
        self._apply_language()
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
        self.safety_label = tk.Label(
            warning.body,
            text=tr("safety"),
            background=BRICK_LIGHT,
            foreground=BRICK,
            font=self.fonts["meta"],
        )
        self.safety_label.grid(row=0, column=0, sticky="nw", padx=(0, 16))
        self.safety_text_label = tk.Label(
            warning.body,
            text=tr("safety_text"),
            background=BRICK_LIGHT,
            foreground=SOIL,
            font=self.fonts["small"],
            justify=tk.LEFT,
            wraplength=760,
        )
        self.safety_text_label.grid(row=0, column=1, sticky="ew")
        warning.body.columnconfigure(1, weight=1)

        actions = tk.Frame(outer, background=PAPER)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        self.ack_check = ttk.Checkbutton(
            actions,
            text=tr("acknowledge"),
            variable=self.ack_var,
            command=self._on_ack_changed,
        )
        self.ack_check.pack(side=tk.LEFT)
        self.send_button = ttk.Button(
            actions,
            text=tr("write_region"),
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
        self.slogan_label = tk.Label(
            content,
            text=tr("slogan"),
            background=LINEN,
            foreground=SOIL,
            font=self.fonts["body_bold"],
        )
        self.slogan_label.grid(row=1, column=1, sticky="nw", padx=(22, 0), pady=(3, 0))
        self.header_meta_label = tk.Label(
            content,
            text=tr("header_meta"),
            background=LINEN,
            foreground=TOAST,
            font=self.fonts["meta"],
        )
        self.header_meta_label.grid(row=2, column=1, sticky="nw", padx=(22, 0), pady=(10, 0))
        self.language_label = tk.Label(
            content,
            text=tr("language"),
            background=LINEN,
            foreground=GRAVEL,
            font=self.fonts["meta"],
        )
        self.language_label.grid(row=0, column=2, sticky="se", padx=(24, 0), pady=(10, 3))
        self.language_combo = ttk.Combobox(
            content,
            textvariable=self.language_var,
            values=list(LANGUAGE_LABELS.values()),
            state="readonly",
            width=12,
        )
        self.language_combo.grid(row=1, column=2, rowspan=2, sticky="ne", padx=(24, 0), pady=(0, 8))

    def _build_configuration(self, parent: tk.Misc) -> None:
        self.connection_title = SectionTitle(parent, "01", tr("section_connection"))
        self.connection_title.pack(fill=tk.X, pady=(0, 10))
        panel = BorderPanel(parent, background=PAPER)
        panel.pack(fill=tk.X)
        panel.body.configure(padx=16, pady=14)

        self.profile_field_label = tk.Label(panel.body, text=tr("scooter_profile"), background=PAPER, foreground=GRAVEL, font=self.fonts["meta"])
        self.profile_field_label.grid(row=0, column=0, sticky="w")
        self.profile_combo = ttk.Combobox(
            panel.body,
            textvariable=self.profile_var,
            values=list(self.profile_by_label),
            state="readonly",
        )
        self.profile_combo.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(5, 13))

        self.port_field_label = tk.Label(panel.body, text=tr("com_port"), background=PAPER, foreground=GRAVEL, font=self.fonts["meta"])
        self.port_field_label.grid(row=2, column=0, sticky="w")
        self.port_combo = ttk.Combobox(panel.body, textvariable=self.port_var, state="readonly")
        self.port_combo.grid(row=3, column=0, sticky="ew", pady=(5, 0))
        self.refresh_button = ttk.Button(panel.body, text=tr("refresh"), command=self.refresh_ports)
        self.refresh_button.grid(row=3, column=1, padx=(8, 0), sticky="ew", pady=(5, 0))
        self.diagnostic_button = ttk.Button(panel.body, text=tr("diagnostics"), command=self._open_diagnostics)
        self.diagnostic_button.grid(row=3, column=2, padx=(8, 0), sticky="ew", pady=(5, 0))
        panel.body.columnconfigure(0, weight=1)

        self.serial_title = SectionTitle(parent, "02", tr("section_serial"))
        self.serial_title.pack(fill=tk.X, pady=(22, 10))
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

        self.target_title = SectionTitle(parent, "03", tr("section_target"))
        self.target_title.pack(fill=tk.X, pady=(22, 10))
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
        self.write_title = SectionTitle(parent, "04", tr("section_write"))
        self.write_title.pack(fill=tk.X, pady=(0, 10))
        panel = BorderPanel(parent, background=LINEN)
        panel.pack(fill=tk.BOTH, expand=True)
        panel.body.configure(padx=18, pady=16)
        panel.body.columnconfigure(1, weight=1)

        self.preview_labels = {
            "profile": labeled_value(panel.body, tr("profile"), self.preview_profile_var, row=0),
            "baudrate": labeled_value(panel.body, tr("baudrate"), self.preview_baud_var, row=1),
            "current": labeled_value(panel.body, tr("current"), self.preview_current_var, row=2),
            "target": labeled_value(panel.body, tr("target"), self.preview_target_var, row=3),
            "uart_serial": labeled_value(panel.body, tr("uart_serial"), self.preview_wire_var, row=4),
        }

        tk.Frame(panel.body, background=RULE, height=1).grid(row=5, column=0, columnspan=2, sticky="ew", pady=14)
        self.data_frame_label = tk.Label(
            panel.body,
            text=tr("data_frame"),
            background=LINEN,
            foreground=GRAVEL,
            font=self.fonts["meta"],
        )
        self.data_frame_label.grid(row=6, column=0, columnspan=2, sticky="w")
        self.data_frame_text = ReadOnlyText(panel.body, lines=5, background=LINEN)
        self.data_frame_text.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=(6, 12))
        self.commit_frame_label = tk.Label(
            panel.body,
            text=tr("commit_frame"),
            background=LINEN,
            foreground=GRAVEL,
            font=self.fonts["meta"],
        )
        self.commit_frame_label.grid(row=8, column=0, columnspan=2, sticky="w")
        self.commit_frame_text = ReadOnlyText(panel.body, lines=2, background=LINEN)
        self.commit_frame_text.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(6, 12))
        self.no_ack_label = tk.Label(
            panel.body,
            text=tr("no_ack_info"),
            background=LINEN,
            foreground=SOIL,
            font=self.fonts["small"],
            justify=tk.LEFT,
            wraplength=340,
        )
        self.no_ack_label.grid(row=10, column=0, columnspan=2, sticky="sw", pady=(8, 0))
        panel.body.rowconfigure(7, weight=1)

    def _bind_state(self) -> None:
        self.profile_var.trace_add("write", lambda *_: self._on_profile_changed())
        self.port_var.trace_add("write", lambda *_: self._on_port_changed())
        self.serial_var.trace_add("write", lambda *_: self._on_serial_changed())
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_changed)

    def _on_language_changed(self, _event: object = None) -> None:
        next_language = language_from_label(self.language_var.get())
        self._change_language(next_language, persist=True)

    def _change_language(self, next_language: str, *, persist: bool) -> None:
        if next_language == self.language:
            return
        self.language = set_language(next_language)
        if persist:
            save_language(self.language)
        self._reset_confirmation()
        self._apply_language()

    def _apply_language(self) -> None:
        set_language(self.language)
        self.language_var.set(LANGUAGE_LABELS[self.language])
        self.safety_label.configure(text=tr("safety"))
        self.safety_text_label.configure(text=tr("safety_text"))
        self.ack_check.configure(text=tr("acknowledge"))
        self.send_button.configure(text=tr("write_region"))
        self.slogan_label.configure(text=tr("slogan"))
        self.header_meta_label.configure(text=tr("header_meta"))
        self.language_label.configure(text=tr("language"))
        self.connection_title.set_title(tr("section_connection"))
        self.profile_field_label.configure(text=tr("scooter_profile"))
        self.port_field_label.configure(text=tr("com_port"))
        self.refresh_button.configure(text=tr("refresh"))
        self.diagnostic_button.configure(text=tr("diagnostics"))
        self.serial_title.set_title(tr("section_serial"))
        self.target_title.set_title(tr("section_target"))
        self.write_title.set_title(tr("section_write"))
        for key, widget in self.preview_labels.items():
            widget.configure(text=tr(key).upper())
        self.data_frame_label.configure(text=tr("data_frame"))
        self.commit_frame_label.configure(text=tr("commit_frame"))
        self.no_ack_label.configure(text=tr("no_ack_info"))
        key, values = self._status_translation
        self.status_var.set(tr(key, **values))
        self.status_canvas.itemconfigure(
            self.status_dot,
            fill={"working": AMBER, "ok": MOSS, "error": BRICK}.get(
                self._status_state, GRAVEL
            ),
        )
        self._recalculate()
        if self.diagnostics is not None and self.diagnostics.exists:
            self.diagnostics.set_language()

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
                messagebox.showerror(tr("ports_unavailable_title"), str(exc), parent=self.root)

        labels: list[str] = []
        mapping: dict[str, str] = {}
        for port in ports:
            description = str(getattr(port, "description", "") or tr("serial_port"))
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
            key = "ports_found_one" if len(labels) == 1 else "ports_found_many"
            self._set_status_key(key, "idle", count=len(labels))

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
                serial_valid = True
                if current_region:
                    self.serial_hint_var.set(tr("serial_known", region=current_region))
                else:
                    self.serial_hint_var.set(tr("serial_unknown", prefix=prefix))
            except (SerialNumberError, SerialTransactionError, ValueError) as exc:
                self.serial_hint_var.set(str(exc))
        elif not raw_serial:
            self.serial_hint_var.set(tr("serial_hint_empty"))

        self.preview_current_var.set(display_serial(canonical))
        if self.target_region and (
            profile is None
            or profile.prefix_for(self.target_region) is None
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
            self.data_frame_text.set_text(tr("choose_target"))
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
                button.configure(text=f"{region}\n{tr('unavailable')}")
                button.state(["disabled"])
            elif region == current_region:
                button.configure(text=f"{region} · {tr('current_region')}\n{prefix}")
                if region == self.target_region:
                    button.state(["selected"])
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
            messagebox.showwarning(
                tr("not_ready_title"), self.ui_state.block_reason(), parent=self.root
            )
            return

        same_note = (
            tr("same_region_note")
            if transaction.current_serial[:5] == transaction.target_serial[:5]
            else ""
        )
        confirmed = messagebox.askokcancel(
            tr("write_confirm_title"),
            tr(
                "write_confirm_body",
                profile=profile.display_name,
                port=port,
                baudrate=profile.baudrate,
                current=display_serial(transaction.current_serial),
                target=display_serial(transaction.target_serial),
                region=transaction.target_region,
                same_note=same_note,
            ),
            icon="warning",
            parent=self.root,
        )
        if not confirmed:
            return

        self.ui_state = self.ui_state.updated(busy=True)
        self._refresh_ready_state()
        self._set_status_key("status_opening", "working")
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
            "opening": "status_opening",
            "opened": "status_opened",
            "completed": "status_completed",
            "closed": "status_closed",
        }
        if event.kind == "frame_written":
            key = "data_frame_sent" if event.phase == "data" else "commit_frame_sent"
            self._set_status_key(key, "working")
        elif event.kind in messages:
            self._set_status_key(messages[event.kind], "working")

    def _handle_write_success(self, result: SerialTransactionResult, transaction: SerialTransaction) -> None:
        self.ui_state = self.ui_state.updated(busy=False)
        self.ack_var.set(False)
        self._refresh_ready_state()
        self._set_status_key("success_status", "ok")
        messagebox.showinfo(
            tr("success_title"),
            tr(
                "success_body",
                data_bytes=result.data_bytes_written,
                commit_bytes=result.commit_bytes_written,
                region=transaction.target_region,
            ),
            parent=self.root,
        )

    def _handle_write_error(self, error: BaseException) -> None:
        self.ui_state = self.ui_state.updated(busy=False)
        self.ack_var.set(False)
        self._refresh_ready_state()
        self._set_status_key("failure_status", "error")
        messagebox.showerror(
            tr("failure_title"),
            tr("failure_body", error=error),
            parent=self.root,
        )

    def _open_diagnostics(self) -> None:
        profile = self.current_profile()
        port = self.current_port()
        if self.ui_state.busy:
            messagebox.showwarning(
                tr("port_busy_title"), tr("port_busy_body"), parent=self.root
            )
            return
        if profile is None or not port:
            messagebox.showwarning(
                tr("diagnostics_not_ready_title"),
                tr("diagnostics_not_ready_body"),
                parent=self.root,
            )
            return
        if self.diagnostics is not None:
            if self.diagnostics.exists:
                self.diagnostics.window.lift()
                return
            if self.diagnostics.active:
                messagebox.showerror(
                    tr("port_release_title"),
                    tr("port_release_body"),
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
            self._set_status_key("diagnostics_busy", "working")
        elif not self.ui_state.busy:
            self._set_status_key("diagnostics_ended", "idle")

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

    def _set_status_key(self, key: str, state: str, **values: object) -> None:
        self._status_translation = (key, dict(values))
        self._status_state = state
        color = {"working": AMBER, "ok": MOSS, "error": BRICK}.get(state, GRAVEL)
        self.status_var.set(tr(key, **values))
        self.status_canvas.itemconfigure(self.status_dot, fill=color)

    def _show_profile_warnings(self) -> None:
        if self.profile_result.warnings:
            messagebox.showwarning(
                tr("profile_warnings_title"),
                tr("profile_warnings_body", warnings="\n".join(self.profile_result.warnings)),
                parent=self.root,
            )

    def _on_close(self) -> None:
        if self.ui_state.busy:
            messagebox.showwarning(
                tr("transfer_running_title"),
                tr("transfer_running_body"),
                parent=self.root,
            )
            return
        if self.diagnostics is not None and self.diagnostics.exists:
            self.diagnostics.close()
        self.root.destroy()


def main() -> None:
    if "--self-test" in sys.argv:
        run_command_line_test(run_self_test)
    if "--ui-smoke-test" in sys.argv:
        run_command_line_test(run_ui_smoke_test)
    enable_windows_dpi_awareness()
    root = tk.Tk()
    try:
        RegionChangerApp(root)
    except Exception as exc:
        root.withdraw()
        messagebox.showerror(
            tr("app_start_failed"),
            str(exc),
            parent=root,
        )
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
