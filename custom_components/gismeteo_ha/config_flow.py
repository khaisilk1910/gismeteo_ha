# Copyright (c) 2019-2024, Andrey "Limych" Khrolenok
# Original work licensed under CC BY-NC-SA 4.0; see repository LICENSE.
"""User interface setup and options for Gismeteo HA."""

from __future__ import annotations

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME, CONF_SHOW_ON_MAP
from homeassistant.core import callback

from . import (
    DEFAULT_POLL_MINUTES, DEFAULT_STALE_MINUTES,
    forecast_days_int,
)
from .const import (
    CONF_ADD_SENSORS, CONF_EXTENDED_DATA, CONF_FORECAST_DAYS,
    CONF_POLL_INTERVAL, CONF_STALE_MINUTES, DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class GismeteoFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for a geographical weather location."""

    VERSION = 1

    async def async_step_import(self, platform_config: dict[str, Any] | None):
        """Handle existing configuration.yaml without performing web requests."""
        if self._async_current_entries():
            return self.async_abort(reason="no_mixed_config")
        return self.async_create_entry(title="configuration.yaml", data=platform_config or {})

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Validate user input at setup time (not at every HA startup)."""
        if any(entry.source == config_entries.SOURCE_IMPORT for entry in self._async_current_entries()):
            return self.async_abort(reason="no_mixed_config")

        errors: dict[str, str] = {}
        if user_input is not None:
            latitude = user_input[CONF_LATITUDE]
            longitude = user_input[CONF_LONGITUDE]
            await self.async_set_unique_id(f"{latitude:.5f},{longitude:.5f}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        config = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_NAME, default=config.get(CONF_NAME, self.hass.config.location_name)
                ): cv.string,
                vol.Required(
                    CONF_LATITUDE, default=config.get(CONF_LATITUDE, self.hass.config.latitude)
                ): cv.latitude,
                vol.Required(
                    CONF_LONGITUDE, default=config.get(CONF_LONGITUDE, self.hass.config.longitude)
                ): cv.longitude,
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> config_entries.OptionsFlow:
        """Return an options flow using HA's config_entry property."""
        return GismeteoOptionsFlowHandler()


class GismeteoOptionsFlowHandler(config_entries.OptionsFlow):
    """Manage forecasting and resource usage without YAML edits."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show and store options."""
        if self.config_entry.source == config_entries.SOURCE_IMPORT:
            return self.async_abort(reason="no_options_available")
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema({
            vol.Required(
                CONF_SHOW_ON_MAP, default=current.get(CONF_SHOW_ON_MAP, False)
            ): bool,
            vol.Required(
                CONF_ADD_SENSORS, default=current.get(CONF_ADD_SENSORS, True)
            ): bool,
            vol.Optional(
                CONF_FORECAST_DAYS, default=current.get(CONF_FORECAST_DAYS, 2)
            ): forecast_days_int,
            vol.Required(
                CONF_POLL_INTERVAL, default=current.get(CONF_POLL_INTERVAL, DEFAULT_POLL_MINUTES)
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=120)),
            vol.Required(
                CONF_STALE_MINUTES, default=current.get(CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES)
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=180)),
            vol.Required(
                CONF_EXTENDED_DATA, default=current.get(CONF_EXTENDED_DATA, True)
            ): bool,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
