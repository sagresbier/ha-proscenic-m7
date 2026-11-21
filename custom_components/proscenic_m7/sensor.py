"""Sensoren: Zustand, Akku, Flaeche, Zeit, Fehler."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfArea, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ProscenicConfigEntry
from .const import (
    ERROR_OPTIONS,
    STATUS_OPTIONS,
    error_codes,
    error_key,
    normalize_status,
)
from .entity import ProscenicEntity


@dataclass(frozen=True, kw_only=True)
class ProscenicSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict], Any]
    attrs_fn: Callable[[dict], dict[str, Any]] | None = None


def _num(key: str) -> Callable[[dict], Any]:
    def fn(status: dict) -> Any:
        value = status.get(key)
        return value if isinstance(value, (int, float)) else None

    return fn


SENSORS: tuple[ProscenicSensorDescription, ...] = (
    ProscenicSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=STATUS_OPTIONS,
        value_fn=lambda s: normalize_status(s.get("mode")),
        attrs_fn=lambda s: {"mode": s.get("mode"), "sub_mode": s.get("subMode")},
    ),
    ProscenicSensorDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_num("elec"),
    ),
    ProscenicSensorDescription(
        key="cleaned_area",
        translation_key="cleaned_area",
        device_class=SensorDeviceClass.AREA,
        native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_num("cleanArea"),
    ),
    ProscenicSensorDescription(
        key="clean_time",
        translation_key="clean_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_num("cleanTime"),
    ),
    ProscenicSensorDescription(
        key="total_area",
        translation_key="total_area",
        device_class=SensorDeviceClass.AREA,
        native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_num("allArea"),
    ),
    ProscenicSensorDescription(
        key="total_time",
        translation_key="total_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_num("allTime"),
    ),
    ProscenicSensorDescription(
        key="error",
        translation_key="error",
        device_class=SensorDeviceClass.ENUM,
        options=ERROR_OPTIONS,
        value_fn=error_key,
        attrs_fn=lambda s: {"error_codes": error_codes(s)},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProscenicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(ProscenicSensor(coordinator, d) for d in SENSORS)


class ProscenicSensor(ProscenicEntity, SensorEntity):
    entity_description: ProscenicSensorDescription

    def __init__(self, coordinator, description: ProscenicSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.status)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        return fn(self.status) if fn else None
