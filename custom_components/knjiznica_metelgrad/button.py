"""Gumb za produženje svih produživih posudbi."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import KnjiznicaCoordinator
from .entity import KnjiznicaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Postavi gumb za ovu karticu."""
    coordinator: KnjiznicaCoordinator = entry.runtime_data.coordinator
    async_add_entities([RenewAllButton(coordinator, entry)])


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
        results = await self.coordinator.async_renew()
        failures = [result for result in results if not result.submitted]
        if failures:
            details = "; ".join(f"{result.title} ({result.error})" for result in failures)
            raise HomeAssistantError(f"Produženje nije poslano za: {details}")
