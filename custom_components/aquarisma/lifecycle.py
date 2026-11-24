"""Device registry and repair issues for one connection."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir

from .const import CONF_BASE_URL, DOMAIN, MANUFACTURER
from .entity import water_model
from .errors import placeholder
from .plan import device_ids, device_reconcile, owned_aquarium_ids


def _devices_for_entry(registry: dr.DeviceRegistry, entry_id: str) -> list[dr.DeviceEntry]:
    return [device for device in registry.devices.values() if entry_id in device.config_entries]


def other_claims(hass: HomeAssistant, entry_id: str) -> list[tuple[str, str, set[str]]]:
    """Complete aquarium claims held by the other connections."""

    claims: list[tuple[str, str, set[str]]] = []
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id == entry_id:
            continue
        runtime = getattr(other, "runtime_data", None)
        if runtime is None:
            continue
        claims.append((other.entry_id, str(runtime.coordinator.connection_id or ""), set(runtime.authorized_ids)))
    return claims


@callback
def async_sync_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    snapshot = coordinator.data if isinstance(coordinator.data, dict) else None
    status = coordinator.last_status
    if not isinstance(snapshot, dict) or status != 200 or snapshot.get("schema_version") != 1:
        return
    complete = snapshot.get("complete") is True
    mine = device_ids(snapshot)
    owned = owned_aquarium_ids(
        entry.entry_id,
        str(coordinator.connection_id or ""),
        mine,
        other_claims(hass, entry.entry_id),
    )
    if complete:
        runtime.authorized_ids = set(mine)
    else:
        # An incomplete snapshot may omit an aquarium that still exists.
        # Remember every aquarium it does list, and keep the previous set.
        runtime.authorized_ids = set(runtime.authorized_ids) | set(mine)
    registry = dr.async_get(hass)
    rows = {
        str(row["id"]): row
        for row in snapshot.get("aquariums") or []
        if isinstance(row, dict) and row.get("id")
    }
    base = str(entry.data.get(CONF_BASE_URL, "")).rstrip("/")
    for aquarium_id in owned:
        row = rows.get(aquarium_id)
        if row is None:
            continue
        team = row.get("team") if isinstance(row.get("team"), dict) else {}
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, aquarium_id)},
            name=str(row.get("name") or aquarium_id),
            manufacturer=MANUFACTURER,
            model=water_model(row.get("water_type")),
            sw_version=str(snapshot.get("api_version") or "") or None,
            configuration_url=f"{base}/panel/tanks/{aquarium_id}" if base else None,
            suggested_area=str(team["name"]) if team.get("name") else None,
        )
    if not complete:
        return
    linked = {
        identifier[1]
        for device in _devices_for_entry(registry, entry.entry_id)
        for identifier in device.identifiers
        if identifier[0] == DOMAIN
    }
    _kept, gone = device_reconcile(linked, snapshot, status, True)
    # Dropping our link while we are the only config entry deletes the device.
    # An aquarium another connection now owns stays linked until that
    # connection has attached, so the entity history is not thrown away.
    detach = set(gone)
    for aquarium_id in mine - owned:
        device = registry.async_get_device(identifiers={(DOMAIN, aquarium_id)})
        if device is not None and any(linked_id != entry.entry_id for linked_id in device.config_entries):
            detach.add(aquarium_id)
    if not detach:
        return
    for device in _devices_for_entry(registry, entry.entry_id):
        identifier = next((item[1] for item in device.identifiers if item[0] == DOMAIN), None)
        if identifier in detach:
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


@callback
def async_sync_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    schema_id = f"schema_{entry.entry_id}"
    if coordinator.unsupported_schema is not None:
        ir.async_create_issue(
            hass,
            DOMAIN,
            schema_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="unsupported_schema",
            translation_placeholders={"schema": placeholder(coordinator.unsupported_schema)},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, schema_id)

    snapshot = coordinator.data if isinstance(coordinator.data, dict) else None
    complete = isinstance(snapshot, dict) and coordinator.last_status == 200 and snapshot.get("complete") is True
    if not complete or not isinstance(snapshot, dict):
        return
    empty_id = f"empty_{entry.entry_id}"
    if not device_ids(snapshot):
        ir.async_create_issue(
            hass,
            DOMAIN,
            empty_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="empty_snapshot",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, empty_id)

    mine = device_ids(snapshot)
    owned = owned_aquarium_ids(
        entry.entry_id,
        str(coordinator.connection_id or ""),
        mine,
        other_claims(hass, entry.entry_id),
    )
    names = {
        str(row["id"]): str(row.get("name") or row["id"])
        for row in snapshot.get("aquariums") or []
        if isinstance(row, dict) and row.get("id")
    }
    current: set[str] = set()
    for aquarium_id in sorted(mine - owned):
        issue_id = f"overlap_{entry.entry_id}_{aquarium_id}"
        current.add(issue_id)
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="aquarium_overlap",
            translation_placeholders={"name": placeholder(names.get(aquarium_id, aquarium_id))},
        )
    _delete_overlap_issues(hass, entry.entry_id, keep=current)


def async_delete_entry_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    ir.async_delete_issue(hass, DOMAIN, f"schema_{entry.entry_id}")
    ir.async_delete_issue(hass, DOMAIN, f"empty_{entry.entry_id}")
    _delete_overlap_issues(hass, entry.entry_id, keep=set())


def _delete_overlap_issues(hass: HomeAssistant, entry_id: str, keep: set[str]) -> None:
    prefix = f"overlap_{entry_id}_"
    registry = ir.async_get(hass)
    for issue in list(registry.issues.values()):
        if getattr(issue, "domain", None) == DOMAIN and str(issue.issue_id).startswith(prefix) and issue.issue_id not in keep:
            ir.async_delete_issue(hass, DOMAIN, issue.issue_id)
