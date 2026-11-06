# Changelog

## 4.0.1

- Render `gismeteo_last_refresh`, `gismeteo_sunrise` and `gismeteo_sunset` in the Home Assistant configured time zone instead of mixing UTC and provider offsets.
- Align the Lovelace card forecast and update clock with the Home Assistant time zone, independently of browser time zone.
- Preserve timezone-aware source instants and timestamp sensor semantics; no change to polling or startup behavior.


## 4.0.0 (2026-11-05)

- **Breaking:** Domain and folder renamed from `gismeteo` to `gismeteo_ha`; existing entries must be reconfigured.
- Bundled custom Lovelace card, visual editor, detailed and compact display, live forecast subscriptions, and resource auto-registration for Lovelace storage mode.
- Added visibility (source + explicit unit only), calculated dew point, sunrise and sunset sensors, plus data source/diagnostics indicators.
- Updated Home Assistant 2026.11 device metadata and Marketplace release workflow; added custom brand icon.
- Preserved async forecast coordinator, safe bounded caching, optional provider enrichment and diagnostic logs.
