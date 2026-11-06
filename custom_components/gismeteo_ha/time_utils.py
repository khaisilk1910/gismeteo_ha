# Copyright (c) 2019-2024, Andrey "Limych" Khrolenok
# Original work licensed under CC BY-NC-SA 4.0; see repository LICENSE.
"""Local display of instants using the time zone configured in Home Assistant.

Keep the original timezone-aware datetime values untouched for sensor and
forecast calculations.  Only convert a copy when rendering display attributes.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def local_isoformat(value: datetime | None, time_zone: str) -> str | None:
    """Render an instant in HA's IANA time zone, preserving its UTC offset.

    Never assign a time zone with ``replace(tzinfo=...)``: it changes the
    instant represented by an existing timestamp.  We intentionally leave
    invalid/missing configurations and naive datetimes unchanged instead of
    guessing their origin.
    """
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    try:
        return value.astimezone(ZoneInfo(time_zone)).isoformat()
    except (ZoneInfoNotFoundError, ValueError, TypeError, KeyError):
        return value.isoformat()
