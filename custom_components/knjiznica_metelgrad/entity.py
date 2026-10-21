"""Zajednička osnova entiteta (uređaj = jedna knjižnična kartica)."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KnjiznicaCoordinator
from .parser import Loan


def loan_key(loan: Loan) -> str:
    """Stabilan ključ posudbe dok je knjiga posuđena.

    Identifikator zapisa (`D…`) ne mijenja se ni kad se rok produži, za razliku
    od oznake primjerka (`MK…`) koja postoji samo dok je produženje ponuđeno.
    Dvije kopije istog naslova odjednom dijele ključ — za dječju knjižnicu je to
    zanemariv slučaj.
    """
    return loan.record_key or loan.title.casefold()


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


class LoanEntity(KnjiznicaEntity):
    """Entitet vezan na jednu posudbu (knjigu)."""

    def __init__(
        self,
        coordinator: KnjiznicaCoordinator,
        entry: ConfigEntry,
        key: str,
        title: str,
        unique_prefix: str,
    ) -> None:
        super().__init__(coordinator, entry, f"{unique_prefix}_{key}")
        self._key = key
        self._attr_name = title

    @property
    def loan(self) -> Loan | None:
        """Trenutno stanje te posudbe, ili None ako knjiga nije više posuđena."""
        return next((loan for loan in self.loans if loan_key(loan) == self._key), None)


@callback
def async_track_loan_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
    make_entity: Callable[[str, Loan], Entity],
) -> None:
    """Održavaj po jedan entitet za svaku posudbu.

    Entitet se doda kad se knjiga pojavi na popisu posudbi, a ukloni — iz sučelja
    i iz registra — kad je knjižnica vrati.
    """
    coordinator: KnjiznicaCoordinator = entry.runtime_data.coordinator
    known: dict[str, Entity] = {}

    @callback
    def _sync() -> None:
        loans = {loan_key(loan): loan for loan in coordinator.data or []}
        registry = entity_registry.async_get(hass)

        for key in [key for key in known if key not in loans]:
            entity = known.pop(key)
            if entity.entity_id is not None:
                # Uklanjanje iz registra platforma pretvara u potpuno uklanjanje;
                # samo async_remove() bi ga ostavilo kao "unavailable".
                registry.async_remove(entity.entity_id)

        added = []
        for key, loan in loans.items():
            if key not in known:
                known[key] = make_entity(key, loan)
                added.append(known[key])
        if added:
            add_entities(added)

    entry.async_on_unload(coordinator.async_add_listener(_sync))
    _sync()
