"""Config flow, ponovna prijava i postavke."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlowWithReload
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .api import MetelgradAuthError, MetelgradClient, MetelgradError
from .const import (
    CONF_EMAIL,
    CONF_LIBRARY_ID,
    CONF_MEMBER_NAME,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_LIBRARY_ID,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    MAX_SCAN_INTERVAL_HOURS,
    MIN_SCAN_INTERVAL_HOURS,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MEMBER_NAME): selector.TextSelector(),
        vol.Required(CONF_EMAIL): selector.TextSelector(selector.TextSelectorType.EMAIL),
        vol.Required(CONF_PASSWORD): selector.TextSelector(selector.TextSelectorType.PASSWORD),
        vol.Required(CONF_LIBRARY_ID, default=DEFAULT_LIBRARY_ID): selector.TextSelector(),
    }
)

PASSWORD_SCHEMA = vol.Schema(
    {vol.Required(CONF_PASSWORD): selector.TextSelector(selector.TextSelectorType.PASSWORD)}
)


async def async_validate(data: Mapping[str, Any]) -> None:
    """Provjeri podatke stvarnom prijavom, u privremenoj sesiji."""
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(),
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        client = MetelgradClient(
            session,
            data[CONF_EMAIL],
            data[CONF_PASSWORD],
            data[CONF_LIBRARY_ID],
        )
        await client.async_fetch_loans()


def _unique_id(data: Mapping[str, Any]) -> str:
    return f"{data[CONF_LIBRARY_ID]}:{data[CONF_EMAIL].casefold()}"


class KnjiznicaMetelgradConfigFlow(ConfigFlow, domain=DOMAIN):
    """Dodavanje jedne knjižnične kartice."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Unos podataka o kartici."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await async_validate(user_input)
            except MetelgradAuthError:
                errors["base"] = "invalid_auth"
            except (aiohttp.ClientError, TimeoutError, MetelgradError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(_unique_id(user_input))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_MEMBER_NAME], data=dict(user_input)
                )
        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Pokreni ponovnu prijavu kad HA javi da podaci više ne rade."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Zatraži novu lozinku."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            try:
                await async_validate(data)
            except MetelgradAuthError:
                errors["base"] = "invalid_auth"
            except (aiohttp.ClientError, TimeoutError, MetelgradError):
                errors["base"] = "cannot_connect"
            else:
                self.hass.config_entries.async_update_entry(entry, data=data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=PASSWORD_SCHEMA, errors=errors
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> KnjiznicaMetelgradOptionsFlow:
        """Vrati options flow."""
        return KnjiznicaMetelgradOptionsFlow()


class KnjiznicaMetelgradOptionsFlow(OptionsFlowWithReload):
    """Postavke jedne kartice."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Interval provjere stranice knjižnice."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL_HOURS, default=current): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL_HOURS, max=MAX_SCAN_INTERVAL_HOURS),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
