# Copyright (c) 2019-2024, Andrey "Limych" Khrolenok
# Original work licensed under CC BY-NC-SA 4.0; see repository LICENSE.
"""Async Gismeteo provider client and defensive XML / optional HTML decoders.

The service endpoint is undocumented. Never infer a valid reading from a missing
field, and never allow the optional website parser to invalidate core weather.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from typing import Any, Final

import defusedxml.ElementTree as ETree
from defusedxml.common import DefusedXmlException
from aiohttp import ClientError, ClientSession, ClientTimeout
from bs4 import BeautifulSoup
from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT, ATTR_CONDITION_CLOUDY, ATTR_CONDITION_FOG,
    ATTR_CONDITION_LIGHTNING, ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_PARTLYCLOUDY, ATTR_CONDITION_POURING, ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY, ATTR_CONDITION_SNOWY_RAINY, ATTR_CONDITION_SUNNY,
    ATTR_CONDITION_WINDY, ATTR_CONDITION_WINDY_VARIANT,
    ATTR_FORECAST_CLOUD_COVERAGE, ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_HUMIDITY, ATTR_FORECAST_IS_DAYTIME,
    ATTR_FORECAST_NATIVE_APPARENT_TEMP, ATTR_FORECAST_NATIVE_PRECIPITATION,
    ATTR_FORECAST_NATIVE_PRESSURE, ATTR_FORECAST_NATIVE_TEMP,
    ATTR_FORECAST_NATIVE_TEMP_LOW, ATTR_FORECAST_NATIVE_WIND_GUST_SPEED,
    ATTR_FORECAST_NATIVE_WIND_SPEED, ATTR_FORECAST_TIME,
    ATTR_FORECAST_UV_INDEX, ATTR_FORECAST_WIND_BEARING, Forecast,
)
from homeassistant.const import ATTR_ID, ATTR_LATITUDE, ATTR_LONGITUDE, CONF_SHOW_ON_MAP

from .cache import Cache
from .const import (
    ATTR_FORECAST_GEOMAGNETIC_FIELD, ATTR_FORECAST_IS_STORM,
    ATTR_FORECAST_PHENOMENON, ATTR_FORECAST_POLLEN_BIRCH,
    ATTR_FORECAST_POLLEN_GRASS, ATTR_FORECAST_POLLEN_RAGWEED,
    ATTR_FORECAST_PRECIPITATION_AMOUNT, ATTR_FORECAST_PRECIPITATION_INTENSITY,
    ATTR_FORECAST_PRECIPITATION_TYPE, ATTR_FORECAST_ROAD_CONDITION,
    ATTR_FORECAST_WATER_TEMPERATURE, ATTR_FORECAST_WIND_BEARING_LABEL,
    ATTR_LAT, ATTR_LON, ATTR_SUNRISE, ATTR_SUNSET, ATTR_VISIBILITY, ATTR_DEW_POINT, CONDITION_FOG_CLASSES,
    CONF_CACHE_DIR, CONF_EXTENDED_DATA, CONF_STALE_MINUTES, ENDPOINT_URL,
    PARSER_URL_FORMAT, PARSER_USER_AGENT, ForecastMode,
)

_LOGGER = logging.getLogger(__name__)
MAX_RESPONSE_BYTES: Final = 2_000_000
_HTTP_TIMEOUT = ClientTimeout(total=9, connect=4, sock_read=6)
_HOUR = timedelta(hours=1)
_HTML_REFRESH = timedelta(minutes=61)
_WEATHER_SLUG = re.compile(r"weather-([a-z0-9-]+)", re.IGNORECASE)


class InvalidCoordinatesError(ValueError):
    """Raised for invalid geographical coordinates."""


class ApiError(Exception):
    """Raised for unavailable, malformed or unsupported provider data."""


class GismeteoForecast(Forecast, total=False):
    """Weather forecast including optional Gismeteo-specific values."""

    precipitation_type: str | None
    precipitation_intensity: str | None
    wind_bearing_label: str | None
    phenomenon: str | None
    pollen_birch: int | None
    pollen_grass: int | None
    pollen_ragweed: int | None
    road_condition: str | None


def _float(value: str | None) -> float | None:
    try:
        result = float(value) if value is not None else None
        return result if result is not None and math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _int(value: str | None) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None


def _element_attr(el: Any, name: str, convert: Callable | None = None) -> Any:
    if el is None:
        return None
    value = el.get(name)
    return convert(value) if convert is not None else value


def _datetime(value: str | None, offset_minutes: int) -> datetime | None:
    """Parse local provider time with an explicit provider UTC offset."""
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        provider_zone = timezone(timedelta(minutes=offset_minutes))
        return (
            timestamp.replace(tzinfo=provider_zone)
            if timestamp.tzinfo is None else timestamp.astimezone(provider_zone)
        )
    except (TypeError, ValueError, OverflowError):
        return None


def _epoch(value: str | None, tz: timezone) -> datetime | None:
    seconds = _float(value)
    if seconds is None or seconds < 0:
        return None
    try:
        # UNIX epoch values are UTC seconds, *not* seconds in provider zone.
        return datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone(tz)
    except (OSError, ValueError, OverflowError):
        return None


def _value(el: Any, name: str, convert: Callable | None = None) -> Any:
    return _element_attr(el, name, convert)


def _wind_text_mps(value: str | None) -> float | None:
    """Reject unlabeled website wind speed rather than assume m/s."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(м/с|m/s|км/ч|km/h)\s*", value, re.IGNORECASE)
    if not match:
        return None
    measured = _float(match.group(1).replace(",", "."))
    if measured is None or measured > 300:
        return None
    return round(measured / 3.6, 2) if match.group(2).lower() in ("км/ч", "km/h") else measured


