"""Provider regression tests that also work without Home Assistant installed.

Run: python -m pytest -q tests/test_provider_offline.py
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import TypedDict


class _Description:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _load_api():
    """Load actual provider modules under a test-only package with tiny HA stubs."""
    components = Path(__file__).resolve().parents[1] / "custom_components" / "gismeteo_ha"
    prefix = "_gismeteo_ha_test"
    for name in tuple(sys.modules):
        if name == prefix or name.startswith(prefix + "."):
            del sys.modules[name]
    package = types.ModuleType(prefix)
    package.__path__ = [str(components)]
    sys.modules[prefix] = package

    def create(name, props):
        module = types.ModuleType(name)
        module.__dict__.update(props)
        sys.modules[name] = module
        return module

    # Provide only the public HA constants used by const.py and api.py.
    weather_constants = {
        "ATTR_FORECAST_NATIVE_APPARENT_TEMP": "native_apparent_temperature",
        "ATTR_FORECAST_NATIVE_TEMP": "native_temperature",
        "ATTR_FORECAST_NATIVE_TEMP_LOW": "native_templow",
        "ATTR_FORECAST_NATIVE_PRESSURE": "native_pressure",
        "ATTR_FORECAST_NATIVE_WIND_SPEED": "native_wind_speed",
        "ATTR_FORECAST_NATIVE_WIND_GUST_SPEED": "native_wind_gust_speed",
        "ATTR_FORECAST_NATIVE_PRECIPITATION": "native_precipitation",
        "ATTR_FORECAST_TIME": "datetime",
        "ATTR_FORECAST_IS_DAYTIME": "is_daytime",
    }
    for key in (
        "ATTR_FORECAST_APPARENT_TEMP", "ATTR_FORECAST_CLOUD_COVERAGE",
        "ATTR_FORECAST_CONDITION", "ATTR_FORECAST_HUMIDITY",
        "ATTR_FORECAST_PRESSURE", "ATTR_FORECAST_TEMP", "ATTR_FORECAST_TEMP_LOW",
        "ATTR_FORECAST_WIND_BEARING", "ATTR_FORECAST_WIND_GUST_SPEED",
        "ATTR_FORECAST_WIND_SPEED", "ATTR_FORECAST_UV_INDEX",
    ):
        weather_constants[key] = key.replace("ATTR_FORECAST_", "").lower()
    for condition in (
        "CLEAR_NIGHT", "CLOUDY", "FOG", "LIGHTNING", "LIGHTNING_RAINY",
        "PARTLYCLOUDY", "POURING", "RAINY", "SNOWY", "SNOWY_RAINY",
        "SUNNY", "WINDY", "WINDY_VARIANT",
    ):
        weather_constants["ATTR_CONDITION_" + condition] = condition.lower().replace("_", "-")
    weather_constants["Forecast"] = TypedDict("Forecast", {}, total=False)

    class _DynamicEnum:
        def __getattr__(self, key):
            return key.lower()

    create("homeassistant", {})
    create("homeassistant.components", {})
    create("homeassistant.components.weather", weather_constants)
    create("homeassistant.components.sensor", {
        "SensorDeviceClass": _DynamicEnum(),
        "SensorStateClass": _DynamicEnum(),
        "SensorEntityDescription": _Description,
    })
    create("homeassistant.const", {
        **{key: value for key, value in (
            ("DEGREE", "°"), ("PERCENTAGE", "%"),
            ("ATTR_ID", "id"), ("ATTR_LATITUDE", "latitude"),
            ("ATTR_LONGITUDE", "longitude"), ("CONF_SHOW_ON_MAP", "show_on_map")
        )},
        "Platform": SimpleNamespace(SENSOR="sensor", WEATHER="weather"),
        "UnitOfPrecipitationDepth": SimpleNamespace(MILLIMETERS="mm"),
        "UnitOfPressure": SimpleNamespace(MMHG="mmHg"),
        "UnitOfSpeed": SimpleNamespace(METERS_PER_SECOND="m/s"),
        "UnitOfTemperature": SimpleNamespace(CELSIUS="°C"),
    })
    return importlib.import_module(prefix + ".api"), importlib.import_module(prefix + ".cache")


class _Response:
    def __init__(self, payload, status=200):
        self.status = status
        self.charset = "utf-8"
        self._payload = payload.encode()
        self.content_length = len(self._payload)
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def read(self, n):
        return self._payload[:n]


class _Session:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        return self.responses.pop(0)


def _example_xml():
    zone = timezone(timedelta(hours=7))
    now = datetime.now(zone).replace(minute=0, second=0, microsecond=0)
    days = []
    for index in range(2):
        day = (now + timedelta(days=index)).replace(hour=0)
        sunrise = int(day.replace(hour=6).timestamp())
        sunset = int(day.replace(hour=18 + index).timestamp())
        if index == 0:
            hourly = f'<forecast valid="{now.isoformat()}"><values t="30" p="760" hum="75" ws="4" wd="2" cl="0" pt="1" pr="0" prflt="0" ts="1"/></forecast>'
        else:
            hourly = f'<forecast valid="{(day + timedelta(hours=12)).isoformat()}"><values t="20" p="753" hum="70" ws="3" wd="3" cl="3" pt="0" ts="0"/></forecast>'
        days.append(
            f'<day date="{day.date()}" sunrise="{sunrise}" sunset="{sunset}" descr="cloud" tmax="{32 - index}" tmin="{24 - index}" ws="3" wd="2" cl="0" pt="0" hum="70">{hourly}</day>'
        )
    sunrise = int(now.replace(hour=6).timestamp())
    sunset = int(now.replace(hour=18).timestamp())
    return (
        '<root><location tzone="420" nowcast_url="/weather-hanoi-12345/now/" '
        f'cur_time="{now.isoformat()}">'
        f'<fact valid="{now.isoformat()}" sunrise="{sunrise}" sunset="{sunset}">'
        '<values tflt="29" p="758" hum="76" ws="4" wd="2" cl="1" pt="0" ts="0"/>'
        '</fact>' + ''.join(days) + '</location></root>'
    )


def test_decode_forecasts_and_units():
    api, _ = _load_api()
    client = api.GismeteoApiClient(_Session([_Response(_example_xml())]), 12345, 21.0285, 105.8542)
    assert asyncio.run(client.async_update())
    assert client.temperature() == 29
    assert client.pressure() == 758
    assert client.wind_bearing() == 45
    assert client.source == "network"
    assert client.is_storm() is False
    rows = client.forecast(api.ForecastMode.DAILY)
    assert len(rows) == 2
    assert rows[0]["native_temperature"] == 32
    assert rows[1]["native_temperature"] == 31
    assert rows[0]["native_templow"] == 24
    assert rows[1]["native_templow"] == 23
    assert client._forecast_daily[0]["sunset"] != client._forecast_daily[1]["sunset"]
    assert client.forecast(api.ForecastMode.HOURLY)[0]["native_precipitation"] == 0
    assert client._forecast_hourly[0]["is_storm"] is True
    assert client.wind_speed({}) is None  # Must not fall back to current weather.
    assert client.condition({}) is None
    assert client.wind_gust_speed(client._forecast_hourly[0]) is None


def test_website_enrichment_preserves_primary_data_source():
    api, _ = _load_api()
    html = '<div class="widget-row" data-row="wind-gust"><div class="row-item">9 м/с</div></div>'
    session = _Session([_Response(_example_xml()), _Response(html)])
    client = api.GismeteoApiClient(session, 12345, 21.0, 105.0)
    async def run():
        await client.async_update()
        assert await client.async_update_parsed()
    asyncio.run(run())
    assert client.wind_gust_speed(client._forecast_hourly[0]) == 9
    assert client.wind_speed(client._forecast_hourly[0]) == 4
    assert client.forecast(api.ForecastMode.HOURLY)[0]["native_wind_gust_speed"] == 9
    assert client.source == "network"
    assert len(session.calls) == 2


def test_http_error_is_non_silent():
    api, _ = _load_api()
    client = api.GismeteoApiClient(_Session([_Response("bad gateway", 503)]), 12345, 21, 105)
    try:
        asyncio.run(client.async_update())
    except api.ApiError as exc:
        assert "HTTP 503" in str(exc)
        assert "503" in (client.last_error or "")
    else:
        raise AssertionError("HTTP 503 must not be reported as valid forecast")


def test_async_cache_atomic_roundtrip(tmp_path):
    _, cache_module = _load_api()
    cache = cache_module.Cache(tmp_path / "cache")
    async def run():
        await cache.async_save("weather.xml", "<good/>")
        assert (await cache.async_read("weather.xml", 60))[0] == "<good/>"
        assert await cache.async_read("weather.xml", -1) is None
    asyncio.run(run())
    assert not list((tmp_path / "cache").glob("*.tmp"))


def test_website_failure_does_not_invalidate_core_readings():
    api, _ = _load_api()
    session = _Session([_Response(_example_xml()), _Response("error", 403)])
    client = api.GismeteoApiClient(session, 12345, 21, 105)

    async def run():
        await client.async_update()
        try:
            await client.async_update_parsed()
        except api.ApiError as exc:
            assert "403" in str(exc)
        else:
            raise AssertionError("HTTP 403 should fail optional website enrichment")

    asyncio.run(run())
    assert client.temperature() == 29
    assert len(client.forecast(api.ForecastMode.DAILY)) == 2
    assert client.last_error is None
    assert client.source == "network"


def test_bounded_stale_cache_fallback(tmp_path):
    import os
    import time

    api, _ = _load_api()
    session = _Session([_Response(_example_xml()), _Response("unavailable", 503)])
    client = api.GismeteoApiClient(
        session, 12345, 21, 105,
        params={"cache_dir": str(tmp_path), "poll_interval": 10, "stale_minutes": 30},
    )

    async def run():
        await client.async_update()
        cache_file = next(tmp_path.glob("forecast_*.xml"))
        old = time.time() - 610
        os.utime(cache_file, (old, old))
        await client.async_update()

    asyncio.run(run())
    assert client.source == "cache_stale"
    assert client.cache_age >= 600
    assert client.temperature() == 29
    assert len(session.calls) == 2


def test_bad_xml_is_never_cached(tmp_path):
    api, _ = _load_api()
    client = api.GismeteoApiClient(
        _Session([_Response("<root><unexpected /></root>")]),
        12345, 21, 105, params={"cache_dir": str(tmp_path)},
    )
    try:
        asyncio.run(client.async_update())
    except api.ApiError:
        pass
    else:
        raise AssertionError("Unexpected XML must never be accepted")
    assert not list(tmp_path.glob("*.xml"))
    assert client.current_data == {}


def test_visibility_requires_explicit_units_and_not_fabricated():
    api, _ = _load_api()
    unqualified = _example_xml().replace('hum="76"', 'hum="76" vis="11000"')
    c = api.GismeteoApiClient(_Session([_Response(unqualified)]), 12345, 21, 105)
    asyncio.run(c.async_update())
    assert c.visibility() is None
    qualified = _example_xml().replace('hum="76"', 'hum="76" visibility_m="13000"')
    c = api.GismeteoApiClient(_Session([_Response(qualified)]), 12345, 21, 105)
    asyncio.run(c.async_update())
    assert c.visibility() == 13.0
    assert c.dew_point() is not None
    assert api._visibility_text_km('5,5 км') == 5.5
    assert api._visibility_text_km('5.5') is None


def test_unknown_precipitation_intensity_never_fabricates_mm():
    api, _ = _load_api()
    xml = _example_xml().replace('cl="1" pt="0" ts="0"', 'cl="1" pt="1" pr="3" ts="0"')
    c = api.GismeteoApiClient(_Session([_Response(xml)]), 12345, 21, 105)
    asyncio.run(c.async_update())
    assert c.rain_amount() is None
    assert c.precipitation_amount() is None


def test_current_sensor_does_not_use_future_day_uv():
    api, _ = _load_api()
    c = api.GismeteoApiClient(_Session([_Response(_example_xml())]), 12345, 21, 105)
    asyncio.run(c.async_update())
    from datetime import timedelta
    c._forecast_daily = [c._forecast_daily[1]]
    c._forecast_daily[0]['uv_index'] = 9
    assert c.uv_index() is None


def test_html_gust_requires_unit():
    api, _ = _load_api()
    assert api._wind_text_mps("9") is None
    assert api._wind_text_mps("36 km/h") == 10.0
    assert api._wind_text_mps("9 м/с") == 9.0
