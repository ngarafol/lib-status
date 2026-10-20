"""Koordinacija dohvata podataka i produženja."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MetelgradAuthError, MetelgradClient, MetelgradError
from .const import DOMAIN
from .parser import Loan

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RenewResult:
    """Ishod produženja jedne posudbe."""

    title: str
    # Zahtjev je poslan (knjižnica ga je primila).
    submitted: bool
    # Rok se stvarno pomaknuo. Produženje na ovoj knjižnici ide kao "zahtjev",
    # pa se promjena može vidjeti i kasnije.
    confirmed: bool
    due_on: date | None
    error: str | None = None


class KnjiznicaCoordinator(DataUpdateCoordinator[list[Loan]]):
    """Dohvaća posudbe i izvodi produženja za jednu karticu."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: MetelgradClient,
        scan_interval_hours: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(hours=scan_interval_hours),
        )
        self.client = client

    async def _async_update_data(self) -> list[Loan]:
        try:
            return await self.client.async_fetch_loans()
        except MetelgradAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Greška pri dohvatu posudbi: {err}") from err

    async def async_renew(self, selector: str | None = None) -> list[RenewResult]:
        """Produži posudbe odabrane po dijelu naslova (ulaz za servis).

        Bez `selector`-a produžuje se sve što je knjižnica ponudila kao produživo.
        """
        return await self.async_renew_loans(self._select(selector))

    async def async_renew_loans(self, loans: list[Loan]) -> list[RenewResult]:
        """Produži točno ove posudbe (npr. jednu, preko njenog gumba)."""
        if not loans:
            return []

        errors: dict[str, str] = {}
        for loan in loans:
            try:
                await self.client.async_renew(loan)
            except (MetelgradError, aiohttp.ClientError, TimeoutError) as err:
                # I tip greške, jer neki aiohttp izuzeci nose samo URL u poruci.
                errors[loan.title] = f"{type(err).__name__}: {err}"

        await self.async_refresh()
        current = {loan.title: loan for loan in self.data or []}

        results: list[RenewResult] = []
        for loan in loans:
            if error := errors.get(loan.title):
                results.append(RenewResult(loan.title, False, False, loan.due_on, error))
                continue
            due_on = current[loan.title].due_on if loan.title in current else None
            results.append(
                RenewResult(
                    loan.title,
                    submitted=True,
                    confirmed=due_on is not None and due_on != loan.due_on,
                    due_on=due_on,
                )
            )
        return results

    def _select(self, selector: str | None) -> list[Loan]:
        renewable = [loan for loan in self.data or [] if loan.renewable]
        if not selector:
            return renewable
        query = selector.strip().casefold()
        return [loan for loan in renewable if query in loan.title.casefold()]
