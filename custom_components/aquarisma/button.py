"""Buttons only for an unambiguous planned action."""

from __future__ import annotations

import secrets

from homeassistant.components.button import ButtonEntity
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
    await async_setup_platform_entities(hass, entry, async_add_entities, "button", AquarismaButton)


class AquarismaButton(AquarismaEntity, ButtonEntity):
    async def async_press(self) -> None:
        try:
            await self.coordinator.client.action(
                self.spec["action"],
                self.spec["aquarium_id"],
                self.spec.get("parameters") or {},
                secrets.token_hex(8),
            )
        except AquarismaError as error:
            raise action_failed(error) from error
        await self.coordinator.async_request_refresh()
