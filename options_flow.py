from __future__ import annotations

import logging
import re
import voluptuous as vol
from aiohttp import ClientSession, ClientError
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN, CONF_ACCOUNT_KEY, CONF_CHANNELS, CONF_POLL_MAP, CONF_SENSOR_MAP,
    API_BASE, DEFAULT_POLL_SECONDS, MIN_POLL_SECONDS, MAX_POLL_SECONDS, KNOWN_FIELDS
)

_LOGGER = logging.getLogger(__name__)
_FIELD_RE = re.compile(r"^field(\d{1,2})$", re.IGNORECASE)

def _canon(key: str | None) -> str | None:
    if not key: return None
    m = _FIELD_RE.match(str(key).strip())
    if not m: return None
    return f"field{int(m.group(1))}"

def _display_from_labels(labels: dict[str, str]) -> dict[str, str]:
    return {k: (v or k).title() for k, v in labels.items()}

class UbibotOptionsFlow(config_entries.OptionsFlow):
    """Allow changing channels, per-channel polling and sensor selection after setup."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry
        self._new_channels = None
        self._selected_ids = None
        self._new_poll_map = {}

    async def _fetch_json(self, session: ClientSession, url: str):
        async with session.get(url, timeout=20) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"HTTP {resp.status}: {text[:200]}")
            return await resp.json()

    async def _fetch_channels(self, session: ClientSession, account_key: str):
        url = f"{API_BASE}/channels/list?account_key={account_key}"
        data = await self._fetch_json(session, url)
        raw = data.get("channels", [])
        channels = []
        for c in raw:
            cid = str(c.get("channel_id") or c.get("id") or "")
            if not cid:
                continue
            channels.append({"channel_id": cid, "name": c.get("name") or cid, "_raw": c})
        return channels

    def _labels_from_cached_channel(self, ch: dict) -> dict[str, str]:
        labels = {}
        raw = ch.get("_raw", {})
        for k, v in raw.items():
            ck = _canon(k)
            if ck and isinstance(v, str) and v.strip():
                labels[ck] = v.strip()
        lv = raw.get("last_values")
        if isinstance(lv, str):
            import json as _json
            try:
                lv = _json.loads(lv)
            except Exception:
                lv = {}
        if isinstance(lv, dict):
            for k in lv.keys():
                ck = _canon(k)
                if ck and ck not in labels and ck in KNOWN_FIELDS:
                    labels[ck] = ck
        if not labels:
            labels = {f: f for f in KNOWN_FIELDS[:10]}
        return labels

    async def async_step_init(self, user_input=None):
        session = async_get_clientsession(self.hass)
        account_key = self.entry.data.get(CONF_ACCOUNT_KEY)
        all_channels = await self._fetch_channels(session, account_key)

        current = [str(c.get("channel_id")) for c in self.entry.data.get(CONF_CHANNELS, [])]
        choices = {c["channel_id"]: c["name"] for c in all_channels}

        if user_input is not None:
            raw = user_input[CONF_CHANNELS]
            if isinstance(raw, dict):
                self._selected_ids = [cid for cid, enabled in raw.items() if enabled] or list(raw.keys())
            else:
                self._selected_ids = [str(cid) for cid in raw] or list(choices.keys())
            self._new_channels = [
                {"channel_id": c["channel_id"], "name": c["name"], "_raw": c.get("_raw")}
                for c in all_channels if c["channel_id"] in self._selected_ids
            ]
            return await self.async_step_polls()

        schema = vol.Schema({
            vol.Required(CONF_CHANNELS, default=current or list(choices.keys())): cv.multi_select(choices)
        })
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_polls(self, user_input=None):
        fields = {}
        poll_map = dict(self.entry.options.get(CONF_POLL_MAP, {}))
        for ch in self._new_channels:
            cid = ch["channel_id"]
            default = int(poll_map.get(cid, DEFAULT_POLL_SECONDS))
            fields[vol.Required(f"poll_{cid}", default=default)] = vol.All(
                vol.Coerce(int), vol.Range(min=MIN_POLL_SECONDS, max=MAX_POLL_SECONDS)
            )

        if user_input is not None:
            self._new_poll_map = {}
            for key, val in user_input.items():
                if key.startswith("poll_"):
                    cid = key.split("poll_", 1)[1]
                    self._new_poll_map[cid] = int(val)
            return await self.async_step_sensors()

        return self.async_show_form(step_id="polls", data_schema=vol.Schema(fields))

    async def async_step_sensors(self, user_input=None):
        fields = {}
        for ch in self._new_channels:
            cid = ch["channel_id"]
            labels = self._labels_from_cached_channel(ch)
            display = _display_from_labels(labels)
            current = self.entry.options.get(CONF_SENSOR_MAP, {}).get(cid)
            default_keys = list(display.keys() if current is None else current)
            fields[vol.Required(f"sensors_{cid}", default=default_keys)] = cv.multi_select(display)

        if user_input is not None:
            new_sensor_map = {}
            for key, val in user_input.items():
                if key.startswith("sensors_"):
                    cid = key.split("sensors_", 1)[1]
                    if isinstance(val, dict):
                        selected = [k for k, enabled in val.items() if enabled]
                    else:
                        selected = [str(k) for k in (val or [])]
                    new_sensor_map[cid] = [str(v).lower() for v in selected]

            new_data = dict(self.entry.data)
            new_data[CONF_CHANNELS] = [{"channel_id": c["channel_id"], "name": c["name"]} for c in self._new_channels]
            new_options = dict(self.entry.options)
            new_options[CONF_POLL_MAP] = self._new_poll_map
            new_options[CONF_SENSOR_MAP] = new_sensor_map
            self.hass.config_entries.async_update_entry(self.entry, data=new_data, options=new_options)
            return self.async_create_entry(title="", data={})

        return self.async_show_form(step_id="sensors", data_schema=vol.Schema(fields))
