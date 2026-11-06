# Copyright (c) 2019-2024, Andrey "Limych" Khrolenok
# Original work licensed under CC BY-NC-SA 4.0; see repository LICENSE.
"""Gismeteo HA: non-blocking Home Assistant weather integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from aiohttp import ClientError
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME, CONF_SHOW_ON_MAP,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, GismeteoApiClient
from .frontend import async_register_card
from .const import (
    CONF_ADD_SENSORS, CONF_CACHE_DIR, CONF_EXTENDED_DATA, CONF_FORECAST_DAYS,
    CONF_POLL_INTERVAL, CONF_STALE_MINUTES, COORDINATOR, DOMAIN, DOMAIN_YAML,
    PLATFORMS, UNDO_UPDATE_LISTENER, ForecastMode,
)

_LOGGER = logging.getLogger(__name__)
DEFAULT_POLL_MINUTES = 15
DEFAULT_STALE_MINUTES = 30

forecast_days_int = vol.All(vol.Coerce(int), vol.Range(min=0, max=9))

LOCATION_SCHEMA = vol.Schema({
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_LATITUDE): cv.latitude,
    vol.Optional(CONF_LONGITUDE): cv.longitude,
    vol.Optional(CONF_SHOW_ON_MAP, default=False): cv.boolean,
    vol.Optional(CONF_ADD_SENSORS, default=True): cv.boolean,
    vol.Optional(CONF_FORECAST_DAYS): forecast_days_int,
    vol.Optional(CONF_CACHE_DIR): cv.string,
    vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_MINUTES): vol.All(
        vol.Coerce(int), vol.Range(min=10, max=120)
    ),
    vol.Optional(CONF_STALE_MINUTES, default=DEFAULT_STALE_MINUTES): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=180)
    ),
    vol.Optional(CONF_EXTENDED_DATA, default=True): cv.boolean,
})
CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: cv.schema_with_slug_keys(vol.Any(LOCATION_SCHEMA, None))},
    extra=vol.ALLOW_EXTRA,
)


def deslugify(text: str) -> str:
    """Create a display label from a YAML slug."""
    return text.replace("_", " ").capitalize()


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register legacy YAML imports without network access."""
    hass.data.setdefault(DOMAIN, {})
    # Static file serving and resource storage run locally, with no remote I/O.
    try:
        await async_register_card(hass)
    except (RuntimeError, OSError, ValueError, AttributeError, TypeError) as exc:
        _LOGGER.warning("Gismeteo HA Lovelace card setup failed: %s", exc)
    if DOMAIN in config:
        hass.data[DOMAIN_YAML] = config[DOMAIN]
        # The flow is lightweight: no external I/O, no dependence on network.
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data={}
            )
        )
    return True


def _get_api_client(hass: HomeAssistant, config: dict[str, Any]) -> GismeteoApiClient:
    """Create a client. No request is performed during construction."""
    cache_dir = config.get(CONF_CACHE_DIR) or hass.config.path(
        STORAGE_DIR, "gismeteo_ha_cache"
    )
    return GismeteoApiClient(
        async_get_clientsession(hass),
        latitude=config.get(CONF_LATITUDE, hass.config.latitude),
        longitude=config.get(CONF_LONGITUDE, hass.config.longitude),
        params={
            CONF_CACHE_DIR: cache_dir,
            CONF_POLL_INTERVAL: config.get(CONF_POLL_INTERVAL, DEFAULT_POLL_MINUTES),
            CONF_SHOW_ON_MAP: config.get(CONF_SHOW_ON_MAP, False),
            CONF_STALE_MINUTES: config.get(CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES),
            CONF_EXTENDED_DATA: config.get(CONF_EXTENDED_DATA, True),
        },
    )


class GismeteoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate one provider request for all the entities in a location."""

    def __init__(
        self, hass: HomeAssistant, unique_id: str, client: GismeteoApiClient,
        poll_minutes: int = DEFAULT_POLL_MINUTES,
    ) -> None:
        super().__init__(
            hass, _LOGGER, name=f"Gismeteo HA {unique_id}",
            update_interval=timedelta(minutes=poll_minutes),
        )
        self.gismeteo = client
        self.unique_id = unique_id
        self._entry: ConfigEntry | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Update core data; failures keep the previous valid snapshot."""
        try:
            await self.gismeteo.async_update()
        except (ApiError, ClientError, TimeoutError, OSError, ValueError) as exc:
            _LOGGER.warning("Gismeteo HA [%s] forecast refresh failed: %s", self.unique_id, exc)
            raise UpdateFailed(str(exc)) from exc
        # The HTML page is an optional, separately scheduled request. It never
        # delays the essential provider update or HA startup.
        if self.gismeteo.enrichment_due and self._entry is not None:
            self._entry.async_create_background_task(
                self.hass, _async_enrich(self),
                f"gismeteo_ha_enrich_{self.unique_id}", eager_start=False,
            )
        _LOGGER.debug(
            "Gismeteo HA [%s] refreshed source=%s hourly=%s daily=%s age=%.0fs",
            self.unique_id, self.gismeteo.source,
            len(self.gismeteo.forecast(ForecastMode.HOURLY)),
            len(self.gismeteo.forecast(ForecastMode.DAILY)),
            self.gismeteo.cache_age or 0,
        )
        return self.gismeteo.current_data


async def _async_enrich(coordinator: GismeteoDataUpdateCoordinator) -> None:
    """Best-effort website enrichment; never holds up core weather updates."""
    try:
        changed = await coordinator.gismeteo.async_update_parsed()
        if changed:
            coordinator.async_set_updated_data(coordinator.gismeteo.current_data)
    except (ApiError, ClientError, TimeoutError, OSError, ValueError) as exc:
        coordinator.gismeteo.last_enrichment_error = str(exc)
        _LOGGER.warning(
            "Gismeteo HA [%s] optional website enrichment unavailable: %s",
            coordinator.unique_id, exc,
        )


async def _async_initial_refresh(coordinator: GismeteoDataUpdateCoordinator) -> None:
    """Run initial I/O entirely outside the Home Assistant startup wait set."""
    await coordinator.async_refresh()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up entities immediately, then fetch remote data in the background."""
    hass.data.setdefault(DOMAIN, {})
    if entry.source == SOURCE_IMPORT:
        configs = hass.data.get(DOMAIN_YAML, {})
        for uid, yaml_config in configs.items():
            config = yaml_config or {}
            client = _get_api_client(hass, config)
            hass.data[DOMAIN][uid] = {
                COORDINATOR: GismeteoDataUpdateCoordinator(
                    hass, uid, client, config.get(CONF_POLL_INTERVAL, DEFAULT_POLL_MINUTES)
                )
            }
    else:
        config = {**entry.data, **entry.options}
        client = _get_api_client(hass, config)
        hass.data[DOMAIN][entry.entry_id] = {
            COORDINATOR: GismeteoDataUpdateCoordinator(
                hass, entry.entry_id, client,
                config.get(CONF_POLL_INTERVAL, DEFAULT_POLL_MINUTES),
            )
        }

    # Domain renamed in v4; previous `gismeteo` config entries must be recreated.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    listener = entry.add_update_listener(update_listener)
    hass.data[DOMAIN][entry.entry_id] = {
        **hass.data[DOMAIN].get(entry.entry_id, {}),
        UNDO_UPDATE_LISTENER: listener,
    }
    entry.async_on_unload(listener)

    keys = list(hass.data.get(DOMAIN_YAML, {})) if entry.source == SOURCE_IMPORT else [entry.entry_id]
    for key in keys:
        coordinator = hass.data[DOMAIN][key][COORDINATOR]
        coordinator._entry = entry
        entry.async_create_background_task(
            hass, _async_initial_refresh(coordinator),
            f"gismeteo_ha_initial_{key}", eager_start=False,
        )
    _LOGGER.debug("Gismeteo HA [%s] entities ready; initial I/O deferred", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload platforms and remove runtime state."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    if entry.source == SOURCE_IMPORT:
        for uid in hass.data.get(DOMAIN_YAML, {}):
            hass.data[DOMAIN].pop(uid, None)
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload an entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)

