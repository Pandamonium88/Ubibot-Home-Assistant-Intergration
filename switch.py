"""Ubibot SP1 switch entity (only for product_id 'ubibot-sp1a')."""
from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import ClientError
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, API_BASE

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Create an on/off switch for SP1 devices only."""
    store = hass.data[DOMAIN][entry.entry_id]
    channels = store.get("channels", [])
    coordinators = store.get("coordinators", {})

    entities: list[SwitchEntity] = []

    for ch in channels:
        channel_id = str(ch.get("channel_id"))
        channel_name = ch.get("name") or channel_id
        coord = coordinators.get(channel_id)
        if not coord:
            continue

        product_id = ((coord.data or {}).get("channel") or {}).get("product_id")
        if str(product_id).lower() != "ubibot-sp1a":
            continue

        entities.append(UbibotSP1Switch(coord))

    if entities:
        async_add_entities(entities, update_before_add=False)

class UbibotSP1Switch(CoordinatorEntity, SwitchEntity):
    """Switch entity controlling an SP1 smart plug (single port: port1)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "Switch"
        self._attr_unique_id = f"{DOMAIN}_{coordinator.channel_id}_sp1_switch"
        # Optimistic state; will be refined after a refresh
        self._is_on = None

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.channel_id)},
            "name": self.coordinator.channel_name,
            "manufacturer": "Ubibot",
            "model": "SP1",
        }

    @property
    def is_on(self) -> bool | None:
        # Try to infer from last_values if present
        ch = (self.coordinator.data or {}).get("channel") or {}
        lv = ch.get("last_values")
        try:
            if isinstance(lv, str):
                lv = json.loads(lv)
        except Exception:
            lv = None
        if isinstance(lv, dict):
            # Heuristics: common keys we might see reflecting current relay state
            for k in ("port1_state", "switch", "relay", "sp1_state", "switch_state"):
                if k in lv:
                    v = lv.get(k)
                    if isinstance(v, (int, float)):
                        return bool(int(v))
                    if isinstance(v, str):
                        return v.lower() in ("on", "1", "true", "enabled")
        return self._is_on

    async def _send_command(self, set_state: int) -> None:
        """POST Add Command API: /channels/{id}/commands?account_key=...&command_string=..."""
        url = f"{API_BASE}/channels/{self.coordinator.channel_id}/commands"
        params = {
            "account_key": self.coordinator.account_key,
            "command_string": json.dumps({"action": "command", "set_state": int(set_state), "s_port": "port1"}),
        }
        try:
            async with self.coordinator.session.post(url, params=params, timeout=20) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}: {text[:200]}")
                _LOGGER.debug("SP1 command OK for %s -> %s; response: %s",
                              self.coordinator.channel_id, set_state, text[:200])
        except (ClientError, Exception) as err:
            raise RuntimeError(f"Failed to send SP1 command: {err}") from err

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send_command(1)
        self._is_on = True  # optimistic
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send_command(0)
        self._is_on = False  # optimistic
        await self.coordinator.async_request_refresh()
