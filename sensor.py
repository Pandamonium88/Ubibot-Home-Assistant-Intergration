"""Ubibot sensors with units & device classes inferred from labels (fixes Recorder warnings)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Tuple

from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, KNOWN_FIELDS

_LOGGER = logging.getLogger(__name__)
_FIELD_RE = re.compile(r"^field(\d{1,2})$", re.IGNORECASE)

def _canon(key: str | None) -> str | None:
    if not key:
        return None
    m = _FIELD_RE.match(str(key).strip())
    if not m:
        return None
    return f"field{int(m.group(1))}"

def _extract_labels(ch: dict[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for k, v in ch.items():
        ck = _canon(k)
        if ck and isinstance(v, str) and v.strip():
            labels[ck] = v.strip()
    return labels

def _extract_lastvalues_map(lv: Any) -> dict[str, Any]:
    if isinstance(lv, str):
        try:
            lv = json.loads(lv)
        except Exception:
            lv = {}
    if not isinstance(lv, dict):
        return {}
    m: dict[str, Any] = {}
    for k, v in lv.items():
        ck = _canon(k)
        if ck:
            m[ck] = v
    return m

def _infer_unit_and_class(label: str) -> tuple[str | None, SensorDeviceClass | None]:
    """Heuristic: map common field labels to HA units/device classes."""
    if not label:
        return None, None
    s = label.lower()
    def has(*subs): return any(x in s for x in subs)

    # Order matters: more specific first
    if has("temperature", "temp", "°c", "deg c"):
        return "°C", SensorDeviceClass.TEMPERATURE
    if has("humidity", "humid", "%rh", "relative humidity"):
        return "%", SensorDeviceClass.HUMIDITY
    if has("illum", "light", "lux", "lx"):
        return "lx", None
    if has("rssi", "wifi", "wi-fi", "signal"):
        return "dBm", None
    if has("battery"):
        return "%", SensorDeviceClass.BATTERY
    if has("pressure", "baro", "hpa"):
        return "hPa", SensorDeviceClass.PRESSURE
    if has("voltage", "volt", "vdc", " v") and not has("uv"):
        return "V", SensorDeviceClass.VOLTAGE
    if has("current", "amp", "ma", " a"):
        return "A", SensorDeviceClass.CURRENT
    if has("power", "watt", " w"):
        return "W", SensorDeviceClass.POWER
    if has("energy", "kwh", "wh"):
        return "kWh", SensorDeviceClass.ENERGY
    if has("co2", "carbon dioxide"):
        return "ppm", None
    if has("tvoc", "voc"):
        return "ppb", None
    # Default: no unit/class
    return None, None

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Create field sensors from the preloaded coordinators."""
    store = hass.data[DOMAIN][entry.entry_id]
    channels: list[dict[str, str]] = store.get("channels", [])
    sensor_map: dict[str, list[str]] = store.get("sensor_map", {})
    coordinators = store.get("coordinators", {})

    entities: list[SensorEntity] = []

    for ch in channels:
        channel_id = str(ch.get("channel_id"))
        channel_name = ch.get("name") or channel_id
        selected_fields = set((f or "").lower() for f in sensor_map.get(channel_id, []))

        coord = coordinators.get(channel_id)
        if coord is None:
            _LOGGER.warning("Coordinator missing for channel %s (%s); skipping.", channel_name, channel_id)
            continue

        ch_payload = (coord.data or {}).get("channel", {})
        labels = _extract_labels(ch_payload)
        lv_map = _extract_lastvalues_map(ch_payload.get("last_values"))
        fields = {**{k: labels.get(k, k) for k in lv_map.keys()}, **labels}
        if not fields:
            fields = {k: k for k in KNOWN_FIELDS[:10]}

        _LOGGER.debug("Channel %s (%s): discovered fields=%s selected=%s",
                      channel_name, channel_id, fields, list(selected_fields))

        for field_key, label in fields.items():
            enabled = (not selected_fields) or (field_key in selected_fields)
            unit, devclass = _infer_unit_and_class(label)
            entities.append(UbibotFieldSensor(coord, field_key, label, unit, devclass, enabled))

    async_add_entities(entities, update_before_add=False)

class UbibotFieldSensor(CoordinatorEntity, SensorEntity):
    """A single field (entity) under a device (channel)."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, field_key: str, label: str, unit: str | None, devclass, enabled: bool) -> None:
        super().__init__(coordinator)
        self._field_key = field_key
        self._label = label or field_key
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = devclass
        if not enabled:
            self._attr_entity_registry_enabled_default = False
        self._attr_unique_id = f"{DOMAIN}_{coordinator.channel_id}_{field_key}"
        self._attr_name = f"{coordinator.channel_name} {self._label}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.channel_id)},
            "name": self.coordinator.channel_name,
            "manufacturer": "Ubibot",
            "model": "Channel",
        }

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        ch = data.get("channel", {})
        lv_map = _extract_lastvalues_map(ch.get("last_values"))
        v = lv_map.get(self._field_key)
        if isinstance(v, dict) and "value" in v:
            return v.get("value")
        return v
