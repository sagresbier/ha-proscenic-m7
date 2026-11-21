"""Gemeinsame Basisklasse."""
from __future__ import annotations

import asyncio

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ProscenicCoordinator
from .api import ProscenicError
from .const import CONF_SERIAL, DOMAIN


class ProscenicEntity(CoordinatorEntity[ProscenicCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: ProscenicCoordinator, key: str) -> None:
        super().__init__(coordinator)
        serial = coordinator.config_entry.data[CONF_SERIAL]
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name="Proscenic M7 Pro",
            manufacturer="Proscenic",
            model="M7 Pro",
            serial_number=serial,
        )

    @property
    def status(self) -> dict:
        return self.coordinator.data.get("status") or {}

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return bool(data.get("connected")) and bool(data.get("status"))

    async def async_run_command(self, name: str) -> None:
        """Befehl senden und kurz danach den Status neu abfragen."""
        client = self.coordinator.client
        try:
            await client.async_command(name)
        except ProscenicError as err:
            raise HomeAssistantError(f"Proscenic-Befehl fehlgeschlagen: {err}") from err
        self.hass.async_create_background_task(self._refresh_soon(), "proscenic_m7_refresh")

    async def _refresh_soon(self) -> None:
        await asyncio.sleep(3)
        await self.coordinator.client.async_refresh()
