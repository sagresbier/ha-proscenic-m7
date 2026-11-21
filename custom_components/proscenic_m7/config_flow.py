"""Config-Flow: Benutzername und Seriennummer."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AuthError, CannotConnect, InvalidSerial, ProscenicClient
from .const import CONF_SERIAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): str, vol.Required(CONF_SERIAL): str}
)


class ProscenicConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            serial = user_input[CONF_SERIAL].strip()
            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured()
            client = ProscenicClient(async_get_clientsession(self.hass), username, serial)
            try:
                await client.async_validate()
            except AuthError:
                errors["base"] = "invalid_auth"
            except InvalidSerial:
                errors["base"] = "invalid_serial"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unerwarteter Fehler im Config-Flow")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="Proscenic M7 Pro",
                    data={CONF_USERNAME: username, CONF_SERIAL: serial},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input),
            errors=errors,
        )
