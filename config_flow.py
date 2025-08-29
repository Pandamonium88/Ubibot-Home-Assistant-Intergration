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

class UbibotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

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

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is None:
            schema = vol.Schema({vol.Required(CONF_ACCOUNT_KEY): str})
            return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

        account_key = user_input[CONF_ACCOUNT_KEY]
        session = async_get_clientsession(self.hass)
        try:
            channels = await self._fetch_channels(session, account_key)
        except Exception as e:
            _LOGGER.exception("Failed to fetch channels: %s", e)
            errors["base"] = "cannot_connect"
            schema = vol.Schema({vol.Required(CONF_ACCOUNT_KEY, default=account_key): str})
            return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

        self._account_key = account_key
        self._all_channels = channels

        choices = {c["channel_id"]: c["name"] for c in channels}
        default_all = list(choices.keys())
        schema = vol.Schema({
            vol.Required(CONF_CHANNELS, default=default_all): cv.multi_select(choices)
        })
        return self.async_show_form(step_id="select_channels", data_schema=schema)

    async def async_step_select_channels(self, user_input=None):
        if user_input is None:
            return await self.async_step_user()

        raw = user_input[CONF_CHANNELS]
        if isinstance(raw, dict):
            selected_ids = [cid for cid, enabled in raw.items() if enabled] or list(raw.keys())
        else:
            selected_ids = [str(cid) for cid in raw] or [c["channel_id"] for c in self._all_channels]
        self._selected_ids = selected_ids

        poll_schema_fields = {}
        for ch in self._all_channels:
            cid = ch["channel_id"]
            if cid in self._selected_ids:
                poll_schema_fields[vol.Required(f"poll_{cid}", default=DEFAULT_POLL_SECONDS)] = vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_POLL_SECONDS, max=MAX_POLL_SECONDS)
                )

        return self.async_show_form(step_id="poll_intervals", data_schema=vol.Schema(poll_schema_fields))

    async def async_step_poll_intervals(self, user_input=None):
        self._poll_map = {}
        for key, val in user_input.items():
            if key.startswith("poll_"):
                cid = key.split("poll_", 1)[1]
                self._poll_map[cid] = int(val)

        self._sensor_labels = {}
        by_id = {c["channel_id"]: c for c in self._all_channels}
        for cid in self._selected_ids:
            self._sensor_labels[cid] = self._labels_from_cached_channel(by_id[cid])

        fields = {}
        for cid, labels in self._sensor_labels.items():
            display = _display_from_labels(labels)
            fields[vol.Required(f"sensors_{cid}", default=list(display.keys()))] = cv.multi_select(display)

        return self.async_show_form(step_id="select_sensors", data_schema=vol.Schema(fields))

    async def async_step_select_sensors(self, user_input=None):
        sensor_map = {}
        for key, val in user_input.items():
            if key.startswith("sensors_"):
                cid = key.split("sensors_", 1)[1]
                if isinstance(val, dict):
                    selected = [k for k, enabled in val.items() if enabled]
                else:
                    selected = [str(k) for k in (val or [])]
                sensor_map[cid] = [str(v).lower() for v in selected]

        slim_channels = [
            {"channel_id": ch["channel_id"], "name": ch["name"]}
            for ch in self._all_channels if ch["channel_id"] in self._selected_ids
        ]

        data = {CONF_ACCOUNT_KEY: self._account_key, CONF_CHANNELS: slim_channels}
        options = {CONF_POLL_MAP: self._poll_map, CONF_SENSOR_MAP: sensor_map}

        return self.async_create_entry(title="Ubibot", data=data, options=options)
