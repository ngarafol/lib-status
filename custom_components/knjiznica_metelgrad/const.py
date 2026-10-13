"""Konstante integracije knjiznica_metelgrad."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "knjiznica_metelgrad"

BASE_URL: Final = "https://library.foi.hr"
LOGIN_PATH: Final = "/auth/loaut.php"
LOANS_PATH: Final = "/lib/korisnik.php"

# Oznaka knjižnice u URL-u (B=11 = Gradska knjižnica Metelgrad, dječji odjel).
DEFAULT_LIBRARY_ID: Final = "11"

CONF_EMAIL: Final = "email"
CONF_PASSWORD: Final = "password"
CONF_LIBRARY_ID: Final = "library_id"
CONF_MEMBER_NAME: Final = "member_name"
CONF_SCAN_INTERVAL_HOURS: Final = "scan_interval_hours"

DEFAULT_SCAN_INTERVAL_HOURS: Final = 24
MIN_SCAN_INTERVAL_HOURS: Final = 6
MAX_SCAN_INTERVAL_HOURS: Final = 168

SERVICE_RENEW: Final = "renew"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_LOAN: Final = "loan"

# Iskren i prepoznatljiv User-Agent za automatizirani pristup.
USER_AGENT: Final = "HomeAssistant-knjiznica-metelgrad/0.1 (osobna upotreba)"
