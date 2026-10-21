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
from .entity import KnjiznicaEntity, LoanEntity, async_track_loan_entities, loan_key
from .parser import Loan


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Postavi gumb "produži sve" i po jedan gumb za svaku posuđenu knjigu."""
    coordinator: KnjiznicaCoordinator = entry.runtime_data.coordinator
    async_add_entities([RenewAllButton(coordinator, entry)])
    _async_prune_stale_buttons(hass, entry)
    async_track_loan_entities(
        hass,
        entry,
        async_add_entities,
        lambda key, loan: RenewLoanButton(coordinator, entry, key, loan),
    )


@callback
def _async_prune_stale_buttons(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Počisti gumbe kojima ključ ne odgovara nijednoj trenutnoj posudbi.

    Pokriva entitete iz 0.1.3 (unique_id građen po oznaci primjerka); bez toga
    ostanu kao nedostupni, a novi gumbi dobiju sufikse (_2) — pa kartica na
    dashboardu pokazuje na mrtav entitet.
    """
    coordinator: KnjiznicaCoordinator = entry.runtime_data.coordinator
    loans = {loan_key(loan) for loan in coordinator.data or []}
    expected = {f"{entry.entry_id}_renew_{key}" for key in loans}
    registry = entity_registry.async_get(hass)

    for reg_entry in entity_registry.async_entries_for_config_entry(registry, entry.entry_id):
        unique_id = reg_entry.unique_id
        if reg_entry.domain != "button" or not unique_id.startswith(f"{entry.entry_id}_renew_"):
            continue
        if unique_id not in expected and unique_id != f"{entry.entry_id}_renew_all":
            registry.async_remove(reg_entry.entity_id)


def _raise_on_failure(results: list[RenewResult]) -> None:
    """Pritisak javlja neuspjeh, ne samo tiho odustaje."""
    failures = [result for result in results if not result.submitted]
    if failures:
        details = "; ".join(f"{result.title} ({result.error})" for result in failures)
        raise HomeAssistantError(f"Produženje nije poslano za: {details}")


class RenewAllButton(KnjiznicaEntity, ButtonEntity):
    """Produžuje sve posudbe koje knjižnica nudi kao produžive."""

    _attr_name = "Produži sve"
    _attr_icon = "mdi:book-refresh"

    def __init__(self, coordinator: KnjiznicaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "renew_all")

    @property
    def available(self) -> bool:
        return super().available and any(loan.renewable for loan in self.loans)

    async def async_press(self) -> None:
        _raise_on_failure(await self.coordinator.async_renew())


class RenewLoanButton(LoanEntity, ButtonEntity):
    """Produžuje jednu posudbu (knjiga iz naziva gumba)."""

    _attr_icon = "mdi:book-refresh"

    def __init__(
        self, coordinator: KnjiznicaCoordinator, entry: ConfigEntry, key: str, loan: Loan
    ) -> None:
        super().__init__(coordinator, entry, key, f"Produži: {loan.title}", "renew")

    @property
    def available(self) -> bool:
        """Dostupan samo dok knjižnica tu posudbu nudi za produženje."""
        loan = self.loan
        return super().available and loan is not None and loan.renewable

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        loan = self.loan
        return {} if loan is None else loan.as_dict(dt_util.now().date())

    async def async_press(self) -> None:
        loan = self.loan
        if loan is None:
            raise HomeAssistantError("Knjiga više nije na popisu posudbi.")
        if not loan.renewable:
            raise HomeAssistantError(f"Knjižnica trenutno ne nudi produženje za '{loan.title}'.")
        _raise_on_failure(await self.coordinator.async_renew_loans([loan]))
