"""Zajednička osnova entiteta (uređaj = jedna knjižnična kartica)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry
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
        # Naziv uređaja = naziv kartice, da entity_id ostanu kratki i predvidivi
        # (npr. sensor.ana_posudbe za karticu "Ana").
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Metelwin",
            model="Knjižnica Metelgrad - korisnički račun",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def loans(self) -> list[Loan]:
        """Trenutne posudbe."""
        return self.coordinator.data or []


@callback
def async_prune_loan_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Ukloni entitete koje su starije verzije stvarale po knjizi.

    0.1.6 je imao senzor i gumb za svaku posudbu (unique_id `_loan_…` / `_renew_…`
    osim `_renew_all`). Ti entiteti su nestajali s vraćenim knjigama, a kartice
    su se morale mijenjati po knjizi — zato su uklonjeni iz integracije, a ovdje
    se čiste i iz registra da ne ostanu kao nedostupni.
    """
    keep = {
        f"{entry.entry_id}_renew_all",
        f"{entry.entry_id}_loans",
        f"{entry.entry_id}_due_date",
    }
    registry = entity_registry.async_get(hass)

    for reg_entry in entity_registry.async_entries_for_config_entry(registry, entry.entry_id):
        unique_id = reg_entry.unique_id
        if reg_entry.domain not in ("sensor", "button") or unique_id in keep:
            continue
        if f"{entry.entry_id}_loan_" in unique_id or f"{entry.entry_id}_renew_" in unique_id:
            registry.async_remove(reg_entry.entity_id)
