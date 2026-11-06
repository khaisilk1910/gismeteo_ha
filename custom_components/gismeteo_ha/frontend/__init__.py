"""Serve and auto-register the bundled dashboard card.

Only the bundled JavaScript file is publicly accessible. There are no tokens,
coordinates, or configuration secrets in this static module.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from ..const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)
URL = f"/{DOMAIN}/gismeteo-ha-card.js"
RESOURCE_URL = f"{URL}?v={VERSION}"


async def async_register_card(hass: HomeAssistant) -> None:
    """Register static resource once and insert into Lovelace storage resources."""
    resource_state = hass.data.setdefault(f"{DOMAIN}_card_registration", {})
    if not resource_state.get("http"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL, Path(__file__).parent / "gismeteo-ha-card.js", False)]
        )
        resource_state["http"] = True

    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None:
        _LOGGER.info("Gismeteo HA card: no Lovelace storage; manually add %s", RESOURCE_URL)
        return
    # YAML resources cannot be edited by custom integrations.
    if getattr(resources, "loaded", False) is False:
        try:
            await resources.async_load()
        except (AttributeError, RuntimeError, OSError) as exc:
            _LOGGER.warning("Card resource collection not ready: %s", exc)
            return
    try:
        existing = [item for item in resources.async_items()
                    if item.get("url", "").split("?", 1)[0] == URL]
        if existing:
            for item in existing:
                if item.get("url") != RESOURCE_URL or item.get("res_type") != "module":
                    await resources.async_update_item(item["id"], {
                        "url": RESOURCE_URL, "res_type": "module",
                    })
                    _LOGGER.info("Updated Gismeteo HA card module to %s", VERSION)
        else:
            await resources.async_create_item({"url": RESOURCE_URL, "res_type": "module"})
            _LOGGER.info("Registered Gismeteo HA Lovelace card v%s", VERSION)
    except (AttributeError, RuntimeError, TypeError, ValueError, OSError) as exc:
        # Resource registration is optional; never block weather data.
        _LOGGER.warning(
            "Unable to register Lovelace resource (%s). Add module URL manually: %s",
            exc, RESOURCE_URL,
        )
