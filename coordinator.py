"""Shared DataUpdateCoordinator for Ubibot channels (polls via /channels/list)."""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from aiohttp import ClientSession, ClientError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant

from .const import API_BASE

_LOGGER = logging.getLogger(__name__)

class UbibotCoordinator(DataUpdateCoordinator[dict[str, Any] | None]):
    """Coordinator that polls a single channel (device) by reusing /channels/list."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        account_key: str,
        channel_id: str,
        channel_name: str,
        update_interval: timedelta,
    ) -> None:
        self.session = session
        self.account_key = account_key
        self.channel_id = channel_id
        self.channel_name = channel_name
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=f"Ubibot {channel_name} ({channel_id})",
            update_interval=update_interval,
        )

    async def _async_update_data(self):
        import asyncio
        url = f"{API_BASE}/channels/list?account_key={self.account_key}"
        try:
            async with self.session.get(url, timeout=20) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise UpdateFailed(f"HTTP {resp.status}: {text[:200]}")
                data = await resp.json()
                chans = data.get("channels", [])
                channel = None
                for c in chans:
                    cid = str(c.get("channel_id") or c.get("id") or "")
                    if cid == self.channel_id:
                        channel = c
                        break
                if channel is None:
                    raise UpdateFailed(f"Channel {self.channel_id} not found in list")
                lv = channel.get("last_values")
                if isinstance(lv, str):
                    try:
                        channel["last_values"] = json.loads(lv)
                    except Exception:
                        channel["last_values"] = {}
                return {"channel": channel}
        except (ClientError, asyncio.TimeoutError) as err:
            raise UpdateFailed(err) from err
        except Exception as err:
            raise UpdateFailed(err) from err
