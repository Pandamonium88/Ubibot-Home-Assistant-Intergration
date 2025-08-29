"""Ubibot integration with preflight refresh (uses /channels/list only)."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, DEFAULT_POLL_SECONDS
from .coordinator import UbibotCoordinator
from .options_flow import UbibotOptionsFlow

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "number", "switch"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ubibot entry and preflight coordinators to avoid forwarded platform errors."""
    hass.data.setdefault(DOMAIN, {})
    store = hass.data[DOMAIN][entry.entry_id] = {
        "channels": entry.data.get("channels", []),
        "poll_map": dict(entry.options.get("poll_map", {})),
        "sensor_map": dict(entry.options.get("sensor_map", {})),
        "coordinators": {},
    }

    session = async_get_clientsession(hass)
    account_key: str = entry.data.get("account_key")

    for ch in store["channels"]:
        channel_id = str(ch.get("channel_id"))
        channel_name = ch.get("name") or channel_id
        seconds = int(store["poll_map"].get(channel_id, DEFAULT_POLL_SECONDS))

        coord = UbibotCoordinator(
            hass=hass,
            session=session,
            account_key=account_key,
            channel_id=channel_id,
            channel_name=channel_name,
            update_interval=timedelta(seconds=seconds),
        )
        try:
            await coord.async_config_entry_first_refresh()
        except Exception as err:
            _LOGGER.warning("Initial refresh failed for channel %s (%s): %s", channel_name, channel_id, err)
            raise ConfigEntryNotReady(str(err)) from err

        store["coordinators"][channel_id] = coord

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded

async def async_get_options_flow(config_entry: ConfigEntry):
    """Return the options flow handler."""
    return UbibotOptionsFlow(config_entry)