def _visibility_text_km(value: str | None) -> float | None:
    """Parse only human readable distances with explicit km/m units."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(км|km|м|m)\s*", value, re.IGNORECASE)
    if not match:
        return None
    dist = _float(match.group(1).replace(",", "."))
    if dist is None:
        return None
    scale = .001 if match.group(2).lower() in ("м", "m") else 1
    return round(dist * scale, 3) if dist * scale <= 1000 else None


def _read_visibility_km(node: Any) -> float | None:
    """Only accept visibility carrying an explicit distance unit.

    The legacy Gismeteo XML format is not formally documented. An unqualified
    `vis` number might represent metres or another index: never guess.
    """
    if node is None:
        return None
    for field, scale in (("visibility_km", 1), ("vis_km", 1),
                         ("visibility_m", .001), ("vis_m", .001)):
        n = _float(node.get(field))
        if n is not None and 0 <= n * scale <= 1000:
            return round(n * scale, 3)
    child = node.find("visibility")
    if child is not None:
        unit = (child.get("unit") or "").strip().lower()
        val = _float(child.get("value") or child.text)
        if val is not None and unit in ("m", "km") and 0 <= val <= 1_000_000:
            km = val / 1000 if unit == "m" else val
            if km <= 1000:
                return round(km, 3)
    return None


def _xml_valid(payload: str, kind: str) -> bool:
    """Validate before adding remote data to the persistent cache."""
    try:
        root = ETree.fromstring(payload)
    except (ETree.ParseError, DefusedXmlException, ValueError, TypeError):
        return False
    if kind == "location":
        item = root.find("item")
        return item is not None and (_int(item.get("id")) or 0) > 0
    if kind == "forecast":
        location = root.find("location")
        fact = location.find("fact") if location is not None else None
        values = fact.find("values") if fact is not None else None
        return bool(
            fact is not None and fact.get("valid")
            and values is not None
            and (_float(values.get("tflt")) is not None
                 or _float(values.get("t")) is not None
                 or _float(values.get("p")) is not None)
            and location.find("day") is not None
        )
    return False


class GismeteoApiClient:
    """Gismeteo XML source with bounded cache and optional website enrichment."""

    def __init__(
        self,
        session: ClientSession,
        location_key: int | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        params = params or {}
        if not (
            isinstance(latitude, (int, float)) and not isinstance(latitude, bool)
            and isinstance(longitude, (int, float)) and not isinstance(longitude, bool)
            and math.isfinite(latitude) and math.isfinite(longitude)
            and -90 <= latitude <= 90 and -180 <= longitude <= 180
        ):
            raise InvalidCoordinatesError("Latitude and longitude must be finite, valid degrees")

        self._session = session
        self._latitude = float(latitude)
        self._longitude = float(longitude)
        self._location_key = location_key
        self._show_on_map = bool(params.get(CONF_SHOW_ON_MAP, False))
        self.extended_data = bool(params.get(CONF_EXTENDED_DATA, True))
        self._stale_seconds = max(0, int(params.get(CONF_STALE_MINUTES, 30))) * 60
        self._forecast_ttl = max(300, min(7200, int(params.get("poll_interval", 15)) * 60))
        self._cache = Cache(params[CONF_CACHE_DIR]) if params.get(CONF_CACHE_DIR) else None
        self._current: dict[str, Any] = {}
        self._forecast_hourly: list[dict[str, Any]] = []
        self._forecast_daily: list[dict[str, Any]] = []
        self._parsed: dict[date, dict[str, str | None]] = {}
        self._website_location: str | None = None
        self._website_date: date | None = None
        self._last_enrich_attempt: datetime | None = None
        self.source: str = "not_loaded"
        self.cache_age: float | None = None
        self.last_success: datetime | None = None
        self.last_error: str | None = None
        self.last_enrichment_error: str | None = None
        # Cache keys use exactly the configured coordinates to avoid collisions.
        self._cache_id = hashlib.sha256(
            f"{self._latitude:.6f},{self._longitude:.6f}".encode("ascii")
        ).hexdigest()[:24]

    @property
    def attributes(self) -> dict[str, Any]:
        """Return provider metadata; avoid exposing location on the map by default."""
        result: dict[str, Any] = {}
        if self._location_key is not None:
            result[ATTR_ID] = self._location_key
        result.update({
            ATTR_LATITUDE if self._show_on_map else ATTR_LAT: self._latitude,
            ATTR_LONGITUDE if self._show_on_map else ATTR_LON: self._longitude,
        })
        return result

    @property
    def current_data(self) -> dict[str, Any]:
        return self._current

    async def _async_get_data(
        self, url: str, filename: str, *, ttl: int, kind: str,
        stale_seconds: int | None = None,
    ) -> str:
        """Use valid fresh cache or fetch over HTTPS with stale-if-error fallback."""
        stale = self._stale_seconds if stale_seconds is None else stale_seconds
        cached = await self._cache.async_read(filename, ttl) if self._cache else None
        if cached and (
            kind == "html" or await asyncio.to_thread(_xml_valid, cached[0], kind)
        ):
            self.source = "cache"
            self.cache_age = cached[1]
            _LOGGER.debug("Gismeteo HA cache hit kind=%s age=%.0fs", kind, cached[1])
            return cached[0]

        try:
            headers = {"Accept": "text/html" if kind == "html" else "application/xml"}
            if kind == "html":
                headers["User-Agent"] = PARSER_USER_AGENT
            _LOGGER.debug("Gismeteo HA requesting %s endpoint", kind)
            async with self._session.get(url, timeout=_HTTP_TIMEOUT, headers=headers) as resp:
                if resp.status != HTTPStatus.OK:
                    raise ApiError(f"{kind} endpoint HTTP {resp.status}")
                if resp.content_length is not None and resp.content_length > MAX_RESPONSE_BYTES:
                    raise ApiError(f"{kind} response too large")
                body = await resp.content.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ApiError(f"{kind} response size limit exceeded")
                try:
                    content = body.decode(resp.charset or "utf-8")
                except (UnicodeError, LookupError) as exc:
                    raise ApiError(f"{kind} response invalid character encoding") from exc
            if not content.strip():
                raise ApiError(f"{kind} endpoint returned an empty response")
            if kind != "html" and not await asyncio.to_thread(_xml_valid, content, kind):
                raise ApiError(f"{kind} endpoint returned malformed or unexpected XML")
            if kind == "html" and "widget-row" not in content:
                raise ApiError("website markup no longer contains supported forecast widgets")
            if self._cache:
                await self._cache.async_save(filename, content)
            self.source = "network"
            self.cache_age = 0.0
            return content
        except (ApiError, ClientError, TimeoutError, OSError) as exc:
            if stale > 0 and self._cache:
                fallback = await self._cache.async_read(filename, ttl + stale)
                if fallback and (
                    kind == "html" or await asyncio.to_thread(_xml_valid, fallback[0], kind)
                ):
                    self.source = "cache_stale"
                    self.cache_age = fallback[1]
                    _LOGGER.warning(
                        "Gismeteo HA %s unavailable (%s); using cached data age=%.0fs",
                        kind, exc, fallback[1],
                    )
                    return fallback[0]
            raise ApiError(f"Unable to read {kind} source: {exc}") from exc

    async def async_update_location(self) -> None:
        """Resolve the nearest Gismeteo city, cached for one week."""
        if self._location_key is not None:
            return
        from urllib.parse import urlencode

        url = f"{ENDPOINT_URL}/cities/?{urlencode({'lat': self._latitude, 'lng': self._longitude, 'count': 1, 'lang': 'en'})}"
        payload = await self._async_get_data(
            url, f"location_{self._cache_id}.xml", ttl=7 * 86400,
            kind="location", stale_seconds=30 * 86400,
        )
        try:
            item = ETree.fromstring(payload).find("item")
            city_id = _int(_element_attr(item, "id"))
            if city_id is None or city_id <= 0:
                raise ValueError("city ID missing")
            self._location_key = city_id
        except (ETree.ParseError, DefusedXmlException, ValueError, TypeError) as exc:
            raise ApiError("City lookup returned invalid metadata") from exc
        _LOGGER.debug("Gismeteo HA resolved city id=%s", self._location_key)

    async def async_get_forecast(self) -> str:
        """Fetch a validated provider XML snapshot."""
        await self.async_update_location()
        return await self._async_get_data(
            f"{ENDPOINT_URL}/forecast/?city={self._location_key}&lang=en",
            f"forecast_{self._cache_id}.xml", ttl=self._forecast_ttl, kind="forecast",
        )

    @staticmethod
    def _decode_xml(payload: str) -> tuple[
        dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], str | None, date
    ]:
        """Parse complete snapshot before mutating live entity data."""
        try:
            root = ETree.fromstring(payload)
            location = root.find("location")
            fact = location.find("fact") if location is not None else None
            values = fact.find("values") if fact is not None else None
            if location is None or fact is None or values is None:
                raise ValueError("missing location/fact/values")
            zone_minutes = _int(location.get("tzone")) or 0
            if abs(zone_minutes) > 14 * 60:
                raise ValueError("invalid provider timezone")
            zone = timezone(timedelta(minutes=zone_minutes))
            valid_time = _datetime(fact.get("valid"), zone_minutes)
            if valid_time is None:
                raise ValueError("missing valid fact timestamp")
            # Provider fact timestamps are checked independently of cache mtime.
            if abs((datetime.now(timezone.utc) - valid_time.astimezone(timezone.utc)).total_seconds()) > 36 * 3600:
                raise ValueError("observation timestamp is over 36 hours from the current time")
            website_date = (
                _datetime(location.get("cur_time"), zone_minutes) or valid_time
            ).date()

            def decode_values(node: Any) -> dict[str, Any]:
                """Map documented existing XML fields without inventing missing data."""
                return {
                    ATTR_FORECAST_CONDITION: _value(node, "descr"),
                    ATTR_FORECAST_NATIVE_TEMP: _value(node, "tflt", _float)
                    if _value(node, "tflt", _float) is not None
                    else _value(node, "t", _float),
                    ATTR_FORECAST_NATIVE_PRESSURE: _value(node, "p", _float),
                    ATTR_FORECAST_HUMIDITY: _value(node, "hum", _int),
                    ATTR_FORECAST_NATIVE_WIND_SPEED: _value(node, "ws", _float),
                    ATTR_FORECAST_WIND_BEARING: _value(node, "wd", _int),
                    ATTR_FORECAST_CLOUD_COVERAGE: _value(node, "cl", _int),
                    ATTR_FORECAST_PRECIPITATION_TYPE: _value(node, "pt", _int),
                    ATTR_FORECAST_PRECIPITATION_AMOUNT: _value(node, "prflt", _float),
                    ATTR_FORECAST_PRECIPITATION_INTENSITY: _value(node, "pr", _int),
                    ATTR_FORECAST_IS_STORM: _value(node, "ts", _int) == 1
                    if _value(node, "ts") is not None else None,
                    ATTR_FORECAST_GEOMAGNETIC_FIELD: _value(node, "grade", _int),
                    ATTR_FORECAST_PHENOMENON: _value(node, "ph", _int),
                    ATTR_FORECAST_WATER_TEMPERATURE: _value(node, "water_t", _float),
                    ATTR_VISIBILITY: _read_visibility_km(node),
                }

            current = decode_values(values)
            current[ATTR_FORECAST_TIME] = valid_time
            current[ATTR_SUNRISE] = _epoch(fact.get("sunrise"), zone)
            current[ATTR_SUNSET] = _epoch(fact.get("sunset"), zone)
            if current[ATTR_FORECAST_NATIVE_TEMP] is None and current[ATTR_FORECAST_NATIVE_PRESSURE] is None:
                raise ValueError("fact contains no recognizable weather measurements")

            hourly: list[dict[str, Any]] = []
            daily: list[dict[str, Any]] = []
            for day in location.findall("day"):
                sunrise = _epoch(day.get("sunrise"), zone)
                sunset = _epoch(day.get("sunset"), zone)
                day_stamp = _datetime(day.get("date"), zone_minutes)
                if day_stamp is not None and day.get("descr") is not None:
                    day_values = decode_values(day)
                    day_values[ATTR_FORECAST_NATIVE_TEMP] = _value(day, "tmax", _float)
                    day_values[ATTR_FORECAST_NATIVE_TEMP_LOW] = _value(day, "tmin", _float)
                    day_values[ATTR_FORECAST_GEOMAGNETIC_FIELD] = _value(day, "grademax", _int)
                    day_values.update({
                        ATTR_FORECAST_TIME: day_stamp,
                        ATTR_SUNRISE: sunrise, ATTR_SUNSET: sunset,
                    })
                    daily.append(day_values)
                for hour in day.findall("forecast"):
                    stamp = _datetime(hour.get("valid"), zone_minutes)
                    hour_values = hour.find("values")
                    if stamp is None or hour_values is None:
                        continue
                    row = decode_values(hour_values)
                    row.update({
                        ATTR_FORECAST_TIME: stamp,
                        ATTR_SUNRISE: sunrise, ATTR_SUNSET: sunset,
                        ATTR_FORECAST_IS_DAYTIME: (
                            sunrise <= stamp < sunset
                            if sunrise is not None and sunset is not None else None
                        ),
                    })
                    hourly.append(row)
            hourly.sort(key=lambda record: record[ATTR_FORECAST_TIME])
            daily.sort(key=lambda record: record[ATTR_FORECAST_TIME])
            if not hourly and not daily:
                raise ValueError("no valid hourly or daily forecasts")
            return current, hourly, daily, location.get("nowcast_url"), website_date
        except (ETree.ParseError, DefusedXmlException, AttributeError, ValueError, TypeError, OverflowError) as exc:
            raise ApiError(f"Invalid Gismeteo forecast XML: {exc}") from exc

    async def async_update(self) -> bool:
        """Get and atomically publish a weather snapshot."""
        try:
            payload = await self.async_get_forecast()
            current, hourly, daily, website_location, website_date = await asyncio.to_thread(
                self._decode_xml, payload
            )
            self._current = current
            self._forecast_hourly = hourly
            self._forecast_daily = daily
            self._website_location = website_location
            self._website_date = website_date
            self._apply_parsed()
            self.last_success = datetime.now(timezone.utc)
            self.last_error = None
            return True
        except (ApiError, ClientError, TimeoutError, OSError, ValueError) as exc:
            self.last_error = str(exc)
            raise

    def _apply_parsed(self) -> None:
        """Enrich only days for which actual HTML data was successfully parsed."""
        for item in (*self._forecast_hourly, *self._forecast_daily):
            stamp = item.get(ATTR_FORECAST_TIME)
            if not isinstance(stamp, datetime):
                continue
            parsed = self._parsed.get(stamp.date())
            if not parsed:
                continue
            for target, key, caster in (
                (ATTR_FORECAST_NATIVE_WIND_GUST_SPEED, "wind-gust", _wind_text_mps),
                (ATTR_FORECAST_POLLEN_BIRCH, "pollen-birch", _int),
                (ATTR_FORECAST_POLLEN_GRASS, "pollen-grass", _int),
                (ATTR_FORECAST_POLLEN_RAGWEED, "pollen-ragweed", _int),
                (ATTR_FORECAST_UV_INDEX, "uv-index", _float),
                (ATTR_FORECAST_ROAD_CONDITION, "roadcondition", str),
                (ATTR_VISIBILITY, "visibility", _visibility_text_km),
            ):
                raw = parsed.get(key)
                if raw is not None:
                    converted = caster(raw)
                    if converted is not None:
                        item[target] = converted

    @property
    def enrichment_due(self) -> bool:
        """Whether the website may be polled without unnecessary requests."""
        return bool(
            self.extended_data and self._website_location and self._website_date
            and (
                self._last_enrich_attempt is None
                or datetime.now(timezone.utc) - self._last_enrich_attempt >= _HTML_REFRESH
            )
        )

    async def async_update_parsed(self) -> bool:
        """Optional website HTML enrichment, at most once per 61 minutes."""
        if not self.extended_data or not self._website_location or not self._website_date:
            return False
        now = datetime.now(timezone.utc)
        if self._last_enrich_attempt and now - self._last_enrich_attempt < _HTML_REFRESH:
            return False
        # Set before the request so repeated failures do not hammer the site.
        self._last_enrich_attempt = now
        match = _WEATHER_SLUG.search(self._website_location)
        if not match:
            _LOGGER.debug("Gismeteo HA website URL has no valid weather slug")
            return False
        slug = match.group(1)
        previous_source, previous_age = self.source, self.cache_age
        try:
            html = await self._async_get_data(
            PARSER_URL_FORMAT.format(slug), f"website_{self._cache_id}.html",
                ttl=3600, kind="html", stale_seconds=0,
            )
        finally:
            # Preserve data provenance of primary weather, not the HTML page.
            self.source, self.cache_age = previous_source, previous_age
        parsed = await asyncio.to_thread(BeautifulSoup, html, "html.parser")
        data: dict[date, dict[str, str | None]] = {}
        for row in parsed.select("div.widget-row[data-row]"):
            metric = row.get("data-row")
            if not metric:
                continue
            for index, cell in enumerate(row.select("div.row-item")):
                day = self._website_date + timedelta(days=index)
                data.setdefault(day, {})[metric] = next(cell.stripped_strings, None)
        if not data:
            self.last_enrichment_error = "Website widgets changed; no supported rows found"
            _LOGGER.warning("Gismeteo HA website widgets changed, no enrichment extracted")
            return False
        self.last_enrichment_error = None
        self._parsed = data
        self._apply_parsed()
        _LOGGER.debug("Gismeteo HA enriched %d forecast dates", len(data))
        return True

    @staticmethod
    def _src(source: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
        # Empty forecast data must NOT be substituted with current observations.
        return current if source is None else source

    def condition(
        self, src: dict[str, Any] | None = None, mode: str = ForecastMode.HOURLY
    ) -> str | None:
        values = self._src(src, self._current)
        cloud = values.get(ATTR_FORECAST_CLOUD_COVERAGE)
        if cloud is None:
            return None
        stamp = values.get(ATTR_FORECAST_TIME)
        sunrise = values.get(ATTR_SUNRISE)
        sunset = values.get(ATTR_SUNSET)
        if cloud == 0:
            if mode == ForecastMode.DAILY or sunrise is None or sunset is None or stamp is None:
                condition = ATTR_CONDITION_SUNNY
            else:
                condition = ATTR_CONDITION_SUNNY if sunrise <= stamp < sunset else ATTR_CONDITION_CLEAR_NIGHT
        elif cloud in (1, 2):
            condition = ATTR_CONDITION_PARTLYCLOUDY
        else:
            condition = ATTR_CONDITION_CLOUDY

        precipitation = values.get(ATTR_FORECAST_PRECIPITATION_TYPE)
        intensity = values.get(ATTR_FORECAST_PRECIPITATION_INTENSITY)
        if values.get(ATTR_FORECAST_IS_STORM):
            return ATTR_CONDITION_LIGHTNING_RAINY if precipitation in (1, 3) else ATTR_CONDITION_LIGHTNING
        if precipitation == 1:
            return ATTR_CONDITION_POURING if intensity == 3 else ATTR_CONDITION_RAINY
        if precipitation == 2:
            return ATTR_CONDITION_SNOWY
        if precipitation == 3:
            return ATTR_CONDITION_SNOWY_RAINY
        if cloud == 0 and values.get(ATTR_FORECAST_PHENOMENON) in CONDITION_FOG_CLASSES:
            return ATTR_CONDITION_FOG
        wind = self.wind_speed(values)
        if wind is not None and wind > 10.8:
            return ATTR_CONDITION_WINDY_VARIANT if condition == ATTR_CONDITION_CLOUDY else ATTR_CONDITION_WINDY
        return condition

    def temperature(self, src: dict | None = None) -> float | None:
        return self._src(src, self._current).get(ATTR_FORECAST_NATIVE_TEMP)

    def templow(self, src: dict | None = None) -> float | None:
        return self._src(src, self._current).get(ATTR_FORECAST_NATIVE_TEMP_LOW)

    def apparent_temperature(self, src: dict | None = None) -> float | None:
        temp = self.temperature(src)
        humidity = self.humidity(src)
        wind = self.wind_speed(src)
        if temp is None or humidity is None or wind is None:
            return None
        # Approximation derived from temperature (C), humidity (%) and wind (m/s).
        vapour_pressure = humidity * 0.06105 * math.exp(17.27 * temp / (237.7 + temp))
        return round(temp + 0.348 * vapour_pressure - 0.7 * wind - 4.25, 1)

    def water_temperature(self, src: dict | None = None) -> float | None:
        return self._src(src, self._current).get(ATTR_FORECAST_WATER_TEMPERATURE)

    def data_source(self, src: dict | None = None) -> str:
        return self.source

    def last_refresh(self, src: dict | None = None) -> datetime | None:
        return self.last_success

    def visibility(self, src: dict | None = None) -> float | None:
        """Return real source visibility in km, never estimated from humidity."""
        return self._src(src, self._current).get(ATTR_VISIBILITY)

    def dew_point(self, src: dict | None = None) -> float | None:
        """Calculate dew point (Magnus approximation) from actual T and RH."""
        temp = self.temperature(src)
        rh = self.humidity(src)
        if temp is None or rh is None or not 0 < rh <= 100 or not -80 <= temp <= 65:
            return None
        gamma = math.log(rh / 100) + 17.625 * temp / (243.04 + temp)
        return round(243.04 * gamma / (17.625 - gamma), 1)

    def sunrise(self, src: dict | None = None) -> datetime | None:
        return self._src(src, self._current).get(ATTR_SUNRISE)

    def sunset(self, src: dict | None = None) -> datetime | None:
        return self._src(src, self._current).get(ATTR_SUNSET)

    def pressure(self, src: dict | None = None) -> float | None:
        return self._src(src, self._current).get(ATTR_FORECAST_NATIVE_PRESSURE)

    def humidity(self, src: dict | None = None) -> float | None:
        return self._src(src, self._current).get(ATTR_FORECAST_HUMIDITY)

    def wind_bearing(self, src: dict | None = None) -> int | None:
        value = self._src(src, self._current).get(ATTR_FORECAST_WIND_BEARING)
        return (value - 1) * 45 if isinstance(value, int) and 1 <= value <= 8 else None

    def wind_bearing_label(self, src: dict | None = None) -> str | None:
        value = self._src(src, self._current).get(ATTR_FORECAST_WIND_BEARING)
        return {1: "n", 2: "ne", 3: "e", 4: "se", 5: "s", 6: "sw", 7: "w", 8: "nw"}.get(value)

    def wind_gust_speed(self, src: dict | None = None) -> float | None:
        return self._src(src, self._current).get(ATTR_FORECAST_NATIVE_WIND_GUST_SPEED)

    def wind_speed(self, src: dict | None = None) -> float | None:
        return self._src(src, self._current).get(ATTR_FORECAST_NATIVE_WIND_SPEED)

    def precipitation_type(self, src: dict | None = None) -> str | None:
        value = self._src(src, self._current).get(ATTR_FORECAST_PRECIPITATION_TYPE)
        return {0: "none", 1: "rain", 2: "snow", 3: "snow-rain"}.get(value)

    def precipitation_amount(self, src: dict | None = None) -> float | None:
        return self._src(src, self._current).get(ATTR_FORECAST_PRECIPITATION_AMOUNT)

    def precipitation_intensity(self, src: dict | None = None) -> str | None:
        value = self._src(src, self._current).get(ATTR_FORECAST_PRECIPITATION_INTENSITY)
        return {0: "none", 1: "small", 2: "normal", 3: "heavy"}.get(value)

    def cloud_coverage(self, src: dict | None = None) -> float | None:
        value = self._src(src, self._current).get(ATTR_FORECAST_CLOUD_COVERAGE)
        if value is None:
            return None
        # Provider code 101 does not encode a measured percent; do not assume 50%.
        return None if value == 101 or not 0 <= value <= 3 else round(value * 100 / 3)

    def _precip_by_type(self, src: dict | None, types: tuple[int, ...]) -> float | None:
        values = self._src(src, self._current)
        kind = values.get(ATTR_FORECAST_PRECIPITATION_TYPE)
        if kind is None:
            return None
        if kind not in types:
            return 0.0
        measured = values.get(ATTR_FORECAST_PRECIPITATION_AMOUNT)
        if measured is not None:  # Zero is a valid measured quantity.
            return measured
        strength = values.get(ATTR_FORECAST_PRECIPITATION_INTENSITY)
        # Provider intensity is categorical, not a measured volume in mm.
        # Do not invent precipitation amounts by translating categories.
        return None

    def rain_amount(self, src: dict | None = None) -> float | None:
        return self._precip_by_type(src, (1, 3))

    def snow_amount(self, src: dict | None = None) -> float | None:
        return self._precip_by_type(src, (2, 3))

    def is_storm(self, src: dict | None = None) -> bool | None:
        return self._src(src, self._current).get(ATTR_FORECAST_IS_STORM)

    def geomagnetic_field(self, src: dict | None = None) -> int | None:
        return self._src(src, self._current).get(ATTR_FORECAST_GEOMAGNETIC_FIELD)

    def _daily(self, src: dict | None) -> dict[str, Any]:
        """Do not substitute tomorrow's forecast for today's observation."""
        if src is not None:
            return src
        observed = self._current.get(ATTR_FORECAST_TIME)
        if not isinstance(observed, datetime):
            return {}
        for row in self._forecast_daily:
            timestamp = row.get(ATTR_FORECAST_TIME)
            if isinstance(timestamp, datetime) and timestamp.date() == observed.date():
                return row
        return {}

    def pollen_birch(self, src: dict | None = None) -> int | None:
        return self._daily(src).get(ATTR_FORECAST_POLLEN_BIRCH)

    def pollen_grass(self, src: dict | None = None) -> int | None:
        return self._daily(src).get(ATTR_FORECAST_POLLEN_GRASS)

    def pollen_ragweed(self, src: dict | None = None) -> int | None:
        return self._daily(src).get(ATTR_FORECAST_POLLEN_RAGWEED)

    def uv_index(self, src: dict | None = None) -> float | None:
        return self._daily(src).get(ATTR_FORECAST_UV_INDEX)

    def road_condition(self, src: dict | None = None) -> str | None:
        road = self._daily(src).get(ATTR_FORECAST_ROAD_CONDITION)
        return {
            "Нет данных": None, "Сухая дорога": "dry",
            "Вода": "water", "Влажная дорога": "wet",
        }.get(road, road if isinstance(road, str) else None)

    def _filtered_forecasts(self, mode: str) -> list[dict[str, Any]]:
        rows = self._forecast_hourly if mode == ForecastMode.HOURLY else self._forecast_daily
        if not rows:
            return []
        now = datetime.now(rows[0][ATTR_FORECAST_TIME].tzinfo)
        if mode == ForecastMode.DAILY:
            return [row for row in rows if row[ATTR_FORECAST_TIME].date() >= now.date()]
        # Include the current hour, not an arbitrarily old observation.
        cutoff = now - _HOUR
        return [row for row in rows if row[ATTR_FORECAST_TIME] >= cutoff]

    def forecast_data(self, pos: int, mode: str = ForecastMode.HOURLY) -> dict[str, Any]:
        """Select a forecast consistently with the weather entity."""
        forecast = self._filtered_forecasts(mode)
        return forecast[pos] if 0 <= pos < len(forecast) else {}

    def forecast(self, mode: str = ForecastMode.HOURLY) -> list[GismeteoForecast]:
        """Return native-unit forecasts with missing values omitted."""
        result: list[GismeteoForecast] = []
        for row in self._filtered_forecasts(mode):
            mapped = {
                ATTR_FORECAST_TIME: row[ATTR_FORECAST_TIME].isoformat(),
                ATTR_FORECAST_IS_DAYTIME: row.get(ATTR_FORECAST_IS_DAYTIME),
                ATTR_FORECAST_CONDITION: self.condition(row, mode),
                ATTR_FORECAST_NATIVE_TEMP: self.temperature(row),
                ATTR_FORECAST_NATIVE_TEMP_LOW: self.templow(row) if mode == ForecastMode.DAILY else None,
                ATTR_FORECAST_NATIVE_APPARENT_TEMP: self.apparent_temperature(row),
                ATTR_FORECAST_NATIVE_PRESSURE: self.pressure(row),
                ATTR_FORECAST_HUMIDITY: self.humidity(row),
                ATTR_FORECAST_WIND_BEARING: self.wind_bearing(row),
                ATTR_FORECAST_NATIVE_WIND_SPEED: self.wind_speed(row),
                ATTR_FORECAST_NATIVE_WIND_GUST_SPEED: self.wind_gust_speed(row),
                ATTR_FORECAST_CLOUD_COVERAGE: self.cloud_coverage(row),
                ATTR_FORECAST_NATIVE_PRECIPITATION: self.precipitation_amount(row),
                ATTR_FORECAST_UV_INDEX: self.uv_index(row),
                "dew_point": self.dew_point(row),
                ATTR_FORECAST_PRECIPITATION_TYPE: self.precipitation_type(row),
                ATTR_FORECAST_PRECIPITATION_INTENSITY: self.precipitation_intensity(row),
                ATTR_FORECAST_WIND_BEARING_LABEL: self.wind_bearing_label(row),
                ATTR_FORECAST_ROAD_CONDITION: self.road_condition(row),
            }
            result.append({key: value for key, value in mapped.items() if value is not None})
        return result
