"""Diagnostics with tokens removed."""

from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN

REDACT = {
    CONF_TOKEN,
    "access_token",
    "refresh_token",
    "client_secret",
    "code",
    "code_verifier",
    "authorization",
    "expires_at",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    runtime = getattr(entry, "runtime_data", None)
    coordinator = None if runtime is None else runtime.coordinator
    snapshot = coordinator.data if coordinator and isinstance(coordinator.data, dict) else None
    token = entry.data.get(CONF_TOKEN) or {}
    aquariums = []
    if isinstance(snapshot, dict):
        for row in snapshot.get("aquariums") or []:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            team = row.get("team") if isinstance(row.get("team"), dict) else {}
            aquariums.append({
                "id": row.get("id"),
                "name": row.get("name"),
                "team": team.get("name"),
                "capabilities": row.get("capabilities") or [],
            })
    return {
        "entry": async_redact_data(dict(entry.data), REDACT),
        "options": dict(entry.options),
        "token_has_expiry": isinstance(token, dict) and isinstance(token.get("expires_at"), (int, float)),
        "last_status": None if coordinator is None else coordinator.last_status,
        "connection_id": None if coordinator is None else coordinator.connection_id,
        "unsupported_schema": None if coordinator is None else coordinator.unsupported_schema,
        "authorized_ids": sorted(runtime.authorized_ids) if runtime is not None else [],
        "snapshot_complete": None if snapshot is None else snapshot.get("complete"),
        "schema_version": None if snapshot is None else snapshot.get("schema_version"),
        "aquarium_count": len(aquariums),
        "aquariums": aquariums,
    }
