"""Sensors created from the snapshot."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import AquarismaEntity
from .platform import async_setup_platform_entities

PARALLEL_UPDATES = 0

_DEVICE_CLASS = {
    "temperature": SensorDeviceClass.TEMPERATURE,
    "ph": SensorDeviceClass.PH,
    "timestamp": SensorDeviceClass.TIMESTAMP,
    "volume_storage": SensorDeviceClass.VOLUME_STORAGE,
}

_UNITS = {
    "°C": UnitOfTemperature.CELSIUS,
    "°F": UnitOfTemperature.FAHRENHEIT,
    "L": UnitOfVolume.LITERS,
    "mL": UnitOfVolume.MILLILITERS,
    "gal": UnitOfVolume.GALLONS,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    await async_setup_platform_entities(hass, entry, async_add_entities, "sensor", AquarismaSensor)


class AquarismaSensor(AquarismaEntity, SensorEntity):
    @property
    def native_value(self) -> datetime | float | int | str | None:
        value = self.spec.get("value")
        if self.spec.get("device_class") == "timestamp":
            if not isinstance(value, str) or not value:
                return None
            return dt_util.parse_datetime(value)
        return value

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.spec.get("device_class") == "ph":
            return None
        unit = self.spec.get("unit")
        if not isinstance(unit, str):
            return None
        return _UNITS.get(unit, unit)

    @property
    def extra_state_attributes(self) -> dict:
        return self.spec.get("attributes") or {}

    @property
    def device_class(self) -> SensorDeviceClass | None:
        return _DEVICE_CLASS.get(self.spec.get("device_class"))

    @property
    def state_class(self) -> SensorStateClass | None:
        if self.spec.get("state_class") == "measurement":
            return SensorStateClass.MEASUREMENT
        return None

    @property
    def suggested_display_precision(self) -> int | None:
        precision = self.spec.get("precision")
        return precision if isinstance(precision, int) else None
