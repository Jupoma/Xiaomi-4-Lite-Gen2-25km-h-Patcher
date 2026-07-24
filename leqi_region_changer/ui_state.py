"""Pure UI state used to keep widget logic deterministic and testable."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

from .i18n import translate as tr
from .profiles import ScooterProfile


def build_profile_label_map(
    profiles: tuple[ScooterProfile, ...],
) -> dict[str, ScooterProfile]:
    """Create stable UI labels without conflating equal display names."""

    counts = Counter(profile.display_name for profile in profiles)
    labels: dict[str, ScooterProfile] = {}
    for profile in profiles:
        label = profile.display_name
        if counts[profile.display_name] > 1:
            label = f"{profile.display_name} · {profile.id}"
        labels[label] = profile
    return labels


@dataclass(frozen=True)
class UiState:
    profile_selected: bool = False
    port_selected: bool = False
    serial_valid: bool = False
    target_region_selected: bool = False
    acknowledged: bool = False
    busy: bool = False
    diagnostics_active: bool = False

    @property
    def can_write(self) -> bool:
        return (
            self.profile_selected
            and self.port_selected
            and self.serial_valid
            and self.target_region_selected
            and self.acknowledged
            and not self.busy
            and not self.diagnostics_active
        )

    def updated(self, **changes: bool) -> "UiState":
        return replace(self, **changes)

    def block_reason(self) -> str:
        if self.busy:
            return tr("block_busy")
        if self.diagnostics_active:
            return tr("block_diagnostics")
        if not self.profile_selected:
            return tr("block_profile")
        if not self.port_selected:
            return tr("block_port")
        if not self.serial_valid:
            return tr("block_serial")
        if not self.target_region_selected:
            return tr("block_region")
        if not self.acknowledged:
            return tr("block_ack")
        return tr("block_ready")
