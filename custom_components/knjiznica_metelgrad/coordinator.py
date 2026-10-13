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
    ok: bool
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
        """Produži odabrane posudbe i provjeri je li se rok stvarno pomaknuo.

        `selector` je dio naslova ili točan URL produženja; bez njega se produžuje
        sve što stranica nudi kao produživo.
        """
        targets = self._select(selector)
        if not targets:
            return []

        errors: dict[str, str] = {}
        for loan in targets:
            try:
                await self.client.async_renew(loan)
            except (MetelgradError, aiohttp.ClientError, TimeoutError) as err:
                errors[loan.title] = str(err)

        # Produženje se potvrđuje tek ako se rok na stranici stvarno promijenio.
        await self.async_refresh()
        current = {loan.title: loan for loan in self.data or []}

        results: list[RenewResult] = []
        for loan in targets:
            if error := errors.get(loan.title):
                results.append(RenewResult(loan.title, False, loan.due_on, error))
                continue
            renewed = current.get(loan.title)
            if renewed is None:
                results.append(RenewResult(loan.title, False, None, "Posudba više nije na popisu."))
            elif renewed.due_on is not None and renewed.due_on != loan.due_on:
                results.append(RenewResult(loan.title, True, renewed.due_on))
            else:
                results.append(
                    RenewResult(
                        loan.title,
                        False,
                        renewed.due_on,
                        "Rok se nije promijenio (produženje je vjerojatno odbijeno).",
                    )
                )
        return results

    def _select(self, selector: str | None) -> list[Loan]:
        renewable = [loan for loan in self.data or [] if loan.renewable]
        if not selector:
            return renewable
        query = selector.strip().casefold()
        return [
            loan
            for loan in renewable
            if query in loan.title.casefold() or query == (loan.renew_url or "")
        ]
