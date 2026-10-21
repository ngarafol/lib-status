"""Integracija Knjižnica Metelgrad (Metelwin) za Home Assistant."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import MetelgradClient
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_LOAN,
    CONF_EMAIL,
    CONF_LIBRARY_ID,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_LIBRARY_ID,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    SERVICE_RENEW,
)
from .coordinator import KnjiznicaCoordinator
from .entity import async_prune_loan_entities

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR]


@dataclass
class KnjiznicaRuntimeData:
    """Resursi jedne kartice, vezani na životni vijek config entryja."""

    session: aiohttp.ClientSession
    coordinator: KnjiznicaCoordinator


KnjiznicaConfigEntry = ConfigEntry[KnjiznicaRuntimeData]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Registriraj servis za produženje, jednom za cijelu integraciju."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_RENEW,
        _async_handle_renew,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
                vol.Optional(ATTR_LOAN): cv.string,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: KnjiznicaConfigEntry) -> bool:
    """Postavi integraciju za jednu karticu."""
    # Vlastita sesija (i vlastiti cookie jar) po kartici: vidi api.py.
    session = aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(),
        timeout=aiohttp.ClientTimeout(total=30),
    )
    client = MetelgradClient(
        session,
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_LIBRARY_ID, DEFAULT_LIBRARY_ID),
    )
    coordinator = KnjiznicaCoordinator(
        hass,
        entry,
        client,
        entry.options.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS),
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await session.close()
        raise

    entry.runtime_data = KnjiznicaRuntimeData(session, coordinator)
    # Promjena opcija (interval provjere) ili podataka (ponovna prijava) reloada
    # integraciju; zamjena za OptionsFlowWithReload iz novijih HA verzija.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    # Entiteti koje su starije verzije stvarale po knjizi nestaju iz registra.
    async_prune_loan_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: KnjiznicaConfigEntry) -> None:
    """Reloadaj karticu nakon promjene podataka ili opcija."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: KnjiznicaConfigEntry) -> bool:
    """Ukloni karticu i oslobodi resurse."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    await entry.runtime_data.session.close()
    return True


async def _async_handle_renew(call: ServiceCall) -> ServiceResponse:
    """Produži posudbe za jednu ili sve kartice."""
    entries = call.hass.config_entries.async_loaded_entries(DOMAIN)
    if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
        entries = [entry for entry in entries if entry.entry_id == entry_id]
        if not entries:
            raise ServiceValidationError(f"Nepoznata kartica: {entry_id}")
    if not entries:
        raise ServiceValidationError("Nema konfiguriranih kartica knjižnice.")

    results: list[dict[str, object]] = []
    for entry in entries:
        for result in await entry.runtime_data.coordinator.async_renew(call.data.get(ATTR_LOAN)):
            results.append(
                {
                    "config_entry_id": entry.entry_id,
                    "title": result.title,
                    "submitted": result.submitted,
                    "confirmed": result.confirmed,
                    "due_on": result.due_on.isoformat() if result.due_on else None,
                    "error": result.error,
                }
            )
    return {
        "submitted": sum(1 for result in results if result["submitted"]),
        "confirmed": sum(1 for result in results if result["confirmed"]),
        "failed": sum(1 for result in results if not result["submitted"]),
        "results": results,
    }
