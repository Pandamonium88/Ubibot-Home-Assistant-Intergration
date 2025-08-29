# Ubibot Home Assistant Integration

A custom [Home Assistant](https://www.home-assistant.io/) integration for [Ubibot](https://www.ubibot.com/) devices.  
This integration supports **multi-channel devices**, **per-device polling intervals**, **user-selectable sensors**, and **SP1 smart plug control**.

---

## Features

- **Device-first structure**  
  Each Ubibot channel is represented as a device in Home Assistant.

- **Dynamic sensors**  
  Field labels from the Ubibot API are mapped to Home Assistant sensor entities.  
  - Units and device classes are auto-inferred from field labels (temperature → °C, humidity → %, light → lx, etc.).
  - Users can select which fields to enable during setup or via options.

- **Per-device poll intervals**  
  Each device exposes a **Number entity** (`<Device> Poll Interval`) allowing you to configure the polling rate (seconds).

- **SP1 Smart Plug (ubibot-sp1a)**  
  - Adds a **Switch entity** for Ubibot SP1 devices.
  - Supports turning `port1` **on/off** via Ubibot’s [Add Command API](https://www.ubibot.com/platform-api/commands-management/6567/add-command/).
  - State is optimistic but refreshed on the next poll. If API returns a `last_values` key such as `port1_state`, it will reflect the actual state.

---

## Installation

1. Download the latest release (`ubibot_vX.Y.Z.zip`).
2. Extract and copy the `ubibot` folder to your Home Assistant config:  
   ```
   config/custom_components/ubibot/
   ```
3. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, go to **Settings → Devices & Services → Integrations → Add Integration**.
2. Search for **Ubibot** and enter your **Account Key**.
3. Select which channels to import.
4. Choose polling intervals per channel.
5. Choose which sensors (fields) to enable per channel.

### Options (after setup)

- Change per-channel polling intervals.
- Enable/disable specific sensors.
- Add or remove channels from the integration.

---

## Entities

- **Sensors**  
  Based on Ubibot fields (e.g., Temperature, Humidity, Voltage, RSSI, etc.).  
  Units and device classes auto-detected where possible.

- **Number**  
  `<Device> Poll Interval` — Adjust the polling interval in seconds.

- **Switch (SP1 only)**  
  `<Device> Switch` — Controls SP1 smart plugs (`product_id: ubibot-sp1a`).

---

## Known Limitations

- SP1 switch state is inferred optimistically unless `last_values` includes a relay status field.
- Only `port1` is currently supported for SP1.
- Statistics compatibility requires consistent units; ensure field labels are meaningful (e.g., “Temperature” instead of “Field1”).

---

## Example

If you have:
- **Office** (WS1 Pro)  
- **External Freezer** (GS1-AETH1RS)  
- **Smart Plug (SP1)**  

You’ll see in HA:
- `sensor.office_temperature (°C)`
- `sensor.office_humidity (%)`
- `number.office_poll_interval`
- `switch.smart_plug_switch`
