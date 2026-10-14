"""HA testovi: config flow, entiteti, servis i gumb za produženje.

Zahtijevaju pytest-homeassistant-custom-component (vidi README, Razvoj). Bez njega
se preskaču, pa `python -m unittest discover` i dalje radi.

    .venv-ha/bin/pytest tests/test_integration.py
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock, patch

try:
    import pytest
    from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
    from homeassistant.const import STATE_UNAVAILABLE
    from homeassistant.core import HomeAssistant
    from homeassistant.data_entry_flow import FlowResultType
    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import MockConfigEntry
except ImportError as err:  # pragma: no cover - samo kad HA nije instaliran
    raise unittest.SkipTest(f"Home Assistant nije instaliran: {err}") from None

from custom_components.knjiznica_metelgrad.api import MetelgradAuthError
from custom_components.knjiznica_metelgrad.const import (
    CONF_EMAIL,
    CONF_LIBRARY_ID,
    CONF_MEMBER_NAME,
    CONF_PASSWORD,
    DOMAIN,
    SERVICE_RENEW,
)
from custom_components.knjiznica_metelgrad.parser import Loan

FETCH = "custom_components.knjiznica_metelgrad.api.MetelgradClient.async_fetch_loans"
RENEW = "custom_components.knjiznica_metelgrad.api.MetelgradClient.async_renew"
VALIDATE = "custom_components.knjiznica_metelgrad.config_flow.async_validate"

USER_INPUT = {
    CONF_MEMBER_NAME: "Ana",
    CONF_EMAIL: "ana@example.com",
    CONF_PASSWORD: "tajna",
    CONF_LIBRARY_ID: "11",
}

TODAY = dt_util.now().date()
# Jedna produživa (ima oznaku primjerka) i jedna koja nije na popisu za produženje.
LOANS = [
    Loan("Mali princ", "Saint-Exupéry", TODAY + timedelta(days=5), "D1", "MK1"),
    Loan("Dnevnik", "Kušec", TODAY + timedelta(days=2), "D2", None),
]
RENEWED = [replace(LOANS[0], due_on=TODAY + timedelta(days=30)), LOANS[1]]


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Ana", data=USER_INPUT, unique_id="11:ana")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _add_second_card(hass: HomeAssistant) -> MockConfigEntry:
    """Drugo dijete = drugi config entry (vlastita sesija i vlastiti entiteti)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Ivo",
        data={**USER_INPUT, CONF_EMAIL: "ivo@example.com"},
        unique_id="11:ivo@example.com",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow_shows_form(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert {str(key) for key in result["data_schema"].schema} == {
        "member_name",
        "email",
        "password",
        "library_id",
    }


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    with (
        patch(VALIDATE, new=AsyncMock(return_value=None)),
        patch(FETCH, new=AsyncMock(return_value=LOANS)),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Ana"
    assert result["data"] == USER_INPUT


async def test_bad_credentials_show_error(hass: HomeAssistant) -> None:
    with patch(VALIDATE, new=AsyncMock(side_effect=MetelgradAuthError("nope"))):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_entities_are_created(hass: HomeAssistant) -> None:
    with patch(FETCH, new=AsyncMock(return_value=LOANS)):
        await _setup_entry(hass)

    loans = hass.states.get("sensor.ana_posudbe")
    assert loans is not None
    assert loans.state == "2"
    assert loans.attributes["renewable_count"] == 1
    assert loans.attributes["overdue_count"] == 0
    assert [item["title"] for item in loans.attributes["loans"]] == ["Mali princ", "Dnevnik"]
    assert loans.attributes["loans"][0] == {
        "title": "Mali princ",
        "author": "Saint-Exupéry",
        "due_on": (TODAY + timedelta(days=5)).isoformat(),
        "days_left": 5,
        "renewable": True,
    }

    due = hass.states.get("sensor.ana_rok_vracanja")
    assert due is not None
    assert due.state == (TODAY + timedelta(days=2)).isoformat()

    days_left = hass.states.get("sensor.ana_dana_do_roka")
    assert days_left is not None
    assert days_left.state == "2"

    assert hass.states.get("button.ana_produzi_sve") is not None


async def test_renew_service(hass: HomeAssistant) -> None:
    renew = AsyncMock(return_value=None)
    with (
        patch(FETCH, new=AsyncMock(side_effect=[LOANS, RENEWED])),
        patch(RENEW, new=renew),
    ):
        await _setup_entry(hass)

        response = await hass.services.async_call(
            DOMAIN, SERVICE_RENEW, {}, blocking=True, return_response=True
        )
        await hass.async_block_till_done()

    # Samo posudba koja je ponuđena za produženje (ima oznaku primjerka).
    assert renew.await_count == 1
    assert renew.await_args.args[0].title == "Mali princ"
    assert response == {
        "submitted": 1,
        "confirmed": 1,
        "failed": 0,
        "results": [
            {
                "config_entry_id": response["results"][0]["config_entry_id"],
                "title": "Mali princ",
                "submitted": True,
                "confirmed": True,
                "due_on": (TODAY + timedelta(days=30)).isoformat(),
                "error": None,
            }
        ],
    }


async def test_renew_button(hass: HomeAssistant) -> None:
    with (
        patch(FETCH, new=AsyncMock(side_effect=[LOANS, RENEWED])),
        patch(RENEW, new=AsyncMock(return_value=None)),
    ):
        await _setup_entry(hass)

        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.ana_produzi_sve"},
            blocking=True,
        )
        await hass.async_block_till_done()


async def test_two_cards_are_separate_and_service_covers_both(hass: HomeAssistant) -> None:
    """Više kartica: svaka ima svoje entitete, a servis bez odabira radi na svima."""
    renew = AsyncMock(return_value=None)
    with (
        patch(FETCH, new=AsyncMock(side_effect=[LOANS, LOANS, RENEWED, RENEWED])),
        patch(RENEW, new=renew),
    ):
        ana = await _setup_entry(hass)
        ivo = await _add_second_card(hass)

        assert hass.states.get("sensor.ana_posudbe").state == "2"
        assert hass.states.get("sensor.ivo_posudbe").state == "2"
        assert hass.states.get("button.ivo_produzi_sve") is not None

        response = await hass.services.async_call(
            DOMAIN, SERVICE_RENEW, {}, blocking=True, return_response=True
        )
        await hass.async_block_till_done()

    # Po jedna produživa posudba na svakoj kartici.
    assert renew.await_count == 2
    assert response["submitted"] == 2
    assert {item["config_entry_id"] for item in response["results"]} == {
        ana.entry_id,
        ivo.entry_id,
    }


async def test_unload_entry(hass: HomeAssistant) -> None:
    with patch(FETCH, new=AsyncMock(return_value=LOANS)):
        entry = await _setup_entry(hass)

    assert hass.states.get("sensor.ana_posudbe").state == "2"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    # HA zadrži "restored" stanje entiteta, ali ono više nije dostupno.
    assert hass.states.get("sensor.ana_posudbe").state == STATE_UNAVAILABLE

    # Servis ostaje registriran (veže se na integraciju, ne na karticu), ali bez
    # učitanih kartica javlja grešku umjesto da tiho ne napravi ništa.
    assert hass.services.has_service(DOMAIN, SERVICE_RENEW)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, SERVICE_RENEW, {}, blocking=True, return_response=True
        )
