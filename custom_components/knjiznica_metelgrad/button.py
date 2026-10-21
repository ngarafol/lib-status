"""Gumbi za produženje: jedan po posudbi i jedan za sve produžive posudbe."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import KnjiznicaCoordinator, RenewResult
from .entity import KnjiznicaEntity
from .parser import Loan


def _loan_key(loan: Loan) -> str:
    """Stabilan ključ posudbe dok je knjiga posuđena.

    Identifikator zapisa (`D…`) ne mijenja se ni kad se rok produži, za razliku
    od oznake primjerka (`MK…`) koja postoji samo dok je produženje ponuđeno.
    Dvije kopije istog naslova odjednom dijele ključ — za dječju knjižnicu je to
    zanemariv slučaj.
    """
    return loan.record_key or loan.title.casefold()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Postavi gumb "produži sve" i po jedan gumb za svaku posuđenu knjigu."""
    coordinator: KnjiznicaCoordinator = entry.runtime_data.coordinator
    async_add_entities([RenewAllButton(coordinator, entry)])

    known: dict[str, RenewLoanButton] = {}

    @callback
    def _sync_loan_buttons() -> None:
        """Uskladi gumbe s posudbama i počisti zaostale entitete.

        Gumb ostaje i kad se produženje trenutno ne nudi — tada je nedostupan,
        umjesto da nestane (nestali entitet na dashboardu daje "entity not found").
        """
        loans = {_loan_key(loan): loan for loan in coordinator.data or []}
        expected = {f"{entry.entry_id}_renew_{key}" for key in loans}
        registry = entity_registry.async_get(hass)

        # 1) Počisti gumbe koji ne pripadaju nijednoj trenutnoj posudbi. To
        # pokriva i entitete iz starijih verzija (0.1.3 je unique_id gradio po
        # oznaci primjerka); bez toga stari ostanu kao nedostupni, a novi gumbi
        # dobiju sufikse (_2) — pa kartica pokazuje na mrtav entitet.
        for reg_entry in entity_registry.async_entries_for_config_entry(registry, entry.entry_id):
            unique_id = reg_entry.unique_id
            if reg_entry.domain != "button" or not unique_id.startswith(f"{entry.entry_id}_renew_"):
                continue
            if unique_id not in expected and unique_id != f"{entry.entry_id}_renew_all":
                registry.async_remove(reg_entry.entity_id)

        # 2) Dodaj gumbe za nove posudbe — nakon čišćenja, da dobiju čist entity_id.
        added = []
        for key, loan in loans.items():
            if key not in known:
                known[key] = RenewLoanButton(coordinator, entry, key, loan.title)
                added.append(known[key])
        if added:
            async_add_entities(added)

        # 3) Zaboravi posudbe kojih više nema (entitet je već uklonjen gore).
        for key in [key for key in known if key not in loans]:
            del known[key]

    entry.async_on_unload(coordinator.async_add_listener(_sync_loan_buttons))
    _sync_loan_buttons()


class _RenewButton(KnjiznicaEntity, ButtonEntity):
    """Zajedničko ponašanje: pritisak javlja neuspjeh, ne samo tiho odustaje."""

    _attr_icon = "mdi:book-refresh"

    @staticmethod
    def _raise_on_failure(results: list[RenewResult]) -> None:
        failures = [result for result in results if not result.submitted]
        if failures:
            details = "; ".join(f"{result.title} ({result.error})" for result in failures)
            raise HomeAssistantError(f"Produženje nije poslano za: {details}")


class RenewAllButton(_RenewButton):
    """Produžuje sve posudbe koje knjižnica nudi kao produžive."""

    _attr_name = "Produži sve"

    def __init__(self, coordinator: KnjiznicaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "renew_all")

    @property
    def available(self) -> bool:
        return super().available and any(loan.renewable for loan in self.loans)

    async def async_press(self) -> None:
        self._raise_on_failure(await self.coordinator.async_renew())


class RenewLoanButton(_RenewButton):
    """Produžuje jednu posudbu (knjiga iz naziva gumba)."""

    def __init__(
        self, coordinator: KnjiznicaCoordinator, entry: ConfigEntry, key: str, title: str
    ) -> None:
        super().__init__(coordinator, entry, f"renew_{key}")
        self._key = key
        self._attr_name = f"Produži: {title}"

    @property
    def _loan(self) -> Loan | None:
        return next((loan for loan in self.loans if _loan_key(loan) == self._key), None)

    @property
    def available(self) -> bool:
        """Dostupan samo dok knjižnica tu posudbu nudi za produženje."""
        loan = self._loan
        return super().available and loan is not None and loan.renewable

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        loan = self._loan
        return {} if loan is None else loan.as_dict(dt_util.now().date())

    async def async_press(self) -> None:
        loan = self._loan
        if loan is None:
            raise HomeAssistantError("Knjiga više nije na popisu posudbi.")
        if not loan.renewable:
            raise HomeAssistantError(f"Knjižnica trenutno ne nudi produženje za '{loan.title}'.")
        self._raise_on_failure(await self.coordinator.async_renew_loans([loan]))
