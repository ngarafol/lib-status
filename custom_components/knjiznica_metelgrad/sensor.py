"""Senzori: ukupan broj posudbi, najbliži rok i rok po svakoj knjizi."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import KnjiznicaCoordinator
from .entity import KnjiznicaEntity, LoanEntity, async_track_loan_entities
from .parser import Loan


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Postavi sažete senzore i po jedan senzor za svaku posuđenu knjigu."""
    coordinator: KnjiznicaCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            LoansSensor(coordinator, entry),
            DueDateSensor(coordinator, entry),
        ]
    )
    async_track_loan_entities(
        hass,
        entry,
        async_add_entities,
        lambda key, loan: LoanDueSensor(coordinator, entry, key, loan),
    )


class LoansSensor(KnjiznicaEntity, SensorEntity):
    """Broj posudbi + popis u atributima."""

    _attr_name = "Posudbe"
    _attr_icon = "mdi:book-open-page-variant"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: KnjiznicaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "loans")

    @property
    def native_value(self) -> int:
        return len(self.loans)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"loans": [loan.as_dict(dt_util.now().date()) for loan in self.loans]}


class DueDateSensor(KnjiznicaEntity, SensorEntity):
    """Najbliži rok vraćanja kao datum."""

    _attr_name = "Rok vraćanja"
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-arrow-right"

    def __init__(self, coordinator: KnjiznicaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "due_date")

    @property
    def native_value(self) -> date | None:
        return min((loan.due_on for loan in self.loans), default=None)


class LoanDueSensor(LoanEntity, SensorEntity):
    """Rok vraćanja jedne knjige (naziv entiteta = naslov knjige)."""

    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:book-clock"

    def __init__(
        self, coordinator: KnjiznicaCoordinator, entry: ConfigEntry, key: str, loan: Loan
    ) -> None:
        super().__init__(coordinator, entry, key, loan.title, "loan")

    @property
    def native_value(self) -> date | None:
        loan = self.loan
        return None if loan is None else loan.due_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        loan = self.loan
        return {} if loan is None else loan.as_dict(dt_util.now().date())
