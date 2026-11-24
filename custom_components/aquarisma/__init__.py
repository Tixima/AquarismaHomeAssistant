"""Aquarisma integration setup."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .client import AquarismaError
from .const import DOMAIN
from .coordinator import AquarismaCoordinator
from .errors import action_failed, require_idempotency_key
from .lifecycle import async_delete_entry_issues, async_sync_devices, async_sync_issues
from .plan import owning_entry

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CALENDAR,
]


@dataclass
class AquarismaRuntime:
    coordinator: AquarismaCoordinator
    authorized_ids: set[str]


type AquarismaConfigEntry = ConfigEntry[AquarismaRuntime]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AquarismaConfigEntry) -> bool:
    coordinator = AquarismaCoordinator(hass, entry)
    entry.runtime_data = AquarismaRuntime(coordinator, set())
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        if coordinator.unsupported_schema is not None:
            async_sync_issues(hass, entry)
        await coordinator.async_shutdown()
        raise
    async_sync_devices(hass, entry)
    async_sync_issues(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(coordinator.async_add_listener(lambda: _on_update(hass, entry)))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AquarismaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and getattr(entry, "runtime_data", None) is not None:
        await entry.runtime_data.coordinator.async_shutdown()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: AquarismaConfigEntry) -> None:
    async_delete_entry_issues(hass, entry)


def _on_update(hass: HomeAssistant, entry: AquarismaConfigEntry) -> None:
    async_sync_devices(hass, entry)
    async_sync_issues(hass, entry)


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "refresh"):
        return

    async def _refresh(_: ServiceCall) -> None:
        for entry in hass.config_entries.async_entries(DOMAIN):
            runtime = getattr(entry, "runtime_data", None)
            if runtime is not None:
                await runtime.coordinator.async_request_refresh()

    async def _run(call: ServiceCall, action: str, parameters: dict) -> None:
        coordinator = _owner_coordinator(hass, call.data["aquarium_id"])
        if coordinator is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="aquarium_not_managed")
        key = call.data.get("idempotency_key") or secrets.token_hex(8)
        require_idempotency_key(key)
        try:
            await coordinator.client.action(action, call.data["aquarium_id"], parameters, key)
        except AquarismaError as error:
            raise action_failed(error) from error
        await coordinator.async_request_refresh()

    async def _confirm(call: ServiceCall) -> None:
        await _run(call, "feeding.confirm", {
            "plan_id": call.data["plan_id"],
            "slot_id": call.data["slot_id"],
            "date": call.data["date"],
        })

    async def _complete(call: ServiceCall) -> None:
        await _run(call, "care.complete", {"occurrence_id": call.data["occurrence_id"]})

    async def _change(call: ServiceCall) -> None:
        await _run(call, "water_change.record", {"liters": call.data["liters"]})

    async def _measure(call: ServiceCall) -> None:
        await _run(call, "water.measurement.record", {
            "parameter": call.data["parameter"],
            "value": call.data["value"],
            "unit": call.data.get("unit"),
            "measured_at": call.data.get("measured_at"),
            "confirm_unusual": call.data.get("confirm_unusual", False),
        })

    hass.services.async_register(DOMAIN, "refresh", _refresh)
    hass.services.async_register(DOMAIN, "confirm_feeding", _confirm)
    hass.services.async_register(DOMAIN, "complete_care", _complete)
    hass.services.async_register(DOMAIN, "record_water_change", _change)
    hass.services.async_register(DOMAIN, "record_measurement", _measure)


def _owner_coordinator(hass: HomeAssistant, aquarium_id: str) -> AquarismaCoordinator | None:
    candidates: list[tuple[str, str]] = []
    entries = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        if runtime is None or aquarium_id not in runtime.authorized_ids:
            continue
        entries[entry.entry_id] = runtime.coordinator
        candidates.append((str(runtime.coordinator.connection_id or entry.entry_id), entry.entry_id))
    owner = owning_entry(candidates)
    if owner is None:
        return None
    return entries.get(owner)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: AquarismaConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    aquarium_id = next((identifier[1] for identifier in device_entry.identifiers if identifier[0] == DOMAIN), None)
    if aquarium_id is None:
        return True
    runtime = getattr(config_entry, "runtime_data", None)
    if runtime is None:
        return True
    return aquarium_id not in runtime.authorized_ids
