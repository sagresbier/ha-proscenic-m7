"""Buttons: Tiefenreinigung und Behälter leeren."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ProscenicConfigEntry
from .entity import ProscenicEntity

BUTTONS = {"deep_clean": "mdi:vacuum", "empty_dust": "mdi:delete-empty"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProscenicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        ProscenicButton(entry.runtime_data, key, icon) for key, icon in BUTTONS.items()
    )


class ProscenicButton(ProscenicEntity, ButtonEntity):
    def __init__(self, coordinator, key: str, icon: str) -> None:
        super().__init__(coordinator, key)
        self._command = key
        self._attr_icon = icon

    async def async_press(self) -> None:
        await self.async_run_command(self._command)
