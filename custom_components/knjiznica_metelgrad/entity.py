"""Zajednička osnova entiteta (uređaj = jedna knjižnična kartica)."""

from __future__ import annotations

from datetime import date

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KnjiznicaCoordinator
from .parser import Loan


class KnjiznicaEntity(CoordinatorEntity[KnjiznicaCoordinator]):
    """Entitet vezan na jednu karticu i njen koordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: KnjiznicaCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Knjižnica Metelgrad ({entry.title})",
            manufacturer="Metelwin",
            model="Korisnički račun knjižnice",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def loans(self) -> list[Loan]:
        """Trenutne posudbe."""
        return self.coordinator.data or []

    def nearest_due(self) -> date | None:
        """Najbliži rok vraćanja."""
        due_dates = [loan.due_on for loan in self.loans if loan.due_on]
        return min(due_dates) if due_dates else None
