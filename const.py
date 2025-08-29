DOMAIN = "ubibot"

CONF_ACCOUNT_KEY = "account_key"
CONF_CHANNELS = "channels"
CONF_POLL_MAP = "poll_map"
CONF_SENSOR_MAP = "sensor_map"

API_BASE = "https://webapi.ubibot.com"

DEFAULT_POLL_SECONDS = 600
MIN_POLL_SECONDS = 60
MAX_POLL_SECONDS = 3600

KNOWN_FIELDS = [f"field{i}" for i in range(1, 16)]
