"""Immutable scooter profiles with validated JSON override support."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Final

from .i18n import translate as tr

SCHEMA_VERSION: Final = 1
SUPPORTED_BAUDRATES: Final = frozenset({19_200, 115_200})
SUPPORTED_PROTOCOL: Final = "leqi_serial_write_v1"
REGION_CODES: Final = ("DE", "EU", "US")

_PROFILE_ID_RE = re.compile(r"^[a-z0-9_]+$", re.ASCII)
_REGION_PREFIX_RE = re.compile(r"^[0-9]{5}$", re.ASCII)
_PROFILE_KEYS: Final = frozenset(
    {
        "schema_version",
        "id",
        "display_name",
        "baudrate",
        "protocol",
        "wire_separator",
        "regions",
    }
)


class ProfileValidationError(ValueError):
    """Raised when a profile does not conform to schema version 1."""


@dataclass(frozen=True, slots=True)
class RegionPrefixes(Mapping[str, str | None]):
    """Fixed, immutable region-to-prefix mapping."""

    DE: str | None
    EU: str | None
    US: str | None

    def __getitem__(self, key: str) -> str | None:
        if key not in REGION_CODES:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(REGION_CODES)

    def __len__(self) -> int:
        return len(REGION_CODES)


@dataclass(frozen=True, slots=True)
class ScooterProfile:
    """Validated immutable description of one supported scooter."""

    schema_version: int
    id: str
    display_name: str
    baudrate: int
    protocol: str
    wire_separator: str
    regions: RegionPrefixes

    @property
    def baud(self) -> int:
        """Compatibility alias for callers that use the shorter name."""

        return self.baudrate

    def prefix_for(self, region: str) -> str | None:
        """Return the configured five-digit prefix for an exact region code."""

        return self.regions[region]


@dataclass(frozen=True, slots=True)
class ProfileLoadResult:
    """Profiles plus non-fatal diagnostics from bundled/external JSON files."""

    profiles: tuple[ScooterProfile, ...]
    warnings: tuple[str, ...]


_BASELINE_DATA: Final = (
    {
        "schema_version": 1,
        "id": "4litegen2_itde_with_turn_signal",
        "display_name": "4 Lite Gen2 DE/IT Version with turn Signals",
        "baudrate": 115_200,
        "protocol": SUPPORTED_PROTOCOL,
        "wire_separator": "",
        "regions": {"DE": "53777", "EU": "53937", "US": None},
    },
    {
        "schema_version": 1,
        "id": "5_plus",
        "display_name": "5 Plus",
        "baudrate": 19_200,
        "protocol": SUPPORTED_PROTOCOL,
        "wire_separator": "/",
        "regions": {"DE": "66232", "EU": "66230", "US": "66227"},
    },
    {
        "schema_version": 1,
        "id": "6_lite",
        "display_name": "6 Lite",
        "baudrate": 19_200,
        "protocol": SUPPORTED_PROTOCOL,
        "wire_separator": "",
        "regions": {"DE": "72367", "EU": "72365", "US": "72364"},
    },
    {
        "schema_version": 1,
        "id": "6",
        "display_name": "6",
        "baudrate": 19_200,
        "protocol": SUPPORTED_PROTOCOL,
        "wire_separator": "/",
        "regions": {"DE": "72363", "EU": "72361", "US": "72359"},
    },
    {
        "schema_version": 1,
        "id": "elite",
        "display_name": "Elite",
        "baudrate": 19_200,
        "protocol": SUPPORTED_PROTOCOL,
        "wire_separator": "",
        "regions": {"DE": "60543", "EU": "60545", "US": "60457"},
    },
)


def _require_exact_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProfileValidationError(tr("profile_string", field=field))
    return value


def profile_from_mapping(raw: Mapping[str, Any]) -> ScooterProfile:
    """Validate and convert one schema-v1 mapping into an immutable profile."""

    if not isinstance(raw, Mapping):
        raise ProfileValidationError(tr("profile_root"))

    keys = frozenset(raw.keys())
    missing = _PROFILE_KEYS - keys
    extra = keys - _PROFILE_KEYS
    if missing:
        raise ProfileValidationError(tr("profile_missing", fields=", ".join(sorted(missing))))
    if extra:
        raise ProfileValidationError(tr("profile_unknown", fields=", ".join(sorted(extra))))

    schema_version = raw["schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        raise ProfileValidationError(tr("profile_schema", version=SCHEMA_VERSION))

    profile_id = _require_exact_string(raw["id"], "id")
    if _PROFILE_ID_RE.fullmatch(profile_id) is None:
        raise ProfileValidationError(tr("profile_id"))

    display_name = _require_exact_string(raw["display_name"], "display_name")

    baudrate = raw["baudrate"]
    if isinstance(baudrate, bool) or not isinstance(baudrate, int) or baudrate not in SUPPORTED_BAUDRATES:
        allowed = ", ".join(str(value) for value in sorted(SUPPORTED_BAUDRATES))
        raise ProfileValidationError(tr("profile_baud", values=allowed))

    protocol = raw["protocol"]
    if protocol != SUPPORTED_PROTOCOL:
        raise ProfileValidationError(tr("profile_protocol", protocol=SUPPORTED_PROTOCOL))

    wire_separator = raw["wire_separator"]
    if wire_separator not in ("", "/"):
        raise ProfileValidationError(tr("profile_separator"))

    raw_regions = raw["regions"]
    if not isinstance(raw_regions, Mapping):
        raise ProfileValidationError(tr("profile_regions_object"))
    if frozenset(raw_regions.keys()) != frozenset(REGION_CODES):
        raise ProfileValidationError(tr("profile_regions_exact"))

    region_values: dict[str, str | None] = {}
    for region in REGION_CODES:
        prefix = raw_regions[region]
        if prefix is not None and (
            not isinstance(prefix, str) or _REGION_PREFIX_RE.fullmatch(prefix) is None
        ):
            raise ProfileValidationError(tr("profile_region_prefix", region=region))
        region_values[region] = prefix

    supported_prefixes = [value for value in region_values.values() if value is not None]
    if not supported_prefixes:
        raise ProfileValidationError(tr("profile_one_region"))
    if len(set(supported_prefixes)) != len(supported_prefixes):
        raise ProfileValidationError(tr("profile_unique_regions"))

    return ScooterProfile(
        schema_version=SCHEMA_VERSION,
        id=profile_id,
        display_name=display_name,
        baudrate=baudrate,
        protocol=protocol,
        wire_separator=wire_separator,
        regions=RegionPrefixes(**region_values),
    )


BASELINE_PROFILES: Final = tuple(profile_from_mapping(raw) for raw in _BASELINE_DATA)


def get_baseline_profiles() -> tuple[ScooterProfile, ...]:
    """Return the embedded profiles, which are always available."""

    return BASELINE_PROFILES


def load_profile_file(path: str | Path) -> ScooterProfile:
    """Read and validate one UTF-8 JSON profile file."""

    profile_path = Path(path)
    try:
        raw = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProfileValidationError(tr("profile_read", name=profile_path.name, error=exc)) from exc
    return profile_from_mapping(raw)


def _apply_profile_directory(
    directory_value: str | Path | None,
    *,
    source_label: str,
    profiles: dict[str, ScooterProfile],
    ordered_ids: list[str],
    diagnostics: list[str],
) -> None:
    if directory_value is None:
        return
    directory = Path(directory_value)
    if not directory.exists():
        return
    if not directory.is_dir():
        diagnostics.append(tr("profile_path", source=source_label, path=directory))
        return

    directory_ids: set[str] = set()
    for path in sorted(directory.glob("*.json"), key=lambda item: item.name.casefold()):
        try:
            profile = load_profile_file(path)
        except ProfileValidationError as exc:
            diagnostics.append(
                tr("profile_invalid", name=path.name, source=source_label, error=exc)
            )
            continue
        if profile.id in directory_ids:
            diagnostics.append(
                tr(
                    "profile_duplicate",
                    profile=profile.id,
                    source=source_label,
                    name=path.name,
                )
            )
            continue
        directory_ids.add(profile.id)
        if profile.id not in profiles:
            ordered_ids.append(profile.id)
        profiles[profile.id] = profile


def load_profiles(
    bundled_dir: str | Path | None = None,
    external_dir: str | Path | None = None,
) -> ProfileLoadResult:
    """Load embedded baseline, then bundled files, then external overrides.

    Invalid JSON files never remove a valid embedded/bundled profile. Instead,
    their human-readable diagnostics are returned for display by the UI.
    """

    profiles = {profile.id: profile for profile in BASELINE_PROFILES}
    ordered_ids = [profile.id for profile in BASELINE_PROFILES]
    diagnostics: list[str] = []
    _apply_profile_directory(
        bundled_dir,
        source_label=tr("profile_source_bundled"),
        profiles=profiles,
        ordered_ids=ordered_ids,
        diagnostics=diagnostics,
    )
    _apply_profile_directory(
        external_dir,
        source_label=tr("profile_source_external"),
        profiles=profiles,
        ordered_ids=ordered_ids,
        diagnostics=diagnostics,
    )
    return ProfileLoadResult(
        profiles=tuple(profiles[profile_id] for profile_id in ordered_ids),
        warnings=tuple(diagnostics),
    )


def find_profile(
    profile_id: str,
    profiles: tuple[ScooterProfile, ...] | ProfileLoadResult | None = None,
) -> ScooterProfile:
    """Return a profile by exact id or raise ``KeyError``."""

    if profiles is None:
        candidates = BASELINE_PROFILES
    elif isinstance(profiles, ProfileLoadResult):
        candidates = profiles.profiles
    else:
        candidates = profiles
    for profile in candidates:
        if profile.id == profile_id:
            return profile
    raise KeyError(profile_id)
