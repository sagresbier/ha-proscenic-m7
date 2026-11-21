"""Binaersensoren: Problem und Roboter online."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ProscenicConfigEntry
from .const import error_codes
from .entity import ProscenicEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProscenicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([ProscenicProblem(coordinator), ProscenicRobotOnline(coordinator)])


class ProscenicProblem(ProscenicEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "problem")

    @property
    def is_on(self) -> bool:
        return bool(error_codes(self.status))


class ProscenicRobotOnline(ProscenicEntity, BinarySensorEntity):
    """Meldet, ob die Cloud den Roboter als online sieht (Heartbeat-Antwort)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "robot_online")

    @property
    def available(self) -> bool:
        return bool(self.coordinator.data.get("connected"))

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("robot_online")
