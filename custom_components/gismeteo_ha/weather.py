#  Copyright (c) 2019-2024, Andrey "Limych" Khrolenok <andrey@khrolenok.ru>
#  Creative Commons BY-NC-SA 4.0 International Public License
#  (see repository LICENSE or https://creativecommons.org/licenses/by-nc-sa/4.0/)
"""The Gismeteo component.

For more details about this platform, please refer to the documentation at
https://github.com/khaisilk1910/gismeteo_ha/
"""

import logging

from homeassistant.components.weather import (
    SingleCoordinatorWeatherEntity,
    Forecast,
    WeatherEntityFeature,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import (
    CONF_NAME,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback

from . import GismeteoDataUpdateCoordinator, deslugify
from .const import ATTRIBUTION, COORDINATOR, DOMAIN, DOMAIN_YAML, ForecastMode
from .time_utils import local_isoformat

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Add a Gismeteo weather entities."""
    entities = []
    if config_entry.source == SOURCE_IMPORT:
        # Setup from configuration.yaml
        for uid, config in hass.data[DOMAIN_YAML].items():
            if config is None:
                config = {}
            location_name = config.get(CONF_NAME, deslugify(uid))
            coordinator = hass.data[DOMAIN][uid][COORDINATOR]

            entities.append(GismeteoWeather(coordinator, location_name))

    else:
        # Setup from config entry
        config = config_entry.data.copy()  # type: ConfigType
        config.update(config_entry.options)

        location_name = config[CONF_NAME]
        coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]

        entities.append(GismeteoWeather(coordinator, location_name))

    async_add_entities(entities, False)


class GismeteoWeather(SingleCoordinatorWeatherEntity):
    """Implementation of an Gismeteo sensor."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_attribution = ATTRIBUTION
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.MMHG
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(
        self,
        coordinator: GismeteoDataUpdateCoordinator,
        location_name: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._gismeteo = coordinator.gismeteo
        self._location_name = location_name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.unique_id)},
            name=location_name,
            manufacturer="Gismeteo HA",
            model="Gismeteo weather forecast",
        )

        self._attr_unique_id = coordinator.unique_id
        self._attr_translation_placeholders = {
            "location_name": location_name,
        }

    @property
    def condition(self) -> str | None:
        """Return the current condition."""
        return self._gismeteo.condition()

    @property
    def native_apparent_temperature(self) -> float | None:
        """Return the apparent temperature in native units."""
        return self._gismeteo.apparent_temperature()

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature in native units."""
        return self._gismeteo.temperature()

    @property
    def native_pressure(self) -> float | None:
        """Return the pressure in native units."""
        return self._gismeteo.pressure()

    @property
    def humidity(self) -> float | None:
        """Return the humidity in %."""
        return self._gismeteo.humidity()

    @property
    def wind_bearing(self) -> float | str | None:
        """Return the wind bearing."""
        return self._gismeteo.wind_bearing()

    @property
    def native_wind_gust_speed(self) -> float | None:
        """Return the wind gust speed in native units."""
        return self._gismeteo.wind_gust_speed()

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed in native units."""
        return self._gismeteo.wind_speed()

    @property
    def cloud_coverage(self) -> float | None:
        """Return the Cloud coverage in %."""
        return self._gismeteo.cloud_coverage()

    @property
    def uv_index(self) -> float | None:
        """Return the UV index."""
        return self._gismeteo.uv_index()

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose confirmed source details in addition to standard weather fields."""
        client = self._gismeteo
        extra: dict[str, object] = {
            "gismeteo_data_source": client.source,
            "gismeteo_is_storm": client.is_storm(),
            "gismeteo_precipitation_type": client.precipitation_type(),
            "gismeteo_precipitation_intensity": client.precipitation_intensity(),
            "gismeteo_geomagnetic_field": client.geomagnetic_field(),
            "gismeteo_dew_point_calculated": client.dew_point(),
        }
        # Unlike timestamp sensor states, custom weather attributes are stored
        # as strings. Home Assistant does not automatically localize them.
        local_zone = self.hass.config.time_zone
        if client.last_success:
            extra["gismeteo_last_refresh"] = local_isoformat(
                client.last_success, local_zone
            )
        if client.cache_age is not None:
            extra["gismeteo_cache_age_seconds"] = round(client.cache_age)
        for key in ("sunrise", "sunset"):
            when = getattr(client, key)()
            if when:
                extra[f"gismeteo_{key}"] = local_isoformat(when, local_zone)
        return {key: value for key, value in extra.items() if value is not None}

    @property
    def native_visibility(self) -> float | None:
        """Return measured or explicitly reported visibility, km."""
        return self._gismeteo.visibility()

    @property
    def native_visibility_unit(self) -> str | None:
        """Do not advertise a unit unless a value is actually available."""
        return "km" if self._gismeteo.visibility() is not None else None

    @callback
    def _async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast in native units."""
        return self._gismeteo.forecast(ForecastMode.DAILY)

    @callback
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly forecast in native units."""
        return self._gismeteo.forecast(ForecastMode.HOURLY)
