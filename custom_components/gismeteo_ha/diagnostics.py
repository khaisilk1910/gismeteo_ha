"""Redacted diagnostics for the Gismeteo HA integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant

from .const import COORDINATOR, DOMAIN, DOMAIN_YAML


def _coordinator_diagnostics(coordinator: Any) -> dict[str, Any]:
    client = coordinator.gismeteo
    return {
        "last_update_success": coordinator.last_update_success,
        "last_success_utc": (
            client.last_success.isoformat() if client.last_success else None
        ),
        "last_error": client.last_error,
        "last_enrichment_error": client.last_enrichment_error,
        "observation_valid_time": (
            client.current_data["datetime"].isoformat()
            if client.current_data.get("datetime") else None
        ),
        "data_source": client.source,
        "cache_age_seconds": round(client.cache_age, 1) if client.cache_age is not None else None,
        "hourly_items": len(client._forecast_hourly),
        "daily_items": len(client._forecast_daily),
        "extended_data_enabled": client.extended_data,
        "visibility_available": client.visibility() is not None,
        "available_measurements": sorted(
            key for key, value in client.current_data.items() if value is not None
        ),
        "has_website_forecast": bool(client._parsed),
        "polling_seconds": int(coordinator.update_interval.total_seconds()),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Expose status, not coordinates, cache payloads, or exact request URLs."""
    if entry.source == SOURCE_IMPORT:
        keys = hass.data.get(DOMAIN_YAML, {})
        return {
            "integration": "Gismeteo HA",
            "config_source": "configuration.yaml",
            "locations": {
                key: _coordinator_diagnostics(hass.data[DOMAIN][key][COORDINATOR])
                for key in keys if key in hass.data.get(DOMAIN, {})
            },
        }
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get(COORDINATOR)
    return {
        "integration": "Gismeteo HA",
        "config_source": "ui",
        "status": _coordinator_diagnostics(coordinator) if coordinator else "not_loaded",
    }
