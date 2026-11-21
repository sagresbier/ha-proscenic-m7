"""Proscenic M7 Pro: Status (Push) und Steuerung ueber die alte Proscenic-Cloud."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import ProscenicClient
from .const import CONF_SERIAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.VACUUM, Platform.BUTTON]

type ProscenicConfigEntry = ConfigEntry[ProscenicCoordinator]


class ProscenicCoordinator(DataUpdateCoordinator[dict]):
    """Verteilt die per Push eingehenden Daten an die Entitaeten."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: ProscenicClient
    ) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry)
        self.client = client
        self.data = client.snapshot()
        client.set_callback(self._on_push)

    def _on_push(self) -> None:
        self.async_set_updated_data(self.client.snapshot())


async def async_setup_entry(hass: HomeAssistant, entry: ProscenicConfigEntry) -> bool:
    client = ProscenicClient(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_SERIAL],
    )
    entry.runtime_data = ProscenicCoordinator(hass, entry, client)
    # Hintergrund-Task wird beim Entladen automatisch beendet
    entry.async_create_background_task(hass, client.run(), f"{DOMAIN}_client")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ProscenicConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
