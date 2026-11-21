"""Vacuum-Entität: Start, Pause, Station, Saugstärke."""
from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ProscenicConfigEntry
from .api import COMMANDS
from .const import normalize_status
from .entity import ProscenicEntity

FAN_SPEEDS = ["quiet", "standard", "powerful"]
# Cloud-Wert (workNoisy / setMode) -> Name in HA
CLOUD_TO_FAN = {"quiet": "quiet", "auto": "standard", "strong": "powerful"}

ACTIVITY = {
    "cleaning": VacuumActivity.CLEANING,
    "returning": VacuumActivity.RETURNING,
    "paused": VacuumActivity.PAUSED,
    "charging": VacuumActivity.DOCKED,
    "charged": VacuumActivity.DOCKED,
    "idle": VacuumActivity.IDLE,
    "dormant": VacuumActivity.IDLE,
    "error": VacuumActivity.ERROR,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProscenicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ProscenicVacuum(entry.runtime_data)])


class ProscenicVacuum(ProscenicEntity, StateVacuumEntity):
    _attr_name = None
    _attr_fan_speed_list = FAN_SPEEDS
    _attr_supported_features = (
        VacuumEntityFeature.STATE
        | VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.FAN_SPEED
        | VacuumEntityFeature.SEND_COMMAND
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "robot")

    @property
    def activity(self) -> VacuumActivity | None:
        return ACTIVITY.get(normalize_status(self.status.get("mode")))

    @property
    def fan_speed(self) -> str | None:
        return CLOUD_TO_FAN.get(self.status.get("workNoisy"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"mode": self.status.get("mode"), "sub_mode": self.status.get("subMode")}

    async def async_start(self) -> None:
        paused = self.activity == VacuumActivity.PAUSED
        await self.async_run_command("continue" if paused else "clean")

    async def async_pause(self) -> None:
        await self.async_run_command("pause")

    async def async_return_to_base(self, **kwargs: Any) -> None:
        await self.async_run_command("charge")

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        if fan_speed not in FAN_SPEEDS:
            raise ServiceValidationError(f"Unbekannte Saugstärke: {fan_speed}")
        await self.async_run_command(f"fan_{fan_speed}")

    async def async_send_command(
        self, command: str, params: dict[str, Any] | list[Any] | None = None, **kwargs: Any
    ) -> None:
        """Erlaubt: clean, deep_clean, empty_dust, pause, continue, charge."""
        allowed = {"clean", "deep_clean", "empty_dust", "pause", "continue", "charge"}
        if command not in allowed:
            raise ServiceValidationError(
                f"Unbekannter Befehl {command}. Erlaubt: {', '.join(sorted(allowed))}"
            )
        await self.async_run_command(command)
