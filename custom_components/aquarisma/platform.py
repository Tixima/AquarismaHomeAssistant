"""Add and remove entities from a snapshot without deleting them on a bad poll."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AquarismaEntity
from .lifecycle import other_claims
from .plan import device_ids, entity_specs, owned_aquarium_ids, reconcile


async def async_setup_platform_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    domain: str,
    factory: Callable[[object, dict], AquarismaEntity],
) -> None:
    coordinator = entry.runtime_data.coordinator
    known: dict[str, AquarismaEntity] = {}

    @callback
    def _sync() -> None:
        snapshot = coordinator.data if isinstance(coordinator.data, dict) else None
        status = coordinator.last_status
        complete = None if snapshot is None else snapshot.get("complete")
        specs = None
        if isinstance(snapshot, dict) and snapshot.get("schema_version") == 1 and status == 200:
            mine = device_ids(snapshot)
            owned = owned_aquarium_ids(
                entry.entry_id,
                str(coordinator.connection_id or ""),
                mine,
                other_claims(hass, entry.entry_id),
            )
            specs = [
                spec
                for spec in entity_specs(snapshot)
                if spec["domain"] == domain and spec["aquarium_id"] in owned
            ]
        desired, removable = reconcile(set(known), specs, status, complete)
        for unique_id in removable:
            entity = known.pop(unique_id, None)
            if entity is not None and entity.hass is not None:
                entry.async_create_background_task(
                    hass,
                    entity.async_remove(),
                    name=f"aquarisma-remove-{unique_id}",
                )
        by_id = {spec["unique_id"]: spec for spec in specs or []}
        fresh: list[AquarismaEntity] = []
        for unique_id in desired:
            spec = by_id.get(unique_id)
            if unique_id in known:
                if spec is not None:
                    known[unique_id].apply_spec(spec)
                continue
            if spec is None:
                continue
            entity = factory(coordinator, spec)
            known[unique_id] = entity
            fresh.append(entity)
        if fresh:
            async_add_entities(fresh)

    entry.async_on_unload(coordinator.async_add_listener(_sync))
    _sync()
