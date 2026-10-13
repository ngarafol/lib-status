"""Senzori posudbi i rokova vraćanja."""

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
from .entity import KnjiznicaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Postavi senzore za ovu karticu."""
    coordinator: KnjiznicaCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            LoansSensor(coordinator, entry),
            DueDateSensor(coordinator, entry),
            DaysLeftSensor(coordinator, entry),
        ]
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
        today = dt_util.now().date()
        return {
            "loans": [loan.as_dict(today) for loan in self.loans],
            "renewable_count": sum(1 for loan in self.loans if loan.renewable),
            "overdue_count": sum(
                1
                for loan in self.loans
                if (days_left := loan.days_until(today)) is not None and days_left < 0
            ),
        }


class DueDateSensor(KnjiznicaEntity, SensorEntity):
    """Najbliži rok vraćanja kao datum."""

    _attr_name = "Rok vraćanja"
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-arrow-right"

    def __init__(self, coordinator: KnjiznicaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "due_date")

    @property
    def native_value(self) -> date | None:
        return self.nearest_due()


class DaysLeftSensor(KnjiznicaEntity, SensorEntity):
    """Broj dana do najbližeg roka (negativno = rok je prošao)."""

    _attr_name = "Dana do roka"
    _attr_native_unit_of_measurement = "d"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: KnjiznicaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "days_left")

    @property
    def native_value(self) -> int | None:
        due_on = self.nearest_due()
        if due_on is None:
            return None
        return (due_on - dt_util.now().date()).days
