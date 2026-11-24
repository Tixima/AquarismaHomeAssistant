"""Shared entity base. Names come from translations, not from the snapshot."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, CONF_BASE_URL, DOMAIN, MANUFACTURER
from .coordinator import AquarismaCoordinator

WATER_MODEL = {
    "fresh": "Freshwater",
    "salt": "Saltwater",
    "saltwater": "Saltwater",
    "marine": "Saltwater",
    "brackish": "Brackish",
}


class AquarismaEntity(CoordinatorEntity[AquarismaCoordinator]):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: AquarismaCoordinator, spec: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self.spec = spec
        self._attr_unique_id = spec["unique_id"]
        self._apply_presentation(spec)

    def apply_spec(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self._apply_presentation(spec)
        if self.hass is not None:
            self.async_write_ha_state()

    def _apply_presentation(self, spec: dict[str, Any]) -> None:
        self._attr_translation_key = spec.get("translation_key")
        self._attr_translation_placeholders = spec.get("translation_placeholders") or {}
        self._attr_entity_registry_enabled_default = spec.get("enabled_default", True)
        self._attr_entity_category = EntityCategory.DIAGNOSTIC if spec.get("category") == "diagnostic" else None

    def _aquarium(self) -> dict[str, Any] | None:
        data = self.coordinator.data if isinstance(self.coordinator.data, dict) else {}
        for row in data.get("aquariums") or []:
            if isinstance(row, dict) and row.get("id") == self.spec["aquarium_id"]:
                return row
        return None

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success:
            return False
        data = self.coordinator.data if isinstance(self.coordinator.data, dict) else {}
        if data.get("complete") is False:
            return True
        return self._aquarium() is not None

    @property
    def device_info(self) -> DeviceInfo:
        aquarium = self._aquarium() or {}
        team = aquarium.get("team") if isinstance(aquarium.get("team"), dict) else {}
        base = str(self.coordinator.entry.data.get(CONF_BASE_URL, "")).rstrip("/")
        aquarium_id = str(self.spec["aquarium_id"])
        info: dict[str, Any] = {
            "identifiers": {(DOMAIN, aquarium_id)},
            "name": aquarium.get("name") or aquarium_id,
            "manufacturer": MANUFACTURER,
            "model": water_model(aquarium.get("water_type")),
        }
        if base:
            info["configuration_url"] = f"{base}/panel/tanks/{aquarium_id}"
        if team.get("name"):
            info["suggested_area"] = str(team["name"])
        data = self.coordinator.data if isinstance(self.coordinator.data, dict) else {}
        if data.get("api_version"):
            info["sw_version"] = str(data["api_version"])
        return DeviceInfo(**info)


def water_model(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return WATER_MODEL.get(value, value)
