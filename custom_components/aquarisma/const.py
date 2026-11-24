"""Constants for the Aquarisma Home Assistant integration."""

from __future__ import annotations

DOMAIN = "aquarisma"
CLIENT_VERSION = "1.2.0"
SCHEMA_VERSION = 1
DEFAULT_POLL = 60
MIN_POLL = 30
MAX_POLL = 300
TOKEN_REFRESH_SKEW = 60
MY_REDIRECT = "https://my.home-assistant.io/redirect/oauth"
DEFAULT_BASE_URL = "https://aquarisma.com"
MANUFACTURER = "Aquarisma"
ATTRIBUTION = "Data provided by Aquarisma"

CONF_BASE_URL = "base_url"
CONF_CLIENT_ID = "client_id"
CONF_REDIRECT_URI = "redirect_uri"
CONF_TOKEN = "token"
CONF_CONNECTION_ID = "connection_id"
CONF_ALLOW_WRITE = "allow_write"
CONF_USE_MY = "use_my_home_assistant"
CONF_POLL = "poll_interval"

READ_SCOPES = [
    "aquariums:read",
    "water.measurements:read",
    "water.targets:read",
    "water.incidents:read",
    "feeding.plans:read",
    "feeding.logs:read",
    "feeding.foods:read",
    "feeding.stocks:read",
    "care.tasks:read",
    "care.plans:read",
    "care.water_changes:read",
    "livestock:read",
]
WRITE_SCOPES = [
    "feeding.logs:create",
    "care.tasks:complete",
    "care.water_changes:create",
    "water.measurements:create",
]

# Parameter keys that have their own translated entity name.
KNOWN_PARAMETERS = {
    "temperature",
    "ph",
    "gh",
    "kh",
    "ammonia_nh3",
    "ammonium_nh4",
    "tan",
    "nitrite",
    "nitrate",
    "nitrate_n",
    "phosphate",
    "phosphate_p",
    "oxygen",
    "co2",
    "conductivity",
    "tds",
    "chlorine",
    "silicate",
    "iron",
    "potassium",
    "salinity",
    "specific_gravity",
    "alkalinity",
    "calcium",
    "magnesium",
    "orp",
    "copper",
}
