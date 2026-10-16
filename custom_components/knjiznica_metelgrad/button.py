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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Postavi gumb "produži sve" i po jedan gumb za svaku produživu posudbu."""
    coordinator: KnjiznicaCoordinator = entry.runtime_data.coordinator
    async_add_entities([RenewAllButton(coordinator, entry)])

    known: dict[str, RenewLoanButton] = {}

    @callback
    def _sync_loan_buttons() -> None:
        """Dodaj gumb za nove posudbe, ukloni ga kad posudba nije produživa."""
        renewable = {loan.renew_id: loan for loan in coordinator.data or [] if loan.renewable}
        added = []
        for renew_id, loan in renewable.items():
            if renew_id not in known:
                known[renew_id] = RenewLoanButton(coordinator, entry, loan)
                added.append(known[renew_id])
        if added:
            async_add_entities(added)

        registry = entity_registry.async_get(hass)
        for renew_id in [key for key in known if key not in renewable]:
            button = known.pop(renew_id)
            if button.entity_id is not None:
                # Uklanjanje iz registra platforma pretvara u potpuno uklanjanje
                # entiteta; samo async_remove() bi ga ostavilo kao "unavailable".
                registry.async_remove(button.entity_id)

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

    def __init__(self, coordinator: KnjiznicaCoordinator, entry: ConfigEntry, loan: Loan) -> None:
        super().__init__(coordinator, entry, f"renew_{loan.renew_id}")
        self._renew_id = loan.renew_id
        self._attr_name = f"Produži: {loan.title}"

    @property
    def _loan(self) -> Loan | None:
        return next((loan for loan in self.loans if loan.renew_id == self._renew_id), None)

    @property
    def available(self) -> bool:
        return super().available and self._loan is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        loan = self._loan
        return {} if loan is None else loan.as_dict(dt_util.now().date())

    async def async_press(self) -> None:
        loan = self._loan
        if loan is None:
            raise HomeAssistantError("Posudba više nije na popisu za produženje.")
        self._raise_on_failure(await self.coordinator.async_renew_loans([loan]))
