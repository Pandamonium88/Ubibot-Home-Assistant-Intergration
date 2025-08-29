"""Ubibot number entities: per-device poll interval control (coordinators preloaded in __init__)."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.number import NumberEntity, NumberDeviceClass
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_POLL_MAP, MIN_POLL_SECONDS, MAX_POLL_SECONDS, DEFAULT_POLL_SECONDS

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up Ubibot number entities (poll interval) from a config entry."""
    store = hass.data[DOMAIN][entry.entry_id]
    channels = store.get("channels", [])
    poll_map: dict[str, int] = store.get("poll_map", {})
    coordinators = store.get("coordinators", {})

    numbers: list[NumberEntity] = []

    for ch in channels:
        channel_id = str(ch.get("channel_id"))
        channel_name = ch.get("name") or channel_id
        interval = int(poll_map.get(channel_id, DEFAULT_POLL_SECONDS))

        coord = coordinators.get(channel_id)
        if coord is None:
            continue

        numbers.append(UbibotPollNumber(hass, entry, coord, channel_id, channel_name))

    async_add_entities(numbers, update_before_add=False)

class UbibotPollNumber(NumberEntity):
    """Device-level number to control the channel's polling interval (seconds)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = "s"
    _attr_native_min_value = MIN_POLL_SECONDS
    _attr_native_max_value = MAX_POLL_SECONDS
    _attr_native_step = 5

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, coordinator, channel_id: str, channel_name: str) -> None:
        super().__init__()
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self._channel_id = channel_id
        self._attr_name = f"{channel_name} Poll Interval"
        self._attr_unique_id = f"{DOMAIN}_{channel_id}_poll_seconds"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.channel_id)},
            "name": self.coordinator.channel_name,
            "manufacturer": "Ubibot",
            "model": "Channel",
        }

    @property
    def native_value(self) -> float | None:
        interval = getattr(self.coordinator, "update_interval", None)
        if interval is None:
            return None
        try:
            return float(interval.total_seconds())
        except Exception:
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Apply immediately; persist in the background to avoid awaiting a possibly sync API."""
        try:
            seconds = max(MIN_POLL_SECONDS, min(MAX_POLL_SECONDS, int(value)))
        except Exception:
            seconds = MIN_POLL_SECONDS

        # 1) Apply live
        self.coordinator.update_interval = timedelta(seconds=seconds)

        # 2) Persist options in a background task (do not await here)
        self.hass.async_create_task(self._persist_options(seconds))

        # 3) Best-effort refresh
        await self.coordinator.async_request_refresh()

    async def _persist_options(self, seconds: int) -> None:
        """Persist per-channel poll seconds to the config entry options."""
        options = dict(self.entry.options or {})
        poll_map = dict(options.get(CONF_POLL_MAP, {}))
        poll_map[self._channel_id] = int(seconds)
        options[CONF_POLL_MAP] = poll_map
        await self.hass.config_entries.async_update_entry(self.entry, options=options)
