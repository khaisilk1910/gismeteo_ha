# Copyright (c) 2019-2024, Andrey "Limych" Khrolenok
# Original work licensed under CC BY-NC-SA 4.0; see repository LICENSE.
"""Shared entity base and stable device identity for Gismeteo HA."""

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from . import GismeteoDataUpdateCoordinator
from .api import GismeteoApiClient
from .const import DOMAIN, NAME


class GismeteoEntity(CoordinatorEntity):
    """An entity bound to one geographical location coordinator."""

    def __init__(self, coordinator: GismeteoDataUpdateCoordinator, location_name: str):
        super().__init__(coordinator)
        self._location_name = location_name

    @property
    def _gismeteo(self) -> GismeteoApiClient:
        return self.coordinator.gismeteo

    @property
    def device_info(self) -> dict:
        """Never change device identifiers when city lookup finishes later."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.unique_id)},
            name=self._location_name,
            manufacturer=NAME,
            model="Gismeteo weather forecast",
        )
