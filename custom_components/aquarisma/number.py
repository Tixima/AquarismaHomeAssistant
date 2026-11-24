"""Writable water values. Setting one records a manual measurement."""

from __future__ import annotations

import secrets

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import AquarismaError
from .entity import AquarismaEntity
from .errors import action_failed
from .platform import async_setup_platform_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    await async_setup_platform_entities(hass, entry, async_add_entities, "number", AquarismaNumber)


class AquarismaNumber(AquarismaEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def _apply_presentation(self, spec: dict) -> None:
        super()._apply_presentation(spec)
        self._attr_native_min_value = float(spec.get("min", 0))
        self._attr_native_max_value = float(spec.get("max", 10000))
        self._attr_native_step = float(spec.get("step", 0.1))
        self._attr_native_unit_of_measurement = spec.get("unit")

    @property
    def native_value(self) -> float | None:
        value = self.spec.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    async def async_set_native_value(self, value: float) -> None:
        parameters = {
            "parameter": self.spec.get("parameter") or self.spec.get("key"),
            "value": value,
        }
        unit = self.spec.get("unit_code") or self.spec.get("unit")
        if unit:
            parameters["unit"] = unit
        try:
            await self.coordinator.client.action(
                "water.measurement.record",
                self.spec["aquarium_id"],
                parameters,
                secrets.token_hex(8),
            )
        except AquarismaError as error:
            raise action_failed(error) from error
        await self.coordinator.async_request_refresh()
