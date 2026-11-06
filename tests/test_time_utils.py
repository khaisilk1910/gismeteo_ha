"""Check time-zone conversion without requiring Home Assistant to be installed."""

from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


source = Path(__file__).resolve().parents[1] / 'custom_components/gismeteo_ha/time_utils.py'
spec = spec_from_file_location('gismeteo_ha_time_utils_test', source)
module = module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
local_isoformat = module.local_isoformat


def test_local_refresh_conversion_to_vietnam():
    original = datetime.fromisoformat('2026-11-05T08:29:03.346773+00:00')
    assert local_isoformat(original, 'Asia/Ho_Chi_Minh') == '2026-11-05T15:29:03.346773+07:00'
    assert original.isoformat() == '2026-11-05T08:29:03.346773+00:00'


def test_sunrise_and_sunset_in_existing_local_timezone():
    sunrise = datetime.fromisoformat('2026-11-05T13:01:05+07:00')
    sunset = datetime.fromisoformat('2026-11-06T19:19:01+07:00')
    assert local_isoformat(sunrise, 'Asia/Ho_Chi_Minh') == sunrise.isoformat()
    assert local_isoformat(sunset, 'Asia/Ho_Chi_Minh') == sunset.isoformat()


def test_other_iana_timezone_and_dst():
    summer = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    winter = datetime(2026, 12, 1, 12, tzinfo=timezone.utc)
    assert local_isoformat(summer, 'America/New_York') == '2026-07-01T08:00:00-04:00'
    assert local_isoformat(winter, 'America/New_York') == '2026-12-01T07:00:00-05:00'


def test_utc_and_negative_offset():
    source = datetime(2026, 11, 5, 13, 1, 5, tzinfo=timezone(timedelta(hours=7)))
    assert local_isoformat(source, 'UTC') == '2026-11-05T06:01:05+00:00'


def test_absent_naive_or_unknown_timezone():
    assert local_isoformat(None, 'Asia/Ho_Chi_Minh') is None
    assert local_isoformat(datetime(2026, 11, 5, 8), 'Asia/Ho_Chi_Minh') is None
    original = datetime(2026, 11, 5, 8, tzinfo=timezone.utc)
    assert local_isoformat(original, 'Not/A_Real_Zone') == original.isoformat()
