"""Binary sensors for due and critical states."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AquarismaEntity
from .platform import async_setup_platform_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    await async_setup_platform_entities(hass, entry, async_add_entities, "binary_sensor", AquarismaBinarySensor)


class AquarismaBinarySensor(AquarismaEntity, BinarySensorEntity):
    @property
    def is_on(self) -> bool:
        return bool(self.spec.get("value"))

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        if self.spec.get("binary_device_class") == "problem":
            return BinarySensorDeviceClass.PROBLEM
        return None
